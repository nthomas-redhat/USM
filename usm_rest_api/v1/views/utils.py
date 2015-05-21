import random
import logging
import uuid
import time

from usm_rest_api.models import Cluster
from usm_rest_api.v1.serializers.serializers import ClusterSerializer
from usm_rest_api.models import Host
from usm_rest_api.v1.serializers.serializers import HostSerializer
from usm_rest_api.models import StorageDevice
from usm_rest_api.models import DiscoveredNode
from usm_rest_api.models import GlusterVolume

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
STATUS_CREATING = 4
STATUS_FAILED = 5
HOST_TYPE_MONITOR = 1
HOST_TYPE_OSD = 2
HOST_TYPE_MIXED = 3
HOST_TYPE_GLUSTER = 4
HOST_STATUS_INACTIVE = 1
HOST_STATUS_ACTIVE = 2
ACCEPT_MINION_TIMEOUT = 3
CONFIG_PUSH_TIMEOUT = 15
STATUS_UP = 0
STATUS_WARNING = 1
STATUS_DOWN = 2
STATUS_UNKNOWN = 3
STATUS_CREATED = 4
VOLUME_TYPE_DISTRIBUTE = 1
VOLUME_TYPE_DISTRIBUTE_REPLICATE = 2
VOLUME_TYPE_REPLICATE = 3
VOLUME_TYPE_STRIPE = 4
VOLUME_TYPE_STRIPE_REPLICATE = 5

# operations
OP_VOLUME_START = 1
OP_VOLUME_STOP = 2
OP_VOLUME_STATUS = 3
OP_VOLUME_DELETE = 4


def add_gluster_host(hostlist, newNode):
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


def setup_transport_and_update_db(nodelist):
    log.debug("Inside setup_transport_and_update_db function")
    failedNodes = []

    # Create the Nodes in the cluster
    # Setup the host communication channel
    minionIds = {}
    for node in nodelist:
        try:
            if 'ssh_username' in node and 'ssh_password' in node:
                ssh_fingerprint = usm_wrapper_utils.get_host_ssh_key(
                    node['management_ip'])
                minionIds[node['management_ip']] = salt_wrapper.setup_minion(
                    node['management_ip'], ssh_fingerprint[0],
                    node['ssh_username'], node['ssh_password'])
            else:
                # Discovered node, add hostname to the minionIds list
                log.debug("Discovered Node: %s" % node)
                minionIds[node['management_ip']] = node['node_name']
        except Exception, e:
            log.exception(e)
            failedNodes.append(node)
    log.debug(minionIds)
    log.debug("Accepting the minions keys")

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
    # Wait till the communication chanel is ready
    #
    started_minions = salt_wrapper.get_started_minions(minionIds.values())
    log.debug("Started Minions %s" % started_minions)
    # if any of the minions are not ready, move ito the failed Nodes
    failedNodes.extend(
        [item for item in nodelist if item['node_name'] not in
         started_minions])
    # Persist the hosts into DB
    for node in nodelist:
        #
        # Get the host uuid from  host and update in DB
        #
        try:
            if node not in failedNodes:
                log.debug("minion: %s" % minionIds[node['management_ip']])
                node['node_id'] = salt_wrapper.get_machine_id(
                    minionIds[node['management_ip']])
                log.debug("Node Id: %s" % node['node_id'])
                if node['node_id'] is None:
                    reload(salt_wrapper)
                    # Retry couple of times
                    for count in range(0, 3):
                        log.debug("Retrying")
                        time.sleep(3)
                        node['node_id'] = salt_wrapper.get_machine_id(
                            minionIds[node['management_ip']])
                        if node['node_id'] is not None:
                            log.debug("Got NodeId after retrying")
                            break
                # node['cluster'] = str(cluster_data['cluster_id'])
                hostSerilaizer = HostSerializer(data=node)

                if hostSerilaizer.is_valid():
                    # Delete all the fields those are not
                    # reqired to be persisted
                    if 'ssh_password' in hostSerilaizer.validated_data:
                        del hostSerilaizer.validated_data['ssh_password']
                    if 'ssh_key_fingerprint' in hostSerilaizer.validated_data:
                        del hostSerilaizer.validated_data[
                            'ssh_key_fingerprint']
                    if 'ssh_username' in hostSerilaizer.validated_data:
                        del hostSerilaizer.validated_data['ssh_username']
                    if 'ssh_port' in hostSerilaizer.validated_data:
                        del hostSerilaizer.validated_data['ssh_port']

                    hostSerilaizer.save()
                else:
                    log.error("Host Creation failed. Invalid hostSerilaizer")
                    log.error("hostSerilaizer Err: %s" % hostSerilaizer.errors)
                    raise Exception("Add to DB Failed", hostSerilaizer.errors)
        except Exception, e:
            log.exception(e)
            failedNodes.append(node)
            continue
        # Remove the node from discovered nodes if present
        try:
            discovered = DiscoveredNode.objects.get(
                node_name__exact=node['node_name'])
            if discovered:
                # delete from discovered nodes table
                log.debug("Clearing the entry from DiscoveredNodes")
                discovered.delete()
        except DiscoveredNode.DoesNotExist:
            pass
        except Exception, e:
            log.exception(e)

    return minionIds, failedNodes


