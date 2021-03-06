import Cookie
from importlib import import_module
import logging

from twisted.internet.defer import inlineCallbacks

from autobahn.twisted.wamp import ApplicationSession
from autobahn.wamp.exception import ApplicationError

from django.conf import settings

from gim import hashed_version

django_session_engine = import_module(settings.SESSION_ENGINE)

from gim.ws import sign

logger = logging.getLogger('gim.ws.authenticator')


def get_uid_from_sid(session_key):
    """
    Return user id `uid` based on django session id `session_key`
    """
    session = django_session_engine.SessionStore(session_key)
    return session.get('_auth_user_id', None)


class GimAuthenticator(ApplicationSession):

    @inlineCallbacks
    def onJoin(self, details):

        def authenticate(realm, authid, details):

            django_session_id = None
            django_user_id = None

            if authid and realm == 'gim':

                try:
                    cookie = Cookie.SimpleCookie()
                    cookie.load(str(details['transport']['http_headers_received']['cookie']))
                    django_session_id = cookie['sessionid'].value
                except Exception:
                    pass
                else:
                    django_user_id = get_uid_from_sid(django_session_id)

                    if django_user_id:

                        signed_user_id = sign(django_user_id)

                        if signed_user_id == authid:
                            signed_session_id = sign(django_session_id)
                            logger.info('Authentication success (auth_id=%s, session_id=%s, user_id=%s)',
                                        authid, django_session_id, django_user_id)
                            return {
                                'secret': signed_session_id,
                                'role': 'frontend',
                            }

            logger.warning('Authentication failure (auth_id=%s, realm=%s, session_id=%s, '
                           'user_id=%s)  ws-details=%s',
                           authid, realm, django_session_id, django_user_id, details)
            raise ApplicationError(u"gim.auth.failure", "Could not authenticate session|software_version=%s" % hashed_version)

        try:
            yield self.register(authenticate, 'gim.authenticate')
        except Exception:
            logger.exception('Failed to register authenticator')
        else:
            logger.info('Authenticator registered')
