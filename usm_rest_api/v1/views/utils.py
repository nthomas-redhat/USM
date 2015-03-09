import random
import logging
import uuid
import time

from usm_rest_api.models import Cluster
from usm_rest_api.v1.serializers.serializers import ClusterSerializer
from usm_rest_api.models import Host
from usm_rest_api.v1.serializers.serializers import HostSerializer

from usm_wrappers import salt_wrapper
from usm_wrappers import utils as usm_wrapper_utils


log = logging.getLogger('django.request')


CLUSTER_TYPE_GLUSTER = 1
CLUSTER_TYPE_CEPH = 2
STORAGE_TYPE_BLOCK = 1
STORAGE_TYPE_FILE = 2
STORAGE_TYPE_OBJECT = 3
STATUS_INACTIVE = 1
STATUS_ACTIVE_NOT_AVAILABLE = 2
STATUS_ACTIVE_AND_AVAILABLE = 3
HOST_TYPE_MONITOR = 1
HOST_TYPE_OSD = 2
HOST_TYPE_MIXED = 3
HOST_TYPE_GLUSTER = 4
HOST_STATUS_INACTIVE = 1
HOST_STATUS_ACTIVE = 2


def peer(hostlist, newNode):
    rc = False
    if hostlist:
        host = random.choice(hostlist)

        rc = salt_wrapper.peer(host, newNode)
        if rc is True:
            return rc
        #
        # random host is not able to peer probe
        # Now try to iterate through the list of hosts
        # in the cluster to peer probe until
        # the peer probe is successful
        #

        # No need to send it to host which we already tried
        hostlist.remove(host)
        for host in hostlist:
            rc = salt_wrapper.peer(host, newNode)
            if rc is True:
                return rc
        return rc
    else:
        return True


def create_cluster(cluster_data):
    # create the cluster
    cluster_data['cluster_id'] = str(uuid.uuid4())
    try:
        clusterSerilaizer = ClusterSerializer(data=cluster_data)
        if clusterSerilaizer.is_valid():
            clusterSerilaizer.save()
        else:
                log.error(
                    "Cluster Creation failed. Invalid clusterSerilaizer")
                log.error(
                    "clusterSerilaizer Err: %s" % clusterSerilaizer.errors)
                raise Exception(
                    "Cluster Creation failed. Invalid clusterSerilaizer",
                    clusterSerilaizer.errors)
    except Exception, e:
        log.exception(e)
        raise e


def setup_transport_and_update_db(cluster_data, nodelist):
    log.debug("Inside setup_transport_and_update_db function")
    failedNodes = []

    # Create the Nodes in the cluster
    # Setup the host communication channel
    # current_task.update_state(state='ESTABLISH_HOST_COMMUNICATION')
    minionIds = {}
    for node in nodelist:
        try:
            ssh_fingerprint = usm_wrapper_utils.get_host_ssh_key(
                node['management_ip'])
            minionIds[node['management_ip']] = salt_wrapper.setup_minion(
                node['management_ip'], ssh_fingerprint[0],
                node['ssh_username'], node['ssh_password'])
        except Exception, e:
            log.exception(e)
            failedNodes.append(node)
    log.debug(minionIds)
    # Sleep for sometime to make sure all the restarted minions are back
    # online
    time.sleep(3)
    log.debug("Accepting the minions keys")
    # current_task.update_state(state='ADD_MINION_KEYS_AND_DB_UPDATE')

    # Accept the keys of the successful minions and add to the DB
    for node in nodelist:
        try:
            if node not in failedNodes:
                salt_wrapper.accept_minion(minionIds[node['management_ip']])
        except Exception, e:
            log.exception(e)
            failedNodes.append(node)
    log.debug(minionIds)
    #
    # Wait for some time so that the communication chanel is ready
    #
    time.sleep(15)

    # Persist the hosts into DB
    for node in nodelist:
        #
        # Get the host uuid from  host and update in DB
        #
        try:
            if node not in failedNodes:
                node['node_id'] = salt_wrapper.get_machine_id(
                    minionIds[node['management_ip']])
                node['cluster'] = str(cluster_data['cluster_id'])
                hostSerilaizer = HostSerializer(data=node)

                if hostSerilaizer.is_valid():
                    # Delete all the fields those are not
                    # reqired to be persisted
                    del hostSerilaizer.validated_data['ssh_password']
                    del hostSerilaizer.validated_data['ssh_key_fingerprint']
                    del hostSerilaizer.validated_data['ssh_username']
                    del hostSerilaizer.validated_data['ssh_port']

                    hostSerilaizer.save()
                else:
                    log.error("Host Creation failed. Invalid hostSerilaizer")
                    log.error("hostSerilaizer Err: %s" % hostSerilaizer.errors)
                    raise Exception("Add to DB Failed", hostSerilaizer.errors)
        except Exception, e:
            log.exception(e)
            failedNodes.append(node)

    # Push the cluster configuration to nodes
    log.debug("Push Cluster config to Nodes")
    # current_task.update_state(state='PUSH_CLUSTER_CONFIG')
    failed_minions = salt_wrapper.setup_cluster_grains(
        minionIds.values(), cluster_data)
    if failed_minions:
        log.debug('Config Push failed for minions %s' % failed_minions)
        # Add the failed minions to failed Nodes list
        for node in nodelist:
            if usm_wrapper_utils.resolve_ip_address(
                    node['management_ip']) in failed_minions:
                failedNodes.append(node)
    log.debug("failedNodes %s" % failedNodes)
    return minionIds, failedNodes


