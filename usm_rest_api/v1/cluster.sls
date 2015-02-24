###
#
# * The state file to create/update cluster configuration file
# * This state file has to be called with appropriate pillars
# * otherwise existing configuration will be lost
# * created/updated cluster configuration file is internally used
# * as grains
#
###

#/etc/usm/cluster:
#  file.present
  
{% if pillar.get('usm_cluster_name') %}
/etc/usm/cluster:
  file.managed:
    - source: salt://cluster-template
    - user: root
    - group: root
    - mode: 644
    - template: jinja
{% endif %}
