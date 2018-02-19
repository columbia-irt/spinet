import os
import sys

if sys.version_info[0] < 3 or sys.version_info[1] < 6:
    raise "Python 3.6 or newer required"


import spinet.enrolled as enrolled
import argparse, sqlite3

p = argparse.ArgumentParser(prog='enrolled')
p.add_argument('-i', '--ifname',  help='Interface name (%s)' % enrolled.ifname)
p.add_argument('-v', '--verbose', help='Increase verbosity', action='store_true')
p.add_argument('-d', '--db',      help='SQLite database file (%s)' % enrolled.db_path, default=enrolled.db_path)
p.add_argument('-n', '--name',    help='Node name (%s)' % enrolled.name, default=enrolled.name)
p.add_argument('-p', '--port',    help='HTTP API listen port (%d)' % enrolled.port, type=int, default=enrolled.port)
p.add_argument('-c', '--cert',    help='Device certificate file (%s)' % enrolled.crt_path, default=enrolled.crt_path)
p.add_argument('-k', '--key',     help='Device private key file (%s)' % enrolled.key_path, default=enrolled.key_path)
args = p.parse_args()

enrolled.ifname   = args.ifname
enrolled.name     = args.name
enrolled.db_path  = args.db
enrolled.db       = sqlite3.connect(enrolled.db_path)
enrolled.port     = args.port
enrolled.verbose  = args.verbose
enrolled.crt_path = args.cert
enrolled.key_path = args.key

from .. import logger
logger.setup()
if enrolled.verbose:
    logger.set_log_level(logger.DEBUG)


import logging
log = logging.getLogger(__name__)


from .. import wpas

@enrolled.on('P2P-INVITATION-RECEIVED')
def connect(ifname, data, **kwds):
    data = wpas.parse_kv_line(data)
    go = data['go_dev_addr']
    log.debug('Accepting invitation from GO %s for BSSID %s' % (go, data['bssid']))
    enrolled.sup.p2p_connect(go, join=True)

from . import data
data.initialize_db()

from .. import ipv6
log.debug('Adding address %s to interface %s' % (enrolled.addr[0], enrolled.ifname))
ipv6.add_addr(enrolled.ifname, enrolled.addr)

enrolled.sup.start(enrolled.ifname)
enrolled.sup.set('device_name', enrolled.name)

log.info('Enrolled [%s,%s,%s]\nwpa_supplicant %s [%s]' % (enrolled.name, enrolled.ifname, enrolled.addr[0], enrolled.sup.uuid, enrolled.sup.address))

from . import srv
name = '_spinet._tcp.local.'
txt = srv.create_TXT(name, {'uri':' https://[%s]:%d/' % (enrolled.addr[0], enrolled.port)})
enrolled.sup.p2p_service_add(txt)

from . import api
api.apply_network_configuration()

enrolled.sup.p2p_find()

from . import cert

if not os.path.isfile(enrolled.key_path):
    log.debug('Generating device private key')
    cert.generate_privkey(enrolled.key_path)

if not os.path.isfile(enrolled.crt_path):
    log.debug('Generating self-signed device certificate')
    cert.generate_cert(enrolled.crt_path, enrolled.name, enrolled.key_path)

log.info('Pubkey: %s' % cert.pubkeySHA256(enrolled.crt_path))

def main():
    api.app.run(host='::', port=enrolled.port, ssl_context=(enrolled.crt_path, enrolled.key_path))
    ipv6.del_addr(enrolled.ifname, enrolled.addr)


# setuptool entry_points need a function to run, so we execute the last
# (blocking) step in a function so that the function can be invoked from setuptools.
#
if __name__ == '__main__':
    main()
