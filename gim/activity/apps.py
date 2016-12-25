from django.apps import AppConfig
from django.db.models.signals import post_save

from gim.core.utils import contribute_to_model


class ActivityConfig(AppConfig):
    name = 'gim.activity'

    def ready(self):
        from gim.core import models as core_models
        from gim.events import models as events_models
        from . import models as activity_models
        from . import signals

        contribute_to_model(activity_models._Repository, core_models.Repository)
        contribute_to_model(activity_models._Issue, core_models.Issue)

        post_save.connect(
            signals.update_activity_for_fk_link,
            sender=core_models.IssueComment,
            weak=False,
            dispatch_uid='update_activity_for_fk_link_IssueComment'
        )
        post_save.connect(
            signals.update_activity_for_fk_link,
            sender=core_models.IssueEvent,
            weak=False,
            dispatch_uid='update_activity_for_fk_link_IssueEvent'
        )
        post_save.connect(
            signals.update_activity_for_fk_link,
            sender=core_models.PullRequestComment,
            weak=False,
            dispatch_uid='update_activity_for_fk_link_PullRequestComment'
        )
        post_save.connect(
            signals.update_activity_for_fk_link,
            sender=events_models.Event,
            weak=False,
            dispatch_uid='update_activity_for_fk_link_Event'
        )
        post_save.connect(
            signals.update_activity_for_fk_link,
            sender=core_models.IssueCommits,
            weak=False,
            dispatch_uid='update_activity_for_fk_link_IssueCommits'
        )
        post_save.connect(
            signals.update_activity_for_fk_link,
            sender=core_models.PullRequestReview,
            weak=False,
            dispatch_uid='update_activity_for_fk_link_PullRequestReview'
        )
        post_save.connect(
            signals.update_activity_for_commit_comment,
            sender=core_models.CommitComment,
            weak=False,
            dispatch_uid='update_activity_for_commit_comment'
        )
        post_save.connect(
            signals.update_activity_for_event_part,
            sender=events_models.EventPart,
            weak=False,
            dispatch_uid='update_activity_for_event_part'
        )
