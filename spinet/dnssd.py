from binascii    import hexlify
from struct      import Struct, pack, unpack_from
from collections import OrderedDict

__all__ = [
    'SDError',
    'DomainName',
    'ANQPData',
    'ANQPQuery',
    'ANQPResponse',
    'PTRData',
    'TXTData'
]


class SDError(Exception):
    pass


class Compressor(object):
    PREFIX = b'\xc0'

    DECOMPRESS = {
        b'\xc0\x11': ['local'],
        b'\xc0\x0c': ['_tcp', 'local'],
        b'\xc0\x1c': ['_udp', 'local']
    }


    COMPRESS = [
        (['_tcp', 'local'], b'\xc0\x0c'),
        (['_udp', 'local'], b'\xc0\x1c'),
        (['local'],         b'\xc0\x11')
    ]

    ref_ptr = b'\xc0\x27'


    def __init__(self, _ref=None):
        if _ref is None:
            return

        if not isinstance(_ref, DomainName):
            raise SDError('Invalid parameter ref')

        ref = _ref.as_list

        self.DECOMPRESS = dict(type(self).DECOMPRESS)
        self.DECOMPRESS[self.ref_ptr] = ref

        self.COMPRESS = list(type(self).COMPRESS)
        self.COMPRESS.append((ref, self.ref_ptr))


    def compress(self, name):
        for k, v in self.COMPRESS:
            if name == k:
                return v


    def decompress(self, bits):
        return self.DECOMPRESS[bits]



class HexPack(object):
    def __str__(self):
        packs = self.pack()
        if not isinstance(packs, tuple):
            packs = (packs,)

        return ' '.join([hexlify(p).decode('ascii') for p in packs])



class DomainName(HexPack):
    def __init__(self, value, compressor=None):
        # If we get a bytes object, convert it to string
        if isinstance(value, bytes):
            value = value.decode('ascii')

        # If we have a string, convert it to list and (optionally) remove the
        # last empty component
        if isinstance(value, str):
            value = value.split('.')
            if value[-1] == '':
                value = value[:-1]

        self.value = value

        if compressor is None:
            self.compressor = Compressor()
        else:
            self.compressor = compressor


    @classmethod
    def parse(cls, data, offset=0, compressor=None):
        if compressor is None:
            compressor = Compressor()

        v = []
        while True:
            l = unpack_from('s', data, offset)[0]
            offset += 1
            if l == b'\0':
                break
            if l == compressor.PREFIX:
                l += unpack_from('s', data, offset)[0]
                offset += 1
                v += compressor.decompress(l)
                break
            else:
                l = ord(l)
                v.append(unpack_from('%ds' % l, data, offset)[0].decode('ascii'))
                offset += l
        return cls(v, compressor=compressor), offset


    def pack(self):
        rv = b''

        for i in range(len(self.value)):
            v = self.compressor.compress(self.value[i:])
            if v is not None:
                rv += v
                return rv
            else:
                v = self.value[i].encode('ascii')
                vl = len(v)
                if vl > 63:
                    raise SDError('Domain name component %s too long' % self.value[i])
                rv += pack('B', vl)
                rv += v

        rv += b'\0'
        return rv


    @property
    def as_str(self):
        return '.'.join(self.value) + '.'


    @property
    def as_list(self):
        return list(self.value)


    def __repr__(self):
        return '%s(%s)' % (type(self).__name__, repr(self.as_str))


    def __eq__(self, other):
        v1 = [v.lower() for v in self.value]
        v2 = [v.lower() for v in other.value]
        return v1 == v2



class ANQP(HexPack):
    PROTO = 1
    tid_counter = 1

    def __init__(self, data, tid=None):
        self.data = data
        if tid is None:
            cls = type(self)
            tid = cls.tid_counter
            cls.tid_counter = (cls.tid_counter + 1) % 256
        self.tid = tid

    def parse_rdata(self, *args, **kwargs):
        return self.data.parse_rdata(*args, **kwargs)


    def create_rdata(self, *args, **kwargs):
        return self.data.create_rdata(*args, **kwargs)



