#!/usr/bin/env python2.5

import sys
from subprocess import Popen,PIPE
import logging
import traceback

log = logging.getLogger('alice.time_manager')

class UncertainTimeError(Exception):
  pass

class TimeManager:

  def __init__(self):
    log.info("Looking for ntpd...")
    try:
      ntpdc = Popen("ntpdc", stdin=PIPE, stdout=PIPE)
    except OSError:
      log.error("Couldn't run ntpdc:\n" + traceback.format_exc())
      raise UncertainTimeError
      
    ntpdc.stdin.write("sysinfo\n")
    ntpdc.stdin.close()
    self.lines = ntpdc.stdout.readlines()
    if not self.lines or "onnection refused" in self.lines[0]:
      log.error('ntpdc is present but ntpd does not appear to be alive: ("%s")' % self.lines)
      raise UncertainTimeError
      
    self.ntp_sysinfo = {}
    for line in self.lines:
      pos = line.find(":")
      key = line[:pos].lower()
      val = line[pos+1:].strip()
      self.ntp_sysinfo[key]=val

    mode = self.ntp_sysinfo["system peer mode"]
    if mode == "unspec":
      log.error("""
      NTP is in "unspec" mode.  This is probably because your system clock
      is quite wrong.  Switzerland won't work if your clock is really out
      of whack.  It could also mean that you're offline or that you need to
      give NTP another minute or two to find time servers.""")
      raise UncertainTimeError
    elif mode != "client":
      log.info("Note that NTP is in mode %s", mode)

  def root_dispersion(self):
    try:
      root_dispersion = float(self.ntp_sysinfo["root dispersion"].split()[0])
    except KeyError:
      log.error("ntpdc's sysinfo does not appear to be reporting root dispersion:")
      log.error("\n".join(self.lines))
      raise UncertainTimeError

    return root_dispersion

if __name__ == "__main__":
  x = TimeManager()
  print x.root_dispersion()
    
# vim: et ts=2
