import logging

from celery import shared_task
from celery import states
from celery import current_task

from usm_rest_api.models import Cluster
from usm_rest_api.models import Host

from usm_wrappers import salt_wrapper
from usm_wrappers import utils as usm_wrapper_utils
from usm_rest_api.v1.views import utils as usm_rest_utils


log = logging.getLogger('django.request')


@shared_task
def setupCluster(cluster_data):
    log.debug("Inside createCephCluster Async Task")
    log.debug(cluster_data)
    nodelist = []
    failedNodes = []
    noOfNodes = 0
    if 'nodes' in cluster_data:
        nodelist = cluster_data['nodes']
        noOfNodes = len(nodelist)
        del cluster_data['nodes']

    # create the cluster
    try:
        current_task.update_state(state='CREATE_CLUSTER')
        usm_rest_utils.create_cluster(cluster_data)
    except Exception, e:
        log.exception(e)
        return {'status': 'CLUSTER_CREATION_FAILURE', 'error': str(e)}

    # Return from here if nodelist is empty
    if noOfNodes == 0:
        log.info("Created Empty Cluster %s" % cluster_data)
        return states.SUCCESS

    # Setup the host communication and update the DB
    current_task.update_state(state='ESTABLISH_HOST_COMMUNICATION')
    minionIds, failedNodes = usm_rest_utils.setup_transport_and_update_db(
        cluster_data, nodelist)

    log.debug("Setting up the Cluster")
    #
    # Do the peer probe  and cluster config only for successful nodes
    #
    probeList = [item for item in nodelist if item not in failedNodes]
    log.debug("Node List %s" % probeList)
    log.debug("About to send commands for cluster creation")
    failed = None
    status = None
    if cluster_data['cluster_type'] == usm_rest_utils.CLUSTER_TYPE_GLUSTER:
        current_task.update_state(state='SETUP_GLUSTER_CLUSTER')
        status, failed = usm_rest_utils.create_gluster_cluster(probeList)
        log.debug("Failed Nodes from create_ceph_cluster %s" % failed)
    elif cluster_data['cluster_type'] == usm_rest_utils.CLUSTER_TYPE_CEPH:
        current_task.update_state(state='SETUP_CEPH_CLUSTER')
        status, failed = usm_rest_utils.create_ceph_cluster(
            probeList, cluster_data, minionIds)
        log.debug("Failed Nodes from create_ceph_cluster %s" % failed)

    # if status is False then cluster creation Failed, no need to
    # proceed further. Otherwise check failed list and merge to the \
    # failed nodes list
    if not status:
        log.critical("Cluster creation Failed %s and Nodelist %s" %
                     (cluster_data, nodelist))
        return {'status': 'ALL_NODES_FAILURE', 'failednodes': str(nodelist)}
    else:
        # merge the failed list
        failedNodes += failed
    log.debug("Done. Executed the commands on nodes")
    successNodes = [item for item in probeList if item not in failedNodes]
    log.debug("Successful Nodes %s" % successNodes)
    log.debug("Failed Nodes %s" % failedNodes)
    current_task.update_state(state='UPDATE_CLUSTER_STATUS')
    try:
        #
        # Update the status of the successful Nodes in DB
        # HOST_STATUS_INACTIVE = 1
        # HOST_STATUS_ACTIVE = 2
        #
        usm_rest_utils.update_host_status(
            successNodes, usm_rest_utils.HOST_STATUS_ACTIVE)
        # Update the status of Cluster to Active if atlest two nodes
        # are added successfully for gluster cluster
        # Update the status of Cluster to Active if atlest one nodes
        # are added successfully for ceph cluster
        # STATUS_INACTIVE = 1
        # STATUS_ACTIVE_NOT_AVAILABLE = 2
        # STATUS_ACTIVE_AND_AVAILABLE = 3
        #
        if (len(successNodes) >= 1 and cluster_data['cluster_type']
                == usm_rest_utils.CLUSTER_TYPE_CEPH) or \
                (len(successNodes) >= 2 and cluster_data['cluster_type'] ==
                 usm_rest_utils.CLUSTER_TYPE_GLUSTER):
            usm_rest_utils.update_cluster_status(
                str(cluster_data['cluster_id']),
                usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE)

    except Exception, e:
        log.exception(e)

    if noOfNodes == len(failedNodes):
        log.critical("Cluster creation Failed %s and Nodelist %s" %
                     (cluster_data, nodelist))
        return {'status': 'ALL_NODES_FAILURE', 'failednodes': str(failedNodes)}
    elif failedNodes:
        log.critical("Cluster creation partially Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        return {'status': 'PARTIAL_FAILURE', 'failednodes': str(failedNodes)}

    return states.SUCCESS


@shared_task
def createHost(data):
    log.debug("Inside createGlusterHost Async Task %s" % data)
    cluster = None
    cluster_data = None
    hostlist = None

    # Get the cluster configuration
    try:
        # Get the cluster config
        cluster = Cluster.objects.get(pk=str(data['cluster']))
        cluster_data = {"cluster_id": cluster.cluster_id,
                        "cluster_name": cluster.cluster_name,
                        "cluster_type": cluster.cluster_type,
                        "storage_type": cluster.storage_type}
        log.debug("Cluster Data %s" % cluster_data)
        # Get nodes belongs to the cluster for peerprobe
        hostlist = Host.objects.filter(cluster_id=str(data['cluster']))
        log.debug("Hosts in the cluster: %s" % hostlist)
    except Exception, e:
        log.exception(e)
        return {'status': 'HOST_CREATION_FAILURE', 'error': str(e)}

    # Setup the host communication
    current_task.update_state(state='ESTABLISH_HOST_COMMUNICATION')
    minionIds, failedNodes = usm_rest_utils.setup_transport_and_update_db(
        cluster_data, [data])
    if failedNodes:
        log.debug("Failed to Establish Transport with Node %s" % failedNodes)
        return {
            'status': 'HOST_CREATION_FAILURE',
            'error': "Failed to Establish Transport with Node %s"
            % failedNodes}
    log.debug("setup_transport_and_update_db done. minionIds %s failedNodes \
              %s" % (minionIds, failedNodes))
    # Add the Host to cluster based on the node type
    # ie if the node type is monitor, then create a monitor
    # else create the OSD
    if data['node_type'] == usm_rest_utils.HOST_TYPE_MONITOR:
        log.debug("Add Monitor Host")
        current_task.update_state(state='ADD_MONITOR_HOST')
        failedNodes = salt_wrapper.add_ceph_mon(
            cluster.cluster_name,
            {usm_wrapper_utils.resolve_ip_address(data['management_ip']):
                {'public_ip': data['public_ip']}})
        if failedNodes:
            log.debug("Failed to add monitor to cluster %s" % failedNodes)
            return {
                'status': 'HOST_CREATION_FAILURE',
                'error': "Failed to add monitor to cluster %s"
                % failedNodes}
        log.debug("After Monitor Host Success %s" % str(failedNodes))
    elif data['node_type'] == usm_rest_utils.HOST_TYPE_OSD:
        current_task.update_state(state='ADD_OSD_HOST')
        # Code to add OSD will go here
        log.debug("Add OSD Host")
    elif data['node_type'] == usm_rest_utils.HOST_TYPE_GLUSTER:
        current_task.update_state(state='ADD_GLUSTER_HOST')
        # Peer probe
        log.debug("Add Gluster Host")
        rc = usm_rest_utils.peer(
            [item.management_ip for item in hostlist if item.management_ip !=
             data['management_ip']], data['management_ip'])
        if rc is not True:
            log.debug("Peer Probe Failed for Node %s" % data)
            return {
                'status': 'HOST_CREATION_FAILURE',
                'error': "Peer Probe Failed for Node %s" % str(data)}
    try:
            #
            # Update the status of the successful Nodes in DB
            # HOST_STATUS_INACTIVE = 1
            # HOST_STATUS_ACTIVE = 2
            #
            usm_rest_utils.update_host_status(
                [data], usm_rest_utils.HOST_STATUS_ACTIVE)
            #
            # Update the status of Cluster to Active if atlest
            # two nodes are active
            # STATUS_INACTIVE = 1
            # STATUS_ACTIVE_NOT_AVAILABLE = 2
            # STATUS_ACTIVE_AND_AVAILABLE = 3
            #
            # if cluster is not active available, check whether the
            # Gluster cluster has atleast two active nodes and set the cluster
            # status to active
            # Ceph cluster has atleast one active nodes and set the cluster
            # status to active
            if cluster.cluster_status != \
                    usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE:
                active_hosts = hostlist.filter(
                    node_status__exact=usm_rest_utils.HOST_STATUS_ACTIVE)
                if (len(active_hosts) >= 1 and cluster_data['cluster_type']
                    == usm_rest_utils.CLUSTER_TYPE_CEPH) or \
                    (len(active_hosts) >= 2 and cluster_data['cluster_type'] ==
                        usm_rest_utils.CLUSTER_TYPE_GLUSTER):
                    cluster.cluster_status = \
                        usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE
                    cluster.save()

    except Exception, e:
        log.exception(e)
        return {'status': 'HOST_CREATION_FAILURE', 'error': str(e)}
    return states.SUCCESS
