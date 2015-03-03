{% if pillar.get('usm') %}
/etc/usm/cluster:
  file.managed:
    - user: root
    - group: root
    - mode: 644
    - template: jinja
    - makedirs: True
    - show_diff: False
    - contents: |
        grains:
        {% for k,v in pillar['usm'].iteritems() %}  usm_{{ k }}: {{ v }}
        {% endfor %}
{% endif %}
