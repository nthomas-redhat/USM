import socket
import binascii
import paramiko
import logging
import re

paramiko.util.get_logger('paramiko').setLevel(logging.ERROR)


def resolve_hostname(hostname):
    return socket.gethostbyname_ex(hostname)[2]


def resolve_ip_address(ip_address):
    return socket.gethostbyaddr(ip_address)[0]


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

    s = binascii.hexlify(key.get_fingerprint())
    fingerprint = ':'.join(re.findall('..', s))

    return fingerprint, key


class SSHCmdExecFailed(Exception):
    message = "SSH command execution failed"

    def __init__(self, cmd, host, port, username, rc, out=(), err=()):
        self.cmd = cmd
        self.host = host
        self.port = port
        self.username = username
        self.rc = rc
        self.out = out
        self.err = err

    def __str__(self):
        s = ("%s\nhost: %s\nport: %s\nusername: %s\ncommand: %s\n"
             "exit code: %s\nstderr: %s\nstdout: %s\n")
        return s % (self.message, self.host, self.port, self.username,
                    self.cmd, self.rc, self.stderr, self.stdout)


class HostKeyMismatchError(paramiko.SSHException):
    def __init__(self, hostname, fingerprint, expected_fingerprint):
        self.err = 'fingerprint %s of host %s does not match with %s' % \
            (fingerprint, hostname, expected_fingerprint)
        paramiko.SSHException.__init__(self, self.err)
        self.hostname = hostname
        self.fingerprint = fingerprint
        self.expected_fingerprint = expected_fingerprint


class HostKeyMatchPolicy(paramiko.AutoAddPolicy):
    def __init__(self, expected_fingerprint):
        self.expected_fingerprint = expected_fingerprint

    def missing_host_key(self, client, hostname, key):
        s = binascii.hexlify(key.get_fingerprint())
        fingerprint = ':'.join(re.findall('..', s))
        if fingerprint.upper() == self.expected_fingerprint.upper():
            paramiko.AutoAddPolicy.missing_host_key(self, client, hostname,
                                                    key)
        else:
            raise HostKeyMismatchError(hostname, fingerprint,
                                       self.expected_fingerprint)


def rexecCmd(cmd, host, port=22, fingerprint=None, username=None,
             password=None, pkey=None, key_filenames=[], timeout=None,
             allow_agent=True, look_for_keys=True, compress=False,
             data=None, raw=True, throwException=True):
    client = paramiko.SSHClient()
    if fingerprint:
        client.set_missing_host_key_policy(HostKeyMatchPolicy(fingerprint))
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port, username, password, pkey, key_filenames,
                   timeout, allow_agent, look_for_keys, compress)
    session = client.get_transport().open_session()
    session.exec_command(cmd)

    stdin = session.makefile('wb')
    stdout = session.makefile('rb')
    stderr = session.makefile_stderr('rb')

    if data:
        stdin.write(data)
        stdin.flush()

    stdin.close()
    session.shutdown_write()
    rc = session.recv_exit_status()
    out = stdout.read()
    err = stderr.read()
    session.close()
    client.close()

    if rc and throwException:
        raise SSHCmdExecFailed(cmd, host, port, username, rc, out, err)

    if raw:
        return (rc, out, err)
    else:
        return (rc, out.splitlines(False), err.splitlines(False))
