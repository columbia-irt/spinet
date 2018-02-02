import os
import sys
import errno
import time
import socket
import blinker
import threading
import _thread
import select
import logging
import functools
import tempfile
from   contextlib      import contextmanager
from   cached_property import cached_property_with_ttl
from   spinet.dnssd    import *

__all__ = [
    'WPAError',
    'WPATimeout',
    'WPAParseError',
    'WPASupplicant',
    'WPSWPASupplicant',
    'P2PWPASupplicant',
    'parse_kv_line'
]

log = logging.getLogger(__name__)


class WPAError(Exception):
    pass


class WPATimeout(WPAError):
    pass


class WPAParseError(WPAError):
    pass


def wait(timeout, signal=None):
    try:
        [r, _, _] = select.select([signal] if signal is not None else [], [], [], timeout)
    except select.error as e:
        if e.errno != errno.EINTR:
            raise
    else:
        if r:
            signal.recv(1)
            _thread.exit()


def quoted(val):
    return '"%s"' % val


def parse_dict(data):
    rv = {}
    for l in data.splitlines():
        sep = l.find('=')
        if sep == -1:
            raise WPAParseError('Invalid status line: %s' % l)
        rv[l[:sep]] = l[sep+1:].strip()
    return rv


def parse_table(data):
    rows = data.splitlines()
    headings = [e.strip() for e in rows[0].split('/')]
    rows = rows[1:]

    data = []
    for row in rows:
        cells = [e.strip() for e in row.split('\t')]
        cells = cells + [''] * (len(headings) - len(cells))
        data.append(cells)
    return data, headings


def parse_kv_line(data):
    '''Parse a line of space-delimited key=value pairs, such as those found in
    asynchronous notifications. Unlike parse_dict, this function also supports
    single-quoted values.
    '''
    rv = {}
    while len(data):
        sep = data.find('=')
        if sep == -1:
            rv[data] = None
            break
        name = data[:sep].strip()
        rest = data[sep+1:]
        if rest[0] == "'":
            ends = rest[1:].find("'")
            if ends == -1:
                raise WPAParseError('Run-away string')
            value = rest[:ends+2].strip()
            data = rest[ends+3:]
        else:
            ends = rest.find(' ')
            if ends == -1:
                value = rest
                data = ''
            else:
                value = rest[:ends+1].strip()
                data = rest[ends+1:]
        rv[name] = value
    return rv


class WPASock(object):
    MAX_LEN = 65536

    def __init__(self, signal=None):
        self.local = tempfile.mktemp(prefix='wpas', suffix='.sock')

        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.setblocking(0)
        self.sock.bind(self.local)
        self.signal = signal


    def _wait(self, timeout):
        if timeout is None:
            deadline = None
        else:
            deadline = time.time() + timeout

        l = [self.sock]
        if self.signal is not None:
            l.append(self.signal)

        while True:
            now = time.time()
            if deadline is not None and now >= deadline:
                raise WPATimeout('Request timed out')

            try:
                if deadline is not None:
                    t = deadline - now
                else:
                    t = None

                [r, _, _] = select.select(l, [], [], t)
            except select.error as e:
                if e.errno == errno.EINTR:
                    continue
                raise
            else:
                if self.signal in r:
                    self.signal.recv(1)
                    _thread.exit()

                if self.sock in r:
                    return


    def connect(self, remote):
        log.debug('Connecting to %s' % remote)
        self.sock.connect(remote)


    def disconnect(self):
        # FIXME: This function currently does nothing, as it does not seem to
        # be possible to disconnect a previously connected SOCK_DGRAM socket
        # directly from Python code. The only workaround I'm aware of would be
        # implementing the function in C and call it via CFFI. This is not
        # really a problem for the wpa_supplicant event socket, since we're
        # not interested in receiving events from other addresses once the
        # socket has been connected for the first time. The socket can be
        # still connected to another destination by repeating the call to
        # connect.
        raise NotImplementedError()


    def fileno(self):
        return self.sock.fileno()


    def __del__(self):
        self.close()


    def close(self):
        if hasattr(self, 'sock'):
            self.sock.close()
            del self.sock

        if hasattr(self, 'local'):
            os.unlink(self.local)
            del self.local


    def tx(self, data, remote):
        log.debug('[%d]< %s' % (self.sock.fileno(), repr(data)))
        rv = self.sock.sendto(data.encode('ascii'), remote)
        if rv != len(data):
            raise WPAError('Cannot send data to %s (%d bytes sent)' % (remote, rv))


    def rx(self, timeout=None, max_len=None):
        if max_len is not None:
            ml = max_len
        else:
            ml = self.MAX_LEN

        self._wait(timeout)
        data, addr = self.sock.recvfrom(ml)
        data = data.decode('ascii')
        log.debug('[%d]> %s' % (self.sock.fileno(), repr(data[:80])))
        if len(data) >= ml:
            raise WPAError('Truncated data')
        return data, addr