class ANQPData(HexPack):
    VERSION = 1
    TYPE_PTR = 12
    TYPE_TXT = 16
    hdr = Struct('>HB')

    def __init__(self, name, type_):
        if isinstance(name, DomainName):
            self.name = name
        else:
            self.name = DomainName(name)

        self.type_ = type_


    @classmethod
    def parse(cls, data, offset=0):
        name, offset = DomainName.parse(data, offset)
        type_, version = cls.hdr.unpack_from(data, offset)
        if version != cls.VERSION:
            raise SDError('Unsupported version %d' % version)
        offset += cls.hdr.size
        return cls(name, type_), offset


    def parse_rdata(self, data, offset=0):
        if self.type_ == self.TYPE_PTR:
            c = Compressor(self.name)
            return PTRData.parse(data, offset, compressor=c)
        elif self.type_ == self.TYPE_TXT:
            return TXTData.parse(data, offset)
        else:
            raise SDError('Invalid type: %d' % self.type_)


    def create_rdata(self, data):
        if self.type_ == self.TYPE_PTR:
            c = Compressor(self.name)
            return PTRData(data, compressor=c)
        elif self.type_ == self.TYPE_TXT:
            return TXTData(data)
        else:
            raise SDError('Invalid type: %d' % self.type_)


    def pack(self):
        return self.name.pack() + self.hdr.pack(self.type_, self.VERSION)


    @classmethod
    def _type2str(cls, type_):
        n = cls.__name__
        t = '%s.TYPE_' % n
        if type_ == cls.TYPE_PTR:
            t += 'PTR'
        elif type_ == cls.TYPE_TXT:
            t += 'TXT'
        else:
            t = '%d' % type_
        return t


    def __repr__(self):
        return '%s(%s, %s)' % \
            (type(self).__name__, repr(self.name), self._type2str(self.type_))



class ANQPQuery(ANQP):
    hdr = Struct('<HBB')

    @classmethod
    def parse(cls, data, offset=0):
        _, proto, tid = cls.hdr.unpack_from(data, offset)
        if proto != cls.PROTO:
            raise SDError('Usupported protocol type %d' % proto)
        offset += cls.hdr.size

        d, offset = ANQPData.parse(data, offset)
        return cls(d, tid), offset


    def pack(self):
        data = self.data.pack()
        hdr = self.hdr.pack(2 + len(data), self.PROTO, self.tid)
        return hdr + data


    def __repr__(self):
        return '%s(%s, %s)' % \
            (type(self).__name__, repr(self.data), self.tid)



class ANQPResponse(ANQP):
    SUCCESS           = 0
    PROTO_UNAVAILABLE = 1
    INFO_UNAVAILABLE  = 2
    BAD_REQUEST       = 3

    hdr = Struct('<HBBB')

    def __init__(self, code, data, rdata, tid=None):
        super().__init__(data, tid)
        self.code = code
        self.rdata = rdata


    @classmethod
    def parse(cls, data, offset=0):
        _, proto, tid, code = cls.hdr.unpack_from(data, offset)
        if proto != cls.PROTO:
            raise SDError('Usupported protocol type %d' % proto)
        offset += cls.hdr.size

        if code == cls.SUCCESS:
            d, offset = ANQPData.parse(data, offset)
            rdata, offset = d.parse_rdata(data, offset)
        else:
            d = None
            rdata = None
        return cls(code, d, rdata, tid), offset


    def pack(self):
        if self.data:
            data = self.data.pack()
        else:
            data = b''

        if self.rdata:
            rdata = self.rdata.pack()
        else:
            rdata = b''
        hdr = self.hdr.pack(3 + len(data) + len(rdata), self.PROTO, self.tid, self.code)
        return hdr + data + rdata


    def __repr__(self):
        return '%s(%d, %s, %s, %s)' % \
            (type(self).__name__, self.code, repr(self.data), repr(self.rdata), self.tid)



class PTRData(DomainName):
    pass


class TXTData(HexPack):
    def __init__(self, attrs):
        self.attrs = OrderedDict(attrs)


    @classmethod
    def parse(cls, data, offset=0):
        dlen = len(data)
        rv = OrderedDict()
        while (dlen - offset) > 0:
            l = unpack_from('s', data, offset)[0]
            offset += 1
            if l == b'\0':
                break
            else:
                l = ord(l)
                kv = unpack_from('%ds' % l, data, offset)[0].decode('ascii')
                k, v = kv.split('=')
                rv[k] = v
                offset += l

        return cls(rv), offset


    def pack(self):
        if not self.attrs:
            return b'\x00'

        rv = b''
        for k,v in self.attrs.items():
            k = k.encode('ascii')
            v = str(v).encode('ascii')
            rv += pack('%dp' % (len(k)+len(v)+2), k + b'=' + v)
        return rv


    def __repr__(self):
        return '%s(%s)' % (type(self).__name__, repr(self.attrs))
