import json
import logging
import sys
import traceback

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from . import EVENTS
from .models import EventManager

logger = logging.getLogger('gim.hooks.views')


class GithubWebHook(View):
    http_method_names = [u'post', u'head', ]

    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        return super(GithubWebHook, self).dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):

        event = None
        payload = None
        repository = None
        result = None

        try:
            # type of event from gthub
            event = request.META['HTTP_X_GITHUB_EVENT']

            if event not in EVENTS:
                return HttpResponse('Event not allowed\n')

            method = getattr(self, 'event_%s' % event, None)
            if method is None:
                return HttpResponse('Event not managed\n')

            payload = json.loads(request.POST['payload'])
            self.event_manager = EventManager(payload['repository'])
            repository = self.event_manager.repository
            if not repository:
                return HttpResponse('Repository not managed\n')

            result = method(payload)

        except Exception as e:
            from pprint import pformat
            log_string = 'DeliveryId: %s\nRepository: %s\nEvent: %s\nPayload:\n%s\n%s\n\n' % (
                request.META.get('HTTP_X_GITHUB_DELIVERY'),
                repository,
                event,
                '-' * 8,
                pformat(payload),
            )
            logger.exception('### Github Hook problem:\n' + log_string)

            if False:  # For debug purpose, set it to `True`
                exc_type, exc_value, exc_tb = sys.exc_info()
                response_string = 'Exception:\n%s\n%s\n%s' % (
                    '-' * 10,
                    '\n'.join(traceback.format_exception(exc_type, exc_value, exc_tb)),
                    log_string,
                )
            else:
                response_string = "Something went wrong"

            return HttpResponse(response_string, status=500)

        return HttpResponse('OK: %s done\n' % ('Nothing' if result is None else 'Something'))

    def event_issues(self, payload):
        return self.event_manager.event_issues(payload['issue'],
                                               payload.get('action'))

    def event_issue_comment(self, payload):
        payload['comment']['issue'] = payload['issue']
        return self.event_manager.event_issue_comment(payload['comment'],
                                                      payload.get('action'))

    def event_pull_request(self, payload):
        return self.event_manager.event_pull_request(payload['pull_request'],
                                                     payload.get('action'),
                                                     label=payload.get('label'))

    def event_pull_request_review_comment(self, payload):
        return self.event_manager.event_pull_request_review_comment(payload['comment'],
                                                                    payload.get('action'))

    def event_commit_comment(self, payload):
        return self.event_manager.event_commit_comment(payload['comment'],
                                                       payload.get('action'))

    def event_push(self, payload):
        return self.event_manager.event_push(payload,
                                             payload.get('action'))

    def event_status(self, payload):
        return self.event_manager.event_status(payload,
                                               payload.get('action'))
