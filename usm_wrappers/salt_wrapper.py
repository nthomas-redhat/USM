import socket
from jinja2 import Template
import salt
from salt import wheel, client

import utils


opts = salt.config.master_config('/etc/salt/master')
master = salt.wheel.WheelClient(opts)
local = salt.client.LocalClient()


def _get_state_result(out):
    failed_minions = {}
    for minion, v in out.iteritems():
        failed_results = {}
        for id, res in v.iteritems():
            if not res['result']:
                failed_results.update({id: res})
        if not v:
            failed_minions[minion] = {}
        if failed_results:
            failed_minions[minion] = failed_results

    return failed_minions


def run_state(local, tgt, state, *args, **kwargs):
    out = local.cmd(tgt, 'state.sls', [state], *args, **kwargs)
    return _get_state_result(out)


def pull_minion_file(local, minion, minion_path, path):
    out = local.cmd(minion, 'file.grep', [minion_path, '.'])

    result = out.get(minion, {})
    if result and result['retcode'] == 0:
        with open(path, 'wb') as f:
            f.write(result['stdout'])
        return True
    else:
        return False


def get_minions():
    keys = master.call_func('key.list_all')
    return keys['minions'], keys['minions_pre']


def setup_minion(host, fingerprint, username, password):
    t = Template(open('setup-minion.sh.template').read())
    cmd = t.render(usm_master=socket.getfqdn())
    utils.rexecCmd(str(cmd), host, fingerprint=fingerprint,
                   username=username, password=password)
    return utils.resolve_ip_address(host)


def accept_minion(minion_id):
    out = master.call_func('key.accept', match=minion_id)
    return (True if out else False)


def get_machine_id(minion_id):
    out = local.cmd(minion_id, 'grains.item', ['machine_id'])
    return out.get(minion_id, {}).get('machine_id')


def setup_cluster_grains(minions, cluster_info):
    grains = {}
    for k, v in cluster_info.iteritems():
        grains['usm_' + k] = v

    out = local.cmd(minions, 'grains.setvals', [grains],
                    expr_form='list')

    failed_minions = set(minions) - set(out)
    return set([k for k, v in out.iteritems() if not v]).union(failed_minions)


def peer(gluster_node, new_node):
    gluster_minion = utils.resolve_ip_address(gluster_node)
    new_minion = utils.resolve_ip_address(new_node)
    out = local.cmd(gluster_minion, 'glusterfs.peer', [new_minion])
    if out and 'success' in out[gluster_minion]:
        return True
    else:
        return False


import ConfigParser
from netaddr import IPNetwork, IPAddress
import os
import string

_CEPH_CLUSTER_CONF_DIR = '/srv/salt/usm/conf/ceph'
_MON_ID_LIST = list(string.ascii_lowercase)

_ceph_authtool = utils.CommandPath("ceph-authtool",
                                   "/usr/bin/ceph-authtool",)

_monmaptool = utils.CommandPath("monmaptool",
                                "/usr/bin/monmaptool",)


def _gen_ceph_cluster_conf(cluster_name, fsid, monitors,
                           public_network,
                           cluster_network,
                           cluster_dir,
                           osd_journal_size = 1024,
                           osd_pool_default_size = 2,
                           osd_pool_default_min_size = 1,
                           osd_pool_default_pg_num = 333,
                           osd_pool_default_pgp_num = 333,
                           osd_crush_chooseleaf_type = 1):
    '''
    :: monitors = {ID: {'name': SHORT_HOSTNAME, 'address': IP_ADDR,
                        'port': INT}, ...}
    '''

    conf_file = cluster_dir + '/' + cluster_name + '.conf'
    config = ConfigParser.RawConfigParser()

    config.add_section('global')
    config.set('global', 'fsid', fsid)
    config.set('global', 'public network', public_network)
    config.set('global', 'cluster network', cluster_network)
    config.set('global', 'auth cluster required', 'cephx')
    config.set('global', 'auth service required', 'cephx')
    config.set('global', 'auth client required', 'cephx')
    config.set('global', 'osd journal size', osd_journal_size)
    config.set('global', 'filestore xattr use omap', 'true')
    config.set('global', 'osd pool default size', osd_pool_default_size)
    config.set('global', 'osd pool default min size',
               osd_pool_default_min_size)
    config.set('global', 'osd pool default pg num', osd_pool_default_pg_num)
    config.set('global', 'osd pool default pgp num', osd_pool_default_pgp_num)
    config.set('global', 'osd crush chooseleaf type',
               osd_crush_chooseleaf_type)

    config.add_section('mon')
    config.set('mon', 'mon initial members', ', '.join(monitors))

    for m, v in monitors.iteritems():
        section = 'mon.' + m
        config.add_section(section)
        config.set(section, 'host', v['name'])
        config.set(section, 'mon addr',
                   '%s:%s' % (v['address'], v.get('port', 6789)))

    with open(conf_file, 'wb') as f:
        config.write(f)

    return True


