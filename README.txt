Switzerland v0.0

e-mail Switzerland-devel@eff.org
       https://falcon.eff.org/mailman/listinfo/Switzerland-devel

IRC    #Switzerland on irc.oftc.org

bugs   https://sourceforge.net/tracker/?func=browse&group_id=233013&atid=1088569

Contents:

1. Overview

1.1. What is Switzerland?
1.1.1 How do I run Switzerland?
1.1.2 NTP usage
1.1.3 How do I understand the output of Switzerland?
1.2. Stability of this release
1.3. Security
1.3.1. Privileged client
1.4. Platforms supported
1.5. Privacy concerns

2. Testing Notes

2.1. NAT (Network Address Translation) firewalls
2.2. Other firewalls
2.3. Test server

3. Contributing

3.1. Ways to help
3.2. svn repository
3.3. Tree organization


1. Overview

1.1. What is Switzerland?

Switzerland is client/server software to detect when ISPs, networks or
firewalls interfere with Internet traffic.  Switzerland clients summarize
incoming and outgoing packets to a trusted server, which verifies that pairs
of clients receive what each other sent.  If a third party injects, alters
or drops packets en route between clients, the Switzerland server alerts the
clients and records data about the event for further analysis.

                     +-----------+
    +----------+     | Internet  |     +----------+
    | Alice    | --> | networks/ | --> | Bob      |
    | (client) | <-- | ISPs/     | <-- | (client) |
    +----------+     | firewalls |     +----------+
       |    ^        +-----------+        ^     |
       v    |                             |     v
    +---------------------------------------------+
    |  |    |_____________________________|     | |
    |  |                   |                    | |
    |  +---------------->  =  <-----------------+ |
    |      summary A               summary B      |
    |                                             |
    |           Switzerland (server)              |
    +---------------------------------------------+

1.1.1. How do I run Switzerland?

Before you run Switzerland, be sure to read the sections on security, privacy
and firewalls below.

Once you've read those sections and installed Switzerland (see the INSTALL file
for instructions -- on some computers installation will be very easy, on
others, it may require some hacking), you can run Switzerland like this:

switzerland-client

By default, the client will use EFF's Switzerland server, switzerland.eff.org.
If you run your own Switzerland server, you can specify that instead using the
-s flag.

1.1.2 NTP usage

When running Switzerland, you may see some errors/warnings about NTP.  NTP, 
or Network Time Protocol, is a way of making sure your computer's clock is
accurate.  Switzerland works best with an accurate clock, but even if your 
clock is not accurate, Switzerland must know how far off your clock is from
the "correct" time.

Under ideal conditions, you will have the ntp daemon installed and running, and
it will have set your clock to the correct time.  Switzerland will try to use a
program called 'ntpdc' to query your ntp daemon to ask it about the clock
accuracy.  If ntpdc is not installed on your system, or it can't connect to the
ntp daemon (usually because it's not running), then Switzerland will tell you
about it. Switzerland will then try to use the program 'ntpdate' (if installed)
to figure out the accuracy of your clock.  If ntpdate fails (usually because
you don't have it installed) then Switzerland will really complain and then
quit.

If you are receiving warnings/errors about NTP, here are some steps you can
take:

 1) Make sure ntp is installed and configured properly for your system.  On
    Linux/UNIX systems, installing and configuring ntp is often as easy as 
    installing the 'ntp' package using your distributions package manager.  If
    you are on windows, you can download and install the ntp package from here:
      http://www.meinberg.de/english/sw/ntp.htm
      (Note: The standard Windows NTP client that comes with many Windows 
       systems is NOT sufficient for Switzerland)
 2) If you've just recently installed ntp and Switzerland is still complaining
    about ntp being in 'UNSPEC' mode:
    a) Check your clock.  ntp will refuse to work if your clock is more than a
       few seconds off (while this may seem silly, there are some good reasons
       for this behavior). Try setting your clock manually, or possibly by 
       using the 'ntpdate' command by running 'ntpdate pool.ntp.org'
	b) If your clock is accurate, it may be that ntp hasn't been running long
       enough to establish that it has correctly synced your clock.  Try 
       waiting a bit longer.  On some systems it may take upwards of 10 or 20
       minutes.        

 3) If, for whatever reason, you can't get ntp installed, then try installing
    the ntpdate program, which Switzerland will try to use if it can't use ntp.

 4) If there is no way to install ntp or ntpdate, then you can use the -u 
    option to switzerland-client to tell it the maximum number of seconds your
    clock will be off by.