class WPARequestSock(WPASock):
    def __init__(self, *args, **kwargs):
        WPASock.__init__(self, *args, **kwargs)
        # We need to lock the socket when waiting for a response to request.
        # wpa_supplicant puts no other information into the response that
        # would allow us to associate the response with the request.
        self.lock = threading.Lock()


    def request(self, data, remote, timeout=None):
        '''Send a request to wpa_supplicant and wait for response.

        This method locks the socket to ensure that there is only one
        outstanding request at a time on the socket. Do not use this method on
        a socket that has been attached for event notifications.
        '''
        with self.lock:
            self.tx(data, remote)
            return self.rx(timeout)[0]


class WPAEventSock(WPASock):
    def __init__(self, *args, **kwargs):
        WPASock.__init__(self, *args, **kwargs)
        self.attached = False


    def attach(self, remote, timeout=None):
        log.debug('Attaching to %s' % remote)
        self.tx('ATTACH', remote)

        data, _ = self.rx(timeout=timeout)
        if data.strip() != 'OK':
            raise WPAError('Attach to %s failed: %s' % (remote, data))

        self.attached = remote



    def detach(self, timeout=None):
        log.debug('Detaching from %s' % self.attached)
        self.tx('DETACH', self.attached)

        # The socket may receive pending events before DETACH is
        # confirmed/rejected and we need to deal with those here

        if timeout is not None:
            deadline = time.time() + timeout
        else:
            deadline = None

        while self.attached:
            now = time.time()

            if deadline is not None:
                if deadline <= now:
                    raise WPATimeout('Detach from %s timed out' % remote)
                t = deadline - now
            else:
                t = None

            data, _ = self.rx(timeout=t)
            data = data.strip()

            if data == 'OK':
                self.attached = False

            if data == 'FAIL':
                raise WPAError('Detach from %s failed: %s' % (remote, data))



