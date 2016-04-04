from uuid import uuid4

from django import template
from django.template import TemplateSyntaxError
from django.template.base import Node
from django.utils.html import strip_spaces_between_tags

register = template.Library()


class InjectNotificationForm(Node):
    template = template.Template("""
        {% load frontutils %}
        <div class="issue-item-notification not-hoverable">
            <span>
                Notified
                <span class="time ago" title="{{ notification.updated_at|date:"DATETIME_FORMAT" }}" data-datetime="{{ notification.updated_at|date:'r' }}">{{ notification.updated_at|ago }}</span>.
                {% with reason=reasons|dict_item:notification.reason %}
                    Reason:
                    <span data-filter="reason:{{ notification.reason }}" title="{{ reason.description_one|capfirst }}" title_all="{{ reason.description|capfirst }}">{{ reason.name }}</span>.
                {% endwith %}
            </span>
            <form action="{{ notification.get_edit_url }}" method="post"{% if notification.manual_unread %} data-manual-unread="true"{% endif %}>{% csrf_token %}
                <div>
                    <span title="Marking unread a read notification will not update the notification on the Github side." data-filter="unread:{{ notification.unread|yesno }}">
                        <input type="checkbox" name="read" id="notif-read-{{ uuid }}" value="1"{% if not notification.unread %} checked=checked{% endif %} autocomplete="off" />
                        <label for="notif-read-{{ uuid }}">Read</label>
                    </span>
                    <span title="A deactivated notification will be reactivated if you comment on it or are mentionned." data-filter="active:{{ notification.subscribed|yesno }}">
                        <input type="checkbox" name="active" id="notif-active-{{ uuid }}" value="1"{% if notification.subscribed %} checked=checked{% endif %} autocomplete="off" />
                        <label for="notif-active-{{ uuid }}">Active</label>
                    </span>
                </div>
            </form>
        </div>
    """.strip())

    def __init__(self, nodelist, notification):
        self.nodelist = nodelist
        self.notification = notification

    def get_notification_form(self, notification, context):
        request = template.Variable('view').resolve(context).request

        rendered = self.template.render(template.RequestContext(request, {
            'notification': notification,
            'reasons': context['reasons'],
            'uuid': uuid4(),
        }))
        result = strip_spaces_between_tags(rendered)
        return result

    def render(self, context):
        output = self.nodelist.render(context).strip()

        notification = self.notification.resolve(context)
        form = self.get_notification_form(notification, context)

        # Add the `with-notification` class to the main `issue-item` tag
        sep1 = 'issue-item'
        before, after = output.split(sep1, 1)
        parts = [before, sep1, ' with-notification']

        # Add the notification block before the last closing `</li>`
        before, after = [after[:-5], after[-5:]]
        parts.extend([before, form, after])

        output = ''.join(parts)

        return strip_spaces_between_tags(''.join(parts))


@register.tag()
def inject_notification_form(parser, token):
    bits = token.split_contents()

    if len(bits) != 2:
        raise TemplateSyntaxError("'inject_notification_form' tag takes one arguments")

    __, notification = bits

    nodelist = parser.parse(('end_inject_notification_form',))

    parser.delete_first_token()

    return InjectNotificationForm(nodelist, parser.compile_filter(notification))
