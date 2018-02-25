import os
import sys

if sys.version_info[0] < 3 or sys.version_info[1] < 6:
    raise "Python 3.6 or newer required"


import spinet.enrolled as enrolled
import argparse, sqlite3

p = argparse.ArgumentParser(prog='device-label')
p.add_argument('-i', '--ifname',  help='Interface name (%s)' % enrolled.ifname, default=enrolled.ifname)
p.add_argument('-d', '--db',      help='SQLite database file (%s)' % enrolled.db_path, default=enrolled.db_path)
p.add_argument('-c', '--cert',    help='Device certificate file (%s)' % enrolled.crt_path, default=enrolled.crt_path)
p.add_argument('-k', '--key',     help='Device private key file (%s)' % enrolled.key_path, default=enrolled.key_path)
args = p.parse_args()

enrolled.ifname   = args.ifname
enrolled.db_path  = args.db
enrolled.db       = sqlite3.connect(enrolled.db_path)
enrolled.crt_path = args.cert
enrolled.key_path = args.key


from spinet.enrolled import data, cert
data.initialize_db()

import pyqrcode
import netifaces
import base64
import cbor

addr = netifaces.ifaddresses(enrolled.ifname)[netifaces.AF_LINK][0]['addr']
name = data.config['name']
crt = cert.load_cert(enrolled.crt_path)
fpr = cert.PubkeyFingerprint(crt.get_pubkey())

qrdata = cbor.dumps([1, name, fpr.as_bytes()])
qr = pyqrcode.create(base64.b64encode(qrdata))

from tabulate import tabulate

def main():
    print(tabulate([['HW Address', addr],
                    ['Device Name', name],
                    ['Public Key', fpr.as_base64()]],
                   [], tablefmt="psql"))
    print(qr.terminal(quiet_zone=1))


# setuptool entry_points need a function to run, so we execute the last
# (blocking) step in a function so that the function can be invoked from setuptools.
#
if __name__ == '__main__':
    main()
