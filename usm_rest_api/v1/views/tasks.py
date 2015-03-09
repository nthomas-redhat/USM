import logging

from celery import shared_task
from celery import states
from celery import current_task

from usm_rest_api.models import Cluster
from usm_rest_api.models import Host

from usm_rest_api.v1.views import utils as usm_rest_utils


log = logging.getLogger('django.request')


@shared_task
def createCephCluster(cluster_data):
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

    log.debug("Setting up the Ceph Cluster")
    current_task.update_state(state='SETUP_CEPH_CLUSTER')
    #
    # Send only the successful nodes
    #
    successNodes = [item for item in nodelist if item not in failedNodes]
    log.debug("Node List %s" % successNodes)
    status = usm_rest_utils.create_ceph_cluster(
        successNodes, cluster_data, minionIds)
    # if status is False then cluster creation Failed, no need to
    # proceed further.
    if not status:
        log.critical("Cluster creation Failed %s and Nodelist %s" %
                     (cluster_data, nodelist))
        return {'status': 'ALL_NODES_FAILURE', 'failednodes': str(nodelist)}

    log.debug("Successfully created ceph cluster on the node")

    log.debug("Successful Nodes %s" % successNodes)
    log.debug("Failed Nodes %s" % failedNodes)
    log.debug("Updating the cluster status")
    current_task.update_state(state='UPDATE_CLUSTER_STATUS')
    try:
        #
        # Update the status of the successful Nodes in DB
        #
        usm_rest_utils.update_host_status(
            successNodes, usm_rest_utils.HOST_STATUS_ACTIVE)
        # Update the status of Cluster to Active if atlest two nodes
        # are added successfully
        # TODO - this is temporary. We need to get the cluster status
        # from the cluster and update it.
        if len(successNodes) >= 1:
            usm_rest_utils.update_cluster_status(
                str(cluster_data['cluster_id']),
                usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE)

    except Exception, e:
        log.exception(e)

    if noOfNodes == len(failedNodes):
        log.critical("Cluster creation Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        return {'status': 'ALL_NODES_FAILURE', 'failednodes': str(failedNodes)}
    elif len(failedNodes) > 0:
        log.critical("Cluster creation partially Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        return {'status': 'PARTIAL_FAILURE', 'failednodes': str(failedNodes)}

    log.debug("Creating Ceph cluster successful")
    return states.SUCCESS


@shared_task
def createGlusterCluster(cluster_data):
    log.debug("Inside createGlusterCluster Async Task")
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

    log.debug("peer probe start")
    current_task.update_state(state='PEER_PROBE')
    #
    # Do the peer probe  and cluster config only for successful nodes
    #
    probeList = [item for item in nodelist if item not in failedNodes]
    log.debug("probList %s" % probeList)
    failedNodes += usm_rest_utils.create_gluster_cluster(probeList)

    successNodes = [item for item in probeList if item not in failedNodes]
    log.debug("Successful Nodes %s" % successNodes)
    log.debug("Failed Nodes %s" % failedNodes)
    log.debug("Updating the cluster status")
    current_task.update_state(state='UPDATE_CLUSTER_STATUS')
    try:
        #
        # Update the status of the successful Nodes in DB
        #
        usm_rest_utils.update_host_status(
            successNodes, usm_rest_utils.HOST_STATUS_ACTIVE)

        # Update the status of Cluster to Active if atlest two nodes
        # are added successfully
        #
        if len(successNodes) >= 2:
            usm_rest_utils.update_cluster_status(
                str(cluster_data['cluster_id']),
                usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE)

    except Exception, e:
        log.exception(e)

    if noOfNodes == len(failedNodes):
        log.critical("Cluster creation Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        return {'status': 'ALL_NODES_FAILURE', 'failednodes': str(failedNodes)}
    elif len(failedNodes) > 0:
        log.critical("Cluster creation partially Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        return {'status': 'PARTIAL_FAILURE', 'failednodes': str(failedNodes)}

    log.debug("Creating Gluster cluster successful")
    return states.SUCCESS


@shared_task
def createCephHost(data):
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
    log.debug("Adding the host to the cluster")
    if data['node_type'] == usm_rest_utils.HOST_TYPE_MONITOR:
        current_task.update_state(state='ADD_MONITOR_TO_CLUSTER')
        failedNodes = usm_rest_utils.add_ceph_monitors(
            [data], cluster_data, minionIds)
    elif data['node_type'] == usm_rest_utils.HOST_TYPE_OSD:
        current_task.update_state(state='ADD_OSD_TO_CLUSTER')
        failedNodes = usm_rest_utils.add_ceph_osds(
            [data], cluster_data, minionIds)

    if failedNodes:
        log.debug("Failed to add node to cluster %s" % failedNodes)
        return {
            'status': 'HOST_CREATION_FAILURE',
            'error': "Failed to add node to cluster %s"
            % failedNodes}
    log.debug("Updating the cluster status")
    current_task.update_state(state='UPDATE_CLUSTER_STATUS')
    try:
            #
            # Update the status of the successful Nodes in DB
            #
            usm_rest_utils.update_host_status(
                [data], usm_rest_utils.HOST_STATUS_ACTIVE)
            #
            # if cluster is not active available, check whether the cluster
            # has atleast one active nodes and set the cluster
            # status to active
            # TODO - this is temporary. We need to get the cluster status
            # from the cluster and update it.
            if cluster.cluster_status != \
                    usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE:
                active_hosts = hostlist.filter(
                    node_status__exact=usm_rest_utils.HOST_STATUS_ACTIVE)
                if len(active_hosts) >= 1:
                    cluster.cluster_status = \
                        usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE
                    cluster.save()
    except Exception, e:
        log.exception(e)
        return {'status': 'HOST_CREATION_FAILURE', 'error': str(e)}

    log.debug("Adding Host successful")
    return states.SUCCESS


@shared_task
def createGlusterHost(data):
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
    # Peer probe
    log.debug("peer probe start")
    rc = usm_rest_utils.add_gluster_host(
        [item.management_ip for item in hostlist if item.management_ip !=
         data['management_ip']], data['management_ip'])
    if rc is not True:
        log.debug("Peer Probe Failed for Node %s" % data)
        return {
            'status': 'HOST_CREATION_FAILURE',
            'error': "Peer Probe Failed for Node %s" % data}
    log.debug("Updating the cluster status")
    current_task.update_state(state='UPDATE_CLUSTER_STATUS')
    try:
            #
            # Update the status of the successful Nodes in DB
            #
            usm_rest_utils.update_host_status(
                [data], usm_rest_utils.HOST_STATUS_ACTIVE)
            #
            # if cluster is not active available, check whether the cluster
            # has atleast two active nodes and set the cluster
            # status to active
            if cluster.cluster_status != \
                    usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE:
                active_hosts = hostlist.filter(
                    node_status__exact=usm_rest_utils.HOST_STATUS_ACTIVE)
                if len(active_hosts) >= 2:
                    cluster.cluster_status = \
                        usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE
                    cluster.save()
    except Exception, e:
        log.exception(e)
        return {'status': 'HOST_CREATION_FAILURE', 'error': str(e)}

    log.debug("Adding Host successful")
    return states.SUCCESS
