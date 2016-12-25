from gim.core.models import Issue

from .managers import ActivityManager


def update_activity_for_fk_link(sender, instance, created, **kwargs):
    if not instance.issue_id:
        return
    # only if the object can be saved in the activity stream
    manager = ActivityManager.get_for_model_instance(instance)
    if not manager.is_obj_valid(instance.issue, instance):
        return
    instance.issue.activity.add_entry(instance)
    instance.issue.ask_for_activity_update()


def update_activity_for_commit_comment(sender, instance, created, **kwargs):
    try:
        instance.issue = instance.commit.related_commits.all()[0].issue
        instance.issue_id = instance.issue.id
    except IndexError:
        return

    update_activity_for_fk_link(sender, instance, created, **kwargs)


def update_activity_for_event_part(sender, instance, created, **kwargs):
    if not instance.event_id or not instance.event.issue_id:
        return
    # first check for fields we want to ignore
    if instance.field in Issue.RENDERER_IGNORE_FIELDS and instance.event.is_update:
        return
    # only if the event can be saved in the activity stream
    manager = ActivityManager.get_for_model_instance(instance.event)
    if not manager.is_obj_valid(instance.event.issue, instance.event):
        return
    instance.event.issue.activity.add_entry(instance.event)
    instance.event.issue.ask_for_activity_update()
