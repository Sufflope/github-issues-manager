# -*- coding: utf-8 -*-

__all__ = [
    'FetchCommitBySha',
    'FetchCommitStatuses',
]

from datetime import datetime

from limpyd import fields
from limpyd_jobs import STATUSES


from gim.core.models import Repository, Commit
from gim.core.ghpool import ApiNotFoundError

from .base import DjangoModelJob, Job


class FetchCommitBySha(Job):
    """
    Fetch a commit in a repository, given only the commit's sha
    """
    queue_name = 'fetch-commit-by-sha'
    deleted = fields.InstanceHashField()
    force_fetch = fields.InstanceHashField()
    fetch_comments = fields.InstanceHashField()
    fetch_comments_only = fields.InstanceHashField()

    permission = 'read'

    @property
    def repository(self):
        if not hasattr(self, '_repository'):
            repository_id, sha = self.identifier.hget().split('#')
            try:
                self._repository = Repository.objects.get(id=repository_id)
            except Repository.DoesNotExist:
                # We can cancel the job if the repository does not exist anymore
                self.hmset(status=STATUSES.CANCELED, cancel_on_error=1)
                raise
        return self._repository

    def run(self, queue):
        """
        Fetch the commit with the given sha for the current repository
        """
        super(FetchCommitBySha, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        repository_id, sha = self.identifier.hget().split('#')

        repository = self.repository

        force_fetch = self.force_fetch.hget() == '1'
        fetch_comments = self.fetch_comments.hget() == '1'
        fetch_comments_only = fetch_comments and self.fetch_comments_only.hget() == '1'

        try:
            commit = repository.commits.filter(sha=sha)[0]
        except (Commit.DoesNotExist, IndexError):
            commit = Commit(repository=repository, sha=sha)
        else:
            if not force_fetch and commit.fetched_at and not fetch_comments:
                # a commit doesn't change so is we already have it, fetch it
                # only if we forced it (or if we want comments to)
                self.status.hset(STATUSES.CANCELED)
                return None

        try:
            if fetch_comments:
                if fetch_comments_only:
                    commit.fetch_comments(gh, force_fetch=force_fetch)
                else:
                    commit.fetch_all(gh, force_fetch=force_fetch)
            else:
                commit.fetch(gh, force_fetch=force_fetch)
        except ApiNotFoundError:
            # the commit doesn't exist anymore, delete it
            if commit.pk:
                commit.deleted = True
                commit.fetched_at = datetime.utcnow()
                commit.save(update_fields=['deleted', 'fetched_at'])
            self.deleted.hset(1)
            return False

        return True

    def success_message_addon(self, queue, result):
        if result is False:
            return ' [deleted]'


class CommitJob(DjangoModelJob):
    """
    Abstract job model for jobs based on the Issue model
    """
    abstract = True
    model = Commit

    @property
    def commit(self):
        if not hasattr(self, '_commit'):
            self._commit = self.object
        return self._commit

    @property
    def repository(self):
        if not hasattr(self, '_repository'):
            self._repository = self.commit.repository
        return self._repository


class FetchCommitStatuses(CommitJob):
    """
    Fetch the statuses of a commit, and requeue it if commits has pending jobs
    """
    queue_name = 'fetch-commit-statuses'

    force_fetch = fields.InstanceHashField()
    force_requeue = fields.InstanceHashField()
    iteration = fields.InstanceHashField()

    permission = 'read'
    clonable_fields = ('force_fetch', 'force_requeue')

    def run(self, queue):
        """
        Get the commit and get the statuses
        """
        super(FetchCommitStatuses, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        commit = self.commit

        force_fetch = self.force_fetch.hget() == '1'
        force_requeue = self.force_requeue.hget() == '1'

        is_recent_commit = bool(
            not commit.deleted
            and commit.committed_at
            and commit.committed_at > datetime.utcnow() - commit.OLD_DELTA
        )

        count = commit.fetch_commit_statuses(gh=gh, force_fetch=force_fetch, refetch_for_pending=False)

        return count, is_recent_commit and (force_requeue or commit.has_pending_statuses())

    def on_success(self, queue, result):
        """
        If there is still issues to fetch, add a new job
        """

        if result[1]:
            iteration = int(self.iteration.hget() or 0)
            if iteration <= 10:
                self.clone(delayed_for=60*1.5**iteration, iteration=iteration+1)

    def success_message_addon(self, queue, result):
        """
        Display the count of closed issues fetched
        """
        if result[1]:
            return ' [fetched=%d (iteration %s), requeued ]' % (result[0], int(self.iteration.hget() or 0))
        else:
            return ' [fetched=%d (iteration %s)]' % (result[0], int(self.iteration.hget() or 0))
