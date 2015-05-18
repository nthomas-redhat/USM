import logging

from celery import shared_task
from celery import current_task

from usm_rest_api.models import Cluster
from usm_rest_api.models import Host
from usm_rest_api.models import StorageDevice
from usm_rest_api.models import GlusterVolume
from usm_rest_api.v1.serializers.serializers import CephOSDSerializer
from usm_rest_api.v1.serializers.serializers import GlusterVolumeSerializer
from usm_rest_api.v1.serializers.serializers import GlusterBrickSerializer

from usm_rest_api.v1.views import utils as usm_rest_utils

log = logging.getLogger('django.request')


@shared_task
def createCephCluster(cluster_data):
    log.debug("Inside createCephCluster Async Task")
    current_task.update_state(state='STARTED')
    log.debug(cluster_data)
    nodelist = []
    failedNodes = []
    noOfNodes = 0
    if 'nodes' in cluster_data:
        nodelist = cluster_data['nodes']
        noOfNodes = len(nodelist)
        del cluster_data['nodes']

    # Return from here if nodelist is empty
    if noOfNodes == 0:
        log.info("Node List is empty, Cluster creation failed")
        raise usm_rest_utils.ClusterCreationFailed(
            nodelist, "Node List is empty, Cluster creation failed")

    # create the cluster
    try:
        usm_rest_utils.create_cluster(cluster_data)
    except Exception, e:
        log.exception(e)
        raise usm_rest_utils.ClusterCreationFailed(
            nodelist, str(e))

    # Setup the host communication and update the DB
    current_task.update_state(
        state='STARTED', meta={'state': 'ESTABLISH_HOST_COMMUNICATION'})
    minionIds, failedNodes = usm_rest_utils.setup_transport_and_update_db(
        cluster_data, nodelist)

    log.debug("Setting up the Ceph Cluster")
    current_task.update_state(
        state='STARTED', meta={'state': 'SETUP_GLUSTER_CLUSTER'})
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
        raise usm_rest_utils.ClusterCreationFailed(
            nodelist, "ALL_NODES_FAILURE")

    log.debug("Successfully created ceph cluster on the node")

    log.debug("Successful Nodes %s" % successNodes)
    log.debug("Failed Nodes %s" % failedNodes)
    log.debug("Updating the cluster status")
    current_task.update_state(
        state='STARTED', meta={'state': 'UPDATE_CLUSTER_STATUS'})
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

    # Discover the Disks from the nodes.
    if not usm_rest_utils.discover_disks(successNodes, minionIds):
        log.critical("Disvovery of disks failed")

    if noOfNodes == len(failedNodes):
        log.critical("Cluster creation Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        raise usm_rest_utils.ClusterCreationFailed(
            failedNodes, "ALL_NODES_FAILURE")
    elif len(failedNodes) > 0:
        log.critical("Cluster creation partially Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        return {'state': 'FAILURE',
                'failednodes': str(failedNodes),
                'reason': 'Cluster creation partially Failed'}

    log.debug("Creating Ceph cluster successful")
    return {'state': 'SUCCESS'}


@shared_task
def createGlusterCluster(cluster_data):
    log.debug("Inside createGlusterCluster Async Task")
    current_task.update_state(state='STARTED')
    log.debug(cluster_data)
    nodelist = []
    failedNodes = []
    noOfNodes = 0
    if 'nodes' in cluster_data:
        nodelist = cluster_data['nodes']
        noOfNodes = len(nodelist)
        del cluster_data['nodes']

    # Return from here if nodelist is empty
    if noOfNodes == 0:
        log.info("Node List is empty, Cluster creation failed")
        raise usm_rest_utils.ClusterCreationFailed(
            nodelist, "Node List is empty, Cluster creation failed")

    # create the cluster
    try:
        usm_rest_utils.create_cluster(cluster_data)
    except Exception, e:
        log.exception(e)
        raise usm_rest_utils.ClusterCreationFailed(
            nodelist, str(e))

    # Setup the host communication and update the DB
    current_task.update_state(
        state='STARTED', meta={'state': 'ESTABLISH_HOST_COMMUNICATION'})
    minionIds, failedNodes = usm_rest_utils.setup_transport_and_update_db(
        cluster_data, nodelist)

    log.debug("peer probe start")
    current_task.update_state(
        state='STARTED', meta={'state': 'SETUP_GLUSTER_CLUSTER'})
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
    current_task.update_state(
        state='STARTED', meta={'state': 'UPDATE_CLUSTER_STATUS'})
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

    # Discover the Disks from the nodes.
    if not usm_rest_utils.discover_disks(successNodes, minionIds):
        log.critical("Disvovery of disks failed")

    if noOfNodes == len(failedNodes):
        log.critical("Cluster creation Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        raise usm_rest_utils.ClusterCreationFailed(
            failedNodes, "ALL_NODES_FAILURE")
    elif len(failedNodes) > 0:
        log.critical("Cluster creation partially Failed %s and Nodelist %s" %
                     (cluster_data, failedNodes))
        return {'state': 'FAILURE',
                'failednodes': str(failedNodes),
                'reason': 'Cluster creation partially Failed'}

    log.debug("Creating Gluster cluster successful")
    return {'state': 'SUCCESS'}


