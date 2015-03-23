from django.conf.urls import patterns, include, url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

from djcelery import views as celery_views

urlpatterns = patterns('',
                       url(r'^api-auth/', include('rest_framework.urls',
                           namespace='rest_framework')),
                       url(r'^api/', include('usm_rest_api.urls')),
                       url(r'^(?P<task_id>[\w\d\-]+)/done/?$',
                           celery_views.is_task_successful,
                           name='celery-is_task_successful'),
                       url(r'^(?P<task_id>[\w\d\-]+)/status/?$',
                           celery_views.task_status,
                           name='celery-task_status'),)
# to stage static files
urlpatterns += staticfiles_urlpatterns()