1.1.3 How do I understand the output of Switzerland?

First, see the following wiki page for an example of what Switzerland should
print to the screen if it's working correctly:
http://switzerland.wiki.sourceforge.net/output+example

Switzerland will output 'Now testing flow' messages when you are exchanging
data with another peer running Switzerland.  About 20 seconds after you see
a 'Now testing flow' message, you should see a flow table.  The columns in the
flow table are as follows:
  Okay      : Unmodified packet count
  Drop      : Dropped packet count
  Mod/frg   : Modified or fragmented packet count
  Pend_t/rt : Number of packets the server is still processing
  Prot      : The flow protocol (tcp/icmp/etc.)

Some dropped packets are not unusual, but a high dropped packet count may be 
indicative of traffic shaping.

1.2. Stability of this release

This is an alpha release; Switzerland is not stable software.  It's been gently
tested but is still heavily under development.  Many planned features have not
been implemented.  We need your help!

1.3. Security

This release of Switzerland may contain bugs or security vulnerabilities that
allow an attacker to compromise your computer's security.  We recommend you do
not run it in a production setting, on computers that store sensitive data or
data that has not been backed up, or on computers exchanging sensitive data
over unencrypted connections.

1.3.1. Privileged client

Because the Switzerland client passively observes all traffic on your
computer's network interface, it needs administrative (root) privileges, much
like the tcpdump program.

1.4. Platforms supported

We've tested the client and server on:
- Linux (x86/debian)
- FreeBSD
- OpenBSD
- Darwin (Tiger, with an upgrade to python2.5)
- Windows XP (it runs, but as with many UNIX programs on win32, installation
              is harder)

Please help us add support for your platform of choice.

1.5. Privacy concerns

In this release, a Switzerland server publishes the IP addresses of all
connected clients.

Your client is designed to only summarize traffic exchanged with other
Switzerland clients, and should not tell the server anything about
communications with computers that are not Switzerland clients.

Summary information uses cryptographic hashes of packets, so it's hard to
reconstruct the contents of your packets from what you send to Switzerland.
However, when it detects forged packets, the Switzerland server may ask your
computer for full copies of packets sent around the time that the forgery was
received.  Therefore it is likely that running Switzerland will result in
portions of your unencrypted communications being logged at the server.  By
default, Switzerland clients will use a server run by the EFF, but you have the
option of running your own server and telling your clients to connect to that
instead.

In this release, traffic between Switzerland clients and the server is
unencrypted, so it's possible for an eavesdropper near the server to see
information about what kind of connections you have open with which other
Switzerland clients, and how frequently you're exchanging data (an eavesdropper
near you could probably see most of this information regardless of whether you
were running Switzerland).

Later releases will reduce some of these privacy issues and add more options
for fine-grained privacy control.  For now though, treat any traffic traveling
between Switzerland clients as "public record" information.

2. Testing Notes

2.1. NAT (Network Address Translation) firewalls

Switzerland is aware of the changes to IP addresses and port numbers that NAT
firewalls normally make, and will not report those as modifications to the
underlying traffic.

But many NAT firewalls, especially home wireless routers, make other
undocumented modifications to the traffic traveling through them, beyond the
minimum required to be a NAT firewall.  As a result, Switzerland clients that
are behind firewalls or talking to machines that are behind firewalls will
often detect and report these modifications to traffic.

