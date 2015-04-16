from django.db import models
from django.utils.translation import ugettext_lazy as _

from django_extensions.db.fields import UUIDField

STATUS_UP = 0
STATUS_WARNING = 1
STATUS_DOWN = 2
STATUS_UNKNOWN = 3
STATUS_CREATED = 4

GEN_STATUS_CHOICES = (
    (STATUS_UP, _('UP')),
    (STATUS_WARNING, _('WARNING')),
    (STATUS_DOWN, _('DOWN')),
    (STATUS_UNKNOWN, _('UNKNOWN')),
    (STATUS_CREATED, _('CREATED')),
)


class Cluster(models.Model):
    """ Model representing a storage cluster"""

    CLUSTER_TYPE_GLUSTER = 1
    CLUSTER_TYPE_CEPH = 2
    CLUSTER_TYPE_CHOICES = (
        (CLUSTER_TYPE_GLUSTER, _('Gluster Cluster')),
        (CLUSTER_TYPE_CEPH, _('Ceph Cluster')),
    )

    STORAGE_TYPE_BLOCK = 1
    STORAGE_TYPE_FILE = 2
    STORAGE_TYPE_OBJECT = 3
    STORAGE_TYPE_CHOICES = (
        (STORAGE_TYPE_BLOCK, _('Block Storage')),
        (STORAGE_TYPE_FILE, _('File Storage')),
        (STORAGE_TYPE_OBJECT, _('Object Storage')),
    )

    STATUS_INACTIVE = 1
    STATUS_ACTIVE_NOT_AVAILABLE = 2
    STATUS_ACTIVE_AND_AVAILABLE = 3

    STATUS_CHOICES = (
        (STATUS_INACTIVE, _('Inactive')),
        (STATUS_ACTIVE_NOT_AVAILABLE, _('Active but Not Available')),
        (STATUS_ACTIVE_AND_AVAILABLE, _('Active and Available')),
    )

    cluster_id = UUIDField(auto=False, primary_key=True)
    cluster_name = models.CharField(max_length=40)
    description = models.CharField(
        max_length=4000, blank=True, null=True, default='')
    compatibility_version = models.CharField(
        max_length=40, blank=True, null=True, default='1.0')
    cluster_type = models.SmallIntegerField(choices=CLUSTER_TYPE_CHOICES)
    storage_type = models.SmallIntegerField(choices=STORAGE_TYPE_CHOICES)
    cluster_status = models.SmallIntegerField(
        choices=STATUS_CHOICES, blank=True, null=True,
        default=STATUS_INACTIVE)

    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.cluster_name


class Host(models.Model):
    """ Model representing a storage Node"""

    HOST_TYPE_MONITOR = 1
    HOST_TYPE_OSD = 2
    HOST_TYPE_MIXED = 3
    HOST_TYPE_GLUSTER = 4
    HOST_TYPE_CHOICES = (
        (HOST_TYPE_MONITOR, _('Monitor Host')),
        (HOST_TYPE_OSD, _('OSD Host')),
        (HOST_TYPE_MIXED, _('OSD and Monitor')),
        (HOST_TYPE_GLUSTER, _('Gluster Host')),
    )

    HOST_STATUS_INACTIVE = 1
    HOST_STATUS_ACTIVE = 2
    HOST_STATUS_CHOICES = (
        (HOST_STATUS_INACTIVE, _('Inactive')),
        (HOST_STATUS_ACTIVE, _('Active')),
    )

    node_id = UUIDField(auto=False, primary_key=True)
    node_name = models.CharField(max_length=40)
    description = models.CharField(
        max_length=4000, blank=True, null=True, default='')
    management_ip = models.CharField(max_length=255)
    cluster_ip = models.CharField(max_length=255)
    public_ip = models.CharField(max_length=255)
    cluster = models.ForeignKey(Cluster)
    node_type = models.SmallIntegerField(choices=HOST_TYPE_CHOICES)
    node_status = models.SmallIntegerField(
        choices=HOST_STATUS_CHOICES, blank=True, null=True,
        default=HOST_STATUS_INACTIVE)
    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.node_name


