import os
from urlparse import unquote

from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.template.defaultfilters import urlencode
from django.test.client import FakePayload, MULTIPART_CONTENT, encode_multipart, BOUNDARY, \
    CONTENT_TYPE_RE
from django.utils.encoding import force_str, force_bytes


def make_querystring(qs_parts):
    """
    Based on the given dict, generate a querystring, using keys of the dict as
    keys for the querystring, and values as values, but if the value is a list,
    join items by a comma
    """
    parts = []
    for key, value in qs_parts.items():
        if isinstance(value, list):
            parts.append((key, ','.join(map(urlencode, value))))
        else:
            parts.append((key, urlencode(value)))

    qs = '&'.join('%s=%s' % part for part in parts)

    return '?' + qs


def _encode_data(data, content_type):
    # from from django.test.client.RequestFactory
    if content_type is MULTIPART_CONTENT:
        return encode_multipart(BOUNDARY, data)
    else:
        # Encode the content so that the byte representation is correct.
        match = CONTENT_TYPE_RE.match(content_type)
        if match:
            charset = match.group(1)
        else:
            charset = settings.DEFAULT_CHARSET
        return force_bytes(data, encoding=charset)


def forge_request(path, querystring='', method='GET', post_data=None, source_request=None,
                  post_content_type=MULTIPART_CONTENT, headers=None, **kwargs):

        if method == 'POST':
            post_data = _encode_data(post_data or {}, post_content_type)

        environ = dict(source_request.environ if source_request else os.environ)

        environ.update({
            'PATH_INFO': unquote(force_str(path)),
            'QUERY_STRING': force_str(querystring or ''),
            'REQUEST_METHOD': str(method),
            'CONTENT_LENGTH': len(post_data) if method == 'POST' else '',
            'CONTENT_TYPE': post_content_type if method == 'POST' else '',
            'HTTP_CONTENT_TYPE': post_content_type if method == 'POST' else '',
            'wsgi.input': FakePayload(b'' if method == 'GET' else post_data),
        })

        if headers:
            environ.update(headers)

        request = WSGIRequest(environ)

        if source_request:
            if kwargs.pop('pass_user', False):
                request._messages = source_request._messages
                request.user = source_request.user
                request.session = source_request.session

        for key, value in kwargs.iteritems():
            setattr(request, key, value)

        return request
