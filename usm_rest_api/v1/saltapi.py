import socket
import paramiko
import logging
import re

import salt
from salt import wheel

_SETUP_MINION = ('mv -f /etc/salt/minion /etc/salt/minion.usm-add-node && '
                 'echo "master: %s" > /etc/salt/minion && '
                 'service salt-minion restart' % socket.getfqdn())

paramiko.util.get_logger('paramiko').setLevel(logging.ERROR)

opts = salt.config.master_config('/etc/salt/master')
master = salt.wheel.WheelClient(opts)


def get_fingerprint(key):
    s = paramiko.util.hexlify(key.get_fingerprint())
    fingerprint = ':'.join(re.findall('..', s))
    return fingerprint


def get_host_ssh_key(host, port=22):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))

    try:
        trans = paramiko.Transport(sock)
        trans.start_client()
        key = trans.get_remote_server_key()
    except paramiko.SSHException:
        sock.close()
        raise

    trans.close()
    sock.close()
    return key


class HostKeyMismatchError(paramiko.SSHException):
    def __init__(self, hostname, fingerprint, expected_fingerprint):
        self.err = 'Fingerprint %s of host %s does not match with %s' % \
            (fingerprint, hostname, expected_fingerprint)
        paramiko.SSHException.__init__(self, self.err)
        self.hostname = hostname
        self.fingerprint = fingerprint
        self.expected_fingerprint = expected_fingerprint


class HostKeyMatchPolicy(paramiko.AutoAddPolicy):
    def __init__(self, expected_fingerprint):
        self.expected_fingerprint = expected_fingerprint

    def missing_host_key(self, client, hostname, key):
        s = paramiko.util.hexlify(key.get_fingerprint())
        fingerprint = ':'.join(re.findall('..', s))
        if fingerprint.upper() == self.expected_fingerprint.upper():
            paramiko.AutoAddPolicy.missing_host_key(self, client, hostname,
                                                    key)
        else:
            raise HostKeyMismatchError(hostname, fingerprint,
                                       self.expected_fingerprint)


def setup_minion(host, fingerprint, username, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(HostKeyMatchPolicy(fingerprint))
    client.connect(host, username=username, password=password)

    session = client.get_transport().open_session()
    session.exec_command(_SETUP_MINION)
    stdin = session.makefile('wb')
    stdout = session.makefile('rb')
    stderr = session.makefile_stderr('rb')
    stdin.close()
    session.shutdown_write()
    rc = session.recv_exit_status()
    out = stdout.read()
    err = stderr.read()
    session.close()
    client.close()

    return (rc, out, err)


class UnknownMinion(Exception):
    def __init__(self, minion, minion_id):
        self.minion = minion
        self.minion_id = minion_id

    def __str__(self):
        return "unknown minion: %s, id=%s" % (self.minion, self.minion_id)


def accept_minion(minion):
    minion_id = socket.gethostbyaddr(minion)[0]

    keys = master.cmd('key.list_all')
    if minion_id not in keys['minions_pre']:
        raise UnknownMinion(minion, minion_id)

    return master.cmd('key.accept', match=minion_id)


def get_minions():
    keys = master.cmd('key.list_all')
    return keys['minions']
