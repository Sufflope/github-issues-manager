import os
from collections import defaultdict
from urlparse import unquote

from statistics import _counts, mean, median, mode, stdev

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.handlers.wsgi import WSGIRequest
from django.core.validators import RegexValidator
from django.template.defaultfilters import urlencode
from django.test.client import FakePayload, MULTIPART_CONTENT, encode_multipart, BOUNDARY, \
    CONTENT_TYPE_RE
from django.utils.encoding import force_str, force_bytes, force_text


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


class FailRegexValidator(RegexValidator):
    """Reverse of RegexValidator: it's ok if the regex does not validate"""
    def __call__(self, value):
        if self.regex.search(force_text(value)):
            raise ValidationError(self.message, code=self.code)


def get_metric(repository, metric_name, first_if_none=False):
    from gim.core.models import LabelType
    if metric_name:
        try:
            return repository.label_types.get(name=metric_name, is_metric=True)
        except LabelType.DoesNotExist:
            pass

    if repository.main_metric_id:
        return repository.main_metric

    if first_if_none:
        # Returns None if no first one
        return repository.all_metrics().first()

    return None


def get_metric_stats(issues, metric, issues_count=None):

    # Get issues count and stop if zero
    if issues_count is None:
        issues_count = len(issues)

    if not issues_count:
        return {
            'metric': metric,
            'count_total': issues_count,
            'count_with': 0,
            'count_too_many':0,
            'count_without': 0,
            'count_invalid': 0,
            'count_valid': 0,
            'distribution': 0,
            'sum': 0,
            'mean': None,
            'median': None,
            'mode': None,
            'stdev': None,
        }

    # Get all couple issue/metric
    from gim.core.models import Issue
    data = Issue.labels.through.objects.filter(
        issue__in=issues,
        label__label_type_id=metric.pk,
    ).values_list('label__order', 'issue_id')

    # Extract values and all issues with more than one
    valid_values = []
    distribution_dict = defaultdict(int)
    issues_done = {}
    invalid_issues = set()
    for value, issue_id in data:
        if issue_id in issues_done:
            # We already have one value for this issue, we mark it as invalid
            invalid_issues.add(issue_id)
            # And we remove the previous value for this issue
            previous_value = issues_done[issue_id]
            valid_values.remove(previous_value)
            # And for the total distribution
            distribution_dict[previous_value] -= 1
        else:
            # First value for this issue, we can add the value
            valid_values.append(value)
            distribution_dict[value] += 1

        # Set the value as last value seen for this issue
        issues_done[issue_id] = value

    # Keep only valid ones
    for issue_id in invalid_issues:
        del issues_done[issue_id]

    count_invalid_issues = len(invalid_issues)
    del invalid_issues

    # Computation!
    count_valid_issues = len(valid_values)
    count_issues_having_data = count_valid_issues + count_invalid_issues
    total = sum(valid_values) if count_valid_issues else None

    # Distribution
    if not hasattr(metric, 'labels_orders_and_names'):
        metric.labels_orders_and_names = {v[0]: v[1] for v in metric.labels.values_list('order', 'name')}
    distribution = [
        {
            'value': value,
            'label_name': metric.labels_orders_and_names[value],
            'count': distribution_dict[value],
            'count_percent': distribution_dict[value] * 100.0 / count_valid_issues,
            'total': distribution_dict[value] * value,
            'metric_percent': (distribution_dict[value] * value) * 100.0 / total,
        }
        for value in sorted(distribution_dict.keys())
        if distribution_dict[value] > 0
    ]

    def multi_mode(data):
        # mode allows only one data, here we accept many in a formatted string if t
        values = map(str, [entry[0] for entry in _counts(data)])
        return ', '.join(values[:-1]) + (' & 'if len(values) > 1 else '') + values[-1]

    return {
        'metric': metric,
        'count_total': issues_count,
        'count_with': count_issues_having_data,
        'count_too_many': count_invalid_issues,
        'count_without': issues_count - count_issues_having_data,
        'count_invalid': issues_count - count_valid_issues,
        'count_valid': count_valid_issues,
        'distribution': distribution,
        'sum': total,
        'mean': mean(valid_values) if count_valid_issues else None,
        'median': median(valid_values) if count_valid_issues else None,
        'mode': multi_mode(valid_values) if count_valid_issues else None,
        'stdev': stdev(valid_values) if count_valid_issues > 1 else None,
        'issues_with_metric': issues_done,
    }