@shared_task
def createCephHost(data):
    log.debug("Inside createCephHost Async Task %s" % data)
    current_task.update_state(state='STARTED')
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
        raise usm_rest_utils.HostAdditionFailed(
            [data], str(e))

    # Setup the host communication
    current_task.update_state(
        state='STARTED', meta={'state': 'ESTABLISH_HOST_COMMUNICATION'})
    minionIds, failedNodes = usm_rest_utils.setup_transport_and_update_db(
        cluster_data, [data])
    if failedNodes:
        log.debug("Failed to Establish Transport with Node %s" % failedNodes)
        raise usm_rest_utils.HostAdditionFailed(
            [data], "Failed to Establish Transport with Node")
    log.debug("setup_transport_and_update_db done. minionIds %s failedNodes \
              %s" % (minionIds, failedNodes))
    # Add the Host to cluster based on the node type
    # ie if the node type is monitor, then create a monitor
    # else create the OSD
    log.debug("Adding the host to the cluster")
    if data['node_type'] == usm_rest_utils.HOST_TYPE_MONITOR:
        current_task.update_state(
            state='STARTED', meta={'state': 'ADD_MONITOR_TO_CLUSTER'})
        failedNodes = usm_rest_utils.add_ceph_monitors(
            [data], cluster_data, minionIds)
    elif data['node_type'] == usm_rest_utils.HOST_TYPE_OSD:
        # current_task.update_state(
        # state='STARTED', meta={'state':'ADD_OSD_TO_CLUSTER'})
        # failedNodes = usm_rest_utils.add_ceph_osds(
        #    [data], cluster_data, minionIds)
        # Now we will not add the OSDs to the cluster at this stage
        # It will be done with another api call
        pass

    if failedNodes:
        log.debug("Failed to add node to cluster %s" % failedNodes)
        raise usm_rest_utils.HostAdditionFailed(
            [data], "Failed to add node to cluster")
    log.debug("Updating the cluster status")
    current_task.update_state(
        state='STARTED', meta={'state': 'UPDATE_CLUSTER_STATUS'})
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
        raise usm_rest_utils.HostAdditionFailed(
            [data], str(e))

    # Discover the Disks from the nodes.
    if not usm_rest_utils.discover_disks([data], minionIds):
        log.critical("Disvovery of disks failed")

    log.debug("Adding Host successful")
    return {'state': 'SUCCESS'}


@shared_task
def createGlusterHost(data):
    log.debug("Inside createGlusterHost Async Task %s" % data)
    current_task.update_state(state='STARTED')
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
        raise usm_rest_utils.HostAdditionFailed(
            [data], str(e))

    # Setup the host communication
    current_task.update_state(
        state='STARTED', meta={'state': 'ESTABLISH_HOST_COMMUNICATION'})
    minionIds, failedNodes = usm_rest_utils.setup_transport_and_update_db(
        cluster_data, [data])
    if failedNodes:
        log.debug("Failed to Establish Transport with Node %s" % failedNodes)
        raise usm_rest_utils.HostAdditionFailed(
            [data], "Failed to Establish Transport with Node")
    log.debug("setup_transport_and_update_db done. minionIds %s failedNodes \
              %s" % (minionIds, failedNodes))
    # Peer probe
    log.debug("peer probe start")
    current_task.update_state(
        state='STARTED', meta={'state': 'ADD_NODE_TO_CLUSTER'})
    rc = usm_rest_utils.add_gluster_host(
        [item.management_ip for item in hostlist if item.management_ip !=
         data['management_ip']], data['management_ip'])
    if rc is not True:
        log.debug("Peer Probe Failed for Node %s" % data)
        raise usm_rest_utils.HostAdditionFailed(
            [data], "Failed to add node to cluster")
    current_task.update_state(
        state='STARTED', meta={'state': 'UPDATE_CLUSTER_STATUS'})
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
        raise usm_rest_utils.HostAdditionFailed(
            [data], str(e))

    # Discover the Disks from the nodes.
    if not usm_rest_utils.discover_disks([data], minionIds):
        log.critical("Disvovery of disks failed")

    log.debug("Adding Host successful")
    return {'state': 'SUCCESS'}


