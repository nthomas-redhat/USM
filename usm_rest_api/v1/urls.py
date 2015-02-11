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
                       url(r'^utils/get_ssh_fingerprint/(.*)/$', v1_views.get_ssh_fingerprint),
                        url(r'^', include(router.urls)),
                      )