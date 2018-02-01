import logging
from tabulate       import tabulate
from binascii       import unhexlify
from spinet.dnssd   import ANQPQuery, ANQPData, ANQPResponse, DomainName
from spinet.wpas    import parse_kv_line
from . import sup, on

log = logging.getLogger(__name__)

discovering = False
request_id = None

services = {}


@on('P2P-SERV-DISC-RESP')
def save_srv(ifname, data, **kwds):
    addr, update, tlv = data.split(' ')
    res, _ = ANQPResponse.parse(unhexlify(tlv))

    if res.code == ANQPResponse.PROTO_UNAVAILABLE:
        try:
            del services[addr]
        except KeyError:
            pass
        return

    if res.code != ANQPResponse.SUCCESS:
        raise Exception('ANQPResponse error: %d' % res.code)

    services[addr] = res


@on('P2P-DEVICE-LOST')
def delete_srv(ifname, data, **kwds):
    d = parse_kv_line(data)
    try:
        del services[d['p2p_dev_addr']]
    except KeyError:
        pass


def start_discovery():
    global discovering, request_id
    if not discovering:
        query = ANQPQuery(ANQPData(DomainName('_cms._tcp.local.'), ANQPData.TYPE_PTR))
        request_id = sup.p2p_serv_disc_req(query)
        discovering = True


def stop_discovery():
    global discovering, request_id
    if discovering:
        try:
            sup.p2p_serv_disc_cancel_req(request_id)
        finally:
            request_id = None
            discovering = False
