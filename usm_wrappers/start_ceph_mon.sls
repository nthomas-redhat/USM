{% set cluster_name = grains['usm_cluster_name'] %}
{% set mon_name = grains['usm_mon_name'] %}

start_ceph_mon:
  cmd.run:
    - name: service ceph --cluster {{ cluster_name }} start mon.{{ mon_name }}
