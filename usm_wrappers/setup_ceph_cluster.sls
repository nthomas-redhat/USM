{% if pillar.get('usm') %}
{% set cluster_name = pillar['usm']['cluster_name'] %}
{% set mon_name = pillar['usm'][grains['id']] %}
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

/var/lib/ceph/mon/{{ cluster_name }}-{{ mon_name }}:
  file.directory:
    - user: root
    - group: root
    - mode: 755
    - makedirs: True

populate-monitor:
  cmd.run:
    - name: ceph-mon --cluster {{ cluster_name }} --mkfs -i {{ mon_name }} --monmap /etc/ceph/{{ cluster_name }}.mon.map --keyring /etc/ceph/{{ cluster_name }}.mon.key
    - require:
      - file: /etc/ceph/{{ cluster_name }}.conf
      - file: /etc/ceph/{{ cluster_name }}.client.admin.keyring
      - file: /etc/ceph/{{ cluster_name }}.mon.key
      - file: /etc/ceph/{{ cluster_name }}.mon.map
      - file: /var/lib/ceph/mon/{{ cluster_name }}-{{ mon_name }}

/var/lib/ceph/mon/{{ cluster_name }}-{{ mon_name }}/done:
  file.touch:
  - require:
    - cmd: populate-monitor

/var/lib/ceph/mon/{{ cluster_name }}-{{ mon_name }}/sysvinit:
  file.touch:
  - require:
    - file: /var/lib/ceph/mon/{{ cluster_name }}-{{ mon_name }}/done
{% endif %}
