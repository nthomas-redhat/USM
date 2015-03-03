import socket
from jinja2 import Template
import salt
from salt import wheel, client

import utils


opts = salt.config.master_config('/etc/salt/master')
master = salt.wheel.WheelClient(opts)
local = salt.client.LocalClient()


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


def setup_cluster_grains(minions, cluster_info, reload=True):
    out = local.cmd(minions, 'state.sls', ['setup_cluster_grains'],
                    expr_form='list',
                    kwarg={'pillar': {'usm': cluster_info}})

    success_minions = []
    failed_minions = []

    for minion in minions:
        result = out.get(minion, {}).values()
        if result and result[0]['result']:
            success_minions.append(minion)
        else:
            failed_minions.append(minion)

    if reload:
        out = local.cmd(success_minions, 'saltutil.sync_grains',
                        expr_form='list')
        success = out.keys()
        failed_minions.append(set(success_minions) - set(success))
        success_minions = success

    return success_minions, failed_minions


def peer(gluster_node, new_node):
    gluster_minion = utils.resolve_ip_address(gluster_node)
    new_minion = utils.resolve_ip_address(new_node)
    out = local.cmd(gluster_minion, 'glusterfs.peer', [new_minion])
    if out and 'success' in out[gluster_minion]:
        return True
    else:
        return False
