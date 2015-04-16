from django.conf.urls import patterns, include, url
from rest_framework import routers
from .views import views as v1_views

from djcelery import views as celery_views

router = routers.DefaultRouter(trailing_slash=False)
router.register(r'users', v1_views.UserViewSet)
router.register(r'clusters', v1_views.ClusterViewSet)
router.register(r'hosts', v1_views.HostViewSet)
router.register(r'storage-devices', v1_views.StorageDeviceViewSet)
router.register(r'discovered-hosts', v1_views.DiscoveredNodeViewSet)
router.register(r'host-interfaces', v1_views.HostInterfaceViewSet)
router.register(r'ceph/osds', v1_views.CephOSDViewSet)


urlpatterns = patterns('',
                       url(r'^auth/login', v1_views.login),
                       url(r'^auth/logout', v1_views.logout),
                       url(r'^utils/get_ssh_fingerprint/(?P<ip_address>'
                           r'((2[0-5]|1[0-9]|[0-9])?[0-9]\.){3}((2[0-5]|'
                           r'1[0-9]|[0-9])?[0-9]))$',
                           v1_views.get_ssh_fingerprint),
                       url(r'^utils/resolve_ip_address/(?P<ip_address>'
                           r'((2[0-5]|1[0-9]|[0-9])?[0-9]\.){3}((2[0-5]|1'
                           r'[0-9]|[0-9])?[0-9]))$',
                           v1_views.resolve_ip_address),
                       url(r'^utils/resolve_hostname/(?P<hostname>'
                           r'(?:(?:(?:(?:[a-zA-Z0-9][-a-zA-Z0-9]{0,61})?'
                           r'[a-zA-Z0-9])[.])*(?:[a-zA-Z][-a-zA-Z0-9]{0,61}'
                           r'[a-zA-Z0-9]|[a-zA-Z])[.]?))$',
                           v1_views.resolve_hostname),
                       url(r'tasks/^(?P<task_id>[\w\d\-]+)/done/?$',
                           celery_views.is_task_successful,
                           name='celery-is_task_successful'),
                       url(r'^tasks/(?P<task_id>[\w\d\-]+)/status/?$',
                           celery_views.task_status,
                           name='celery-task_status'),
                       url(r'^tasks/?$',
                           celery_views.registered_tasks,
                           name='celery-tasks'),
                       url(r'^utils/validate-host', v1_views.validate_host),
                       url(r'^', include(router.urls)),)