class WPASupplicant(object):
    NET_PARAMS = {
        'altsubject_match': True,
        'altsubject_match2': True,
        'anonymous_identity': True,
        'ap_max_inactivity': True,
        'auth_alg': True,
        'beacon_int': True,
        'bg_scan_period': True,
        'bgscan': True,
        'bssid': True,
        'bssid_blacklist': True,
        'bssid_whitelist': True,
        'ca_cert': True,
        'ca_cert2': True,
        'ca_cert2_id': True,
        'ca_cert_id': True,
        'ca_path': True,
        'ca_path2': True,
        'cert2_id': True,
        'cert_id': True,
        'client_cert': True,
        'client_cert2': True,
        'dh_file': True,
        'dh_file2': True,
        'disabled': True,
        'domain_match': True,
        'domain_match2': True,
        'domain_suffix_match': True,
        'domain_suffix_match2': True,
        'dot11MeshConfirmTimeout': True,
        'dot11MeshHoldingTimeout': True,
        'dot11MeshMaxRetries': True,
        'dot11MeshRetryTimeout': True,
        'dtim_period': True,
        'eap': True,
        'eap_workaround': True,
        'eapol_flags': True,
        'engine': True,
        'engine2': True,
        'engine2_id': True,
        'engine_id': True,
        'erp': True,
        'fixed_freq': True,
        'fragment_size': True,
        'freq_list': True,
        'frequency': True,
        'go_p2p_dev_addr': True,
        'group': True,
        'ht': True,
        'ht40': True,
        'id_str': True,
        'identity': True,
        'ignore_broadcast_ssid': True,
        'key2_id': True,
        'key_id': True,
        'key_mgmt': True,
        'mac_addr': True,
        'max_oper_chwidth': True,
        'mesh_basic_rates': True,
        'mixed_cell': True,
        'mode': True,
        'no_auto_peer': True,
        'ocsp': True,
        'openssl_ciphers': True,
        'p2p_client_list': True,
        'pac_file': True,
        'pairwise': True,
        'password': True,
        'pbss': True,
        'pcsc': True,
        'peerkey': True,
        'phase1': True,
        'phase2': True,
        'pin': True,
        'pin2': True,
        'priority': True,
        'private_key': True,
        'private_key2': True,
        'private_key2_passwd': True,
        'private_key_passwd': True,
        'proactive_key_caching': True,
        'proto': True,
        'psk': quoted,
        'psk_list': True,
        'scan_freq': True,
        'scan_ssid': True,
        'sim_num': True,
        'ssid': quoted,
        'subject_match': True,
        'subject_match2': True,
        'vht': True,
        'vht_center_freq1': True,
        'vht_center_freq2': True,
        'wep_key0': True,
        'wep_key1': True,
        'wep_key2': True,
        'wep_key3': True,
        'wep_tx_keyidx': True,
        'wpa_ptk_rekey': True,
        'wps_disabled': True
    }


    def __init__(self, sock_dir='/run/wpa_supplicant'):
        self.threads = {}
        self.sock_dir = sock_dir
        self.signals = blinker.Namespace()


    def on(self, event, sender=blinker.ANY):
        def decorator(f):
            s = self.signals.signal(event)
            s.connect(f, sender=sender)
            return f
        return decorator


    def _ifname2remote(self, ifname):
        return '%s/%s' % (self.sock_dir, ifname)


    def start_event_thread(self, ifname):
        log.debug('Starting event reader thread [%s]' % ifname)
        signal = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        t = threading.Thread(target=self._thread_main, args=(ifname, signal[0]))
        t.start()
        self.threads[ifname] = {
            'thread': t,
            'signal': signal[1]
        }


    def stop_event_thread(self, ifname):
        log.debug('Stopping event reader thread [%s]' % ifname)
        t = self.threads[ifname]
        t['signal'].send(b'S')
        t['thread'].join()
        t['signal'].close()
        del self.threads[ifname]


    def start(self, ifname):
        log.debug('Starting wpa_supplicant controller [%s]' % ifname)
        self.ifname = ifname

        self.remote = self._ifname2remote(ifname)

        self.sock = WPARequestSock()
        self.sock.connect(self.remote)

        self.start_event_thread(ifname)


    def stop(self):
        log.debug('Stopping wpa_supplicant controller [%s]' % self.ifname)
        for ifname in list(self.threads.keys()):
            self.stop_event_thread(ifname)

        self.sock.close()
        del self.sock

        del self.ifname
        del self.remote


    @cached_property_with_ttl(ttl=5)
    def uuid(self):
        return self.status()['uuid']


    @cached_property_with_ttl(ttl=5)
    def address(self):
        return self.status()['address']


    def request(self, data, timeout=10):
        return self.sock.request(data, self.remote, timeout=timeout).strip()


    def request_check(self, data, timeout=10, response=None):
        rv = self.request(data, timeout=timeout)
        if rv != response:
            raise WPAError(rv)


    def request_ok(self, data, timeout=10):
        return self.request_check(data, timeout=timeout, response='OK')


    def _thread_main(self, ifname, signal):
        try:
            while True:
                try:
                    try:
                        self._event_loop(ifname, signal)
                    except Exception:
                        logging.exception('Error in event receiver')

                    wait(2, signal)
                except SystemExit:
                        break
        finally:
            signal.close()


    def _event_loop(self, ifname, signal):
        sock = WPAEventSock(signal=signal)

        remote = self._ifname2remote(ifname)
        sock.connect(remote)
        try:
            sock.attach(remote, timeout=5)
            try:
                while True:
                    data = sock.rx()[0]
                    try:
                        self._on_event(data, ifname)
                    except WPAError:
                        # Log and ignore event processing errors
                        logging.exception('Error while processing event')
            finally:
                # Detach the socket, but if the operation generates an error,
                # ignore it. There is nothing else we can do anyway.
                try:
                    sock.detach(timeout=3)
                except Exception:
                    logging.exception('Detach failed')
        finally:
            try:
                sock.disconnect()
            except Exception:
                pass


    def _on_event(self, data, ifname):
        data = data.strip()
        priority = None
        if data[0] == '<':
            e = data.find('>')
            if e == -1:
                raise WPAParseError('Malformed event priority: %s' % data)
            priority = int(data[1:e])
            data = data[e+1:].lstrip()

        e = data.find(' ')
        if e == -1:
            event = data
            data = ''
        else:
            event = data[:e]
            data = data[e+1:]

        s = self.signals.signal(event)
        try:
            s.send(ifname, priority=priority, event=event, data=data, sup=self)
        except Exception:
            logging.exception('Error in event handler')


    def ping(self):
        '''Test whether wpa_supplicant is replying to the control interface commands.
        '''
        self.request_check('PING', response='PONG')


    def save_config(self):
        '''Save the current configuration.
        '''
        self.request_ok('SAVE_CONFIG')


    def status(self):
        '''Request current WPA/EAPOL/EAP status information.
        '''
        return parse_dict(self.request('STATUS'))


    def mib(self):
        '''Request a list of MIB variables (dot1x, dot11).

        The output is a text block with each line in variable=value format.
        '''
        return parse_dict(self.request('MIB'))


    def reassociate(self):
        '''Force reassociation.
        '''
        self.request_ok('REASSOCIATE')


    def reconnect(self):
        '''Connect if disconnected.

        Like REASSOCIATE, but only connect if in disconnected state.
        '''
        self.request_ok('RECONNECT')


    def disconnect(self):
        '''Disconnect and wait for REASSOCIATE or RECONNECT command before connecting.
        '''
        self.request_ok('DISCONNECT')


    def reconfigure(self):
        '''Force wpa_supplicant to re-read its configuration data.
        '''
        self.request_ok('RECONFIGURE')


    def scan(self):
        '''Request a new BSS scan.
        '''
        self.request_ok('SCAN')


    def scan_results(self):
        '''Get the latest scan results.
        '''
        return parse_table(self.request('SCAN_RESULTS'))


    def bss(self, bssid):
        '''Get detailed per-BSS scan results.

        BSS command can be used to iterate through scan results one BSS at a
        time and to fetch all information from the found BSSes. This provides
        access to the same data that is available through SCAN_RESULTS but in
        a way that avoids problems with large number of scan results not
        fitting in the ctrl_iface messages.

        There are two options for selecting the BSS with the BSS command: "BSS
        <idx>" requests information for the BSS identified by the index (0 ..
        size-1) in the scan results table and "BSS <BSSID>" requests
        information for the given BSS (based on BSSID in 00:01:02:03:04:05
        format).
        '''
        data = self.request('BSS %s' % bssid)
        if len(data) == 0:
            return None
        if data.startswith('Invalid BSS command'):
            raise WPAError(data)
        return parse_dict(data)


    def list_networks(self):
        '''List configured networks.
        '''
        return parse_table(self.request('LIST_NETWORKS'))


    def select_network(self, id):
        '''Select a network (disable others).

        Network id can be received from the LIST_NETWORKS command output.
        '''
        self.request_ok('SELECT_NETWORK %s' % id)


    def enable_network(self, id='all'):
        '''Enable a network.

        Network id can be received from the LIST_NETWORKS command output.
        Special network id all can be used to enable all network.
        '''
        self.request_ok('ENABLE_NETWORK %s' % id)


    def disable_network(self, id='all'):

        '''Disable a network.

        Network id can be received from the LIST_NETWORKS command output.
        Special network id all can be used to disable all network.
        '''
        self.request_ok('DISABLE_NETWORK %s' % id)


    def add_network(self):
        '''Add a new network.

        This command creates a new network with empty configuration. The new
        network is disabled and once it has been configured it can be enabled
        with ENABLE_NETWORK command. ADD_NETWORK returns the network id of the
        new network.
        '''
        id = self.request('ADD_NETWORK')
        if id == 'FAIL':
            raise WPAError(id)
        return id


    def remove_network(self, id='all'):
        '''Remove a network.

        Network id can be received from the LIST_NETWORKS command output.
        Special network id all can be used to remove all network.
        '''
        self.request_ok('REMOVE_NETWORK %s' % id)


    def set_network(self, id, key, value):
        '''Set network variables.

        Network id can be received from the LIST_NETWORKS command output.
        This command uses the same variables and data formats as the configuration
        file. See example wpa_supplicant.conf for more details.
        '''
        f = self.NET_PARAMS.get(key, None)
        if f is None:
            raise WPAError('Unsupported parameter %s' % key)

        if f is not True:
            value = f(value)

        self.request_ok('SET_NETWORK %s %s %s' % (id, key, value))


    def get_network(self, id, key):
        '''Get network variables.

        Network id can be received from the LIST_NETWORKS command output.
        '''
        v = self.request('GET_NETWORK %s %s' % (id, key))
        if v == "FAIL":
            raise WPAError(v)
        return v[1:-1]


    def create_network(self, config):
        id = self.add_network()
        try:
            for k, v in config.items():
                self.set_network(id, k, v)
        except:
            self.remove_network(id)
            raise
        else:
            return id


    def interfaces(self):
        return self.request('INTERFACES').splitlines()[::-1]


    @contextmanager
    def interface(self, ifname, sock_dir=None):
        old_ifname   = self.ifname
        old_sock_dir = self.sock_dir
        old_remote   = self.remote

        self.ifname = ifname
        if sock_dir is not None:
            self.sock_dir = sock_dir
        self.remote = self._ifname2remote(self.ifname)
        self.sock.connect(self.remote)

        yield

        self.remote   = old_remote
        self.sock.connect(self.remote)
        self.sock_dir = old_sock_dir
        self.ifname   = old_ifname


    def set(self, key, value):
        self.request_ok('SET %s %s' % (key, str(value)))


    def dump(self):
        return parse_dict(self.request('DUMP'))


    def sta(self, addr=None):
        if addr is None:
            cmd = 'STA-FIRST'
        elif addr.startswith('NEXT '):
            cmd = 'STA-%s' % addr
        else:
            cmd = 'STA % addr'

        rv = self.request(cmd)
        if rv == '' or rv == 'FAIL':
            return None, {}
        eol = rv.find('\n')
        if eol == -1:
            raise WPAParseError('Invalid response for STA')
        addr = rv[:eol].strip()
        return addr, parse_dict(rv[eol:].strip())


    def all_sta(self):
        addr, data = self.sta()
        while addr is not None:
            yield addr, data
            addr, data = self.sta('NEXT %s' % addr)


