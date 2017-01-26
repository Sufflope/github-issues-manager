from datetime import datetime
from uuid import uuid4

import json

from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

from gim import hashed_version
from gim.core.models import GITHUB_STATUS_CHOICES, GithubNotification
from gim.ws import publisher, sign


def get_auth_keys(request):

    if not request.user or request.user.is_anonymous:
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
        'utcnow': datetime.utcnow(),
        'GITHUB_STATUSES': GITHUB_STATUS_CHOICES,
        'new_uuid': uuid4,
        'AVATARS_PREFIX': settings.AVATARS_PREFIX,
        'default_avatar': GithubUser.get_default_avatar(),
        'states': ('open', 'closed'),
    }


def user_context(request):
    if request.user and request.user.is_authenticated:
        from gim.front.github_notifications.views import GithubNotifications
        return{
            'github_notifications_url': GithubNotifications.get_default_url(),
            'github_notifications_last_url': GithubNotification.get_last_url(),
        }

    return {}


def get_js_data(request):
    data = {
        'software': {
            'name': settings.BRAND_SHORT_NAME,
            'version': hashed_version,
        },
        'select2_statics': {
            'css': static('front/css/select.2.css'),
            'js': static('front/js/select.2.js'),
        },
        'plotly_statics': {
            'js': static('front/js/plotly.min.js'),
        },
        'auth_keys': get_auth_keys(request),
        'dynamic_favicon_colors': {
            'background': settings.FAVICON_DYN_BACKGROUND_COLOR,
            'text': settings.FAVICON_DYN_TEXT_COLOR,
        },
        'ws': {
            'uri': (settings.WS_SUBDOMAIN + '.' if settings.WS_SUBDOMAIN else '') + request.get_host() + '/ws',
            'last_msg_id': publisher.get_last_msg_id(),
        }
    }

    if request.user and request.user.is_authenticated:
        data['ws']['user_topic_key'] = request.user.wamp_topic_key

    if settings.HEADWAYAPP_ACCOUNT:
        data['HW_config'] = {
            'selector': "body > header .brand",
            'account': settings.HEADWAYAPP_ACCOUNT,
            'translations': {
                'title': "%s changelog" % settings.BRAND_SHORT_NAME,
                'readMore': "Read more",
            }
        }

    if settings.GOOGLE_ANALYTICS_ID:
        data['GA_id'] = settings.GOOGLE_ANALYTICS_ID

    return data


def js_data(request):
    # in a func to execute it only when needed

    def get_json():
        return mark_safe(json.dumps(get_js_data(request)))

    return {
        'js_data': get_json
    }
