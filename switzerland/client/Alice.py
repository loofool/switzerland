#!/usr/bin/env python
import sys
import time
import os
import platform
import traceback
import threading
import socket as s
import logging

from switzerland.client import PacketListener
from switzerland.client import Cleaner
from switzerland.client import Reporter
from switzerland.client.AliceLink import AliceLink
from switzerland.client.FlowManager import FlowManager
from switzerland.client.AliceConfig import AliceConfig
from switzerland.client.TimeManager import TimeManager, UncertainTimeError
from switzerland.client.Tracerouter import Tracerouter
from switzerland.common.PcapLogger import PcapLogger

#logging.basicConfig(level=logging.DEBUG,
#                    format="[%(name)s]: %(message)s")

log = logging.getLogger('')
log.setLevel(logging.DEBUG)
startup_handler = logging.StreamHandler()
log.addHandler(startup_handler)

welcome_msg = \
"""--------------------------------------------------------------------------------
Welcome to Switzerland.  
READ THE PRIVACY AND SECURITY SECTIONS OF THE README.txt!!

Once you've done that... this is a Version Zero alpha release.  It's sure to
break at some point.  If/when that happens, please let us know by email 
(switzerland-devel@eff.org), IRC (#switzerland on irc.oftc.net) or bug report
( https://sourceforge.net/tracker/?func=browse&group_id=233013&atid=1088569 )
--------------------------------------------------------------------------------"""

class Alice:
    """
    Alice is the Switzerland client.
    config is an AliceConfig object saying how she should operate;
    linkobj is only changed in test cases
    """
    def __init__(self, config, linkobj=AliceLink):

        self.config = config

        #logging.basicConfig(level=config.log_level,
        #                    format="[%(name)s]: %(message)s")
        config.check()

        self.init_logging()
         
        self.params = {}
        if config.use_ntp:
            self.ntp_setup()

        # local address may be fake for testing
        self.fm = FlowManager(config, parent=self)
        self.quit_event = threading.Event()
        self.cleaner = Cleaner.Cleaner(self)
        
        self.listener = PacketListener.PacketListener(self)
        self.link = linkobj(self.quit_event, self, config)
        self.reporter = Reporter.Reporter(self)
        self.tr = Tracerouter()
    
        self.cleaner.setDaemon(True)
        self.listener.setDaemon(True)
        self.reporter.setDaemon(True)
        self.link.setDaemon(True)
        self.tr.setDaemon(True)

        # XXX we need a privacy setting to disable this, since it might in some
        # cases create link between separate client sessions at separate IPs.
        # But this is about the minimum amount of information we need to spot
        # weird platform specific crashes in early releases
        version = (platform.system(), platform.release(), \
                    platform.machine(), sys.version_info)
        self.params["version"] = version
        
        log.debug("Starting AliceLink...")
        self.link.start()
        self.tr.start() # do something while we wait
        self.link.ready.wait(20.0)
        if self.link.quit_event.isSet():
          # error during handshake
          self.listener.cleanup()
          sys.exit(0)
        if not self.link.ready.isSet():
            log.error("failed to start link with switzerland")
            sys.exit(1)
        
        if config.use_ntp:
            self.link.send_message("parameters", [self.params])

    def init_logging(self):
        "Setup all logging for the client"
        global log

        rootlogger = logging.getLogger()
        if not self.config.quiet:
            output = logging.StreamHandler(sys.stdout)
            rootlogger.addHandler(output)

        # now remove the temporary stderr output we were using during startup
        log.removeHandler(startup_handler)
        log = rootlogger

        if self.config.logfile not in ("-", None)  :
            fileout = logging.FileHandler(self.config.logfile)
            rootlogger.addHandler(fileout)
            log.error("Logging events to " + self.config.logfile)

        if self.config.pcap_logdir not in ("-", None):
            self.pcap_logger = PcapLogger(self.config.pcap_logdir)
        else:
            self.pcap_logger = None


    def start(self):
        "Launch various sub-threads."
        #self.listener.start()
        self.reporter.start()
        if self.config.do_cleaning:
            self.cleaner.start()
        try:
            import psyco
            psyco.profile()
        except ImportError:
            log.info("The psyco package is unavailable (that's okay, but the client is more\nefficient if psyco is installed).")

    def ntp_setup(self):
        try:
            self.time_manager = TimeManager()
            self.root_dispersion = self.time_manager.get_time_error()
            log.info("We believe this system's clock is accurate to within %f seconds" % self.root_dispersion)
            if self.root_dispersion > 5.0:
              log.error("Sorry, your clock is out by more than 5 secs. Switzerland isn't going to work!")
              sys.exit(1)
        except UncertainTimeError:
            if not self.config.allow_uncertain_time:
                print "  Please fix NTP!!\n"
                print "  (If that is not possible, you can specify an error bound on your system clock"
                print "  using the -u flag, but you must ensure that it is correct. Failure to do so"
                print "  may result in false reports of packet modification.)"
                print "  see http://switzerland.wiki.sourceforge.net/NTP for further details."
                sys.exit(1)
            else:
                #log.warn("NTP is not working:\n"+traceback.format_exc())
                log.warn("but allow_uncertain_time is set so we're defaulting the clock error to %f" % self.config.manual_clock_error)
                self.root_dispersion = self.config.manual_clock_error
                self.time_manager.method = "blind faith"
        self.params["clock dispersion"] = self.root_dispersion

    def shutdown(self):
        logging.shutdown()
        self.link.send_message("signoff")

def main():
    me = None
    try:
        print welcome_msg
        try:
            if platform.system() != "Windows":
                os.setuid(0)
        except OSError:
            log.error("Unfortunately, you need root privileges to run the Switzerland client :(")
            log.error("(for better or worse, packet sniffing is a privileged operation)")
            sys.exit(1)
        me = Alice(config=AliceConfig(getopt=True))
        me.listener.start()
        me.start()
        # This wasn't helping:
        while not me.quit_event.isSet():
            me.quit_event.wait(5)
        # if the quit came from anywhere other than PacketListener,
        # we'll need to call its cleanup function to shred and delete the
        # packet capture tempfile
        me.listener.cleanup()
    except s.error,e:
        log.error("socket error: %s", `e`)
        if me != None:
            me.listener.cleanup()
            me.shutdown()
        raise
    except KeyboardInterrupt:
        log.info("Exiting at your request...")
        if me != None:
            me.listener.cleanup()
            me.shutdown()
        sys.exit(0)
    log.info("shutting down...")
    time.sleep(0.5) # prevents a crash in the logging library?
    sys.exit(0)

if __name__ == "__main__":
    main()
# vim: et ts=4
