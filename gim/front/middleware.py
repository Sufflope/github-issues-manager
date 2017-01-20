import re

from django.template.response import TemplateResponse
from django.template.loader import render_to_string
from django.contrib.messages.api import get_messages
from django.utils.encoding import smart_text


class AddMessagesToAjaxResponseMiddleware(object):
    def process_response(self, request, response):
        if request.is_ajax() and isinstance(response, TemplateResponse) and response.template_name[0] != 'front/messages.html':
            messages_html = render_to_string('front/messages.html',
                                             {'messages': get_messages(request)})

            response.content = smart_text(response.content) + smart_text(messages_html)

        return response


class VaryOnAcceptHeaderMiddleware(object):
    delimiter = re.compile(r'\s*,\s*')

    def process_response(self, request, response):
        vary = []
        if response.has_header('Vary'):
            vary = self.delimiter.split(response['Vary'])

        if 'Accept' not in vary:
            vary.append('Accept')

        response['Vary'] = ','.join(vary)

        return response
