from django.db import models
from django.utils.translation import ugettext_lazy as _

from django_extensions.db.fields import UUIDField


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
    
    cluster_id = UUIDField(auto=True, primary_key=True)
    name = models.CharField(max_length=40, blank=True, default='')
    description = models.CharField(max_length=4000, blank=True, null=True, default='')
    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    compatibility_version = models.CharField(max_length=40, default='1.0')
    cluster_type = models.SmallIntegerField(choices=CLUSTER_TYPE_CHOICES)
    storage_type = models.SmallIntegerField(choices=STORAGE_TYPE_CHOICES)
    cluster_status = models.SmallIntegerField(choices=STATUS_CHOICES, default=STATUS_INACTIVE)
    
    def __str__(self):
        return self.name
    
    
class Host(models.Model):
    """ Model representing a storage Node"""
    
    HOST_TYPE_MONITOR = 1
    HOST_TYPE_OSD = 2
    HOST_TYPE_MIXED = 3
    HOST_TYPE_CHOICES = (
        (HOST_TYPE_MONITOR, _('Monitor Host')),
        (HOST_TYPE_OSD, _('OSD Host')),
        (HOST_TYPE_MIXED, _('OSD and Monitor')),
    )
    
    host_id = UUIDField(auto=True, primary_key=True)
    host_name = models.CharField(max_length=40)
    description = models.CharField(max_length=4000, blank=True, null=True, default='')
    host_ip = models.CharField(max_length=255)
    host_unique_id = models.CharField(max_length=128, blank=True, null=True, default='')
    cluster = models.ForeignKey(Cluster)
    #server_ssl_enabled = models.BooleanField(default=True)
    #ssh_username = models.CharField(max_length=255)
    #ssh_password = models.CharField(max_length=255)
    #ssh_port = models.IntegerField(default=22)
    #ssh_key_fingerprint = models.CharField(max_length=128, blank=True, null=True, default='')
    host_type = models.SmallIntegerField(choices=HOST_TYPE_CHOICES)
    
    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.host_name
    

class Host_interface(models.Model):
    interface_id = UUIDField(auto=True, primary_key=True)
    name = models.CharField(max_length=40, blank=True, default='')
    network_name = models.CharField(max_length=40, blank=True, null=True)
    host_id = models.ForeignKey(Host)
    mac_address = models.CharField(max_length=60, blank=True, null=True)
    is_bond = models.BooleanField(default=False)
    bond_name = models.CharField(max_length=50, blank=True, null=True)
    speed = models.IntegerField()
    def __str__(self):
        return self.host_name