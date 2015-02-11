from django.conf.urls import patterns, include, url
from .v1 import urls as v1_urls

urlpatterns = patterns('',
                        url(r'^v1/', include(v1_urls, namespace='v1')),
                        )