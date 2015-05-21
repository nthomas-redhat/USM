import logging
import random
import time

from celery import shared_task
from celery import current_task

from usm_rest_api.models import Cluster
from usm_rest_api.models import Host
from usm_rest_api.models import GlusterVolume
from usm_rest_api.v1.serializers.serializers import CephOSDSerializer
from usm_rest_api.v1.serializers.serializers import GlusterVolumeSerializer
from usm_rest_api.v1.serializers.serializers import GlusterBrickSerializer
from usm_rest_api.v1.serializers.serializers import CephPoolSerializer

from usm_wrappers import salt_wrapper

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

    # Push the cluster configuration to nodes
    log.debug("Push Cluster config to Nodes")
    failed_minions = salt_wrapper.setup_cluster_grains(
        [item['node_name'] for item in nodelist],
        cluster_data)
    if failed_minions:
        #reload the salt_wrapper to refresh connections
        reload(salt_wrapper)
        # Retry couple of times
        for count in range(0, 3):
            log.debug("Retrying config push")
            time.sleep(3)
            failed_minions = salt_wrapper.setup_cluster_grains(
                failed_minions, cluster_data)
            if not failed_minions:
                log.debug("Success after retrying")
                break
    if failed_minions:
        log.debug('Config Push failed for minions %s' % failed_minions)
        # Add the failed minions to failed Nodes list
        failedNodes = [
            item for item in nodelist if item['node_name'] in failed_minions]
        log.debug("failedNodes %s" % failedNodes)

    log.debug("Setting up the Ceph Cluster")
    current_task.update_state(
        state='STARTED', meta={'state': 'SETUP_CEPH_CLUSTER'})
    #
    # Send only the successful nodes
    #
    successNodes = [item for item in nodelist if item not in failedNodes]
    log.debug("Node List %s" % successNodes)
    status = usm_rest_utils.create_ceph_cluster(
        successNodes, cluster_data)
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
        # Update the host in DB
        #
        usm_rest_utils.update_host_details(
            successNodes, str(cluster_data['cluster_id']))
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
    # if not usm_rest_utils.discover_disks(successNodes, minionIds):
    #    log.critical("Disvovery of disks failed")

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

    # Push the cluster configuration to nodes
    log.debug("Push Cluster config to Nodes")
    failed_minions = salt_wrapper.setup_cluster_grains(
        [item['node_name'] for item in nodelist],
        cluster_data)
    if failed_minions:
        #reload the salt_wrapper to refresh connections
        reload(salt_wrapper)
        # Retry couple of times
        for count in range(0, 3):
            log.debug("Retrying config push")
            time.sleep(3)
            failed_minions = salt_wrapper.setup_cluster_grains(
                list(failed_minions), cluster_data)
            if not failed_minions:
                log.debug("Success after retrying")
                break
    if failed_minions:
        log.debug('Config Push failed for minions %s' % failed_minions)
        # Add the failed minions to failed Nodes list
        failedNodes = [
            item for item in nodelist if item['node_name'] in failed_minions]
        log.debug("failedNodes %s" % failedNodes)

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
        # Update Nodes in DB
        #
        usm_rest_utils.update_host_details(
            successNodes, str(cluster_data['cluster_id']))

        # Update the status of Cluster to Active if atlest two nodes
        # are added successfully
        #
        if len(successNodes) == 0:
            usm_rest_utils.update_cluster_status(
                str(cluster_data['cluster_id']),
                usm_rest_utils.STATUS_FAILED)
        elif len(successNodes) >= 2:
            usm_rest_utils.update_cluster_status(
                str(cluster_data['cluster_id']),
                usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE)
        else:
            usm_rest_utils.update_cluster_status(
                str(cluster_data['cluster_id']),
                usm_rest_utils.STATUS_INACTIVE)

    except Exception, e:
        log.exception(e)

    # Discover the Disks from the nodes.
    # if not usm_rest_utils.discover_disks(successNodes, minionIds):
    #    log.critical("Disvovery of disks failed")

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
    failedNodes = []

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

    # Push the cluster configuration to nodes
    log.debug("Push Cluster config to Nodes")
    failed_minions = salt_wrapper.setup_cluster_grains(
        [item['node_name'] for item in [data]],
        cluster_data)
    if failed_minions:
        #reload the salt_wrapper to refresh connections
        reload(salt_wrapper)
        # Retry couple of times
        for count in range(0, 3):
            log.debug("Retrying config push")
            time.sleep(3)
            failed_minions = salt_wrapper.setup_cluster_grains(
                failed_minions, cluster_data)
            if not failed_minions:
                log.debug("Success after retrying")
                break
    if failed_minions:
        log.debug('Config Push failed for minions %s' % failed_minions)
        raise usm_rest_utils.HostAdditionFailed(
            [data], "Failed to push config to Node")

    # Add the Host to cluster based on the node type
    # ie if the node type is monitor, then create a monitor
    # else create the OSD
    log.debug("Adding the host to the cluster")
    if data['node_type'] == usm_rest_utils.HOST_TYPE_MONITOR:
        current_task.update_state(
            state='STARTED', meta={'state': 'ADD_MONITOR_TO_CLUSTER'})
        failedNodes = usm_rest_utils.add_ceph_monitors(
            [data], cluster_data)
    elif data['node_type'] == usm_rest_utils.HOST_TYPE_OSD:
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
            # Update the Nodes in DB
            #
            usm_rest_utils.update_host_details(
                [data], str(cluster_data['cluster_id']))
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
    # if not usm_rest_utils.discover_disks([data], minionIds):
    #    log.critical("Disvovery of disks failed")

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

    # Push the cluster configuration to nodes
    log.debug("Push Cluster config to Nodes")
    failed_minions = salt_wrapper.setup_cluster_grains(
        [item['node_name'] for item in [data]],
        cluster_data)
    if failed_minions:
        #reload the salt_wrapper to refresh connections
        reload(salt_wrapper)
        # Retry couple of times
        for count in range(0, 3):
            log.debug("Retrying config push")
            time.sleep(3)
            failed_minions = salt_wrapper.setup_cluster_grains(
                failed_minions, cluster_data)
            if not failed_minions:
                log.debug("Success after retrying")
                break
    if failed_minions:
        log.debug('Config Push failed for minions %s' % failed_minions)
        raise usm_rest_utils.HostAdditionFailed(
            [data], "Failed to push config to Node")

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
            # Update the Nodes in DB
            #
            usm_rest_utils.update_host_details(
                [data], str(cluster_data['cluster_id']))
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
    # if not usm_rest_utils.discover_disks([data], minionIds):
    #    log.critical("Disvovery of disks failed")

    log.debug("Adding Host successful")
    return {'state': 'SUCCESS'}


