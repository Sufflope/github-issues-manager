from django import template
from django.core.urlresolvers import reverse

from gim.subscriptions.models import Subscription, SUBSCRIPTION_STATES

register = template.Library()


@register.filter
def repository_view_url(repository, url_name):
    return repository.get_view_url(url_name)


@register.filter
def can_user_write(repository, user):
    """
    Return True if the given user has write rights on the given repository
    """

    subscription = repository.get_subscription_for_user(user)

    if subscription:
        return subscription.state in SUBSCRIPTION_STATES.WRITE_RIGHTS

    return False


@register.filter
def files_enhanced_for_user(obj, user):
    return obj.files_enhanced_for_user(user)


@register.filter
def file_toggle_locally_reviewed_url(file, user):
    from gim.front.repository.views import ToggleLocallyReviewedCommitFile, ToggleLocallyReviewedPullRequestFile
    from gim.core.models import CommitFile, PullRequestFile

    if isinstance(file, CommitFile):
        url_name = ToggleLocallyReviewedCommitFile.url_name
    elif isinstance(file, PullRequestFile):
        url_name = ToggleLocallyReviewedPullRequestFile.url_name
    else:
        return ''

    kwargs = dict(file.repository.get_reverse_kwargs(), file_pk=file.pk, set_or_unset='set')

    url = reverse('front:repository:%s' % url_name, kwargs=kwargs)

    return url.replace('/set/', '/%s/')
