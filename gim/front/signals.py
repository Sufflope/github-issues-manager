from logging import getLogger

logger = getLogger('gim.log')

from gim.core import models as core_models

from .publish import PUBLISHABLE_MODELS, publish_update, thread_data


def publish_github_updated(sender, instance, created, **kwargs):
    """Publish a message each time a github object is created/updated."""

    # Only for objects we care about
    if not isinstance(instance, PUBLISHABLE_MODELS):
        return

    # That we got from github
    if not getattr(instance, 'skip_status_check_to_publish', False) and \
            getattr(instance, 'github_status', instance.GITHUB_STATUS_CHOICES.FETCHED) != instance.GITHUB_STATUS_CHOICES.FETCHED:
        return

    # Only if we didn't specifically say to not publish
    if getattr(thread_data, 'skip_publish', False):
        return
    if getattr(instance, 'skip_publish', False):
        return

    # Ignore some cases
    update_fields = kwargs.get('update_fields', [])
    if update_fields:

        # Remove fields that are not real updates
        update_fields = set([
            f for f in update_fields
            if f not in ('front_uuid', ) and
                not f.endswith('fetched_at') and
                not f.endswith('etag')
        ])

        # If no field left, we're good
        if not update_fields:
            return

        # If only status and updated date, we're good
        if update_fields in [
                    {'github_status'},
                    {'github_status', 'updated_at'},
                    {'github_status', 'submitted_at'},
                ]:
            return

    extra_data = {}
    if created or getattr(instance, 'is_new', False):
        extra_data['is_new'] = True

    # extra_data['updated_fields'] = list(update_fields or [])

    publish_update(instance, 'updated', extra_data)


def publish_github_deleted(sender, instance, **kwargs):
    """Publish a message each time a github object is deleted."""

    # Only for objects we care about
    if not isinstance(instance, PUBLISHABLE_MODELS):
        return

    # Only if we didn't specifically say to not publish
    if getattr(thread_data, 'skip_publish', False):
        return

    # That we are not currently deleting before creating from github
    if getattr(instance, 'github_status', None) == instance.GITHUB_STATUS_CHOICES.WAITING_CREATE:
        return

    publish_update(instance, 'deleted')


def hash_check(sender, instance, created, **kwargs):
    """
    Check if the hash of the object has changed since its last save and if True,
    update the Issue if its an issue, or related issues if it's a:
    - user
    - milestone
    - label_type
    - label
    """

    if not isinstance(instance, (
                        core_models.GithubUser,
                        core_models.Milestone,
                        core_models.LabelType,
                        core_models.Label,
                        core_models.Project,
                        core_models.Column,
                        core_models.Card,
                        core_models.Issue,
                        core_models.PullRequestReview,
                      )):
        return

    # Only if the data is fresh from github
    if hasattr(instance, 'github_status') and instance.github_status != instance.GITHUB_STATUS_CHOICES.FETCHED:
        return

    if not hasattr(instance, 'signal_hash_changed'):
        instance.signal_hash_changed = instance.hash_changed(force_update=created)

    if not instance.signal_hash_changed:
        return

    if isinstance(instance, core_models.Issue):
        issue_ids = [instance.id]
        repository = instance.repository
    else:
        issue_ids = instance.get_related_issues().values_list('id', flat=True)
        if hasattr(instance, 'repository_id'):
            repository = instance.repository
        else:
            repository = core_models.Issue.objects.get(pk=issue_ids[0]).repository if issue_ids else None

    logger.info(
        'HASH CHANGED for %s #%s (repo %s): %s => %s',
        instance.model_name, instance.pk, repository,
        getattr(instance, 'previous_hash', None), instance.signal_hash_changed
    )

    from gim.core.tasks.issue import UpdateIssueCacheTemplate

    if isinstance(instance, core_models.Issue):
        # if an issue, add a job to update its template
        UpdateIssueCacheTemplate.add_job(issue_ids[0])
    else:
        # if not an issue, add a job to update the templates of all related issues
        for issue_id in issue_ids:
            UpdateIssueCacheTemplate.add_job(issue_id, force_regenerate=1)
