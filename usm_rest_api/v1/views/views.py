import logging
import copy

from django.core.exceptions import PermissionDenied
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User

from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets, mixins
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import detail_route
from rest_framework.decorators import list_route

from usm_rest_api.v1.serializers.serializers import UserSerializer
from usm_rest_api.models import Cluster
from usm_rest_api.v1.serializers.serializers import ClusterSerializer
from usm_rest_api.models import Host
from usm_rest_api.v1.serializers.serializers import HostSerializer
from usm_rest_api.v1.serializers.serializers import StorageDeviceSerializer
from usm_rest_api.models import StorageDevice
from usm_rest_api.v1.serializers.serializers import DiscoveredNodeSerializer
from usm_rest_api.models import DiscoveredNode
from usm_rest_api.v1.serializers.serializers import HostInterfaceSerializer
from usm_rest_api.models import HostInterface
from usm_rest_api.v1.serializers.serializers import CephOSDSerializer
from usm_rest_api.models import CephOSD
from usm_rest_api.v1.serializers.serializers import GlusterBrickSerializer
from usm_rest_api.models import GlusterBrick
from usm_rest_api.v1.serializers.serializers import GlusterVolumeSerializer
from usm_rest_api.models import GlusterVolume
from usm_rest_api.v1.serializers.serializers import CephPoolSerializer
from usm_rest_api.models import CephPool

from usm_wrappers import utils as usm_wrapper_utils

