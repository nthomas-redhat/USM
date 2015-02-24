import time
import socket
import uuid


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


from usm_rest_api.v1.serializers.serializers import UserSerializer
from usm_rest_api.models import Cluster
from usm_rest_api.v1.serializers.serializers import ClusterSerializer
from usm_rest_api.models import Host
from usm_rest_api.v1.serializers.serializers import HostSerializer

from usm_rest_api.v1 import saltapi


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
            "node-name": "NAME",
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
    ##create the cluster configuration
    ##Setup the minions on each of the nodes and push the cluster configuration
    ##create the cluster(ex peer probe for gluster)
    ##Update the database
    
    #print request.data
    postdata = request.data.copy()
    #resultdata = request.data.copy()
    nodelist = postdata['nodes']
    del postdata['nodes']
    
     #create the cluster
    postdata['cluster_id'] = uuid.uuid4()
    #print postdata
    clusterSerilaizer = ClusterSerializer(data=postdata)
    if clusterSerilaizer.is_valid():
        #print clusterSerilaizer.validated_data
        clusterSerilaizer.save()
        #transaction.commit()
    else:
            print "Error........." 
            print clusterSerilaizer.errors
   
    #Create the Nodes in the cluster
    for node in nodelist:
        node['node_id'] = uuid.uuid4()
        node['cluster'] = str(postdata['cluster_id'])
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
               print "Error........." 
               print hostSerilaizer.errors
        except Exception, e:
            transaction.rollback()
            print str(e)

    return Response({'message': 'Success'}, status=201)


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
        print request.data
        postdata = request.POST.copy()
        postdata['cluster_id'] = uuid.uuid4()
        clusterSerilaizer = ClusterSerializer(data=postdata)
        if clusterSerilaizer.is_valid():
            print clusterSerilaizer.validated_data
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
        ssh_fingerprint = saltapi.get_fingerprint(saltapi.get_host_ssh_key(request.data['host_ip']))
        saltapi.setup_minion(request.data['host_ip'],
                                   ssh_fingerprint,
                                   request.data['ssh_username'], request.data['ssh_password'])
        time.sleep( 1 )
        saltapi.accept_minion(socket.gethostbyaddr(request.data['host_ip'])[0])

        #
        #TODO Get the host uuid from  host and update in DB
        #
        hostSerilaizer = HostSerializer(data=request.data)
        if hostSerilaizer.is_valid():
            
            #Delete all the fields those are not reqired to be persisted
            del hostSerilaizer.validated_data['ssh_password']
            del hostSerilaizer.validated_data['ssh_key_fingerprint']
            del hostSerilaizer.validated_data['ssh_username']
            del hostSerilaizer.validated_data['ssh_port']
            
            hostSerilaizer.save()
            return Response(hostSerilaizer.data, status=201)
        return Response(hostSerilaizer.errors, status=400)
   


