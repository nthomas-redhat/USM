from django.conf.urls import patterns, include, url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

from djcelery import views as celery_views

urlpatterns = patterns('',
                       url(r'^api-auth/', include('rest_framework.urls',
                           namespace='rest_framework')),
                       url(r'^api/', include('usm_rest_api.urls')),)
# to stage static files
urlpatterns += staticfiles_urlpatterns()