@shared_task
def createCephOSD(data):
    log.debug("Inside createCephOSD Async Task %s" % data)
    current_task.update_state(state='STARTED')

    node = Host.objects.get(pk=str(data['node']))

    storage_device = StorageDevice.objects.get(pk=str(data['storage_device']))
    current_task.update_state(
        state='STARTED', meta={'state': 'ADD_OSD_TO_CLUSTER'})

    node_data = {'cluster_ip': str(node.cluster_ip),
                 'public_ip': str(node.public_ip),
                 'devices': {str(storage_device.storage_device_name): 'xfs'}}
    # Send the request to add the OSD
    log.debug("Creating the OSD")
    failedNodes = usm_rest_utils.add_ceph_osd(
        node_data,  str(node.cluster.cluster_name), str(node.node_name))
    if failedNodes:
        log.debug("Failed to add OSD to cluster %s" % failedNodes)
        raise Exception(data, "Failed to add OSD to cluster")
    # Update the DB
    log.debug("Updating the DB")
    try:
        osdSerilaizer = CephOSDSerializer(data=data)
        if osdSerilaizer.is_valid():
            osdSerilaizer.save()
    except Exception, e:
        log.exception(e)
        raise Exception(
            data, "Failed to add OSD to DB")
    return {'state': 'SUCCESS'}


@shared_task
def createGlusterVolume(data):
    log.debug("Inside createGlusterVolume Async Task %s" % data)
    current_task.update_state(state='STARTED')

    if 'bricks' in data:
        bricklist = data['bricks']
        del data['bricks']

    # Return from here if bricklist is empty
    if len(bricklist) == 0:
        log.info("Brick List is empty, Volume creation failed")
        raise usm_rest_utils.VolumeCreationFailed(
            bricklist, "Brick List is empty, Volume creation failed")

    hostlist = Host.objects.filter(cluster_id=str(data['cluster']))
    # Prepare the disks for brick creation
    failed = usm_rest_utils.create_gluster_brick(bricklist)
    log.critical("Brick creation failed for bricks: %s" % str(failed))
    # Remove the failed bricks from bricklist
    bricks = [item for item in bricklist if item not in failed]
    # Return from here if bricks are empty
    if len(bricks) == 0:
        log.info("Brick List is empty, Brick creation failed")
        raise usm_rest_utils.VolumeCreationFailed(
            bricklist, "Brick Creation failed")
    log.debug("Creating the volume with bricks %s", str(bricks))
    # create the Volume
    try:
        rc = usm_rest_utils.create_gluster_volume(data, bricks, hostlist)
        if rc is False:
            log.debug("Creating the volume failed")
            raise usm_rest_utils.VolumeCreationFailed(data, str(bricks))
    except usm_rest_utils.VolumeCreationFailed, e:
        log.exception(e)
        raise
    # Get UUID of the newly created volume
    uuid = usm_rest_utils.get_volume_uuid(
        data['volume_name'], data['cluster'], hostlist)
    if uuid is None:
        log.debug("Unable to get the volume UUID")
        raise usm_rest_utils.VolumeCreationFailed(
            data, str(bricks), "Unable to get the volume UUID")

    # Persist the volume configuration into DB
    try:
        data['volume_id'] = uuid
        data['volume_status'] = usm_rest_utils.STATUS_CREATED
        volSerilaizer = GlusterVolumeSerializer(data=data)
        if volSerilaizer.is_valid():
            volSerilaizer.save()
        for brick in bricks:
            brick['volume'] = uuid
            brick['brick_status'] = usm_rest_utils.STATUS_UP
            brickSerilaizer = GlusterBrickSerializer(data=brick)
            if brickSerilaizer.is_valid():
                brickSerilaizer.save()
    except Exception, e:
        log.exception(e)
        raise usm_rest_utils.VolumeCreationFailed(
            data, str(bricks), "Unable to update the DB")
    return {'state': 'SUCCESS'}


@shared_task
def createGlusterBrick(data):
    log.debug("Inside createGlusterBrick Async Task %s" % data)
    current_task.update_state(state='STARTED')

    bricklist = data['bricks']
    # Return from here if bricklist is empty
    if len(bricklist) == 0:
        log.info("Brick List is empty, Brick addition failed")
        raise Exception(
            bricklist, "Brick List is empty, Brick addition failed")

    # Prepare the disks for brick creation
    failed = usm_rest_utils.create_gluster_brick(bricklist)
    log.critical("Brick creation failed for bricks: %s" % str(failed))
    # Remove the failed bricks from bricklist
    bricks = [item for item in bricklist if item not in failed]
    # Return from here if bricks are empty
    if len(bricks) == 0:
        log.info("Brick List is empty, Brick creation failed")
        raise Exception(
            bricklist, "Brick Creation failed")
    
    # create the Brick
    try:
        volume = GlusterVolume.objects.get(pk=str(data['volume']))
        rc = usm_rest_utils.add_volume_bricks(volume, bricks)
        if rc is False:
            raise Exception(
                bricks, "Brick List is empty, Brick addition failed")
    except Exception, e:
        log.exception(e)
        raise

    # Persist the Bricks into DB
    try:
        for brick in bricks:
            brick['volume'] = str(volume.volume_id)
            brick['brick_status'] = usm_rest_utils.STATUS_UP
            brickSerilaizer = GlusterBrickSerializer(data=brick)
            if brickSerilaizer.is_valid():
                brickSerilaizer.save()
    except Exception, e:
        log.exception(e)
        raise Exception(str(bricks), "Unable to update the DB")
    return {'state': 'SUCCESS'}
