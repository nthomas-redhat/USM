from django.contrib.auth.models import User

from rest_framework import serializers

from usm_rest_api.models import Cluster
from usm_rest_api.models import Host
from usm_rest_api.models import StorageDevice
from usm_rest_api.models import DiscoveredNode
from usm_rest_api.models import HostInterface
from usm_rest_api.models import CephOSD


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the Django User model.

    Used to expose a django-rest-framework user management resource.
    """
    class Meta:
        model = User
        fields = ('id', 'username', 'password', 'email')

    def to_native(self, obj):
        # Before conversion, remove the password field. This prevents the hash
        # from being displayed when requesting user details.
        if 'password' in self.fields:
            del self.fields['password']
        return super(UserSerializer, self).to_native(obj)

    def create(self, validated_data):
        user = User.objects.create(**validated_data)
        if user:
            user.set_password(validated_data['password'])
            user.save()
        return user

    def update(self, instance, validated_data):

        instance.email = validated_data.get('email', instance.email)
        instance.username = validated_data.get('username', instance.username)
        if instance.password != validated_data.get('password'):
            instance.set_password(validated_data['password'])
        else:
            instance.password = validated_data.get(
                'password', instance.password)

        instance.save()
        return instance


class StorageDeviceSerializer(serializers.ModelSerializer):
    """
    Serializer for the Storage_Device model.

    Used to expose a usm-rest-api Storage_Device management resource.
    """
    class Meta:
        model = StorageDevice
        fields = ('storage_device_id', 'storage_device_name', 'device_uuid',
                  'filesystem_uuid', 'node', 'description', 'device_type',
                  'device_path', 'filesystem_type', 'device_mount_point')


class HostInterfaceSerializer(serializers.ModelSerializer):
    """
    Serializer for the Host_Interface model.

    Used to expose a usm-rest-api Host_Interface management resource.
    """
    class Meta:
        model = HostInterface
        fields = ('interface_id', 'interface_name', 'network_name',
                  'node', 'mac_address', 'ip_address',
                  'subnet_address', 'gateway_address')


class CephOSDSerializer(serializers.ModelSerializer):
    """
    Serializer for the Discovered_Nodes model.

    Used to expose a usm-rest-api Discovered_Nodes management resource.
    """
    class Meta:
        model = CephOSD
        fields = ('osd_id', 'node', 'storage_device')


class HostSerializer(serializers.ModelSerializer):
    """
    Serializer for the Host model.

    Used to expose a usm-rest-api Host management resource.
    """
    cluster = serializers.PrimaryKeyRelatedField(
        queryset=Cluster.objects.all())
    storageDevices = StorageDeviceSerializer(many=True, read_only=True)
    hostInterfaces = HostInterfaceSerializer(many=True, read_only=True)
    osds = CephOSDSerializer(many=True, read_only=True)

    ssh_username = serializers.CharField(
        write_only=True, max_length=255, required=False, allow_null=True)
    ssh_port = serializers.IntegerField(
        write_only=True, default=22, required=False, allow_null=True)
    ssh_key_fingerprint = serializers.CharField(
        write_only=True, max_length=128, default='', required=False,
        allow_null=True)
    ssh_password = serializers.CharField(
        write_only=True, max_length=255, required=False, allow_null=True)

    class Meta:
        model = Host
        fields = ('node_id', 'node_name', 'description', 'management_ip',
                  'cluster_ip', 'public_ip', 'cluster', 'ssh_username',
                  'ssh_port', 'ssh_key_fingerprint', 'ssh_password',
                  'node_type', 'node_status', 'storageDevices',
                  'hostInterfaces', 'osds')


class ClusterSerializer(serializers.ModelSerializer):
    """
    Serializer for the Cluster model.

    Used to expose a usm-rest-api cluster management resource.
    """
    hosts = HostSerializer(many=True, read_only=True)

    class Meta:
        model = Cluster
        fields = ('cluster_id', 'cluster_name', 'description',
                  'compatibility_version', 'cluster_type',
                  'storage_type', 'cluster_status', 'hosts')


class DiscoveredNodeSerializer(serializers.ModelSerializer):
    """
    Serializer for the Discovered_Nodes model.

    Used to expose a usm-rest-api Discovered_Nodes management resource.
    """
    class Meta:
        model = DiscoveredNode
        fields = ('node_id', 'node_name', 'management_ip')
