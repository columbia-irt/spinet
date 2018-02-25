import hashlib
import base64
from OpenSSL import crypto


def generate_privkey(path):
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)

    with open(path, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))


def generate_cert(path, name, key_path):
    with open(key_path, 'r') as kf:
        key = crypto.load_privatekey(crypto.FILETYPE_PEM, kf.read())

    c = crypto.X509()
    c.get_subject().CN = name
    c.set_serial_number(1)
    c.gmtime_adj_notBefore(-1*365*24*60*60)
    c.gmtime_adj_notAfter(10*365*24*60*60)
    c.set_issuer(c.get_subject())
    c.set_pubkey(key)
    c.sign(key, 'sha1')

    with open(path, 'wb') as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, c))

    return c


def load_cert(cert_path):
    with open(cert_path, 'r') as cf:
        return crypto.load_certificate(crypto.FILETYPE_PEM, cf.read())


class PubkeyFingerprint(object):
    def __init__(self, pubkey):
        der = crypto.dump_publickey(crypto.FILETYPE_ASN1, pubkey)
        self.fpr = hashlib.sha256(der).digest()

    def as_base64(self):
        return base64.b64encode(self.fpr).decode()

    def as_bytes(self):
        return self.fpr
