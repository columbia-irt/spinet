import sys
import cmd
import code
import json
import logging
from   tabulate import tabulate

from .. import logger

import spinet.cms as cms
from . import data, api, srv, peer, ping

log = logging.getLogger(__name__)


class Shell(cmd.Cmd):
    def __init__(self, intro, prompt, *args, **kwds):
        super().__init__(*args, **kwds)
        self.intro = intro
        self.prompt = prompt


    def do_debug(self, v):
        '''debug [<on|off>] - Configure debugging

Without any arguments, the command shows whether debugging is currently
enabled or disabled. With an on/off argument, the command enables or disables
debugging to the console.
        '''
        if v == '':
            if cms.verbose:
                print('Debugging is enabled')
            else:
                print('Debugging is disabled')
        elif v == 'on':
            logger.set_log_level(logger.DEBUG)
            cms.verbose = True
        elif v == 'off':
            logger.set_log_level(logger.INFO)
            cms.verbose = False
        else:
            print('Usage: debug [<on|off>]')


    def do_peer_discovery(self, v):
        '''peer_discovery [<on|off>] - Configure peer discovery
        '''
        if v == '':
            if peer.discovering:
                print('Peer discovery is enabled')
            else:
                print('Peer discovery is disabled')
        elif v == 'on':
            peer.start_discovery()
        elif v == 'off':
            peer.stop_discovery()
        else:
            print('Usage: peer_discovery [<on|off>]')


    def do_net(self, *args):
        '''Show configured networks

This command shows a table of all the network blocks configured in the
commissioner.
        '''
        c = cms.db.cursor()
        c.execute('SELECT id, ssid, type, attrs, created FROM net')

        print(tabulate(c.fetchall(),
            ['Id', 'SSID', 'Type', 'Attributes', 'Created'],
            tablefmt="psql"))


    def do_net_add(self, args):
        'net_add <ssid> <Open|WPA-PSK|WPA-802.1X> [JSON attrs]'
        ssid, type_, attrs = args.split(maxsplit=2)
        data.add_net(ssid, type_=type_, **json.loads(attrs))
        print('OK')


    def do_net_remove(self, id):
        'net_remove <id>'
        data.remove_net(id)
        print('OK')


    def do_interfaces(self, *args):
        tab = []
        for ifname in cms.sup.interfaces():
            with cms.sup.interface(ifname):
                d = cms.sup.status()
                sta = "\n".join([addr for addr, attrs in cms.sup.all_sta()])
                tab.append([ifname, d.get('mode', ''), d.get('ssid', ''),
                            d.get('bssid', ''), d.get('freq', ''), sta])

        print(tabulate(tab,
            ['Interface', 'Mode', 'SSID', 'BSSID', 'Freq. [MHz]', 'Stations'],
            tablefmt='psql'))


    def do_group_add(self, *args):
        cms.sup.p2p_group_add()
        print('OK')


    def do_group_remove(self, id):
        cms.sup.p2p_group_remove(id)
        print('OK')


    def do_info(self, *args):
        keys = {
            'device_name': True,
            'manufacturer': True,
            'model_name': True,
            'model_number': True,
            'serial_number': True,
            'p2p_listen_channel': True
        }
        data = cms.sup.dump()
        print(tabulate([[key, data[key]] for key in data.keys() if keys.get(key, None) ],
                       ['Parameter', 'Value'], tablefmt='psql'))


    def do_peers(self, *args):
        print(tabulate([
            [addr, data['device_name'], data['listen_freq'], data['level'], data['age']] for addr, data in cms.sup.p2p_peers()],
            ['Address', 'Name', 'Freq. [MHz]', 'Signal [dBm]', 'Age [s]'],
            tablefmt="psql"))


    def do_stations(self, *args):
        tab = []
        for ifname in cms.sup.interfaces():
            with cms.sup.interface(ifname):
                for addr, attrs in cms.sup.all_sta():
                    tab.append([addr, attrs['p2p_device_name'], attrs['wpsUuid'], attrs['connected_time'], attrs['inactive_msec']])

        print(tabulate(tab,
            ['Address', 'Name', 'UUID', 'Connected [s]', 'Inactive [ms]'],
            tablefmt='psql'))


    def do_sta_disconnect(self, addr):
        cms.sup.p2p_remove_client(addr)
        print('OK')


    def do_ip(self, *args):
        data = []
        for k in ping.ip_nodes():
            data.append([k])

        print(tabulate(data,
            ['IP'],
            tablefmt='psql'))


    def do_post_net(self, args):
        id, ip = args.split(maxsplit=1)
        api.post_net(int(id), ip=ip)
        print('OK')


    def do_apply_netconfig(self, ip):
        api.apply_netconfig(ip)
        print('OK')


    def do_services(self, *args):
        print(tabulate([
            [addr, repr(srv.services[addr].rdata.attrs)] for addr in srv.services.keys()
        ], ['Address', 'Instance'], tablefmt='psql'))


    def do_service_discovery(self, v):
        '''service_discovery [<on|off>] - Configure DNS-SD discovery
        '''
        if v == '':
            if srv.discovering:
                print('DNS-SD discovery is enabled')
            else:
                print('DNS-SD discovery is disabled')
        elif v == 'on':
            srv.start_discovery()
        elif v == 'off':
            srv.stop_discovery()
        else:
            print('Usage: service_discovery [<on|off>]')


    def do_invite(self, args):
        'invite <peer> <ifname>'
        peer, ifname = args.split(maxsplit=1)
        peer = [peer]

        with cms.sup.interface(ifname):
            cms.sup.wps_pbc()

        print('Inviting:', end='')
        for addr in peer:
            print(' %s' % addr, end='')
            cms.sup.p2p_invite(addr, ifname)
        print('')


    def do_status(self, args):
        'Display commissioner status'
        print('Commissioner:')
        print(tabulate([['Discovery', peer.discovering]],
                       ['Parameter', 'Value'], tablefmt='psql'))
        print('')

        print('Configured Networks:')
        self.do_net()
        print('')

        print('WPASupplicant:')
        self.do_info()
        print('')

        print('Interfaces:')
        self.do_interfaces()
        print('')

        print('Discovered Peers:')
        self.do_peers()
        print('')

        print('Connected Stations:')
        self.do_stations()
        print('')

        print('Discovered IP nodes:')
        self.do_ip()


    def do_flush(self, *args):
        cms.sup.p2p_flush()
        print('OK')


    def do_EOF(self, *args):
        'Exit the commissioner command line shell.'
        return True


    def do_shell(self, *args):
        '''Launch an interactive Python interpreter

This command will drop you into an interactive Python interpreter which gives
you access to commissioner's internals. You can inspect all variables and
invoke any Python function. The package spinet contains all the code for the
commissioner. The global symbol table is set to the module spinet.cms.main.
        '''
        banner = '''Python %s
Type "help", "copyright", "credits" or "license" for more information.''' % sys.version
        code.interact(banner, local=sys.modules['__main__'].__dict__)


    def postloop(self):
        print('Bye!')
