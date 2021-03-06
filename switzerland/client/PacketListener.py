#!/usr/bin/env python

import threading
import tempfile
import os
import sys
import platform
from binascii import hexlify
import struct
import logging
import mmap
import time
import select
import signal
import traceback
from subprocess import Popen, PIPE

if platform.system() == 'Windows':
    import msvcrt
    from win32pipe import PeekNamedPipe

# hack: import util first to make sure we can import win32api
from switzerland.common import util
if platform.system() == 'Windows':
    import win32api
else:
    import posix

from switzerland.client import Packet

try:
    from switzerland.lib.shrunk_scapy.layers.l2 import Ether
    have_scapy = True
except Exception, e:
    print "No scapy... that's okay, we don't really need it"
    have_scapy = False

double_check = False
if double_check:
  pcount = 0

lag_check_frequency = 10000

poll_interval = 0.005
log = logging.getLogger('alice.packet_listener')
dummy = False

packet_size = 1600 
# an unsigned int for the packet size, and a double for the timestamp
valid_size = 2 # the field is actually 1 byte, but stay word aligned
packlen_size = struct.calcsize("H")
padding2_size = 4
ts_size = struct.calcsize("d")

# now some syntactic sugar... 
# but XXX this could be cleaned up a great deal!
pls = packlen_size   # size of packet length field
assert pls == struct.calcsize("H")
tss = ts_size        # size of timestamp field
assert tss == struct.calcsize("d")
vs = valid_size
#assert vs == struct.calcsize("c")  let's use 2 to stay word aligned

class SnifferError(Exception):
  pass

