import time
import socket
import uuid
import logging
import copy

from django.core.exceptions import ValidationError, PermissionDenied
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import get_object_or_404
from django_extensions.db.fields import UUIDField


from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated


from celery import shared_task
from celery import states


from usm_rest_api.v1.serializers.serializers import UserSerializer
from usm_rest_api.models import Cluster
from usm_rest_api.v1.serializers.serializers import ClusterSerializer
from usm_rest_api.models import Host
from usm_rest_api.v1.serializers.serializers import HostSerializer

from usm_wrappers import salt_wrapper
from usm_wrappers import utils as usm_wrapper_utils
from usm_rest_api.v1 import utils as usm_rest_utils


log = logging.getLogger('django.request')


@api_view(['GET', 'POST'])
@permission_classes((AllowAny,))
@ensure_csrf_cookie
@never_cache
def login(request):
    """
This resource is used to authenticate with the REST API by POSTing a message
as follows:

::

    {
        "username": "<username>",
        "password": "<password>"
    }

If authentication is successful, 200 is returned, if it is unsuccessful
then 401 is returend.
    """
    if request.method == 'POST':
        username = request.DATA.get('username', None)
        password = request.DATA.get('password', None)
        msg = {}
        if not username:
            msg['username'] = 'This field is required'
        if not password:
            msg['password'] = 'This field is required'
        if len(msg) > 0:
            return Response(msg, status=status.HTTP_400_BAD_REQUEST)
        
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                auth_login(request, user)
            else:
                 return Response({
                'message': 'User Account Disbaled'
            }, status=status.HTTP_401_UNAUTHORIZED)
        else:
             return Response({
                'message': 'User authentication failed'
            }, status=status.HTTP_401_UNAUTHORIZED)
        if request.session.test_cookie_worked():
            request.session.delete_test_cookie()
        return Response({'message': 'Logged out'})
    else:
        pass
    request.session.set_test_cookie()
    return Response({})


@api_view(['GET', 'POST'])
@permission_classes((AllowAny,))
def logout(request):
    """
The resource is used to terminate an authenticated session by POSTing an
empty request.
    """
    auth_logout(request)
    return Response({'message': 'Logged out'})


@api_view(['GET'])
@permission_classes((IsAuthenticated,))
def get_ssh_fingerprint(request,ip_address):
    """
The resource is used to get the ssh fingerprint from a
remote host:

    """
    try:
        ssh_fingerprint = usm_wrapper_utils.get_host_ssh_key(ip_address)
    except Exception, e:
        log.exception(e)
        return Response({'message': 'Error while getting fingerprint'}, status=417)

    return Response({'ssh_key_fingerprint': ssh_fingerprint[0]}, status=200)


@api_view(['GET'])
@permission_classes((IsAuthenticated,))
def resolve_hostname(request,hostname):
    """
The resource is used to get the ip address from a
hostname:

    """
    try:
        ipaddress = usm_wrapper_utils.resolve_hostname(hostname)
    except Exception, e:
        log.exception(e)
        return Response({'message': 'Error while resolving hostname'}, status=417)

    return Response({'IP Address': ipaddress}, status=200)


@api_view(['GET'])
@permission_classes((IsAuthenticated,))
def resolve_ip_address(request,ip_address):
    """
The resource is used to get the hostname from a
ip address:

    """
    try:
        hostname = usm_wrapper_utils.resolve_ip_address(ip_address)
    except Exception, e:
        log.exception(e)
        return Response({'message': 'Error while resolving IP Address'}, status=417)

    return Response({'Hostname': hostname}, status=200)


