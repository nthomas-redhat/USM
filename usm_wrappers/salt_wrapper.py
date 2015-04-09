import socket
from jinja2 import Template
from netaddr import IPNetwork, IPAddress
import time
import fnmatch
import salt
from salt import wheel, client
import salt.config
import salt.utils.event
import salt.runner

import utils


opts = salt.config.master_config('/etc/salt/master')
master = salt.wheel.WheelClient(opts)
local = salt.client.LocalClient()
sevent = salt.utils.event.get_event('master',
                                    sock_dir=opts['sock_dir'],
                                    transport=opts['transport'],
                                    opts=opts)
runner = salt.runner.RunnerClient(opts)
DEFAULT_WAIT_TIME = 5


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
            f.write('\n')
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


def get_started_minions(minions=[], timeout=60):
    def _get_up_minions():
        up_minions = set(runner.cmd('manage.up', []))
        if minion_set:
            return up_minions.intersection(minion_set)
        else:
            return up_minions

    minion_set = set(minions)
    started_minions = _get_up_minions()

    time_spent = 0
    while timeout > 0:
        if minion_set and started_minions == minion_set:
            break

        wait = timeout - time_spent
        if wait <= 0:
            break
        if wait > DEFAULT_WAIT_TIME:
            wait = DEFAULT_WAIT_TIME

        start_time = time.time()
        ret = sevent.get_event(wait=wait, full=True, tag='salt/minion')
        end_time = time.time()

        time_spent += (end_time - start_time)

        if ret is None:
            started_minions = _get_up_minions()
        elif fnmatch.fnmatch(ret['tag'], 'salt/minion/*/start'):
            minion = ret['data']['id']
            if minion_set and minion not in minion_set:
                continue
            started_minions.add(minion)

    return started_minions


def get_machine_id(minion_id):
    out = local.cmd(minion_id, 'grains.item', ['machine_id'])
    return out.get(minion_id, {}).get('machine_id')


def get_minion_network_info(minions):
    out = local.cmd(minions, ['grains.item', 'network.subnets'],
                    [['ipv4', 'ipv6'], []], expr_form='list')
    netinfo = {}
    for minion in minions:
        info = out.get(minion)
        if info:
            netinfo[minion] = {'ipv4': info['grains.item']['ipv4'],
                               'ipv6': info['grains.item']['ipv6'],
                               'subnet': info['network.subnets']}
        else:
            netinfo[minion] = {'ipv4': [], 'ipv6': [], 'subnet': []}

    return netinfo


def setup_cluster_grains(minions, cluster_info):
    grains = {}
    for k, v in cluster_info.iteritems():
        grains['usm_' + k] = v

    out = local.cmd(minions, 'grains.setvals', [grains],
                    expr_form='list')

    failed_minions = set(minions) - set(out)
    return set([k for k, v in out.iteritems() if not v]).union(failed_minions)


def check_minion_networks(minions, public_network=None, cluster_network=None,
                          check_cluster_network=False):
    '''
    :: minions = {MINION_ID: {'public_ip': IP_ADDRESS,
                              'cluster_ip': IP_ADDRESS}, ...}
    '''

    def _get_ip_network(ip, subnets):
        for subnet in subnets:
            network = IPNetwork(subnet)
            if ip in network:
                return network

    def _check_ip_network(minion, ip, ip_list, network, subnets,
                          label='public'):
        if ip not in ip_list:
            raise ValueError('%s ip %s not found in minion %s' %
                             (label, ip, minion))
        ip = IPAddress(ip)
        if not network:
            network = _get_ip_network(ip, subnets)
        if network and ip not in network:
            raise ValueError('minion %s %s ip %s not in network %s' %
                             (m, ip, label, network))
        return network

    netinfo = get_minion_network_info(minions)
    for m,v in minions.iteritems():
        public_network = _check_ip_network(m, v['public_ip'],
                                           netinfo[m]['ipv4'],
                                           public_network,
                                           netinfo[m]['subnet'])
        if not check_cluster_network:
            continue
        cluster_network = _check_ip_network(m, v['cluster_ip'],
                                            netinfo[m]['ipv4'],
                                            cluster_network,
                                            netinfo[m]['subnet'])

    return public_network, cluster_network