def update_host_details(nodes, cluster_id):
    cluster = Cluster.objects.get(pk=cluster_id)
    for node in nodes:
        glusterNode = Host.objects.filter(
            node_name__exact=node['node_name']).filter(
            management_ip__exact=node['management_ip'])[0]
        glusterNode.node_status = HOST_STATUS_ACTIVE
        if glusterNode.cluster is None:
            glusterNode.cluster = cluster
        if 'cluster_ip' in node:
            glusterNode.cluster_ip = node['cluster_ip']
        if 'public_ip' in node:
            glusterNode.public_ip = node['public_ip']
        if 'node_type' in node:
            glusterNode.node_type = node['node_type']
        glusterNode.save()


def update_host_status(host_id, status):
    host = Host.objects.get(pk=host_id)
    host.node_status = status
    host.save()


def update_cluster_status(cluster_id, status):
    cluster = Cluster.objects.get(pk=cluster_id)
    cluster.cluster_status = status
    cluster.save()


def create_ceph_cluster(nodelist, cluster_data):
    status = True
    if nodelist:
        minions = {}
        for node in nodelist:
            if node['node_type'] == HOST_TYPE_OSD:
                continue
            nodeInfo = {'public_ip': node['public_ip'],
                        'cluster_ip': node['cluster_ip']}
            minions[node['node_name']] = nodeInfo
        log.debug("cluster_name %s" % cluster_data['cluster_name'])
        log.debug("cluster_id %s" % cluster_data['cluster_id'])
        log.debug("minions %s" % minions)
        try:
            status = salt_wrapper.setup_ceph_cluster(
                cluster_data['cluster_name'],
                cluster_data['cluster_id'],
                minions)
            return status
        except Exception, e:
            log.exception(e)
            # Should we return failure from here?
            return False

    return status


def add_ceph_osd(node, cluster_name, minionId):
    failedNodes = []
    try:
        failed = salt_wrapper.add_ceph_osd(
            cluster_name, {minionId: node})
        if failed:
            log.debug("Failed:%s" % failed)
            if minionId in failed.keys():
                failedNodes.append(minionId)
    except Exception, e:
        log.exception(e)
        failedNodes.append(node)

    return failedNodes


def add_ceph_osds(osdlist):
    failedNodes = []
    for osd in osdlist:
        try:
            node = Host.objects.get(pk=str(osd['node']))

            storage_device = StorageDevice.objects.get(
                pk=str(osd['storage_device']))
            node_data = {'cluster_ip': str(node.cluster_ip),
                         'public_ip': str(node.public_ip),
                         'devices': {str(storage_device.storage_device_name): 'xfs'}}  # noqa
            failed = salt_wrapper.add_ceph_osd(
                str(node.cluster.cluster_name), {node.node_name: node_data})
            if failed:
                log.debug("Failed:%s" % failed)
                if node.node_name in failed.keys():
                    failedNodes.append(osd)
        except Exception, e:
            log.exception(e)
            failedNodes.append(osd)

    return failedNodes


def add_ceph_monitors(nodelist, cluster_data):
    failedNodes = []
    if nodelist:
        for node in nodelist:
            nodeInfo = {'public_ip': node['public_ip']}
            try:
                failed = salt_wrapper.add_ceph_mon(
                    cluster_data['cluster_name'],
                    {node['node_name']: nodeInfo})
                if failed:
                    failedNodes += _map_failed_nodes(
                        failed, nodelist)
            except Exception, e:
                log.exception(e)
                failedNodes.append(node)
    return failedNodes


def create_gluster_cluster(nodelist):
    failedNodes = []
    if nodelist:
        rootNode = nodelist[0]['management_ip']
        for node in nodelist[1:]:
            rc = salt_wrapper.peer(rootNode, node['management_ip'])
            if rc is False:
                log.critical("Peer Probe Failed for node %s" % node)
                failedNodes.append(node)
    return failedNodes


def _map_failed_nodes(failed, nodelist, minionIds):
    failedNodes = []
    if failed:
        log.debug("Failed:" % failed)
        failedlist = failed.keys()
        for node in nodelist:
            if node['node_name'] in failedlist:
                failedNodes.append(node)
    return failedNodes


