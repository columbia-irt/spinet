import json
import logging
import urllib3
from   .     import db
from   .ping import ip_nodes

log = logging.getLogger(__name__)

http = urllib3.PoolManager()


def post_net(id, ip=None):
    c = db.cursor()
    c.execute('SELECT ssid, attrs FROM net where id=?', (id,))
    ssid, attrs = c.fetchone()
    attrs = json.loads(attrs)

    if attrs.get('ssid', None) is None:
        attrs['ssid'] = ssid

    if ip is not None:
        ips = [ip]
    else:
        ips = ip_nodes()

    for ip in ips:
        log.debug('Posting network configuration %d to %s' % (id, ip))
        r = http.request('POST', 'http://[%s]:10000/net' % ip,
                         headers={'Content-Type': 'application/json'},
                         body=json.dumps(attrs))
        if r.status != 200 and r.status != 204:
            raise Exception('Error: %d', r.status)


def apply_netconfig(ip=None):
    if ip is not None:
        ips = [ip]
    else:
        ips = ip_nodes()

    for ip in ips:
        log.debug('Applying network configuration at %s' % ip)
        r = http.request('POST', 'http://[%s]:10000/apply' % ip)
        if r.status != 200 and r.status != 204:
            raise Exception('Error: %d', r.status)
