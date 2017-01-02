from django.apps import AppConfig
from django.db.models.signals import post_delete, post_save

from gim.core.utils import contribute_to_model


class FrontConfig(AppConfig):
    name = 'gim.front'

    def ready(self):
        from gim.core import models as core_models
        from gim.subscriptions import models as subscriptions_models
        from . import models as front_models
        from . import signals

        contribute_to_model(front_models._GithubUser, core_models.GithubUser)
        contribute_to_model(front_models._Repository, core_models.Repository, {'delete'}, {'delete'})
        contribute_to_model(front_models._LabelType, core_models.LabelType)
        contribute_to_model(front_models._Label, core_models.Label, {'defaults_create_values'})
        contribute_to_model(front_models._Milestone, core_models.Milestone, {'defaults_create_values'})
        contribute_to_model(front_models._Issue, core_models.Issue, {'defaults_create_values'})
        contribute_to_model(front_models._Commit, core_models.Commit)
        contribute_to_model(front_models._WaitingSubscription, subscriptions_models.WaitingSubscription)
        contribute_to_model(front_models._IssueComment, core_models.IssueComment, {'defaults_create_values'})
        contribute_to_model(front_models._PullRequestComment, core_models.PullRequestComment, {'defaults_create_values'})
        contribute_to_model(front_models._CommitComment, core_models.CommitComment, {'defaults_create_values'})
        contribute_to_model(front_models._GithubNotification, core_models.GithubNotification)
        contribute_to_model(front_models._PullRequestReview, core_models.PullRequestReview, {'save', 'defaults_create_values'}, {'save'})
        contribute_to_model(front_models._Project, core_models.Project, {'save', 'defaults_create_values'}, {'save'})
        contribute_to_model(front_models._Column, core_models.Column, {'defaults_create_values'})
        contribute_to_model(front_models._Card, core_models.Card, {'save', 'defaults_create_values'}, {'save'})

        post_save.connect(signals.publish_github_updated, dispatch_uid='publish_github_updated', weak=False)
        post_delete.connect(signals.publish_github_deleted, dispatch_uid='publish_github_deleted', weak=False)
        post_save.connect(signals.hash_check, dispatch_uid='hash_check', weak=False)
