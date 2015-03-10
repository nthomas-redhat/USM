{% if pillar.get('usm') %}
{% set this_node = grains['id'] %}
{% set cluster_name = pillar['usm'][this_node]['cluster_name'] %}
{% set mon_id = pillar['usm'][this_node]['mon_id'] %}
{% set mon_name = pillar['usm'][this_node]['mon_name'] %}
{% set port = pillar['usm'][this_node].get('port') %}

usm_node_type:
  grains.present:
    - value: mon

usm_mon_id:
  grains.present:
    - value: {{ mon_id }}

usm_mon_name:
  grains.present:
    - value: {{ mon_name }}

/etc/ceph/{{ cluster_name }}.conf:
  file.managed:
    - source: salt://usm/conf/ceph/{{ cluster_name }}/{{ cluster_name }}.conf
    - user: root
    - group: root
    - mode: 644
    - makedirs: True
    - show_diff: False

/etc/ceph/{{ cluster_name }}.client.admin.keyring:
  file.managed:
    - source: salt://usm/conf/ceph/{{ cluster_name }}/client.admin.keyring
    - user: root
    - group: root
    - mode: 644
    - makedirs: True
    - show_diff: False

/etc/ceph/{{ cluster_name }}.mon.key:
  file.managed:
    - source: salt://usm/conf/ceph/{{ cluster_name }}/mon.key
    - user: root
    - group: root
    - mode: 644
    - makedirs: True
    - show_diff: False

/etc/ceph/{{ cluster_name }}.mon.map:
  file.managed:
    - source: salt://usm/conf/ceph/{{ cluster_name }}/mon.map
    - user: root
    - group: root
    - mode: 644
    - makedirs: True
    - show_diff: False

/var/lib/ceph/mon/{{ cluster_name }}-{{ mon_id }}:
  file.directory:
    - user: root
    - group: root
    - mode: 755
    - makedirs: True

populate-monitor:
  cmd.run:
    - name: ceph-mon --cluster {{ cluster_name }} --mkfs -i {{ mon_id }} --monmap /etc/ceph/{{ cluster_name }}.mon.map --keyring /etc/ceph/{{ cluster_name }}.mon.key
    - require:
      - file: /etc/ceph/{{ cluster_name }}.conf
      - file: /etc/ceph/{{ cluster_name }}.client.admin.keyring
      - file: /etc/ceph/{{ cluster_name }}.mon.key
      - file: /etc/ceph/{{ cluster_name }}.mon.map
      - file: /var/lib/ceph/mon/{{ cluster_name }}-{{ mon_id }}

/var/lib/ceph/mon/{{ cluster_name }}-{{ mon_id }}/done:
  file.touch:
  - require:
    - cmd: populate-monitor

/var/lib/ceph/mon/{{ cluster_name }}-{{ mon_id }}/sysvinit:
  file.touch:
  - require:
    - file: /var/lib/ceph/mon/{{ cluster_name }}-{{ mon_id }}/done

start_ceph_mon:
  cmd.run:
    - name: service ceph --cluster {{ cluster_name }} start mon.{{ mon_id }}
    - require:
      - file: /var/lib/ceph/mon/{{ cluster_name }}-{{ mon_id }}/sysvinit

{% if not pillar['usm'].get('mon_bootstrap') %}
add-monitor:
  cmd.run:
    - name: ceph --cluster {{ cluster_name }} mon add {{ mon_id }} {{ pillar['usm'][this_node]['public_ip'] }}
    - require:
      - cmd: start_ceph_mon
{% endif %}
{% endif %}