def discover_disks(nodelist):
    minions = [item['node_name'] for item in nodelist]
    if nodelist:
        try:
            disksInfo = salt_wrapper.get_minion_disk_info(minions)
            for node in nodelist:
                diskInfo = disksInfo[node['node_name']]
                for k in diskInfo:
                    log.debug("Disks: %s" % diskInfo[k])
                    log.debug("node UUID: %s" % node['node_id'])
                    sd = StorageDevice(
                        storage_device_name=diskInfo[k]['NAME'],
                        device_uuid=diskInfo[k]['UUID'],
                        node_id=node['node_id'],
                        device_type=diskInfo[k]['TYPE'],
                        device_path=diskInfo[k]['KNAME'],
                        filesystem_type=diskInfo[k]['FSTYPE'],
                        device_mount_point=diskInfo[k]['MOUNTPOINT'],
                        size=float(diskInfo[k]['SIZE'])/1073741824,
                        inuse=diskInfo[k]['INUSE'])
                    log.debug("Saving")
                    sd.save()
        except Exception, e:
            log.exception(e)
            return False
    return True


def create_gluster_volume(data, bricklist, hostlist):
    # create the Volume
    try:
        bricks = [item['brick_path'] for item in bricklist]
        hostlist = [item.node_name for item in hostlist]
        log.debug("Hostlist: %s" % hostlist)
        if hostlist:
            host = random.choice(hostlist)
            log.debug("Host: %s" % host)
            # reload(salt_wrapper)
            rc = salt_wrapper.create_gluster_volume(
                host, data['volume_name'], bricks, stripe=0,
                replica=data['replica_count'], transport=[], force=True)
            if rc:
                return True
            log.debug("Request failed with Host: %s" % host)
            #
            # random host is not able to create volume
            # Now try to iterate through the list of hosts
            # in the cluster until
            # the volume creation is successful

            # No need to send it to host which we already tried
            hostlist.remove(host)
            for host in hostlist:
                log.debug("Re trying with Host: %s" % host)
                rc = salt_wrapper.create_gluster_volume(
                    host, data['volume_name'], bricks, stripe=0,
                    replica=data['replica_count'], transport=[], force=True)
                if rc:
                    return True
                    break
                log.debug("Request failed with Host: %s" % host)
            return False
        else:
            return False
    except Exception, e:
        log.exception(e)
        raise VolumeCreationFailed(data, bricks, str(e))


def get_volume_uuid(name, cluster_uuid, hostlist=None):
    try:
        if hostlist is None:
            if cluster_uuid is not None:
                hostlist = Host.objects.filter(
                    cluster_id=str(cluster_uuid))
            else:
                return None

        host = random.choice(hostlist)

        vols = salt_wrapper.list_gluster_volumes(host.node_name)

        # TO DO: Error handling will be added once the support
        # is added in the backend
        # if rc is True:
        #    return rc
        #
        # random host is not able to create volume
        # Now try to iterate through the list of hosts
        # in the cluster until
        # the volume creation is successful

        # No need to send it to host which we already tried
        # hostlist.remove(host)
        # for host in hostlist:
        #     vols = salt_wrapper.list_gluster_volumes(host)
        #    if rc is True:
        #        return rc

        if name in vols:
            return vols[name]['uuid']
    except Exception, e:
        log.exception(e)

    return None


volume_operations_dict = {
    OP_VOLUME_START: salt_wrapper.start_gluster_volume,
    OP_VOLUME_STOP: salt_wrapper.stop_gluster_volume,
    OP_VOLUME_STATUS: salt_wrapper.get_gluster_volume_status,
    OP_VOLUME_DELETE: salt_wrapper.delete_gluster_volume,
    }


def volume_operations(volume, op_id):
    try:
        log.debug("Volume Name: %s" % volume.volume_name)
        log.debug("Volume cluster: %s" % volume.cluster_id)
        hostlist = Host.objects.filter(
            cluster_id=str(volume.cluster_id))
        hostlist = [item.node_name for item in hostlist]
        log.debug("Hostlist: %s" % hostlist)
        if hostlist:
            host = random.choice(hostlist)
            log.debug("Host: %s" % host)

            rc = volume_operations_dict[op_id](host, volume.volume_name)
            if rc is True:
                return rc
            #
            # random host is not able to execute command
            # Now try to iterate through the list of hosts
            # in the cluster until
            # the execution is successful

            # No need to send it to host which we already tried
            log.debug("Sending the request failed with host: %s" % host)
            hostlist.remove(host)
            for host in hostlist:
                rc = volume_operations_dict[op_id](host, volume.volume_name)
                if rc is True:
                    return rc
                    break
                log.debug("Sending the request failed with host: %s" % host)
            if rc is False:
                log.critical("Start volume failed: %s" % volume.volume_name)
            return rc
        else:
            return False
    except Exception, e:
        log.exception(e)
        raise


