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
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from usm_rest_api.v1.serializers.serializers import UserSerializer
from usm_rest_api.models import Cluster
from usm_rest_api.v1.serializers.serializers import ClusterSerializer
from usm_rest_api.models import Host
from usm_rest_api.v1.serializers.serializers import HostSerializer

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
                return Response(
                    {'message': 'User Account Disbaled'},
                    status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response(
                {'message': 'User authentication failed'},
                status=status.HTTP_401_UNAUTHORIZED)
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
        return Response(str(jobId), status=201)


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
        return Response(str(jobId), status=201)
