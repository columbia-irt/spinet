def main():
    import spinet.enrolled as enrolled
    import argparse, sqlite3

    p = argparse.ArgumentParser(prog='enrolled')
    p.add_argument('-i', '--ifname',  help='Interface name (%s)' % enrolled.ifname)
    p.add_argument('-v', '--verbose', help='Increase verbosity', action='store_true')
    p.add_argument('-d', '--db',      help='SQLite database file (%s)' % enrolled.db_path, default=enrolled.db_path)
    p.add_argument('-n', '--name',    help='Node name (%s)' % enrolled.name, default=enrolled.name)
    p.add_argument('-p', '--port',    help='HTTP API listen port (%d)' % enrolled.port, type=int, default=enrolled.port)
    args = p.parse_args()

    enrolled.ifname  = args.ifname
    enrolled.name    = args.name
    enrolled.db_path = args.db
    enrolled.db      = sqlite3.connect(enrolled.db_path)
    enrolled.port    = args.port
    enrolled.verbose = args.verbose

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
    txt = srv.create_TXT(name, {'uri':' http://[%s]:%d/' % (enrolled.addr[0], enrolled.port)})
    enrolled.sup.p2p_service_add(txt)

    from . import api
    api.apply_network_configuration()

    enrolled.sup.p2p_find()

    api.app.run(host='::', port=enrolled.port)

    ipv6.del_addr(enrolled.ifname, enrolled.addr)

#
# The extra level of indirection via the main function is needed for setuptool
# entry_points.
#
if __name__ == '__main__':
    main()