class ClusterViewSet(viewsets.ModelViewSet):
    """
      The resource is used to manage a cluster with a list of hosts. Cluster can be 
      created by posting a message as follows:
  
      {
      "cluster_name": "NAME",
      "cluster_type": "TYPE",
      "storage_type": "FSTYPE",
      "nodes": [
          {
              "node_name": "NAME",
              "management_ip": "ADDR",
              "cluster_ip": "ADDR",
              "public_ip": "ADDR",
              "ssh_username": "USER",
              "ssh_password": "PASS",
              "ssh_key_fingerprint": "FINGER",
              "ssh_port": 22,
              "node_type": "nodetype"
          },
          {
              
          } ]
      }
      """
    queryset = Cluster.objects.all()
    serializer_class = ClusterSerializer
    
    
    def create(self, request):
       
        log.debug("Inside Cluster Create. Request Data: %s" % request.data )
        data = copy.deepcopy(request.data.copy())
        log.debug(data)
        #
        #TODO:Check the type of the cluster to be created and call appropriate task
        #
        #create gluster cluster
        jobId = createGlusterCluster.delay(data)
        log.debug("Exiting create_cluster JobID: %s" % jobId)
        return Response(str(jobId), status=201)


@shared_task
def createGlusterCluster(cluster_data):
    log.debug("Inside createGlusterCluster Async Task")
    log.debug(cluster_data)
    failedNodes=[]
    successNodes=[]
    nodelist=[]
    noOfNodes = 0
    if 'nodes' in cluster_data:
        nodelist = cluster_data['nodes']
        noOfNodes = len(nodelist)
        del cluster_data['nodes']
    
     #create the cluster
    createGlusterCluster.update_state(state='CREATE_CLUSTER')
    cluster_data['cluster_id'] = str(uuid.uuid4())
    try:
        clusterSerilaizer = ClusterSerializer(data=cluster_data)
        if clusterSerilaizer.is_valid():
            clusterSerilaizer.save()
        else:
                log.error("Cluster Creation failed. Invalid clusterSerilaizer")
                log.error("clusterSerilaizer Err: %s" % clusterSerilaizer.errors)
                return {'status':'CLUSTER_CREATION_FAILURE','error':clusterSerilaizer.errors}
        ##Return from here if nodelist is empty
        if noOfNodes == 0:
            log.info("Created Empty Cluster %s" % cluster_data)
            return states.SUCCESS
    except Exception, e:
        log.exception(e)
        return {'status':'CLUSTER_CREATION_FAILURE','error':str(e)}
    
    #Create the Nodes in the cluster
    #Setup the host communication channel
    createGlusterCluster.update_state(state='ESTABLISH_HOST_COMMUNICATION')
    minionIds={}
    for node in nodelist:
        try:
            ssh_fingerprint = usm_wrapper_utils.get_host_ssh_key(node['management_ip'])
            minionIds[node['management_ip']] = salt_wrapper.setup_minion(
                node['management_ip'], ssh_fingerprint[0],
                node['ssh_username'], node['ssh_password'])
        except Exception, e:
            log.exception(e)
            failedNodes.append(node)
    #Sleep for sometime to make sure all the restarted minions are back
    #online
    time.sleep( 3 )
    log.debug("Accepting the minions keys" )
    createGlusterCluster.update_state(state='ADD_MINION_KEYS_AND_DB_UPDATE')
    
    #Accept the keys of the successful minions and add to the DB
    for node in nodelist:
        try:
            salt_wrapper.accept_minion(minionIds[node['management_ip']])
        except Exception, e:
            log.exception(e)
            if node not in failedNodes:
                failedNodes.append(node)
            continue
    #
    #Wait for some time so that the communication chanel is ready
    #
    time.sleep(10)
    
    for node in nodelist:
        #
        #Get the host uuid from  host and update in DB
        #
        node['node_id'] = salt_wrapper.get_machine_id(minionIds[node['management_ip']])
        node['cluster'] = str(cluster_data['cluster_id'])
        hostSerilaizer = HostSerializer(data=node)   
        try:
            if hostSerilaizer.is_valid():
                #Delete all the fields those are not reqired to be persisted
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
            if node not in failedNodes:
                failedNodes.append(node)
            continue
        
    #Push the cluster configuration to nodes
    log.debug("Push Cluster config to Nodes" )
    createGlusterCluster.update_state(state='PUSH_CLUSTER_CONFIG')
    failed_minions = salt_wrapper.setup_cluster_grains(minionIds.values(), cluster_data)
    if len(failed_minions)>0:
        log.debug('Config Push failed for minions %s' % failed_minions)
    #Add the failed minions to failed Nodes list
    for node in nodelist:
        if usm_wrapper_utils.resolve_ip_address(node['management_ip']) in failed_minions:
            failedNodes.append(node)
            
    #Now create the cluster
    log.debug("peer probe start" )
    createGlusterCluster.update_state(state='PEER_PROBE')
    #
    #Do the peer probe  and cluster config only for successful nodes 
    #
    probeList = [item for item in nodelist if item not in failedNodes]
    log.debug("probList %s" % probeList)
    if len(probeList)>0:
        rootNode = probeList[0]['management_ip']
        for node in probeList[1:]:
            rc = salt_wrapper.peer(rootNode,node['management_ip'])
            if rc == False:
                log.critical("Peer Probe Failed for node %s" % node)
                failedNodes.append(node)
    
    successNodes = [item for item in probeList if item not in failedNodes]
    log.debug("Successful Nodes %s" %  successNodes)
    log.debug("Failed Nodes %s" %  failedNodes)
    try:
        #
        #Update the status of the successful Nodes in DB
        #HOST_STATUS_INACTIVE = 1
        #HOST_STATUS_ACTIVE = 2
        #
        for node in successNodes:
            glusterNode = Host.objects.get(pk=str(node['node_id']))
            log.debug(glusterNode)
            glusterNode.node_status = usm_rest_utils.HOST_STATUS_ACTIVE
            glusterNode.save()
        #
        #Update the status of Cluster to Active if atlest two nodes are added successfully
        #STATUS_INACTIVE = 1
        #STATUS_ACTIVE_NOT_AVAILABLE = 2
        #STATUS_ACTIVE_AND_AVAILABLE = 3
        #
        if len(successNodes) >=2:
            cluster = Cluster.objects.get(pk=str(cluster_data['cluster_id']))
            log.debug(cluster)
            cluster.cluster_status = usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE
            cluster.save()
    except Exception, e:
        log.exception(e)
        
    if noOfNodes == len(failedNodes):
        return {'status':'ALL_NODES_FAILURE','failednodes':str(failedNodes)}
    elif len(failedNodes)>0:
        return {'status':'PARTIAL_FAILURE','failednodes':str(failedNodes)}
    
    return states.SUCCESS
    
    