class WPSWPASupplicant(WPASupplicant):
    def wps_pbc(self):
        '''Activate the WPS Push Button Mode.

        Note that this command must be run on the correct interface, e.g., on
        p2p-iface-x in case of Wi-Fi P2P.
        '''
        self.request_ok('WPS_PBC')


    def wps_pin(self, pin, addr='any'):
        '''wps_pin <any|address> <PIN>

        Start WPS PIN method. This allows a single WPS Enrollee to connect to
        the AP/GO. This is used on the GO when a P2P client joins an existing
        group. The second parameter is the address of the Enrollee or a string
        "any" to allow any station to use the entered PIN (which will restrict
        the PIN for one-time-use). PIN is the Enrollee PIN read either from a
        label or display on the P2P Client/WPS Enrollee.
        '''
        self.request_check('WPS_PIN %s %s' % (addr, pin), response=pin)



class P2PWPASupplicant(WPSWPASupplicant):

    def start(self, ifname):
        super().start(ifname)

        for i in self.interfaces():
            if i.startswith('p2p-dev-'):
                self.p2p_remote = self._ifname2remote('p2p-dev-' + ifname)
                self.start_event_thread('p2p-dev-' + ifname)
                break


    def stop(self):
        super().stop()
        try:
            del self.p2p_remote
        except AttributeError:
            pass



    @cached_property_with_ttl(ttl=5)
    def p2p_device_address(self):
        return self.status()['p2p_device_address']


    def p2p_find(self, duration=None, search_type=None):
        '''Start P2P device discovery.

        Optional parameter can be used to specify the duration for the
        discovery in seconds (e.g., "P2P_FIND 5"). If the duration is not
        specified, discovery will be started for indefinite time, i.e., until
        it is terminated by P2P_STOP_FIND or P2P_CONNECT (to start group
        formation with a discovered peer).

        The default search type is to first run a full scan of all channels
        and then continue scanning only social channels (1, 6, 11). This
        behavior can be changed by specifying a different search type: social
        (e.g., "P2P_FIND 5 type=social") will skip the initial full scan and
        only search social channels; progressive (e.g., "P2P_FIND
        type=progressive") starts with a full scan and then searches
        progressively through all channels one channel at the time with the
        social channel scans. Progressive device discovery can be used to find
        new groups (and groups that were not found during the initial scan,
        e.g., due to the GO being asleep) over time without adding
        considerable extra delay for every Search state round.
        '''
        s = 'P2P_FIND'
        if duration is not None:
            s += ' %d' % duration
        if search_type is not None:
            s += ' type=%s' % search_type
        self.request_ok(s)


    def p2p_stop_find(self):
        '''Stop ongoing P2P device discovery or other operation (connect, listen mode).
        '''
        self.request_ok('P2P_STOP_FIND')


    def p2p_flush(self):
        self.request_ok('P2P_FLUSH')


    def p2p_peer(self, peer='FIRST'):
        rv = self.request('P2P_PEER %s' % peer)
        if rv == 'FAIL':
            return None, {}
        eol = rv.find('\n')
        if eol == -1:
            raise WPAParseError('Invalid response for P2P_PEER')
        addr = rv[:eol].strip()
        return addr, parse_dict(rv[eol:].strip())


    def p2p_peers(self):
        addr, data = self.p2p_peer()
        while addr is not None:
            yield addr, data
            addr, data = self.p2p_peer('NEXT-%s' % addr)


    def p2p_listen(self):
        '''Start Listen-only state.

        Optional parameter can be used to specify the duration for the Listen
        operation in seconds. This command may not be of that much use during
        normal operations and is mainly designed for testing. It can also be
        used to keep the device discoverable without having to maintain a
        group.
        '''
        self.request_ok('P2P_LISTEN')


    def p2p_group_remove(self, id):
        '''Terminate a P2P group.

        If a new virtual network interface was used for the group, it will
        also be removed. The network interface name of the group interface is
        used as a parameter for this command.
        '''
        self.request_ok('P2P_GROUP_REMOVE %s' % id)


    def p2p_group_add(self):
        '''Set up a P2P group owner manually.

        (i.e., without group owner negotiation with a specific peer). This is
        also known as autonomous GO. Optional persistent=<network id>=""> can
        be used to specify restart of a persistent group.
        '''
        self.request_ok('P2P_GROUP_ADD')


    def p2p_reject(self, addr):
        '''Reject connection attempt from a peer (specified with a device address).

        This is a mechanism to reject a pending GO Negotiation with a peer and
        request to automatically block any further connection or discovery of
        the peer.
        '''
        self.request_ok('P2P_REJECT %s' % addr)


    def p2p_invite(self, addr, group):
        '''Invite a peer to join a group or to (re)start a persistent group.
        '''
        self.request_ok('P2P_INVITE group=%s peer=%s' % (group, addr))


    def p2p_connect(self, addr, wps_method='12345670', pin_type='', persistent='', join='', go_intent='', freq='', auto='', ssid=''):
        '''Start P2P group formation with a discovered P2P peer.

        This includes optional group owner negotiation, group interface setup,
        provisioning, and establishing data connection.

        The <pbc|pin|PIN#> parameter specifies the WPS provisioning method.
        "pbc" string starts pushbutton method, "pin" string start PIN method
        using an automatically generated PIN (which will be returned as the
        command return code), PIN# means that a pre-selected PIN can be used
        (e.g., 12345670). [display|keypad] is used with PIN method to specify
        which PIN is used (display=dynamically generated random PIN from local
        display, keypad=PIN entered from peer display). "persistent" parameter
        can be used to request a persistent group to be formed. The
        "persistent=<network id>" alternative can be used to pre-populate
        SSID/passphrase configuration based on a previously used persistent
        group where this device was the GO. The previously used parameters
        will then be used if the local end becomes the GO in GO Negotiation
        (which can be forced with go_intent=15).

        "join" indicates that this is a command to join an existing group as a
        client. It skips the GO Negotiation part. This will send a Provision
        Discovery Request message to the target GO before associating for WPS
        provisioning.

        "auth" indicates that the WPS parameters are authorized for the peer
        device without actually starting GO Negotiation (i.e., the peer is
        expected to initiate GO Negotiation). This is mainly for testing
        purposes.

        "go_intent" can be used to override the default GO Intent for this GO
        Negotiation.

        "freq" can be used to set a forced operating channel (e.g., freq=2412
        to select 2.4 GHz channel 1).

        "provdisc" can be used to request a Provision Discovery exchange to be
        used prior to starting GO Negotiation as a workaround with some
        deployed P2P implementations that require this to allow the user to
        accept the connection.

        "auto" can be used to request wpa_supplicant to automatically figure
        out whether the peer device is operating as a GO and if so, use
        join-a-group operation rather than GO Negotiation.

        "ssid=<hexdump>" can be used to specify the Group SSID for join
        operations. This allows the P2P Client interface to filter scan
        results based on SSID to avoid selecting an incorrect BSS entry in
        case the same P2P Device or Interface address have been used in
        multiple groups recently.
        '''
        args = {
            'addr'      : addr,
            'wps_method': wps_method,
            'pin_type'  : pin_type,
            'persistent': 'persistent' if persistent is True else 'persistent=%s' % persistent if persistent else '',
            'join'      : 'join' if join is True else join,
            'go_intent' : 'go_intent=%d' % go_intent if go_intent != '' else '',
            'freq'      : 'freq=%d' % freq if freq != '' else '',
            'auto'      : 'auto' if auto is True else auto,
            'ssid'      : 'ssid=%s' % ssid if ssid != '' else ''
        }
        self.request_ok('P2P_CONNECT %(addr)s %(wps_method)s %(pin_type)s %(persistent)s %(join)s %(go_intent)s %(freq)s %(auto)s %(ssid)s' % args)


    def p2p_remove_client(self, addr):
        self.request_ok('P2P_REMOVE_CLIENT %s' % addr)


    def p2p_service_add(self, data):
        self.request_ok('P2P_SERVICE_ADD %s' % data)


    def p2p_service_del(self, data):
        self.request_ok('P2P_SERVICE_DEL %s' % data)


    def p2p_service_flush(self):
        self.request_ok('P2P_SERVICE_FLUSH')


    def p2p_service_update(self):
        self.request_ok('P2P_SERVICE_UPDATE')


    def p2p_serv_disc_req(self, query, addr='00:00:00:00:00:00'):
        id = self.request('P2P_SERV_DISC_REQ %s %s' % (addr, query))
        if id == 'FAIL':
            raise WPAError(id)
        return id


    def p2p_serv_disc_cancel_req(self, id):
        self.request_ok('P2P_SERV_DISC_CANCEL_REQ %s' % id)
