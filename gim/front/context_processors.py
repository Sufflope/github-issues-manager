from datetime import datetime
from uuid import uuid4

from django.conf import settings

from gim import hashed_version
from gim.core.models import GITHUB_STATUS_CHOICES
from gim.ws import publisher, sign


def auth_keys(request):

    if not request.user or request.user.is_anonymous():
        return {}

    return {
        'key1': sign(request.user.id),
        'key2': sign(request.session.session_key),
    }


def default_context_data(request):
    from gim.core.models import GithubUser

    return {
        'brand': {
            'short_name': settings.BRAND_SHORT_NAME,
            'long_name': settings.BRAND_LONG_NAME,
            'favicon': {
                'path': settings.FAVICON_PATH,
                'static_managed': settings.FAVICON_STATIC_MANAGED,
            },
        },
        'headwayapp_account': settings.HEADWAYAPP_ACCOUNT,
        'dynamic_favicon_colors': {
            'background': settings.FAVICON_DYN_BACKGROUND_COLOR,
            'text': settings.FAVICON_DYN_TEXT_COLOR,
        },
        'utcnow': datetime.utcnow(),
        'gim_version': hashed_version,
        'GITHUB_STATUSES': GITHUB_STATUS_CHOICES,
        'WS': {
            'uri': (settings.WS_SUBDOMAIN + '.' if settings.WS_SUBDOMAIN else '') +
                   request.get_host() + '/ws',
            'last_msg_id': publisher.get_last_msg_id(),
        },
        'new_uuid': uuid4,
        'AVATARS_PREFIX': settings.AVATARS_PREFIX,
        'default_avatar': GithubUser.get_default_avatar(),
        'states': ('open', 'closed'),
    }


def user_context(request):
    context = {
        'auth_keys': auth_keys(request),
    }

    if request.user and request.user.is_authenticated():
        from gim.front.github_notifications.views import GithubNotifications

        context.update({
            'wamp_topic_key': request.user.wamp_topic_key,
            'github_notifications_count': request.user.unread_notifications_count,
            'github_notifications_last_date': request.user.last_unread_notification_date,
            'github_notifications_url': GithubNotifications.get_default_url(),
        })

    return context
