import sys

if sys.version_info[0] < 3 or sys.version_info[1] < 6:
    raise "Python 3.6 or newer required"


import spinet.cms as cms
import argparse, sqlite3

p = argparse.ArgumentParser(prog='commissioner')
p.add_argument('-i', '--ifname',  help='Interface name (%s)' % cms.ifname)
p.add_argument('-v', '--verbose', help='Increase verbosity', action='store_true')
p.add_argument('-d', '--db',      help='SQLite database file (%s)' % cms.db_path, default=cms.db_path)
p.add_argument('-n', '--name',    help='Node name (%s)' % cms.name, default=cms.name)
args = p.parse_args()

cms.ifname  = args.ifname
cms.name    = args.name
cms.db_path = args.db
cms.db      = sqlite3.connect(cms.db_path)
cms.verbose = args.verbose

from .. import logger
logger.setup()
if cms.verbose:
    logger.set_log_level(logger.DEBUG)


import logging
log = logging.getLogger(__name__)


@cms.on('P2P-PROV-DISC-PBC-REQ')
def activate_pbc(ifname, data, sup, **kwds):
    # TODO: Activate PBC only for peers which we invited to connect
    with cms.sup.interface(ifname):
        log.debug('Activating PBC on interface %s' % ifname)
        cms.sup.wps_pbc()


@cms.on('WPS-PIN-NEEDED')
@cms.on('P2P-PROV-DISC-SHOW-PIN')
def activate_pin(ifname, data, sup, **kwds):
    with cms.sup.interface(ifname):
        log.debug('Activating PIN on interface %s' % ifname)
        cms.sup.wps_pin('12345670')


from .. import wpas

@cms.on('P2P-DEVICE-FOUND')
def on_device(ifname, data, sup, **kwds):
    sep = data.find(' ')
    attrs = wpas.parse_kv_line(data[sep:])
    log.info('Discovered %s' % attrs['p2p_dev_addr'])


from . import data
data.initialize_db()

cms.sup.start(cms.ifname)
cms.sup.set('device_name', cms.name)

from . import peer, ping

log.debug('Enabling peer discovery')
peer.start_discovery()


#log.debug('Creating Wi-Fi P2P group')
#cms.sup.p2p_group_add()


from .shell import Shell
sh = Shell('Commissioner [%s,%s,%s]\nwpa_supplicant [%s,%s]' % (cms.name, cms.ifname, cms.addr[0], cms.sup.uuid, cms.sup.address), '[%s]> ' % cms.name)


def main():
    sh.cmdloop()
    cms.sup.stop()


# setuptool entry_points need a function to run, so we need to define main
# here and execute the last (blocking) statement in it.
#
if __name__ == '__main__':
    main()
