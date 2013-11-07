from django import template

from adv_cache_tag.tag import CacheTag

from ..views import UserIssuesView

register = template.Library()


def _base_url_issues_for_user(repository, user, filter_type):
    if filter_type not in UserIssuesView.user_filter_types:
        return ''
    username = 'none'
    if user:
        if isinstance(user, basestring):
            username = user
        else:
            username = user.username
    return repository.get_issues_user_filter_url_for_username(filter_type, username)


@register.filter
def base_url_issues_filtered_by_created_by(repository, user):
    return _base_url_issues_for_user(repository, user, 'created_by')


@register.filter
def base_url_issues_filtered_by_assigned(repository, user):
    return _base_url_issues_for_user(repository, user, 'assigned')


@register.filter
def base_url_issues_filtered_by_closed_by(repository, user):
    return _base_url_issues_for_user(repository, user, 'closed_by')


class IssueCacheTag(CacheTag):
    class Meta(CacheTag.Meta):
        versioning = True
        compress = True
        compress_spaces = True
        include_pk = True
        cache_backend = 'issues_tag'
        internal_version = "1"

IssueCacheTag.register(register, 'issue_cache')
