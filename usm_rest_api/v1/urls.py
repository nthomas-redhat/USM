from django.conf.urls import patterns, include, url
from rest_framework import routers
from .views import views as v1_views

router = routers.DefaultRouter()
router.register(r'users', v1_views.UserViewSet)
router.register(r'clusters', v1_views.ClusterViewSet)
router.register(r'hosts', v1_views.HostViewSet)


urlpatterns = patterns('',
                       url(r'^auth/login', v1_views.login),
                       url(r'^auth/logout', v1_views.logout),
                       url(r'^utils/get_ssh_fingerprint/(?P<ip_address>((2[0-5]|1[0-9]|[0-9])?[0-9]\.){3}((2[0-5]|1[0-9]|[0-9])?[0-9]))/$',
                           v1_views.get_ssh_fingerprint),
                       url(r'^utils/resolve_ip_address/(?P<ip_address>((2[0-5]|1[0-9]|[0-9])?[0-9]\.){3}((2[0-5]|1[0-9]|[0-9])?[0-9]))/$',
                           v1_views.resolve_ip_address),
                       url(r'^utils/resolve_hostname/(?P<hostname>(?:(?:(?:(?:[a-zA-Z0-9][-a-zA-Z0-9]{0,61})?[a-zA-Z0-9])[.])*(?:[a-zA-Z][-a-zA-Z0-9]{0,61}[a-zA-Z0-9]|[a-zA-Z])[.]?))/$',
                           v1_views.resolve_hostname),
                       url(r'^', include(router.urls)),
                      )