def start_gluster_volume(volume_id):
    try:
        volume = GlusterVolume.objects.get(pk=str(volume_id))
        log.debug("Volume Name: %s" % volume.volume_name)
        rc = volume_operations(volume, OP_VOLUME_START)
        if rc is True:
            # update the DB
            volume.volume_status = STATUS_UP
            volume.save()
        return rc
    except Exception, e:
        log.exception(e)
        raise


def stop_gluster_volume(volume_id):
    try:
        volume = GlusterVolume.objects.get(pk=str(volume_id))
        rc = volume_operations(volume, OP_VOLUME_STOP)
        if rc is True:
            # update the DB
            volume.volume_status = STATUS_DOWN
            volume.save()
        return rc
    except Exception, e:
        log.exception(e)
        raise


def delete_gluster_volume(volume_id):
    try:
        volume = GlusterVolume.objects.get(pk=str(volume_id))
        return volume_operations(volume, OP_VOLUME_DELETE)
    except Exception, e:
        log.exception(e)
        raise


def add_volume_bricks(volume, bricklist):
    # Add Bricks
    try:
        bricks = [item['brick_path'] for item in bricklist]
        hostlist = Host.objects.filter(
            cluster_id=str(volume.cluster_id))
        hostlist = [item.node_name for item in hostlist]
        log.debug("Hostlist: %s" % hostlist)
        if hostlist:
            host = random.choice(hostlist)
            log.debug("Host: %s" % host)
            rc = salt_wrapper.add_gluster_bricks(
                host, volume.volume_name, bricks, force=True)
            if rc is True:
                return rc
            #
            # random host is not able to add the brick
            # Now try to iterate through the list of hosts
            # in the cluster until
            # the brick addition is successful

            # No need to send it to host which we already tried
            hostlist.remove(host)
            for host in hostlist:
                rc = salt_wrapper.add_gluster_bricks(
                    host, volume.volume_name, bricks, force=True)
                if rc is True:
                    return rc
                    break
            return rc
        else:
            return False
    except Exception, e:
        log.exception(e)
        raise


def create_gluster_brick(bricklist):
    log.debug("In Create Bricks. bricklist %s" % bricklist)
    # create the Volume
    failed = []
    for brick in bricklist:
        storage_device = None
        try:
            host = Host.objects.get(pk=str(brick['node']))
            if host:
                storage_device = StorageDevice.objects.get(
                    pk=str(brick['storage_device']))
                out = salt_wrapper.create_gluster_brick(
                    host.node_name, str(storage_device.storage_device_name))
                if out:
                    # failed
                    log.debug("Brick creation failed %s" % out)
                    failed.append(brick)
                else:
                    brick['brick_path'] = \
                        str(host.cluster_ip) + ':' + '/bricks/' + \
                        str(storage_device.storage_device_name.split(
                            '/')[-1]) + '1'
        except Exception, e:
            log.exception(e)
            failed.append(brick)
        # Mark the INUSE to True
        # TODO: Right now marking all disks in the list
        # because we are not sure about the reason of failure
        # Need to write a sync function which does the job
        # cleanly
        try:
            storage_device.inuse = True
            storage_device.save()
        except Exception, e:
            log.exception(e)
            log.critical(
                "Setting Inuse Flag failed for %s" % brick['storage_device'])

    return failed


class ClusterCreationFailed(Exception):
    message = "Cluster creation failed"

    def __init__(self, nodelist, reason):
        self.failedNodes = nodelist
        self.reason = reason

    def __str__(self):
        nodeNames = []
        for node in self.failedNodes:
            nodeNames.append(node['node_name'])
        s = ("%s\nfailednodes: %s\nreason: %s\n")
        return s % (self.message, nodeNames, self.reason)


class HostAdditionFailed(Exception):
    message = "Host Addition failed"

    def __init__(self, nodelist, reason):
        self.failedNodes = nodelist
        self.reason = reason

    def __str__(self):
        nodeNames = []
        for node in self.failedNodes:
            nodeNames.append(node['node_name'])
        s = ("%s\nfailednodes: %s\nreason: %s\n")
        return s % (self.message, nodeNames, self.reason)


class VolumeCreationFailed(Exception):
    message = "Volume Creation failed"

    def __init__(self, vol_data, bricklist, reason=''):
        self.volInfo = vol_data
        self.bricks = bricklist
        self.reason = reason

    def __str__(self):
        s = ("%s\nvolume: %s\nbricks: %s\nreason: %s\n")
        return s % (self.message,
                    self.volInfo['volume_name'],
                    self.bricks, self.reason)