from usm_rest_api.v1.views import utils as usm_rest_utils
from usm_rest_api.v1.views import tasks


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
        username = request.data.get('username', None)
        password = request.data.get('password', None)
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
                return Response(
                    {'message': 'User Account Disbaled'},
                    status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response(
                {'message': 'User authentication failed'},
                status=status.HTTP_401_UNAUTHORIZED)
        if request.session.test_cookie_worked():
            request.session.delete_test_cookie()
        return Response({'message': 'Logged in'})
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
def get_ssh_fingerprint(request, ip_address):
    """
The resource is used to get the ssh fingerprint from a
remote host:

    """
    try:
        ssh_fingerprint = usm_wrapper_utils.get_host_ssh_key(ip_address)
    except Exception, e:
        log.exception(e)
        return Response(
            {'message': 'Error while getting fingerprint'}, status=417)

    return Response({'ssh_key_fingerprint': ssh_fingerprint[0]}, status=200)


@api_view(['GET'])
@permission_classes((IsAuthenticated,))
def resolve_hostname(request, hostname):
    """
The resource is used to get the ip address from a
hostname:

    """
    try:
        ipaddress = usm_wrapper_utils.resolve_hostname(hostname)
    except Exception, e:
        log.exception(e)
        return Response(
            {'message': 'Error while resolving hostname'}, status=417)

    return Response({'IP_Address': ipaddress}, status=200)


@api_view(['GET'])
@permission_classes((IsAuthenticated,))
def resolve_ip_address(request, ip_address):
    """
The resource is used to get the hostname from a
ip address:

    """
    try:
        hostname = usm_wrapper_utils.resolve_ip_address(ip_address)
    except Exception, e:
        log.exception(e)
        return Response(
            {'message': 'Error while resolving IP Address'}, status=417)

    return Response({'Hostname': hostname}, status=200)


@api_view(['GET', 'POST'])
@permission_classes((IsAuthenticated,))
def validate_host(request):
    """
The resource is used to validate the host details before adding
to the cluster by POSTing a message as follows:

::

    {
        "host": "<ip address>",
        "port": "<ssh port>"
        "fingerprint": <ssh fingerprint>
        "username": <ssh username>
        "password": <ssh password>
    }:

    """
    log.debug(
        "Inside validate_host. Request Data: %s" % request.data)
    if request.method == 'POST':
        try:
            status = usm_wrapper_utils.check_host_ssh_auth(
                request.data['host'],
                request.data['port'],
                request.data['fingerprint'],
                request.data['username'],
                request.data['password'])
            if status:
                return Response({'message': 'Success'}, status=200)
            else:
                return Response({'message': 'Failed'}, status=417)
        except Exception, e:
            log.exception(e)
            return Response(
                {'message': 'Failed'}, status=417)
    else:
        return Response({})


@api_view(['GET', 'POST'])
@permission_classes((IsAuthenticated,))
def accept_hosts(request):
    """
The resource is used to setup the salt communication and
add the host to USM by POSTing a message as follows:

::

    "nodes": [
          {
              "node_name": "NAME",
              "management_ip": "ADDR",
              "ssh_username": "USER",
              "ssh_password": "PASS",
              "ssh_key_fingerprint": "FINGER",
              "ssh_port": 22,
          },
          {

          } ]:

    """
    log.debug(
        "Inside accept_hosts. Request Data: %s" % request.data)
    if request.method == 'POST':
        data = copy.deepcopy(request.data.copy())
        jobId = tasks.acceptHosts.delay(data)
        log.debug("Exiting ... JobID: %s" % jobId)
        return Response(str(jobId), status=202)
    else:
        return Response({})


class ClusterViewSet(viewsets.ModelViewSet):
    """
      The resource is used to manage a cluster with a list of hosts. Cluster
      can be created by posting a message as follows:

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
              "node_type": "nodetype"
          },
          {

          } ]
      }
      """
    queryset = Cluster.objects.all()
    serializer_class = ClusterSerializer

    def create(self, request):

        log.debug("Inside Cluster Create. Request Data: %s" % request.data)
        data = copy.deepcopy(request.data.copy())
        log.debug(data)
        jobId = None
        #
        # Check the type of the cluster to be created and call appropriate task
        #
        log.debug(data['cluster_type'])
        log.debug(usm_rest_utils.CLUSTER_TYPE_GLUSTER)
        if data['cluster_type'] == usm_rest_utils.CLUSTER_TYPE_GLUSTER:
            log.debug("Gluster cluster create")
            jobId = tasks.createGlusterCluster.delay(data)
        else:
            log.debug("Ceph cluster create")
            jobId = tasks.createCephCluster.delay(data)

        log.debug("Exiting create_cluster JobID: %s" % jobId)
        return Response(str(jobId), status=202)

    @detail_route(methods=['get'],
                  permission_classes=[permissions.IsAuthenticated])
    def hosts(self, request, pk=None):
        log.debug("Inside get hosts")
        hosts = Host.objects.filter(cluster_id=pk)
        serializer = HostSerializer(hosts, many=True,
                                    context={'request': request})
        return Response(serializer.data)

    @detail_route(methods=['get'],
                  permission_classes=[permissions.IsAuthenticated])
    def volumes(self, request, pk=None):
        log.debug("Inside get volumes details")
        volumes = GlusterVolume.objects.filter(cluster_id=pk)
        serializer = GlusterVolumeSerializer(volumes, many=True,
                                             context={'request': request})
        return Response(serializer.data)


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
    Host information.
    """
    queryset = Host.objects.all()
    serializer_class = HostSerializer

    def create(self, request):
        log.debug(
            "Inside HostViewSet Create. Request Data: %s" % request.data)
        data = copy.deepcopy(request.data.copy())
        jobId = None
        #
        # Check the type of the host to be created and call appropriate task
        #
        if data['node_type'] == usm_rest_utils.HOST_TYPE_GLUSTER:
            # Create a host and add to gluster cluster
            jobId = tasks.createGlusterHost.delay(data)
        else:
            # Create a node and add to the Ceph Cluster
            jobId = tasks.createCephHost.delay(data)

        log.debug("Exiting ... JobID: %s" % jobId)
        return Response(str(jobId), status=202)

    @detail_route(methods=['get'],
                  permission_classes=[permissions.IsAuthenticated],
                  url_path='storage-devices')
    def storageDevices(self, request, pk=None):
        storageDevices = StorageDevice.objects.filter(node_id=pk)
        serializer = StorageDeviceSerializer(
            storageDevices, many=True,
            context={'request': request})
        return Response(serializer.data)

    @detail_route(methods=['get'],
                  permission_classes=[permissions.IsAuthenticated],
                  url_path='host-interfaces')
    def hostInterfaces(self, request, pk=None):
        hostInterfaces = HostInterface.objects.filter(node_id=pk)
        serializer = HostInterfaceSerializer(
            hostInterfaces, many=True,
            context={'request': request})
        return Response(serializer.data)

    @detail_route(methods=['get'],
                  permission_classes=[permissions.IsAuthenticated])
    def osds(self, request, pk=None):
        osds = CephOSD.objects.filter(node_id=pk)
        serializer = CephOSDSerializer(osds, many=True,
                                       context={'request': request})
        return Response(serializer.data)

    @detail_route(methods=['get'],
                  permission_classes=[permissions.IsAuthenticated])
    def bricks(self, request, pk=None):
        bricks = GlusterBrick.objects.filter(node_id=pk)
        serializer = GlusterBrickSerializer(bricks, many=True,
                                            context={'request': request})
        return Response(serializer.data)


class StorageDeviceViewSet(mixins.RetrieveModelMixin,
                           mixins.ListModelMixin,
                           mixins.UpdateModelMixin,
                           viewsets.GenericViewSet):
    """
    Storage_Device information.
    """
    queryset = StorageDevice.objects.all()
    serializer_class = StorageDeviceSerializer


class DiscoveredNodeViewSet(mixins.RetrieveModelMixin,
                            mixins.ListModelMixin,
                            viewsets.GenericViewSet):
    """
    Discovered_Nodes information.
    """
    queryset = DiscoveredNode.objects.all()
    serializer_class = DiscoveredNodeSerializer

    @list_route(methods=['post', 'get'],
                permission_classes=[permissions.IsAuthenticated],
                url_path='accept-hosts')
    def accept_hosts(self, request):
        if request.method == 'POST':
            log.debug("Inside accept hosts. Request Data: %s" % request.data)
            data = copy.deepcopy(request.data.copy())
            jobId = tasks.acceptHosts.delay(data)
            log.debug("Exiting ... JobID: %s" % jobId)
            return Response(str(jobId), status=202)
        elif request.method == 'GET':
            return Response({})


class HostInterfaceViewSet(mixins.RetrieveModelMixin,
                           mixins.ListModelMixin,
                           viewsets.GenericViewSet):
    """
    Host interfaces information.
    """
    queryset = HostInterface.objects.all()
    serializer_class = HostInterfaceSerializer


class CephOSDViewSet(viewsets.ModelViewSet):
    """
      The resource is used to manage a Ceph OSDs.
      OSD can be created by posting a message as follows:

      {
        "osds": [
          {
              "node": "node uuid",
              "storage_device": "storage_device uuid"
          },
          {

          } ]
      }
    """
    queryset = CephOSD.objects.all()
    serializer_class = CephOSDSerializer

    def create(self, request):
        log.debug(
            "Inside CephOSDViewSet Create. Request Data: %s" % request.data)
        data = copy.deepcopy(request.data.copy())
        jobId = tasks.createCephOSD.delay(data)
        log.debug("Exiting ... JobID: %s" % jobId)
        return Response(str(jobId), status=202)


class GlusterVolumeViewSet(viewsets.ModelViewSet):
    """
      The resource is used to manage a Volume with a list of bricks.
      Volume can be created by posting a message as follows:

      {
      "cluster": "cluster uuid"
      "volume_name": "NAME",
      "volume_type": 1,
      "replica_count": 3,
      "bricks": [
          {
              "node": "node uuid",
              "brick_path": "node:/dev/vdc",
              "storage_device": "storage_device uuid",
          },
          {

          } ]
      }
      """
    queryset = GlusterVolume.objects.all()
    serializer_class = GlusterVolumeSerializer

    def create(self, request):
        log.debug(
            "Inside GlusterVolumeViewSet Create. Request Data: %s"
            % request.data)
        data = copy.deepcopy(request.data.copy())
        jobId = tasks.createGlusterVolume.delay(data)
        log.debug("Exiting ... JobID: %s" % jobId)
        return Response(str(jobId), status=202)

    def destroy(self, request, pk=None):
        log.debug(
            "Inside GlusterVolumeViewSet destroy. pk: %s" % pk)
        rc = usm_rest_utils.delete_gluster_volume(pk)
        if rc is True:
            return super(GlusterVolumeViewSet, self).destroy(request, pk)
        else:
            return Response(
                {'message': 'Error while Starting the Volume'}, status=417)

    @detail_route(methods=['get', 'post'],
                  permission_classes=[permissions.IsAuthenticated])
    def bricks(self, request, pk=None):
        if request.method == 'GET':
            log.debug("Inside get volumes details")
            bricks = GlusterBrick.objects.filter(volume_id=pk)
            serializer = GlusterBrickSerializer(bricks, many=True,
                                                context={'request': request})
            return Response(serializer.data)
        elif request.method == 'POST':
            log.debug("POST")
            data = copy.deepcopy(request.data.copy())
            jobId = tasks.createGlusterBrick.delay(data)
            log.debug("Exiting ... JobID: %s" % jobId)
            return Response(str(jobId), status=201)

    @detail_route(methods=['get', 'post'],
                  permission_classes=[permissions.IsAuthenticated])
    def start(self, request, pk=None):
        log.debug("Inside get volumes start pk: %s" % pk)
        rc = usm_rest_utils.start_gluster_volume(pk)
        if rc is True:
            return Response({'message': "Success"}, status=200)
        else:
            return Response(
                {'message': 'Error while Starting the Volume'}, status=417)

    @detail_route(methods=['get', 'post'],
                  permission_classes=[permissions.IsAuthenticated])
    def stop(self, request, pk=None):
        log.debug("Inside get volumes stop")
        rc = usm_rest_utils.stop_gluster_volume(pk)
        if rc is True:
            return Response({'message': "Success"}, status=200)
        else:
            return Response(
                {'message': 'Error while Stopping the Volume'}, status=417)


class GlusterBrickViewSet(viewsets.ModelViewSet):
    """
    Gluster Brick information.
    """
    queryset = GlusterBrick.objects.all()
    serializer_class = GlusterBrickSerializer

    def create(self, request):
        log.debug(
            "Inside GlusterBrickViewSet Create. Request Data: %s"
            % request.data)
        data = copy.deepcopy(request.data.copy())
        jobId = tasks.createGlusterBrick.delay(data)
        log.debug("Exiting ... JobID: %s" % jobId)
        return Response(str(jobId), status=202)


class CephPoolViewSet(viewsets.ModelViewSet):
    """
      The resource is used to manage a Ceph Pools.
      Pool can be created by posting a message as follows:

      {
        "cluster": "cluster uuid"
        "pools": [
          {
              "pool_name": "Name of the pool to be created",
              "pg_num": "pg number"
          },
          {

          } ]
      }
    """
    queryset = CephPool.objects.all()
    serializer_class = CephPoolSerializer

    def create(self, request):
        log.debug(
            "Inside CephPoolViewSet Create. Request Data: %s" % request.data)
        data = copy.deepcopy(request.data.copy())
        jobId = tasks.createCephPool.delay(data)
        log.debug("Exiting ... JobID: %s" % jobId)
        return Response(str(jobId), status=202)
