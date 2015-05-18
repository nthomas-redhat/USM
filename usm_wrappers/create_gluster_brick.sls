{% if pillar.get('usm') %}
{% set this_node = grains['id'] %}
{% set device = pillar['usm'][this_node]['device'] %}
{% set fs_type = pillar['usm'][this_node]['fs_type'] %}
{% set brick_name = pillar['usm'][this_node]['brick_name'] %}

mklabel:
  cmd.run:
    - name: parted --script --align optimal {{ device }} mklabel gpt
    - onlyif: lsblk --nodeps -n -o TYPE {{ device }} | grep -q 'disk'

mkpart:
  cmd.run:
    - name: parted --script --align optimal {{ device }} mkpart primary {{ fs_type }} 0% 100%
    - require:
      - cmd: mklabel

mkfs:
  cmd.run:
    - name: mkfs.xfs -f -i size=512 {{ device }}1
    - require:
      - cmd: mkpart

/bricks/{{ brick_name }}:
  file.directory:
    - user: root
    - group: root
    - mode: 755
    - makedirs: True
    - require:
      - cmd: mkfs

mount:
  mount.mounted:
    - name: /bricks/{{ brick_name }}
    - device: {{ device }}1
    - fstype: xfs
    - mkmnt: True
    - require:
      - file: /bricks/{{ brick_name }}

{% endif %}
