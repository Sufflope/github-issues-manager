{% load staticfiles frontutils %}

{%  if headwayapp_account %}
var HW_config = {
    selector: "body > header .brand",
    account: "{{ headwayapp_account }}",
    translations: {
        title: "{{ brand.short_name }} changelog",
        readMore: "Read more"
    }
};
{% endif %}

var AppGlobal = {
    InitData: {
        software: {
            name: "{{ brand.short_name }}",
            version: "{{ gim_version }}"
        },
        select2_statics: {css: '{% static "front/css/select.2.css" %}', js: '{% static "front/js/select.2.js" %}'},
        auth_keys: {
            key1: "{{ auth_keys.key1 }}",
            key2: "{{ auth_keys.key2 }}"
        },
        dynamic_favicon_colors: {
            background: "{{ dynamic_favicon_colors.background }}",
            text: "{{ dynamic_favicon_colors.text }}"
        },
        WS_uri: "{{ WS.uri }}",
        WS_user_topic_key: "{{ wamp_topic_key }}",
        WS_last_msg_id: {{ WS.last_msg_id }}
    }
};
