def main():
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


    from . import data
    data.initialize_db()

    cms.sup.start(cms.ifname)
    cms.sup.set('device_name', cms.name)

    from . import peer, ping

    from .shell import Shell
    sh = Shell('Commissioner [%s] [%s], wpa_supplicant %s [%s]' % (cms.name, cms.ifname, cms.sup.uuid, cms.sup.address), '[%s]> ' % cms.name)
    sh.cmdloop()

    cms.sup.stop()


#
# The extra level of indirection via the main function is needed for setuptool
# entry_points.
#
if __name__ == '__main__':
    main()