class PacketListener(threading.Thread):
    """ sniff incoming IP datagrams on a network interface or from a save file.
        pass packets off to FlowManager. """

    def __init__(self, parent):
        """self.parent.fm: FlowManager to receive packets"""
        threading.Thread.__init__(self)
        self.parent = parent
        self.packets_in_buf = parent.config.packet_buffer_size
        self.entry_size = packet_size + packlen_size + ts_size + valid_size + \
                          padding2_size
        self.buffer_size = self.packets_in_buf * self.entry_size
        self._zcat_pipe = None
        self._zcat = None
        self.tmpfile = None
        self.lock = threading.RLock()
        self.latest = 0
        self.max_timewarp = 0
        self._skew = parent.config.skew
        self.kernel_tweaked = False
        self.frag_warn = False # have we warned about fragmented packets?
        self.done = threading.Event() # are we done replaying an 
                                      # offline capture?
        self.half_done = False  # True when FastCollector has finished
                                # healthily but we haven't read all the
                                # packets from the buffer yet
        
        if platform.system() == 'Windows':
          self.sniffer_thread = os.path.sep.join(['FastCollector.exe'])
          self.sniffer_thread2 = os.path.sep.join(['bin','FastCollector.exe'])
        else:
          self.sniffer_thread = os.path.sep.join(['FastCollector'])
          self.sniffer_thread2 = os.path.sep.join(['bin','FastCollector'])
        if parent.config.pcap_playback:
          self.live = False
          self.target = self.filename_magic(parent.config.pcap_playback)
        else:
          assert parent.config.interface, "Can't create PacketListner with neither a pcap file nor an interface"
          self.live = True
          self.target = parent.config.interface

    def minimize_packet_loss(self):
        """
        Platform-specific code to maximise buffer/queue space in the kernel
        captured packets, to minimize the risk that the kernel drops packets
        before they get to the sniffer.
        """
        p = platform.system()
        # Implementing the recommendations from
        # http://www.net.t-labs.tu-berlin.de/research/hppc/
        if p[-3:] == "BSD" or p == "Darwin":
          cmd = ["sysctl","-w","net.bpf.bufsize=10485760"]
          try:     # Recent FreeBSDs
            proc = Popen(cmd, stdin=PIPE, stdout=PIPE)
            assert proc.wait() == 0
            cmd[2] = "net.bpf.maxbufsize=10485760"
            proc = Popen(cmd, stdin=PIPE, stdout=PIPE)
            assert proc.wait() == 0
          except:  # Older FreeBSDs
            cmd[2] = "debug.bpf_bufsize=10485760"
            proc = Popen(cmd, stdin=PIPE, stdout=PIPE)
            assert proc.wait() == 0
            cmd[2] = "debug.maxbpf_bufsize=10485760"
            proc = Popen(cmd, stdin=PIPE, stdout=PIPE)
            assert proc.wait() == 0

        elif p == "Linux":
          vars = [("/proc/sys/net/core/rmem_default", "33554432"),
                  ("/proc/sys/net/core/rmem_max", "33554432"),
                  ("/proc/sys/net/core/netdev_max_backlog", "10000")]
          self.old_kernel_state = []
          for file, value in vars:
            # save kernel state before overwriting it
            f = open(file, 'r')
            self.old_kernel_state.append((file, f.read()))
            f.close()
            f = open(file, 'w')
            f.write(value)
            f.close()
          self.kernel_tweaked = True

        # on Windows, we should call pcap_setbuff from inside FastCollector.

    def restore_kernel_state(self):
        p = platform.system()
        if p == "Linux":
            for file, value in self.old_kernel_state:
                # save kernel state before overwriting it
                f = open(file, 'w')
                f.write(value)
                f.close()
            self.kernel_tweaked = False

    def launch_collector(self):
        """
        Launch the PacketCollector, which lives in another process.
        For live captures this approach is necessary to avoid packet loss;
        for offline playback it is helpful for testing.
        Because of the weirdness of pypcap, target can be *either* an
        interface name or a pcap filename! :/
        """
        
        try:
          if self.live: self.minimize_packet_loss()
        except:
          log.info(traceback.format_exc())
          print "Failed to set kernel buffers to minimize packet loss!!!"
          print "You may encounter problems as a result of this..."

        try:
          if platform.system() == 'Windows':
            use_shell = True
          else:
            use_shell = False
          try: 
            mode = '-i' # interactive
            if not self.live:
              mode = '-f'
            sz = "-b%ld" % self.packets_in_buf
            log.debug("Launching packet collector: "+ `[self.sniffer_thread, mode, self.target]`)
            try:
              self.sniff = Popen(
                [self.sniffer_thread, mode, sz, self.target], shell=use_shell,
                stdout=PIPE, stdin=PIPE, stderr=PIPE
              )         
            except:
              # try bin/FastCollector
              self.sniff = Popen(
                [self.sniffer_thread2, mode, sz, self.target], shell=use_shell,
                stdout=PIPE, stdin=PIPE, stderr=PIPE
              )         
          except:
            log.error("failed to start %s", self.sniffer_thread)
            raise

          if self.live: self.prioritise_sniffer()

        except OSError:
          value = sys.exc_info()[1]
          if "No such file or directory" in value:
            print self.sniffer_thread, "does not appear to be in the PATH..."
            #print "(which is", os.environ["PATH"] + ")"
          else:
            raise
          self.parent.quit_event.set()
          print "exiting"
          print threading.enumerate()
          sys.exit(1)

        self.tmpfile = self.get_tempfile_name()
        log.debug("Opening tempfile %s" % self.tmpfile)
        self.file = open(self.tmpfile, "a+b")
        fd = self.file.fileno()
        self.mem = mmap.mmap(fd, self.buffer_size, access=mmap.ACCESS_WRITE)

        self.parent.config.pcap_datalink = self.get_pcap_datalink()
        log.debug("Got pcap_datalink: %s" % `self.parent.config.pcap_datalink`)

    def prioritise_sniffer(self):
        """
        OS-dependent code to ensure the sniffer runs with the highest
        available priority level.
        """
        if platform.system() == 'Windows':
          util.set_win32_priority(self.sniff.pid, 5)
        else:  # UNIX is nice
          try:
            n = Popen(["renice", "-19", `self.sniff.pid`], stdout=PIPE)
            log.debug(n.stdout.read())
          except OSError:
            log.error("Attempt to prioritise sniffer failed with" + `sys.exc_info[0:2]`)

    def get_tempfile_name(self):
      """
      Communicate with the sniffer process to obtain the name of the
      mmap()ed tempfile through which it will pass us packets.
      """
      log.debug("looking for temp file..")
      self.sniff.stdin.close()
      line = self.sniff.stdout.readline()
      while line == "":
        line = self.sniff.stdout.readline()
        rval = self.sniff.poll()
        if rval != None:              # The sniffer died
          msg = "packet collector exited with return code %d\n" % rval
          msg += self.sniff.stderr.read()
          raise SnifferError, msg

      words = line.split()
      if len(words) == 0 or words[0] != "Tempfile:":
        raise SnifferError("packet collector didn't print a Tempfile: line")
      return words[1]

    def get_pcap_datalink(self):
        """
        Communicate with sniffer process to obtain the output of
        pcap_datalink on the capture (this will later determine header
        length of link layer portion of the packet).
        """
        line = self.sniff.stdout.readline() # XXX This is for "Initialized..." line
        line = self.sniff.stdout.readline()
        while line == "":
            line = self.sniff.stdout.readline()
            rval = self.sniff.poll()
            if rval != None:              # The sniffer died
                msg = "packet collector exited with return code %d\n" % (rval)
                msg += self.sniff.stderr.read()
                raise SnifferError, msg
        words = line.split()
        if len(words) == 0 or words[0] != "pcap_datalink:":
            raise SnifferError,"packet collector didn't print a pcap_datalink: line"
        return int(words[1])


    def run(self):
        """ sit in a tight loop and collect packets
            in interactive mode, run until the parent thread exits.
            in offline mode, break when the dump file ends """

        # This only returns on an error condition...
        try:
          self.launch_collector()
          self.read_packets()

          # The obvious thing to do with exceptions here would be to set the
          # quit event and then "raise".  But if there's a context switch in
          # between those two lines, we might never see the exception.  So
          # print it before sending quit_event.
        except SnifferError,e:    # sniffer error; clean up on the way out
          self.cleanup()
          log.error(e)
          if "handle a packet of size" in repr(e):
            self.large_segment_message()
          self.parent.quit_event.set()
          sys.exit(1)
        except:                   # What kind of error is this?
          self.cleanup()
          log.error(traceback.format_exc())
          self.parent.quit_event.set()
          sys.exit(1)

        # notify parent thread that there's no more input
        self.done.set()
        self.cleanup()
        # close pipe from zcat for gzipped traces
        if self._zcat != None:
            self._zcat.wait()
            if self._zcat_pipe:
                os.unlink(self._zcat_pipe)
        # organise shutdown for the entire client process
        log.info("Goodbye...")
        self.parent.quit_event.set()


    def filename_magic(self, filename):
        """
        Do all our housekeeping for playbacks of stored pcaps.  Sometimes
        these are gzipped, so we try to use named pipes to decompress them
        for the pcap library code.  Returns a filename for a pcap library.
        """
        # pcapy can't deal with gzipped input
        if filename.endswith('.gz'):
            trim_gz = filename[:-3]

            # if there's an ungzipped copy in the same place, use it
            if os.path.exists(trim_gz):
                filename = trim_gz

            # XXX this isn't going to work on windows
            elif platform.system() == 'Windows':
                print "sorry, I don't know how to open gzipped traces on windows"
                print "please gunzip %s and try again\n" % (filename)
                raise NotImplementedError

            # use a named pipe if we got em
            else:
                tmp = tempfile.mktemp()
                posix.mkfifo(tmp)

                self._zcat = Popen('zcat "%s" > "%s"' % (filename, tmp), shell=True)
                self._zcat_pipe = tmp
                filename = tmp
            
        return filename

    def read_packets(self):
      """
      Read packets out of the mmap()ed buffer that PacketCollector.py
      is busy writing them into.
      """

      self.pos = 0
      count = 0

      if platform.system() == 'Windows':
        self.check_for_sniffer_error = self.check_for_sniffer_error_win32
        self.sniff.fd_stderr = self.sniff.stderr.fileno()
        self.sniff.os_stderr = msvcrt.get_osfhandle(self.sniff.fd_stderr)
      else:
        self.check_for_sniffer_error = self.check_for_sniffer_error_posix

      while True:
        packet = self.read_one_packet()
        if packet == None:
          return
        else:
          timestamp, data = packet
          
        count +=1
        if count % lag_check_frequency == 0:
          delta = time.time() - timestamp
          log.info("Capturing a packet currently takes us %lf seconds" % delta)
        self.process_packet(timestamp, data)
        if double_check:
          print "Pos is now 0x%x" % self.pos
          print Ether(data).summary()

        #if count % 10 == 0:
        #  # at this point we aren't interested in normal playback termination
        #  # from the sniffer (ie, half_done==True).  We just need to know
        #  # about urgent conditions like dropped packets in live deployment
        #  self.check_for_sniffer_error()

    def read_one_packet(self):
      "Read a single packet out of the mmaped buffer; return (timestamp, data)."
      self.lock.acquire()
      try:
        if not self.tmpfile: return
        valid = self.mem[self.pos]
        while valid == '\x00':
          if self.check_for_sniffer_error(): return     # playback complete
          time.sleep(poll_interval)
          valid = self.mem[self.pos]
          if double_check: sys.stdout.write(".")

        base_pos = self.pos
        self.pos += vs

        len = struct.unpack("H", self.mem[self.pos:self.pos+pls])[0]
        if double_check: print "Packet of length", len
        if len > 1514:
          print "Wild packet length %d at pos 0x%x" % (len, self.pos)
          self.parent.quit_event.set()
          sys.exit(1)
        self.pos +=pls + padding2_size

        timestamp = struct.unpack("d", self.mem[self.pos:self.pos+tss])[0]
        if timestamp > self.latest:
          self.latest = timestamp
        else:
          t = self.latest - timestamp

          # Tell the user and the server every time we see packets
          # more out-of-order than anything we've seen yet
          if t > self.max_timewarp:
            msg = "Timestamp monotonicity violated by up to %g seconds" % t
            self.max_timewarp = t
            if t > 0.0002:  # 200 microseconds
              log.error(msg)
              # XXX if this gets up into the millisecond range we should
              # probably switch to a hard error.
              self.parent.link.send_message("error-cont", [msg])
            else:
              log.debug(msg)


        if double_check: print "Timestamp", timestamp
        self.pos += tss

        data = self.mem[self.pos:self.pos+len]
        # mark this packet as read
        self.mem[base_pos] = "\x00"
        self.pos = (self.pos + packet_size) % self.buffer_size
        return (timestamp, data)
      finally:
        self.lock.release()

    def process_packet(self, timestamp, data):
      "Integrate this packet appropriately into Alice's data structures."
      try:
        packet = Packet.Packet(
          timestamp + self._skew,
          data, 
          self.parent
        )
      except:
        msg = "Packet parser failed on this packet (raw hex):\n"
        msg += hexlify(data) + "\n"
        if have_scapy:
          msg += "Scapy analysis\n" + `Ether(data).summary()` + "\n"
        msg += "The error was:\n" + traceback.format_exc()
        log.warn(msg)
        self.parent.link.send_message("error-cont", [msg])
        # HELP I'M STUCK IN AN EXCEPTION HANDLER!
        return
        
      if dummy:
        return
      if packet.is_fragment(): # skip fragmented packets
          if not self.frag_warn:
              log.warn("We saw fragments! This may result in false drop reports.")
              self.frag_warn = True
          return
      self.parent.fm.batch_to_process.acquire()
      # notify reporter thread if this packet completes a batch
      if self.parent.fm.handle_packet(packet):
          self.parent.fm.batch_to_process.notify()
      self.parent.fm.batch_to_process.release()

    def check_for_sniffer_error_win32(self):
      """
      Windows doesn't have "select" for pipes, so we have to resort to dirty tricks
      adapted from http://mail.python.org/pipermail/python-list/2006-August/396531.html
      """
      if self.half_done:
        return True
      try:
        data, avail, _ = PeekNamedPipe(self.sniff.os_stderr, 0)
      except: # pipe closed, we must be done
        return self.report_sniffer_error()
      if avail != 0:
        return self.report_sniffer_error()
      return False

    def check_for_sniffer_error_posix(self):
      """
      Return False for no condition; -1 for an error and +1 for a healthy
      shutdown
      """
      if self.half_done:
        return True
      # XXX perhaps we should use some combination of os.open() flags
      # and read() here instead of select...
      s = select.select([self.sniff.stderr], [], [], 0)
      if s[0]:
        self.report_sniffer_error()
        return True
      return False

    def report_sniffer_error(self):
      """
      go ahead and read from the sniffer's stderr, there's something there
      """
      print "We have news from PacketCollector:"
      ret = self.sniff.wait()
      output= self.sniff.stderr.read()
      if output:
        msg = "Packet sniffer error\n" + output
        try:
          self.parent.link.send_message("error-bye", [msg])
        except:
          pass
        raise SnifferError, output
      else:
        print "(Normal termination)..."
        print self.sniff.stdout.read()
        self.half_done = True
        return True

    def cleanup(self):
      # Alice may call this code too, so avoid deadlocks
      self.lock.acquire()
      try:
        if self.kernel_tweaked:
          self.restore_kernel_state()
      except:
        log.error(traceback.format_exc())
      try:
        if not self.tmpfile:
          return
        self.mem.close()
        self.file.close()
        try:            # to kill FastCollector
          if platform.system() == "Windows":
            # According to http://code.activestate.com/recipes/347462/, 
            # this is how we killa process on Windows
            win32api.TerminateProcess(int(self.sniff._handle), -1)
          else:
            os.kill(self.sniff.pid, signal.SIGTERM)
        except:
          pass          # it's probably already dead
        time.sleep(0.3) # give the FastCollector time to exit
        if self.packets_in_buf > 25000:   # the old/default value
          log.info("Closing packet capture thread...")
          # this takes longer with large buffers!
          time.sleep (0.5 * self.packets_in_buf / 25000.0)
        try:
          cmd = ["shred", "-n", "1", self.tmpfile]
          shred = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
          assert shred.wait() == 0
        except:
          # XXX some platforms won't have shred.  Ideally we should use their
          # native RNGs here... also, is this a good mode for open()?
          if not self.tmpfile:
            log.error("tmpfile already gone")
            return
          f = open(self.tmpfile, 'w')
          blank_entry = "\x00" * self.entry_size
          for n in xrange(self.packets_in_buf):
            f.write(blank_entry)
          f.close()
        try:
          os.unlink(self.tmpfile)
        except OSError, e:
          if "No such file or directory" in e:
            pass
          else:
            raise
      finally:
        self.lock.release()
        self.tmpfile = None
          

    segment_message = \
"""This error is usually a results of having a feature called "TCP Segmentation
Offloading" or "Large Segment Offloading" enabled in your operating
system.  See http://en.wikipedia.org/wiki/Large_segment_offload for more info.
Try running Switzerland with Segmentation Offloading disabled.
"""

    def large_segment_message(self):
      "Tell the user about large segement offloading and how to disable it"
      msg = self.segment_message
      plat = platform.system()
      if plat == "Linux":
        msg += "On linux, you can disable it with the following command:\n"
        msg += "ethtool -K %s tso off" % self.parent.config.interface
      elif plat == "Darwin" or plat[-3:] == "BSD":
        msg += "On %s, you can disable it with the following command:\n" % plat
        msg += "ifconfig %s -tso" % self.parent.config.interface
      elif plat == "Windows":
        msg += "On Windows, you should be able to disable it using the advanced "
        msg += "settings for your network driver." 
      else:
        msg += "Sorry, we can't yet tell you how to disable it on %s" % plat
      log.warn(msg)

if __name__ == "__main__":
  import AliceConfig
  logging.basicConfig()
  from switzerland.common.Dummies import DummyAlice
  
  if "-v" in sys.argv:
    double_check = True
  dummy = True
  listener = PacketListener(DummyAlice())
  listener.run()