def get_minion_disk_info(minions):
    '''
    This function returns disk/storage device info excluding their
    parent devices

    Output dictionary is
    {DEV_MAME: {'INUSE': BOOLEAN,
                'NAME': SHORT_NAME,
                'KNAME': DEV_NAME,
                'FSTYPE': FS_TYPE,
                'MOUNTPOINT': MOUNT_POINT,
                'UUID': FS_UUID,
                'PARTUUID': PART_UUID,
                'MODEL': MODEL_STRING,
                'SIZE': SIZE_BYTES,
                'TYPE': TYPE,
                'PKNAME', PARENT_DEV_NAME,
                'VENDOR': VENDOR_STRING}, ...}
    '''

    columes = 'NAME,KNAME,FSTYPE,MOUNTPOINT,UUID,PARTUUID,MODEL,SIZE,TYPE,' \
              'PKNAME,VENDOR'
    keys = columes.split(',')
    lsblk = ("lsblk --all --bytes --noheadings --output='%s' --path --raw" %
             columes)
    out = local.cmd(minions, 'cmd.run', [lsblk], expr_form='list')

    minion_dev_info = {}
    for minion in minions:
        lsblk_out = out.get(minion)

        if not lsblk_out:
            minion_dev_info[minion] = {}
            continue

        devlist = map(lambda line: dict(zip(keys, line.split(' '))),
                      lsblk_out.splitlines())

        parents = set([d['PKNAME'] for d in devlist])

        dev_info = {}
        for d in devlist:
            in_use = True

            if d['TYPE'] == 'disk':
                if d['KNAME'] in parents:
                    # skip it
                    continue
                else:
                    in_use = False
            elif not d['FSTYPE']:
                in_use = False

            d.update({'INUSE': in_use})
            dev_info.update({d['KNAME']: d})

        minion_dev_info[minion] = dev_info

    return minion_dev_info


def peer(gluster_node, new_node):
    gluster_minion = utils.resolve_ip_address(gluster_node)
    new_minion = utils.resolve_ip_address(new_node)
    out = local.cmd(gluster_minion, 'glusterfs.peer', [new_minion])
    if out and out[gluster_minion] == True:
        return True
    else:
        return False


def create_gluster_volume(minion, name, bricks, stripe=0, replica=0,
                          transport=[], force=False):
    out = local.cmd(minion, 'glusterfs.create', [name, bricks, stripe, replica,
                                                 False, transport, force])
    volume_id = out.get(minion, {}).get('uuid')
    if volume_id:
        return volume_id
    else:
        False


def list_gluster_volumes(minion):
    out = local.cmd(minion, 'glusterfs.list_volumes')
    return out.get(minion)


def get_gluster_volume_status(minion, name):
    out = local.cmd(minion, 'glusterfs.status', [name])
    return out.get(minion)


def start_gluster_volume(minion, name):
    out = local.cmd(minion, 'glusterfs.start_volume', [name])
    if out and out[minion] == True:
        return True
    else:
        return False


def stop_gluster_volume(minion, name):
    out = local.cmd(minion, 'glusterfs.stop_volume', [name])
    if out and out[minion] == True:
        return True
    else:
        return False


def delete_gluster_volume(minion, name):
    out = local.cmd(minion, 'glusterfs.delete', [name])
    if out and out[minion] == True:
        return True
    else:
        return False


import ConfigParser
import os
import string

_CEPH_CLUSTER_CONF_DIR = '/srv/salt/usm/conf/ceph'
_MON_ID_LIST = list(string.ascii_lowercase)
_DEFAULT_MON_PORT = 6789

_ceph_authtool = utils.CommandPath("ceph-authtool",
                                   "/usr/bin/ceph-authtool",)

