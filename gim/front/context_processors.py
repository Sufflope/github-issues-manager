from datetime import datetime
from uuid import uuid4

from django.conf import settings
from django.core.signing import Signer

from gim.core.models import GITHUB_STATUS_CHOICES
from gim.ws import publisher


def auth_keys(request):

    if request.user.is_anonymous():
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
        'utcnow': datetime.utcnow(),
        'GITHUB_STATUSES': GITHUB_STATUS_CHOICES,
        'auth_keys': auth_keys(request),
        'WS': {
            'uri': (settings.WS_SUBDOMAIN + '.' if settings.WS_SUBDOMAIN else '') +
                   request.get_host() + '/ws',
            'last_msg_id': publisher.get_last_msg_id(),
        },
        'new_uuid': uuid4,
    }