@shared_task
def createCephOSD(data):
    log.debug("Inside createCephOSD Async Task %s" % data)
    current_task.update_state(state='STARTED')

    osdlist = []
    if 'osds' in data:
        osdlist = data['osds']

    # Return from here if nodelist is empty
    if len(osdlist) == 0:
        log.info("OSD List is empty, Pool creation failed")
        raise Exception(
            "OSD List is empty, OSD creation failed")

    # Send the request to add the OSD
    current_task.update_state(
        state='STARTED', meta={'state': 'ADD_OSD_TO_CLUSTER'})
    log.debug("Creating the OSDs")
    failedNodes = usm_rest_utils.add_ceph_osds(osdlist)
    if failedNodes:
        osdlist = [item for item in osdlist if item not in failedNodes]

    # Update the DB
    current_task.update_state(
        state='STARTED', meta={'state': 'UPDATE_DB'})
    log.debug("Updating the DB")
    for osd in osdlist:
        try:
            osdSerilaizer = CephOSDSerializer(data=osd)
            if osdSerilaizer.is_valid():
                osdSerilaizer.save()
        except Exception, e:
            log.exception(e)
            failedNodes.append(osd)
    if failedNodes:
        log.debug("Failed devices %s" % failedNodes)
        raise Exception(failedNodes, "Failed to add few OSDs to cluster")

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


@shared_task
def acceptHosts(data):
    log.debug("Inside accepthosts Async Task %s" % data)
    current_task.update_state(state='STARTED')

    if 'nodes' in data:
        nodelist = data['nodes']
    else:
        log.info("Node List is empty")
        raise Exception(
            data, "Node List is empty, Accept Hosts failed")

    minionIds, failedNodes = usm_rest_utils.setup_transport_and_update_db(
        nodelist)
    successNodes = [item for item in nodelist if item not in failedNodes]

    # Discover the Disks from the nodes.
    if not usm_rest_utils.discover_disks(
            successNodes):
        log.critical("Disvovery of disks failed")

    if failedNodes:
        return {'state': 'FAILURE',
                'failednodes': str(failedNodes),
                'reason': 'Accept Failed for few hosts'}

    return {'state': 'SUCCESS'}


@shared_task
def createCephPool(data):
    log.debug("Inside createCephPool Async Task %s" % data)
    current_task.update_state(state='STARTED')

    poollist = []
    if 'pools' in data:
        poollist = data['pools']

    # Return from here if nodelist is empty
    if len(poollist) == 0:
        log.info("Pool List is empty, Pool creation failed")
        raise Exception(
            "Pool List is empty, Pool creation failed")

    monitors = Host.objects.filter(cluster_id=str(data['cluster'])).filter(
        node_type__exact=usm_rest_utils.HOST_TYPE_MONITOR)
    if not monitors:
        log.critical(
            "No monitors present in the cluster. Pool creation failed")
        raise Exception(
            "No monitors present in the cluster. Pool creation failed")
    # Send the request to add the OSD
    current_task.update_state(
        state='STARTED', meta={'state': 'CREATE_POOL'})
    log.debug("Creating the Pools")
    failed = []
    for pool in poollist:
        try:
            pool['cluster'] = data['cluster']
            monitor = random.choice(monitors)
            if 'pg_num' in pool:
                if pool['pg_num'] is None:
                    pool['pg_num'] = 128
            else:
               pool['pg_num'] = 128

            result = salt_wrapper.create_ceph_pool(
                monitor.node_name, monitor.cluster.cluster_name,
                pool['pool_name'], pool['pg_num'])
            log.debug("Pool:%s" % pool)
            if result:
                # update DB
                log.debug("Updating the DB")
                poolSerilaizer = CephPoolSerializer(data=pool)
                if poolSerilaizer.is_valid():
                    poolSerilaizer.save()
            else:
                failed.append(pool)
        except Exception, e:
            log.exception(e)
            failed.append(pool)

    if failed:
        log.debug("Failed requests %s" % failed)
        raise Exception(failed, "Failed to create few pools")

    return {'state': 'SUCCESS'}