class StorageDevice(models.Model):
    storage_device_id = UUIDField(auto=True, primary_key=True, max_length=100)
    storage_device_name = models.CharField(max_length=1000)
    device_uuid = UUIDField(blank=True, null=True, max_length=100)
    filesystem_uuid = UUIDField(blank=True, null=True, max_length=100)
    node = models.ForeignKey(Host)
    description = models.CharField(
        max_length=4000, blank=True, null=True, default='')
    device_type = models.CharField(
        max_length=50, blank=True, null=True, default='')
    device_path = models.CharField(
        max_length=4096, blank=True, null=True, default='')
    filesystem_type = models.CharField(
        max_length=50, blank=True, null=True, default='')
    device_mount_point = models.CharField(
        max_length=4096, blank=True, null=True, default='')
    size = models.FloatField(blank=True, null=True)
    inuse = models.BooleanField(default=False)

    def __str__(self):
        return self.storage_device_name


class DiscoveredNode(models.Model):
    node_id = UUIDField(auto=True, primary_key=True)
    node_name = models.CharField(max_length=40)
    management_ip = models.CharField(max_length=255)


class HostInterface(models.Model):
    interface_id = UUIDField(auto=True, primary_key=True)
    interface_name = models.CharField(max_length=40, blank=True, default='')
    network_name = models.CharField(max_length=40, blank=True, null=True)
    node = models.ForeignKey(Host)
    mac_address = models.CharField(max_length=60, blank=True, null=True)
    ip_address = models.CharField(max_length=20, blank=True, null=True)
    subnet_address = models.CharField(max_length=20, blank=True, null=True)
    gateway_address = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.interface_name


class CephOSD(models.Model):
    osd_id = UUIDField(auto=True, primary_key=True)
    node = models.ForeignKey(Host)
    storage_device = models.ForeignKey(StorageDevice)
    osd_status = models.SmallIntegerField(choices=GEN_STATUS_CHOICES)


class GlusterVolume(models.Model):
    VOLUME_TYPE_DISTRIBUTE = 1
    VOLUME_TYPE_DISTRIBUTE_REPLICATE = 2
    VOLUME_TYPE_REPLICATE = 3
    VOLUME_TYPE_STRIPE = 4
    VOLUME_TYPE_STRIPE_REPLICATE = 5
    VOLUME_TYPE_CHOICES = (
        (VOLUME_TYPE_DISTRIBUTE, _('Distributed volume')),
        (VOLUME_TYPE_DISTRIBUTE_REPLICATE, _('Distributed Replicate volume')),
        (VOLUME_TYPE_REPLICATE, _('Replicated Volume')),
        (VOLUME_TYPE_STRIPE, _('Striped Volume')),
        (VOLUME_TYPE_STRIPE_REPLICATE, _('Striped Replicate Volume')),
    )
    volume_id = UUIDField(auto=False, primary_key=True)
    cluster = models.ForeignKey(Cluster)
    volume_name = models.CharField(max_length=40)
    volume_type = models.SmallIntegerField(choices=VOLUME_TYPE_CHOICES)
    replica_count = models.SmallIntegerField(default=0)
    stripe_count = models.SmallIntegerField(default=0)
    volume_status = models.SmallIntegerField(
        choices=GEN_STATUS_CHOICES, default=4)


class GlusterBrick(models.Model):
    brick_id = UUIDField(auto=True, primary_key=True)
    volume = models.ForeignKey(GlusterVolume)
    node = models.ForeignKey(Host)
    brick_path = models.CharField(max_length=4096)
    storage_device = models.ForeignKey(StorageDevice)
    brick_status = models.SmallIntegerField(
        choices=GEN_STATUS_CHOICES, default=3)
