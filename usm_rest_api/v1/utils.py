import random
import logging

from usm_wrappers import salt_wrapper


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


def peer(hostlist,newNode):
    rc=False
    if len(hostlist) > 0:
        host = random.choice(hostlist)
        
        rc = salt_wrapper.peer(host,newNode)
        if rc==True:
            return rc
        #random host is not able to peer probe
        #Now try to iterate through the list of hosts
        #in the cluster to peer probe until
        #the peer probe is successful
        
        #No need to send it to host which we already
        hostlist.remove(host)
        for host in hostlist:
            rc = salt_wrapper.peer(host,newNode)
            if rc==True:
                return rc
        return rc
    else:
        return True