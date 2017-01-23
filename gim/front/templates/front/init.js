{% load staticfiles frontutils %}
var software = {
    name: "{{ brand.short_name }}",
    version: "{{ gim_version }}",
    foo: 1
};
var select2_statics = {css: '{% static "front/css/select.2.css" %}', js: '{% static "front/js/select.2.js" %}'};
var default_avatar = "{{ default_avatar }}";
var auth_keys = {
  key1: "{{ auth_keys.key1 }}",
  key2: "{{ auth_keys.key2 }}"
};
var WS_uri = "{{ WS.uri }}";
var WS_last_msg_id = {{ WS.last_msg_id }};
var WS_user_topic_key = "{{ wamp_topic_key }}";
var dynamic_favicon_colors = {
    background: "{{ dynamic_favicon_colors.background }}",
    text: "{{ dynamic_favicon_colors.text }}"
};
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
