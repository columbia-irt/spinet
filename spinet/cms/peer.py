import logging
from   . import on, sup

log = logging.getLogger(__name__)


discovering = False


@on('P2P-FIND-STOPPED')
def restart_p2p_find(ifname, sup, **kwds):
    if discovering:
        log.debug('Restarting p2p_find')
        sup.p2p_find()


def start_discovery():
    global discovering
    if not discovering:
        discovering = True
        sup.p2p_find()


def stop_discovery():
    global discovering
    if discovering:
        sup.p2p_stop_find()
        discovering = False
