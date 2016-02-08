__all__ = [
    'SearchReferenceCommitForEvent',
]

from limpyd import fields
from limpyd_jobs import STATUSES
from limpyd_jobs.utils import compute_delayed_until

from gim.core.models import IssueEvent, Commit

from .base import DjangoModelJob


class EventJob(DjangoModelJob):
    """
    Abstract job model for jobs based on the Event model
    """
    abstract = True
    model = IssueEvent

    @property
    def event(self):
        if not hasattr(self, '_event'):
            self._event = self.object
        return self._event

    @property
    def repository(self):
        if not hasattr(self, '_repository'):
            self._repository = self.event.repository
        return self._repository


class SearchReferenceCommitForEvent(EventJob):
    """
    When an event is a reference to a commit, we may not have it, so we'll
    wait because it may have been fetched after the event was received
    """
    queue_name = 'search-ref-commit-event'

    nb_tries = fields.InstanceHashField()

    def run(self, queue):
        super(SearchReferenceCommitForEvent, self).run(queue)

        try:
            event = self.event
        except IssueEvent.DoesNotExist:
            # The event doesn't exist anymore, we can cancel the job
            self.status.hset(STATUSES.CANCELED)
            return None

        try:
            # try to find the matching commit
            event.related_object = Commit.objects.filter(
                authored_at__lte=event.created_at,
                sha=event.commit_sha,
                author=event.user
            ).order_by('-authored_at')[0]
        except IndexError:
            # the commit was not found

            tries = int(self.nb_tries.hget() or 0)

            if tries >= 5:
                # enough tries, stop now
                self.status.hset(STATUSES.CANCELED)
                return None
            else:
                # we'll try again...
                self.status.hset(STATUSES.DELAYED)
                self.delayed_until.hset(compute_delayed_until(delayed_for=60*tries))
                self.nb_tries.hincrby(1)
            return False

        # commit found, save the event
        event.save()

        return True
