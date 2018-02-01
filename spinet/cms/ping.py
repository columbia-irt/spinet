import logging
import threading
import netifaces
import socket
import select
import time
from   . import sup, on

icmp = socket.getprotobyname('ipv6-icmp')

log = logging.getLogger(__name__)

pingers = {}


class IPv6McastPinger(object):
    DATA = '\x80\0\0\0\0\0\0\0'
    ALL_NODES = 'ff02::1'


    def __init__(self, data, ifname, ping_interval=1, lifetime=5, purge_interval=1, notify=None):
        self.data = data
        self.ifname = ifname
        self.ping_interval = ping_interval
        self.lifetime = lifetime
        self.purge_interval = purge_interval
        self.notify = notify

        self.last_ping = 0
        self.last_purge = 0

        self.my_addrs = [i['addr'] for i in netifaces.ifaddresses(ifname)[netifaces.AF_INET6]]

        addrs = socket.getaddrinfo('%s%%%s' % (self.ALL_NODES, ifname), 0, socket.AF_INET6, 0, socket.SOL_IP)
        self.addr = addrs[0][4]
        self.sock = socket.socket(socket.AF_INET6, socket.SOCK_RAW, icmp)

        self.running = False


    def ping(self):
        try:
            self.sock.sendto(self.DATA, self.addr)
        except Exception as e:
            pass


    def purge(self):
        now = time.time()
        for addr in list(self.data.keys()):
            timestamp = self.data[addr]
            if (timestamp + self.lifetime) < now:
                del self.data[addr]
                if self.notify:
                    self.notify(False, addr)


    def process_response(self, msg, addrinfo):
        addr = addrinfo[0]

        if not self.ifname in addr:
            return

        if addr in self.my_addrs:
            return

        new = self.data.get(addr, None) is None
        self.data[addr] = time.time()
        if new and self.notify:
            self.notify(True, addr)


    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()


    def stop(self):
        self.running = False
        del self.thread


    def run(self):
        self.running = True
        while self.running:
            now = time.time()
            try:
                t1 = self.last_ping + self.ping_interval - now
                t2 = self.last_purge + self.purge_interval - now
                tout = min(t1, t2)
                if tout <= 0:
                    tout = 0.01

                self.sock.settimeout(tout)
                msg, addrinfo = self.sock.recvfrom(4096)
            except socket.timeout:
                pass
            else:
                self.process_response(msg, addrinfo)

            if (now - self.last_ping) > self.ping_interval:
                self.ping()
                self.last_ping = now

            if (now - self.last_purge) > self.purge_interval:
                self.purge()
                self.last_purge = now


def ip_nodes():
    for _, p in pingers.items():
        for k in p['data'].keys():
            yield k


@on('P2P-GROUP-STARTED')
def start_pinger(ifname, data, **kwds):
    d = data.split(' ')
    if len(d) < 2:
        log.warn('Invalid P2P-GROUP-STARTED notification: %s' % event)
        return

    if d[1] != 'GO':
        return

    ifn = d[0]
    if pingers.get(ifn, None) is None:
        log.debug('Starting IPv6 pinger for interface %s' % ifn)
        pingers[ifn] = {
            'data': {}
        }
        p = IPv6McastPinger(pingers[ifn]['data'], ifn)
        pingers[ifn]['pinger'] = p
        p.start()


@on('P2P-GROUP-REMOVED')
def stop_pinger(ifname, data, **kwds):
    d = data.split(' ')
    if len(d) < 2:
        log.warn('Invalid P2P-GROUP-REMOVED notification: %s' % data)
        return
    if d[1] != 'GO':
        return

    ifn = d[0]
    if pingers.get(ifn, None) is not None:
        log.debug('Stopping IPv6 pinger for interface %s' % ifn)
        pingers[ifn]['pinger'].stop()
        del pingers[ifn]