class UserViewSet(viewsets.ModelViewSet):
    """
    User account information.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
            
    def update(self, request, *args, **kwargs):
        user = self.get_object()
        if user.id != self.request.user.id:
            raise PermissionDenied("May not change another user's password")

        return super(UserViewSet, self).update(request, *args, **kwargs)    


class HostViewSet(viewsets.ModelViewSet):
    """
    Cluster information.
    """
    queryset = Host.objects.all()
    serializer_class = HostSerializer
    
    def create(self, request):
        log.debug("Inside HostViewSet Create. Request Data: %s" % request.data )
        data = copy.deepcopy(request.data.copy())
    
         #
        #TODO:Check the type of the host to be created and call appropriate task
        #
        #Create a host and add to gluster cluster
        jobId = createGlusterHost.delay(data)
        log.debug("Exiting ... JobID: %s" % jobId)
        return Response(str(jobId), status=201)
   
@shared_task
def createGlusterHost(data):
    log.debug("Inside createGlusterHost Async Task %s" % data)
    minionId=''
    cluster=None
    #Setup the host communication
    try:
        createGlusterHost.update_state(state='ESTABLISH_HOST_COMMUNICATION')
        ssh_fingerprint = usm_wrapper_utils.get_host_ssh_key(data['management_ip'])
        minionId = salt_wrapper.setup_minion(data['management_ip'],
                                             ssh_fingerprint[0], data['ssh_username'],
                                             data['ssh_password'])
    except Exception, e:
        log.exception(e)
        return {'status':'HOST_CREATION_FAILURE','error':str(e)}
    #Sleep for sometime to make sure all the restarted minions are back
    #online
    time.sleep( 3 )
    log.debug("Accepting the minions keys" )
    createGlusterHost.update_state(state='ADD_MINION_KEYS_AND_DB_UPDATE')
    try:
        salt_wrapper.accept_minion(minionId)
        #
        #Wait for some time so that the communication chanel is ready
        #
        time.sleep(10)
        #
        #Now get nodes belongs to the cluster for peerprobe
        #
        hostlist = Host.objects.filter(cluster_id=str(data['cluster']))
        log.debug("Hosts in the cluster: %s" % hostlist)
        #
        #Get the host uuid from  host and update in DB
        #
        data['node_id'] = salt_wrapper.get_machine_id(minionId)
        hostSerilaizer = HostSerializer(data=data)
        if hostSerilaizer.is_valid():
            #Delete all the fields those are not reqired to be persisted
            del hostSerilaizer.validated_data['ssh_password']
            del hostSerilaizer.validated_data['ssh_key_fingerprint']
            del hostSerilaizer.validated_data['ssh_username']
            del hostSerilaizer.validated_data['ssh_port']
            #Save the instance to DB
            hostSerilaizer.save()
        else:
            log.error("Host Creation failed. Invalid hostSerilaizer")
            log.error("hostSerilaizer Err: %s" % hostSerilaizer.errors)
            return {'status':'HOST_CREATION_FAILURE','error':hostSerilaizer.errors}
    except Exception, e:
        log.exception(e)
        return {'status':'HOST_CREATION_FAILURE','error':str(e)}
    
    #Push the cluster configuration and form the cluster
    try:
        #Get the cluster config
        cluster = Cluster.objects.get(pk=str(data['cluster']))
        log.debug(cluster)
        #Push the cluster config
        cluster_data = {"cluster_id": cluster.cluster_id,
                        "cluster_name": cluster.cluster_name,
                        "cluster_type": cluster.cluster_type,
                        "storage_type": cluster.storage_type}
        failed_minions = salt_wrapper.setup_cluster_grains([minionId], cluster_data)
        if len(failed_minions)>0:
            raise Exception("Cluster Config Push Failed")
        #
        #Peer probe
        #
        rc = usm_rest_utils.peer([item.management_ip for item in hostlist if item.management_ip != data['management_ip']],data['management_ip'])
        if rc!=True:
            raise Exception("Peer Probe Failed")
    except Exception, e:
        log.exception(e)
        return {'status':'HOST_CREATION_FAILURE','error':str(e)}
    try:
            #
            #Update the status of the successful Nodes in DB
            #HOST_STATUS_INACTIVE = 1
            #HOST_STATUS_ACTIVE = 2
            #
            glusterNode = Host.objects.get(pk=str(data['node_id']))
            log.debug(glusterNode)
            glusterNode.node_status = usm_rest_utils.HOST_STATUS_ACTIVE
            glusterNode.save()
            #
            #Update the status of Cluster to Active if atlest two nodes are active
            #STATUS_INACTIVE = 1
            #STATUS_ACTIVE_NOT_AVAILABLE = 2
            #STATUS_ACTIVE_AND_AVAILABLE = 3
            #
            #if cluster is not active available, check whether the cluster has
            #atleast two active nodes and set the cluster status to active
            if cluster.cluster_status != usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE:
                hostlist = Host.objects.filter(cluster_id=str(data['cluster']))
                active_hosts = hostlist.filter(node_status__exact=usm_rest_utils.HOST_STATUS_ACTIVE)
                if len(active_hosts) >=2:
                    cluster.cluster_status = usm_rest_utils.STATUS_ACTIVE_AND_AVAILABLE
                    cluster.save()
    except Exception, e:
        log.exception(e)
    return states.SUCCESS

