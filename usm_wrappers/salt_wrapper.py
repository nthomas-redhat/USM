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
        for id, res in v:
            if not res['result']:
                failed_results.update({id: res})
        else:
            failed_minions[minion] = {}
        if failed_results:
            failed_minions[minion] = failed_results

    return failed_minions


def run_state(local, tgt, state, *args, **kwargs):
    out = local.cmd(tgt, 'state.sls', [state], *args, **kwargs)
    return _get_state_result(out)


def get_minions():
    keys = master.call_func('key.list_all')
    return keys['minions'], keys['minions_pre']


def setup_minion(host, fingerprint, username, password):
    t = Template(open('setup-minion.sh.template').read())
    cmd = t.render(usm_master=socket.getfqdn())
    utils.rexecCmd(cmd, host, fingerprint=fingerprint,
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

    minions_set = set(minions)
    failed_minions = minions_set - set(out)
    for k, v in out.iteritems():
        if not v:
            failed_minions.add(k)
    success_minions = minions_set - failed_minions

    return success_minions, failed_minions


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

_CEPH_CLUSTER_CONF_DIR = '/srv/salt/usm/conf/ceph'

_ceph_authtool = utils.CommandPath("ceph-authtool",
                                   "/usr/bin/ceph-authtool",)

_monmaptool = utils.CommandPath("monmaptool",
                                "/usr/bin/monmaptool",)


def _gen_ceph_cluster_conf(cluster_name, fsid, monitors, cluster_dir,
                           osd_journal_size = 1024,
                           osd_pool_default_size = 2,
                           osd_pool_default_min_size = 1,
                           osd_pool_default_pg_num = 333,
                           osd_pool_default_pgp_num = 333,
                           osd_crush_chooseleaf_type = 1):
    def _get_subnet(ip_address, subnets):
        ip = IPAddress(ip_address)
        for subnet in subnets:
            if ip in IPNetwork(subnet):
                return subnet
        return ''

    conf_file = cluster_dir + '/' + cluster_name + '.conf'

    mon_initial_members = []
    mon_host = []
    public_network = []
    cluster_network = []

    out = local.cmd(monitors, 'network.subnets', expr_form='list')

    for m,v in monitors.iteritems():
        mon_initial_members.append(v.get('monitor_name',
                                         utils.get_short_hostname(m)))
        mon_host.append(v['public_ip'])
        public_network.append(_get_subnet(v['public_ip'], out.get(m, [])))
        cluster_network.append(_get_subnet(v['cluster_ip'], out.get(m, [])))

    config = ConfigParser.RawConfigParser()
    config.add_section('global')
    config.set('global', 'fsid', fsid)
    config.set('global', 'mon initial members', ', '.join(mon_initial_members))
    config.set('global', 'mon host', ', '.join(mon_host))
    config.set('global', 'public network', ', '.join(public_network))
    config.set('global', 'cluster network', ', '.join(cluster_network))
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

    with open(conf_file, 'wb') as f:
        config.write(f)

    return mon_initial_members, mon_host, public_network, cluster_network


def _gen_keys(cluster_name, mon_initial_members, mon_host, fsid, cluster_dir):
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
    for i in range(0, len(mon_initial_members)):
        cmd += ['--add', mon_initial_members[i], mon_host[i]]
    cmd += ['--fsid', fsid, mon_map_path]
    utils.execCmd(cmd)

    return mon_key_path, admin_key_path, mon_map_path


def setup_ceph_cluster(cluster_name, fsid, monitors):
    '''
    :: cluster_name = STRING
    :: fsid = UUID
    :: monitors = {MINION_ID: {'public_ip': IP_ADDRESS,
                               'cluster_ip': IP_ADDRESS,
                               'monitor_name': NAME}, ...}
    '''
    cluster_dir = _CEPH_CLUSTER_CONF_DIR + '/' + cluster_name
    if not os.path.exists(cluster_dir):
        os.makedirs(cluster_dir)

    rv = _gen_ceph_cluster_conf(cluster_name, fsid, monitors, cluster_dir)

    mon_initial_members = rv[0]
    mon_host = rv[1]

    _gen_keys(cluster_name, mon_initial_members, mon_host, fsid, cluster_dir)

    cluster_info = dict(zip(monitors, mon_initial_members))
    cluster_info.update({'cluster_name': cluster_name})
    pillar = {'usm': cluster_info}

    return run_state(local, monitors, 'setup_ceph_cluster', expr_form='list',
                     kwarg={'pillar': pillar})


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
