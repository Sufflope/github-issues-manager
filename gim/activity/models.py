__all__ = []

from datetime import timedelta

from django.db import models


class _Repository(models.Model):
    class Meta:
        abstract = True

    @property
    def activity(self):
        from .limpyd_models import RepositoryActivity
        a, created = RepositoryActivity.get_or_connect(object_id=self.id)
        return a


class _Issue(models.Model):
    class Meta:
        abstract = True

    @property
    def activity(self):
        if not hasattr(self, '_activity_limpyd_object'):
            from .limpyd_models import IssueActivity
            self._activity_limpyd_object, created = IssueActivity.get_or_connect(object_id=self.id)
        return self._activity_limpyd_object

    def ask_for_activity_update(self):
        from gim.activity.tasks import ResetIssueActivity
        ResetIssueActivity.add_job(self.pk, priority=-5, delayed_for=timedelta(minutes=15))