def update_host_status(nodes, status):
    for node in nodes:
        glusterNode = Host.objects.get(pk=str(node['node_id']))
        glusterNode.node_status = status
        glusterNode.save()


def update_cluster_status(cluster_id, status):
    cluster = Cluster.objects.get(pk=cluster_id)
    cluster.cluster_status = status
    cluster.save()


def create_ceph_cluster(nodelist, cluster_data, minionIds):
    # create the dictionary for cluster creation
    failedNodes = None
    minions = {}
    for node in nodelist:
        nodeInfo = {'public_ip': node['public_ip'],
                    'cluster_ip': node['cluster_ip']}
        minions[minionIds[node['management_ip']]] = nodeInfo
    log.debug("cluster_name %s" % cluster_data['cluster_name'])
    log.debug("cluster_id %s" % cluster_data['cluster_id'])
    log.debug("minions %s" % minions)
    try:
        out = salt_wrapper.setup_ceph_cluster(
            cluster_data['cluster_name'], cluster_data['cluster_id'], minions)
        # Should we return failure from here?
        # Need to discuss and figure out how to handle the error here
        if not out:
            raise Exception("Ceph Cluster creation Failed")
    except Exception, e:
        log.exception(e)
        # Should we return failure from here?
        return False, _map_failed_nodes(failedNodes, nodelist, minionIds)

    # Start the mons
    try:
        failedNodes = salt_wrapper.start_ceph_mon(
            cluster_data['cluster_name'])
        log.debug("failedNodes %s" % failedNodes)
    except Exception, e:
        log.exception(e)
        # Should we return failure from here?
        return False, _map_failed_nodes(failedNodes, nodelist, minionIds)

    return True, _map_failed_nodes(failedNodes, nodelist, minionIds)


def create_gluster_cluster(nodelist):
    failedNodes = []
    if nodelist:
        rootNode = nodelist[0]['management_ip']
        for node in nodelist[1:]:
            rc = salt_wrapper.peer(rootNode, node['management_ip'])
            if rc is False:
                log.critical("Peer Probe Failed for node %s" % node)
                failedNodes.append(node)

    return True, failedNodes


def _map_failed_nodes(failed, nodelist, minionIds):
    failedNodes = []
    if failed:
        if failed['minion']:
            failedlist = failed['minion'].keys()
            for node in nodelist:
                if minionIds[node['management_ip']] in failedlist:
                    failedNodes.append(node)
    return failedNodes
