__all__ = [
    'IssueCommentEditJob',
    'PullRequestCommentEditJob',
    'CommitCommentEditJob',
    'SearchReferenceCommitForComment',
    'SearchReferenceCommitForPRComment',
    'SearchReferenceCommitForCommitComment',
]


from limpyd import fields
from limpyd_jobs import STATUSES
from limpyd_jobs.utils import compute_delayed_until

from async_messages import messages

from gim.core.models import IssueComment, PullRequestComment, Commit, CommitComment
from gim.core.ghpool import ApiError

from .base import DjangoModelJob


class IssueCommentJob(DjangoModelJob):
    """
    Abstract job model for jobs based on the IssueComment model
    """
    abstract = True
    model = IssueComment

    permission = 'self'


class CommentEditJob(IssueCommentJob):
    abstract = True

    mode = fields.InstanceHashField(indexable=True)
    created_pk = fields.InstanceHashField(indexable=True)

    def obj_message_part(self, obj):
        return '%s <strong>#%s</strong>' % (obj.issue.type, obj.issue.number)

    def run(self, queue):
        """
        Get the comment and create/update/delete it
        """
        super(CommentEditJob, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        mode = self.mode.hget()

        try:
            comment = self.object
        except self.model.DoesNotExist:
            return None

        delta = 0
        try:
            if mode == 'delete':
                comment.dist_delete(gh)
                delta = -1
            else:
                comment = comment.dist_edit(mode=mode, gh=gh)
                if mode == 'create':
                    self.created_pk.hset(comment.pk)
                    delta = 1
                else:
                    # force publish
                    from gim.front.models import publish_update
                    publish_update(comment, 'updated', {})

        except ApiError, e:
            message = None

            if e.code == 422:
                message = u'Github refused to %s your comment on the %s on <strong>%s</strong>' % (
                    mode, self.obj_message_part(comment), comment.repository.full_name)

            elif e.code in (401, 403):
                tries = self.tries.hget()
                if tries and int(tries) >= 5:
                    message = u'You seem to not have the right to %s a comment on the %s on <strong>%s</strong>' % (
                        mode, self.obj_message_part(comment), comment.repository.full_name)

            if message:
                messages.error(self.gh_user, message)
                if mode == 'create':
                    comment.delete()
                else:
                    try:
                        comment.fetch(gh, force_fetch=True)
                    except ApiError:
                        pass
                return None

            else:
                raise

        self.after_run(gh, comment, delta)

        return None

    def success_message_addon(self, queue, result):
        """
        Display the action done (created/updated/deleted)
        """
        return ' [%sd]' % self.mode.hget()


class IssueCommentEditJob(CommentEditJob):
    queue_name = 'edit-issue-comment'
    model = IssueComment

    def after_run(self, gh, obj, delta):
        if delta:
            issue = obj.issue
            for key, value in self.extra_args.hgetall().items():
                setattr(issue, key, value)
            issue.comments_count = (issue.comments_count or 0) + delta
            issue.save(update_fields=['comments_count'])


class PullRequestCommentEditJob(CommentEditJob):
    queue_name = 'edit-pr-comment'
    model = PullRequestComment

    def after_run(self, gh, obj, delta):
        if delta:
            issue = obj.issue
            for key, value in self.extra_args.hgetall().items():
                setattr(issue, key, value)
            issue.pr_comments_count = (issue.pr_comments_count or 0) + delta
            issue.save(update_fields=['pr_comments_count'])


class CommitCommentEditJob(CommentEditJob):
    queue_name = 'edit-commit-comment'
    model = CommitComment

    def obj_message_part(self, obj):
        return 'commit <strong>#%s</strong>' % (obj.commit.sha[:7])

    def after_run(self, gh, obj, delta):
        if delta:
            # Update the commit
            commit = obj.commit
            commit.comments_count = (commit.comments_count or 0) + delta
            commit.save(update_fields=['comments_count'], skip_update_issues=True)

            # Update all related issues
            extra_args = self.extra_args.hgetall()
            for issue in commit.issues.all():
                for key, value in extra_args.items():
                    setattr(issue, key, value)
                issue.update_commits_comments_count()


class SearchReferenceCommitForComment(IssueCommentJob):
    """
    When an comment references a commit, we may not have it, so we'll
    wait because it may have been fetched after the comment was received
    """

    queue_name = 'search-ref-commit-comment'

    repository_id = fields.InstanceHashField()
    commit_sha = fields.InstanceHashField()
    nb_tries = fields.InstanceHashField()

    def run(self, queue):
        super(SearchReferenceCommitForComment, self).run(queue)

        repository_id, commit_sha = self.hmget('repository_id', 'commit_sha')

        try:
            # try to find the matching commit
            Commit.objects.filter(
                repository_id=repository_id,
                sha__startswith=commit_sha,
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

        # commit found, save the comment
        self.object.save()

        return True


class SearchReferenceCommitForPRComment(SearchReferenceCommitForComment):
    model = PullRequestComment
    queue_name = 'search-ref-commit-pr-comment'


class SearchReferenceCommitForCommitComment(SearchReferenceCommitForComment):
    model = CommitComment
    queue_name = 'search-ref-commit-commit-comment'
