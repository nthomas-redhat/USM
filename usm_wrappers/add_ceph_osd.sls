{% if pillar.get('usm') %}
{% this_node = grains['id'] %}
{% set cluster_name = grains['usm_cluster_name'] %}
{% set cluster_id = grains['usm_cluster_id'] %}

/var/lib/ceph/bootstrap-osd/{{ cluster_name }}.keyring:
  file.managed:
    - source: salt://usm/conf/ceph/{{ cluster_name }}/{{ cluster_name }}.keyring
    - user: root
    - group: root
    - mode: 644
    - makedirs: True
    - show_diff: False

/etc/ceph/{{ cluster_name }}.conf:
  file.managed:
    - source: salt://usm/conf/ceph/{{ cluster_name }}/{{ cluster_name }}.conf
    - user: root
    - group: root
    - mode: 644
    - makedirs: True
    - show_diff: False

{% for osd, fstype in pillar['usm'][this_node] %}
{{ osd }}:
   file.exists

prepare-{{ osd }}:
  cmd.run:
    - name: ceph-disk prepare --cluster {{ cluster_name }} --cluster-uuid {{ cluster_id }} --fs-type {{ fstype }} {{ osd }}
    - require:
      - file: {{ osd }}

activate-{{ osd }}:
  cmd.run:
    - name: ceph-disk activate {{ osd }}1
    - require:
      - file: /etc/ceph/{{ cluster_name }}.conf
      - file: /var/lib/ceph/bootstrap-osd/{{ cluster_name }}.keyring
      - cmd: prepare-{{ osd }}
{% endfor %}

{% endif %}
