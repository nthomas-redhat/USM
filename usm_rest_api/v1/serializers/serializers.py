from django.contrib.auth.models import User

from rest_framework import serializers

from usm_rest_api.models import Cluster
from usm_rest_api.models import Host


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


class ClusterSerializer(serializers.ModelSerializer):
    """
    Serializer for the Cluster model.

    Used to expose a usm-rest-api cluster management resource.
    """
    class Meta:
        model = Cluster
        fields = ('cluster_id', 'cluster_name', 'description',
                  'compatibility_version', 'cluster_type',
                  'storage_type', 'cluster_status')


class HostSerializer(serializers.ModelSerializer):
    """
    Serializer for the Cluster model.

    Used to expose a usm-rest-api cluster management resource.
    """
    cluster = serializers.PrimaryKeyRelatedField(
        queryset=Cluster.objects.all())

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
                  'node_type', 'node_status')