def _gen_keys(cluster_name, fsid, monitors, cluster_dir):
    '''
    :: monitors = {ID: {'name': SHORT_HOSTNAME, 'address': IP_ADDR,
                        'port': INT}, ...}
    '''
    mon_key_path = cluster_dir + '/mon.key'
    admin_key_path = cluster_dir + '/client.admin.keyring'
    mon_map_path = cluster_dir + '/mon.map'

    utils.execCmd([_ceph_authtool.cmd, '--create-keyring', mon_key_path,
                   '--gen-key', '-n', 'mon.', '--cap', 'mon', 'allow *'])

    utils.execCmd([_ceph_authtool.cmd, '--create-keyring', admin_key_path,
                   '--gen-key', '-n', 'client.admin', '--set-uid=0', '--cap',
                   'mon', 'allow *', '--cap', 'osd', 'allow *', '--cap',
                   'mds', 'allow'])

    utils.execCmd([_ceph_authtool.cmd, mon_key_path, '--import-keyring',
                   admin_key_path])

    cmd = [_monmaptool.cmd, '--create', '--clobber']
    for m, v in monitors.iteritems():
        cmd += ['--add', 'mon.' + m, v['address']]
    cmd += ['--fsid', fsid, mon_map_path]
    utils.execCmd(cmd)

    return True


def setup_ceph_cluster(cluster_name, fsid, minions):
    '''
    :: cluster_name = STRING
    :: fsid = UUID
    :: minions = {MINION_ID: {'public_ip': IP_ADDRESS,
                              'cluster_ip': IP_ADDRESS,
                              'monitor_name': NAME}, ...}
    '''
    cluster_dir = _CEPH_CLUSTER_CONF_DIR + '/' + cluster_name
    cluster_key_file = cluster_name + '.keyring'
    bootstrap_osd_key_file = '/var/lib/ceph/bootstrap-osd/' + cluster_key_file
    cluster_key_path = cluster_dir + '/' + cluster_key_file

    public_network = None
    cluster_network = None

    if not os.path.exists(cluster_dir):
        os.makedirs(cluster_dir)

    out = local.cmd(minions, 'network.subnets', expr_form='list')

    for m,v in minions.iteritems():
        if not out[m]:
            raise ValueError('%s: failed to get subnet' % m)

        public_ip = IPAddress(v['public_ip'])
        cluster_ip = IPAddress(v['cluster_ip'])

        for subnet in out[m]:
            network = IPNetwork(subnet)
            if public_ip in network:
                if public_network and public_network != subnet:
                    raise KeyError(
                        'minion %s:%s is in different public network %s' % (
                            m, public_ip, subnet))
                else:
                    public_network = subnet

            if cluster_ip in network:
                if cluster_network and cluster_network != subnet:
                    raise KeyError(
                        'minion %s:%s is in different cluster network %s' % (
                            m, cluster_ip, subnet))
                else:
                    cluster_network = subnet

    mon_id_map = dict(zip(_MON_ID_LIST, minions))
    monitors = {}
    for id, minion in mon_id_map.iteritems():
        monitors[id] = {
            'name': minions[minion].get('monitor_name',
                                        utils.get_short_hostname(minion)),
            'address': minions[minion]['public_ip']
        }

    _gen_ceph_cluster_conf(cluster_name, fsid, monitors, public_network,
                           cluster_network, cluster_dir)
    _gen_keys(cluster_name, fsid, monitors, cluster_dir)

    d = {}
    for id, minion in mon_id_map.iteritems():
        d[minion] = {'cluster_name': cluster_name, 'mon_id': id,
                     'mon_name': monitors[id]['name']}
    pillar = {'usm': d}

    out = run_state(local, minions, 'setup_ceph_cluster', expr_form='list',
                    kwarg={'pillar': pillar})
    if out:
        return out

    out = {}
    for minion in minions:
        if pull_minion_file(local, minion, bootstrap_osd_key_file,
                            cluster_key_path):
            return {}
        else:
            out[minion] = {}

    return out


def start_ceph_mon(cluster_name = None, monitors = []):
    if cluster_name:
        tgt = 'G@usm_cluster_name:%s and G@usm_node_type:mon' % (cluster_name)
        expr_form = 'compound'
    elif monitors:
        tgt = monitors
        expr_form = 'list'
    else:
        return

    return run_state(local, tgt, 'start_ceph_mon', expr_form=expr_form)


def add_ceph_osd(osds):
    '''
    :: osds = {MINION_ID: {DEVICE: FSTYPE, ...}, ...}

    '''

    pillar = {'usm': osds}
    return run_state(local, osds, 'add_ceph_osd', expr_form='list',
                     kwarg={'pillar': pillar})