_monmaptool = utils.CommandPath("monmaptool",
                                "/usr/bin/monmaptool",)


def sync_ceph_conf(cluster_name, minions):
    out = local.cmd(minions,
                    'state.single',
                    ['file.managed', '/etc/ceph/%s.conf' % cluster_name,
                     'source=salt://usm/conf/ceph/%s/%s.conf' % (
                         cluster_name, cluster_name),
                     'show_diff=False'], expr_form='list')
    return _get_state_result(out)


def _config_add_monitors(config, monitors):
    for m, v in monitors.iteritems():
        section = 'mon.' + m
        config.add_section(section)
        config.set(section, 'host', v['name'])
        config.set(section, 'mon addr',
                   '%s:%s' % (v['address'], v.get('port', _DEFAULT_MON_PORT)))


def _gen_ceph_cluster_conf(conf_file, cluster_name, fsid, monitors,
                           public_network,
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
    config = ConfigParser.RawConfigParser()

    config.add_section('global')
    config.set('global', 'fsid', fsid)
    config.set('global', 'public network', public_network)
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
    _config_add_monitors(config, monitors)

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


def _get_mon_id_map(unused_mon_ids, minions):
    mon_id_map = dict(zip(unused_mon_ids, minions))
    monitors = {}
    for id, minion in mon_id_map.iteritems():
        monitors[id] = {
            'name': minions[minion].get('monitor_name',
                                        utils.get_short_hostname(minion)),
            'address': minions[minion]['public_ip']
        }
    return mon_id_map, monitors


def _add_ceph_mon_pillar_data(mon_id_map, cluster_name, monitors):
    pillar_data = {}
    for id, minion in mon_id_map.iteritems():
        pillar_data[minion] = {'cluster_name': cluster_name, 'mon_id': id,
                               'mon_name': monitors[id]['name'],
                               'public_ip': monitors[id]['address']}
    return pillar_data


def setup_ceph_cluster(cluster_name, fsid, minions):
    '''
    :: cluster_name = STRING
    :: fsid = UUID
    :: minions = {MINION_ID: {'public_ip': IP_ADDRESS,
                              'cluster_ip': IP_ADDRESS,
                              'monitor_name': NAME}, ...}
    '''
    public_network, cluster_network = check_minion_networks(minions)
    mon_id_map, monitors = _get_mon_id_map(_MON_ID_LIST, minions)

    cluster_dir = _CEPH_CLUSTER_CONF_DIR + '/' + cluster_name
    if not os.path.exists(cluster_dir):
        os.makedirs(cluster_dir)

    conf_file = cluster_dir + '/' + cluster_name + '.conf'
    _gen_ceph_cluster_conf(conf_file, cluster_name, fsid, monitors,
                           public_network)

    _gen_keys(cluster_name, fsid, monitors, cluster_dir)

    pillar_data = _add_ceph_mon_pillar_data(mon_id_map, cluster_name, monitors)
    pillar = {'usm': pillar_data}

    bootstrapped_minion = None
    for id, minion in mon_id_map.iteritems():
        out = run_state(local, minion, 'add_ceph_mon',
                        kwarg={'pillar':
                               {'usm': {'mon_bootstrap': True,
                                        minion: pillar_data[minion]}}})
        if not out:
            bootstrapped_minion = minion
            break

    if not bootstrapped_minion:
        ## TODO: cleanup created dir/files
        print "bootstraped_minion is empty"
        return False

    cluster_key_file = cluster_name + '.keyring'
    bootstrap_osd_key_file = '/var/lib/ceph/bootstrap-osd/' + cluster_key_file
    cluster_key_path = cluster_dir + '/' + cluster_key_file

    if not pull_minion_file(local, bootstrapped_minion, bootstrap_osd_key_file,
                            cluster_key_path):
        print "pull_minion_file fails"
        ## mon failed to start
        return False

    minion_set = set(minions)
    minion_set.remove(bootstrapped_minion)
    if minion_set:
        rv = run_state(local, minion_set, 'add_ceph_mon', expr_form='list',
                       kwarg={'pillar': pillar})
        if rv:
            raise Exception('add_ceph_mon state failed somewhere')
    return True


def add_ceph_mon(cluster_name, minions):
    conf_file = (_CEPH_CLUSTER_CONF_DIR + '/' + cluster_name + '/' +
                 cluster_name + '.conf')
    config = ConfigParser.RawConfigParser()
    config.read(conf_file)

    public_network = IPNetwork(config.get('global', 'public network'))
    check_minion_networks(minions, public_network)

    used_mon_ids = set([id.strip() for id in config.get(
        'mon', 'mon initial members').split(',')])
    unused_mon_ids = list(set(_MON_ID_LIST) - used_mon_ids)
    unused_mon_ids.sort()

    mon_id_map, monitors = _get_mon_id_map(unused_mon_ids, minions)

    mon_initial_members = list(used_mon_ids) + list(monitors)
    mon_initial_members.sort()
    config.set('mon', 'mon initial members', ', '.join(mon_initial_members))

    _config_add_monitors(config, monitors)

    with open(conf_file, 'wb') as f:
        config.write(f)

    pillar_data = _add_ceph_mon_pillar_data(mon_id_map, cluster_name, monitors)
    pillar = {'usm': pillar_data}

    out = run_state(local, minions, 'add_ceph_mon', expr_form='list',
                    kwarg={'pillar': pillar})
    if out:
        return out

    return sync_ceph_conf(cluster_name, minions)


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


def add_ceph_osd(cluster_name, minions):
    '''
    :: minions = {MINION_ID: {'public_ip': IP_ADDRESS,
                              'cluster_ip': IP_ADDRESS,
                              'host_name': HOSTNAME,
                              'devices': {DEVICE: FSTYPE, ...}}, ...}

    '''
    conf_file = (_CEPH_CLUSTER_CONF_DIR + '/' + cluster_name + '/' +
                 cluster_name + '.conf')
    config = ConfigParser.RawConfigParser()
    config.read(conf_file)

    public_network = IPNetwork(config.get('global', 'public network'))
    if config.has_option('global', 'cluster network'):
        cluster_network = IPNetwork(config.get('global', 'cluster network'))
    else:
        cluster_network = None
    public_network, cluster_network = check_minion_networks(
        minions, public_network, cluster_network, check_cluster_network=True)

    pillar_data = {}
    for minion, v in minions.iteritems():
        pillar_data[minion] = {'cluster_name': cluster_name,
                               'cluster_id': config.get('global', 'fsid'),
                               'devices': v['devices']}
    pillar = {'usm': pillar_data}

    out = run_state(local, minions, 'prepare_ceph_osd', expr_form='list',
                    kwarg={'pillar': pillar})
    if out:
        return out

    out = local.cmd(minions, 'state.single',
                    ['cmd.run', 'ceph-disk activate-all'],
                    expr_form='list')

    osd_map = {}
    failed_minions = {}
    for minion, v in out.iteritems():
        osds = []
        failed_results = {}
        for id, res in v.iteritems():
            if not res['result']:
                failed_results.update({id: res})

            stdout = res['changes']['stdout']
            for line in stdout.splitlines():
                if line.startswith('=== '):
                    osds.append(line.split('=== ')[1].strip())
        osd_map[minion] = osds
        if not v:
            failed_minions[minion] = {}
        if failed_results:
            failed_minions[minion] = failed_results

    config.set('global', 'cluster network', cluster_network)
    for minion, osds in osd_map.iteritems():
        name = minions[minion].get('host_name',
                                   utils.get_short_hostname(minion))
        for osd in osds:
            config.add_section(osd)
            config.set(osd, 'host', name)
            config.set(osd, 'public addr', minions[minion]['public_ip'])
            config.set(osd, 'cluster addr', minions[minion]['cluster_ip'])

    with open(conf_file, 'wb') as f:
        config.write(f)

    sync_ceph_conf(cluster_name, minions)

    return failed_minions
