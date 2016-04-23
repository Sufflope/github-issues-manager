from django import template

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
