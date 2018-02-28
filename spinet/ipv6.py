import os
import binascii
from pyroute2 import IPRoute


def random_addr():
    '''Generate a random link-local IPv6 address
    '''
    d = binascii.hexlify(os.urandom(8)).decode('ascii')
    return ('2222::%s:%s:%s:%s' % (d[0:4], d[4:8], d[8:12], d[12:16]), 64)


def add_addr(ifname, addr):
    ip = IPRoute()
    i = ip.link_lookup(ifname=ifname)[0]
    ip.addr('add', index=i, address=addr[0], scope=253, prefixlen=addr[1])
    ip.close()


def del_addr(ifname, addr):
    ip = IPRoute()
    i = ip.link_lookup(ifname=ifname)[0]
    ip.addr('del', index=i, address=addr[0], prefixlen=addr[1])
    ip.close()
