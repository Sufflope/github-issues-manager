from datetime import datetime
from uuid import uuid4

from django.conf import settings
from django.core.signing import Signer
from django.core.urlresolvers import reverse

from gim import hashed_version
from gim.core.models import GITHUB_STATUS_CHOICES
from gim.ws import publisher


def auth_keys(request):

    if not request.user or request.user.is_anonymous():
        return {}

    signer = Signer(salt='wampcra-auth')

    def sign(value):
        return signer.sign(value).split(':', 1)[1]

    return {
        'key1': sign(request.user.id),
        'key2': sign(request.session.session_key),
    }


def default_context_data(request):
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
        'utcnow': datetime.utcnow(),
        'gim_version': hashed_version,
        'GITHUB_STATUSES': GITHUB_STATUS_CHOICES,
        'WS': {
            'uri': (settings.WS_SUBDOMAIN + '.' if settings.WS_SUBDOMAIN else '') +
                   request.get_host() + '/ws',
            'last_msg_id': publisher.get_last_msg_id(),
        },
        'new_uuid': uuid4,
    }


def user_context(request):
    context = {
        'auth_keys': auth_keys(request),
    }

    if request.user and request.user.is_authenticated():
        from gim.front.dashboard.views import GithubNotifications

        context['github_notifications_count'] = request.user.github_notifications.filter(
            unread=True, issue__isnull=False).count()

        context['github_notifications_url'] = reverse(GithubNotifications.url_name)
        if GithubNotifications.default_qs:
            context['github_notifications_url'] += '?' + GithubNotifications.default_qs

    return context
