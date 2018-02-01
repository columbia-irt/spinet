import logging
from   ..dnssd import ANQPData, DomainName


def create_PTR(name):
    sep = name.find('.')
    data = ANQPData(DomainName(name[sep+1:]), ANQPData.TYPE_PTR)
    rdata = data.create_rdata(name)
    return 'bonjour %s %s' % (data, rdata)


def create_TXT(name, attrs):
    data = ANQPData(DomainName(name), ANQPData.TYPE_TXT)
    rdata = data.create_rdata(attrs)
    return 'bonjour %s %s' % (data, rdata)