It is important not to confuse packet modification by your firewall or another
client's firewall with interference by an ISP.  If you want to perform reliable
tests of an ISP, you'll need to plug your computer directly into your DSL or
cable modem, and only consider results obtained with non-firewalled peers.
Switzerland will tell you which other clients are behind NAT firewalls.

In the future we may be able to build a database of different models of common
NAT firewalls and the things they do, which would allow preliminary tests to be
done through the firewall.  At the moment, for instance, we think that devices
running the DD-WRT open firmware make no unexpected modifications to traffic,
so you should be able to run ISP tests through them.  A firewall-free setup
should always be used to confirm test results.

2.2 Other firewalls

It is theoretically possible that interference can be performed by non-NAT
firewalls.  These are most likely to be encountered on corporate and university
networks.  Switzerland will detect this as interference by an intermediary.  It
isn't a bug, it's a feature.  Remember, traffic interference could be occurring
at any step along the way from your computer to another.

2.3 Test server

EFF runs a default server at switzerland.eff.org:7778 (we expect it'll crash
and misbehave a bit for early versions of the code), but you can run your own
servers elsewhere if you wish.

2.4 Tests you can run

http://switzerland.wiki.sourceforge.net/tests

There are a few different ways to run tests with Switzerland.

Any packets exchanged between Switzerland clients connected to the same server
will be tested automatically.  The question is, how do you find other clients
and talk to them using the protocols you want to test?

For now, the easiest way to set up tests is to co-ordinate them through the
wiki page linked above or the IRC channel.  If you want to test whether
BitTorrent downloads are working correctly, go to that page and find some
torrents that others are seeding from test machines.  If you want to test if
your ISP is interfering with BitTorrent seeding, you can post a link to a
torrent file on the wiki, seed that torrent while running a Switzerland client
and other people can find it on the wiki and try to download it while running a
Switzerland client.

Another way is to run clients on two different computers, and then make the
machines talk to each other using whatever protocol you'd like to test.  That's
fine if you have administrator accounts on two suitable machines for running
the test, and are comfortable running the right clients and servers on them.

If you're a developer working on an application (say a P2P or IP telephony app)
that might be a target for interference, you could automate one of the above
methodologies.

3. Contributing

3.1. Ways to help

- use the software and report bugs / results
- run or write new unit test cases
- add or fix support for your platform (especially installation!)
- help find and fix security vulnerabilities
- implement new features
- send us patches, become a maintainer!

3.2. svn repository

Switzerland's public ssh repository is available at
https://Switzerland.svn.sourceforge.net/svnroot/Switzerland

3.3. Tree organization

bin/                     : supporting binaries
Switzerland/             : source code
  client/                : client code
    Alice.py             : main file for client
    AliceConfig.py       : command-line option/configuration file handling
    AliceFlow.py         : one direction of an IP communication
    AliceLink.py         : interaction with Switzerland server
    Cleaner.py           : thread to remove stale queued packets
    FastCollector.c      : packet sniffer that writes to mmap'd buffer
    FlowManager.py       : thread to track active flows
    Packet.py            : an IP datagram
    PacketBatch.py       : group of IP datagrams
    PacketDiff.py        : figure out what changed inside a modified packet
    PacketListener.py    : thread to listen for incoming packets
    PacketQueue.py       : a queue of batches in the same flow
    Reporter.py          : thread to report traffic to server
    TimeManager.py       : interface with NTP
  common/                : code shared between client+server
    Flow.py              : one direction of an IP communication
    Messages.py          : Switzerland protocol messages
    PcapLogger.py        : write datagrams to pcap files
    Protocol.py          : client/server socket communication
    local_ip.py          : detect IP address / network interfaces
    util.py              : miscellaneous
  lib/                   : third-party libraries
    tweaked_cerealizer.py: modified version of python cerealizer
  server/                : server code
    Reconciliator.py     : test whether two views of a flow agree
    Switzerland.py       : main server file
    SwitzerlandConfig.py : command-line options/configuration file handling
    SwitzerlandLink.py   : interaction with clients
  tests/                 : unit tests
switzerland-client*      : client
switzerland-server*      : server

