import time
import socket
import uuid
import logging

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

from usm_rest_api.v1 import saltapi


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
def get_ssh_fingerprint(request,ip):
    """
The resource is used to get the ssh fingerprint from a
remote host:

    """
    try:
        ssh_fingerprint = saltapi.get_fingerprint(saltapi.get_host_ssh_key(ip))
    except Exception as inst:
        return Response({'message': 'Error while getting fingerprint'}, status=417)

    return Response({'ssh_key_fingerprint': ssh_fingerprint}, status=200)


@api_view(['POST'])
@permission_classes((IsAuthenticated,))
def create_cluster(request):
    """
The resource is used to create a cluster with a list of hosts by posting a
message as follows:

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
            
        }
    ]
}
    """
    log.debug("Inside create_cluster. Request Data: %s" % request.data )
    data = request.data.copy()
    jobId = createCluster.delay(data)
    log.debug("Exiting create_cluster JobID: %s" % jobId)
    return Response(str(jobId), status=200) 


@shared_task
def createCluster(postdata):
    log.debug("Inside createCluster Async Task")
    failedNodes=[]
    nodelist = postdata['nodes']
    noOfNodes = len(nodelist)
    del postdata['nodes']
    
     #create the cluster
    createCluster.update_state(state='CREATE_CLUSTER')
    postdata['cluster_id'] = uuid.uuid4()
    try:
        clusterSerilaizer = ClusterSerializer(data=postdata)
        if clusterSerilaizer.is_valid():
            clusterSerilaizer.save()
        else:
                log.error("Cluster Creation failed. Invalid clusterSerilaizer")
                log.error("clusterSerilaizer Err: %s" % clusterSerilaizer.errors)
                #createCluster.update_state(state='FAILURE',meta=clusterSerilaizer.errors)
                return {'status':'CLUSTER_CREATION_FAILURE','error':clusterSerilaizer.errors}
    except Exception, e:
        log.exception(e)
        return {'status':'CLUSTER_CREATION_FAILURE','error':str(e)}
   
    #Create the Nodes in the cluster
    #Setup the host communication channel
    createCluster.update_state(state='ESTABLISH_HOST_COMMUNICATION')
    for node in nodelist[:]:
        try:
            ssh_fingerprint = saltapi.get_fingerprint(
                saltapi.get_host_ssh_key(node['management_ip']))
            rc,out,err = saltapi.setup_minion(node['management_ip'],
                                              ssh_fingerprint, node['ssh_username'],
                                              node['ssh_password'], postdata)
            if rc!=0:
                raise Exception("Accept Minion Failed", rc,out,err)
        except Exception, e:
            log.exception(e)
            #Delete the node from list to avoid further processing
            nodelist.remove(node)
            failedNodes.append(node)
    #Sleep for sometime to make sure all the restarted minions are back
    #online
    log.debug("Accepting the minions keys" )
    createCluster.update_state(state='ADD_MINION_KEYS')
    time.sleep( 3 )
    #Accept the keys of the successful minions and add to the DB
    for node in nodelist[:]:
        #
        #TODO Get the host uuid from  host and update in DB
        #
        node['node_id'] = uuid.uuid4()
        node['cluster'] = str(postdata['cluster_id'])
        try:
            saltapi.accept_minion(socket.gethostbyaddr(node['management_ip'])[0])
        except UnknownMinion, e:
            log.exception(e)
            #Delete the node from list to avoid peer probing
            nodelist.remove(node)
            failedNodes.append(node)
            continue
        hostSerilaizer = HostSerializer(data=node)   
        try:
            if hostSerilaizer.is_valid():
                #Delete all the fields those are not reqired to be persisted
                del hostSerilaizer.validated_data['ssh_password']
                del hostSerilaizer.validated_data['ssh_key_fingerprint']
                del hostSerilaizer.validated_data['ssh_username']
                del hostSerilaizer.validated_data['ssh_port']
                
                hostSerilaizer.save()
                #transaction.commit()
                #return Response(hostSerilaizer.data, status=201)
            else:
               log.error("Host Creation failed. Invalid hostSerilaizer")
               log.error("hostSerilaizer Err: %s" % hostSerilaizer.errors)
               raise Exception("Add to DB Failed", hostSerilaizer.errors)
        except Exception, e:
            log.exception(e)
            if node not in failedNodes:
                failedNodes.append(node)
            if node in nodelist:
                nodelist.remove(node)
            continue
        
    #Now create the cluster
    log.debug("peer probe start" )
    createCluster.update_state(state='PEER_PROBE')
    #
    #Wait for some time so that the communication chanel is ready
    #
    time.sleep(10)
    #Need peerprobe only if the length is more than one
    if len(nodelist)>1:
        rootNode = nodelist[0]['management_ip']
        del nodelist[0]
        for node in nodelist:
            ###
            #Need to add the error check here
            ###
            saltapi.peer(rootNode,node['management_ip'])
    
    log.debug("Failed Nodes %s" %  failedNodes)
    if noOfNodes == len(failedNodes):
        #createCluster.update_state(state='ALL_FAILURE',meta={'nodes':failedNodes})
        return {'status':'ALL_NODES_FAILURE','failednodes':str(failedNodes)}
    elif len(failedNodes)>0:
        #createCluster.update_state(state='PARTIAL_FAILURE',meta={'nodes':failedNodes})
        return {'status':'PARTIAL_FAILURE','failednodes':str(failedNodes)}
    else:
        #createCluster.update_state(state='SUCCESS')
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
    

class ClusterViewSet(viewsets.ModelViewSet):
    """
    Cluster information.
    """
    queryset = Cluster.objects.all()
    serializer_class = ClusterSerializer
    
    
    def create(self, request):
        postdata = request.POST.copy()
        postdata['cluster_id'] = uuid.uuid4()
        clusterSerilaizer = ClusterSerializer(data=postdata)
        if clusterSerilaizer.is_valid():
            clusterSerilaizer.save()
            return Response(clusterSerilaizer.data, status=201)
        return Response(clusterSerilaizer.errors, status=400)


class HostViewSet(viewsets.ModelViewSet):
    """
    Cluster information.
    """
    queryset = Host.objects.all()
    serializer_class = HostSerializer
    
    def create(self, request):
        data = request.POST.copy()
        jobId = createHost.delay(data)
        return Response(str(jobId), status=200)
   
@shared_task
def createHost(data):
    #Setup the host communication
    ssh_fingerprint = saltapi.get_fingerprint(saltapi.get_host_ssh_key(data['management_ip']))
    saltapi.setup_minion(data['management_ip'],ssh_fingerprint,data['ssh_username'], data['ssh_password'])
    time.sleep( 1 )
    saltapi.accept_minion(socket.gethostbyaddr(data['management_ip'])[0])
    
    #Now persist the host in to DB
    #
    #TODO Get the host uuid from  host and update in DB
    #
    data['node_id'] = uuid.uuid4()
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
       print "Error........." 
       print hostSerilaizer.errors 
        

