
__all__ = [
    'Commit',
    'IssueCommits',
    'CommitStatus',
]

from collections import OrderedDict
from datetime import datetime
from urlparse import urlparse

from django.db import models

from ..managers import (
    CommitManager,
    CommitStatusManager,
    IssueCommitsManager,
)

from .base import (
    GithubObject,
    GithubObjectWithId,
    GITHUB_COMMIT_STATUS_CHOICES,
)

from .mixins import (
    WithRepositoryMixin,
)


class Commit(WithRepositoryMixin, GithubObject):
    repository = models.ForeignKey('Repository', related_name='commits')
    author = models.ForeignKey('GithubUser', related_name='commits_authored', blank=True, null=True)
    committer = models.ForeignKey('GithubUser', related_name='commits_commited', blank=True, null=True)
    sha = models.CharField(max_length=40, db_index=True)
    message = models.TextField(blank=True, null=True)
    author_name = models.TextField(blank=True, null=True)
    author_email = models.CharField(max_length=256, blank=True, null=True)
    committer_name = models.TextField(blank=True, null=True)
    committer_email = models.CharField(max_length=256, blank=True, null=True)
    authored_at = models.DateTimeField(db_index=True, blank=True, null=True)
    committed_at = models.DateTimeField(db_index=True, blank=True, null=True)
    comments_count = models.PositiveIntegerField(blank=True, null=True)
    tree = models.CharField(max_length=40, blank=True, null=True)
    deleted = models.BooleanField(default=False, db_index=True)
    files_fetched_at = models.DateTimeField(blank=True, null=True)
    nb_additions = models.PositiveIntegerField(blank=True, null=True)
    nb_deletions = models.PositiveIntegerField(blank=True, null=True)
    nb_changed_files = models.PositiveIntegerField(blank=True, null=True)
    commit_comments_fetched_at = models.DateTimeField(blank=True, null=True)
    commit_comments_etag = models.CharField(max_length=64, blank=True, null=True)
    # this list is not ordered, we must memorize the last page
    commit_comments_last_page = models.PositiveIntegerField(blank=True, null=True)
    last_status = models.PositiveSmallIntegerField(default=GITHUB_COMMIT_STATUS_CHOICES.NOTHING,
                                                   choices=GITHUB_COMMIT_STATUS_CHOICES)

    commit_statuses_fetched_at = models.DateTimeField(blank=True, null=True)
    commit_statuses_etag = models.CharField(max_length=64, blank=True, null=True)

    GITHUB_COMMIT_STATUS_CHOICES = GITHUB_COMMIT_STATUS_CHOICES

    objects = CommitManager()

    # we keep old commits for reference
    delete_missing_after_fetch = False

    class Meta:
        app_label = 'core'
        ordering = ('committed_at', )
        unique_together = (
            ('repository', 'sha'),
        )

    github_identifiers = {'repository__github_id': ('repository', 'github_id'), 'sha': 'sha'}

    github_matching = dict(GithubObjectWithId.github_matching)
    github_matching.update({
        'comment_count': 'comments_count',
        'additions': 'nb_additions',
        'deletions': 'nb_deletions',
    })
    github_ignore = GithubObject.github_ignore + ('deleted', 'comments_count',
        'nb_additions', 'nb_deletions') + ('url', 'parents', 'comments_url',
        'html_url', 'commit', 'last_status')

    @property
    def github_url(self):
        return self.repository.github_url + '/commit/%s' % self.sha

    def __unicode__(self):
        return u'%s' % self.sha

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_commits + [
            self.sha,
        ]

    @property
    def created_at(self):
        return self.authored_at

    def fetch(self, gh, defaults=None, force_fetch=False, parameters=None,
                                                        meta_base_name=None):
        if defaults is None:
            defaults = {}
        defaults.setdefault('related', {}).setdefault('*', {}).setdefault('fk', {})['commit'] = self
        return super(Commit, self).fetch(gh, defaults, force_fetch, parameters, meta_base_name)

    def save(self, *args, **kwargs):
        """
        Handle case where author/commiter computer have dates in the future: in
        this case, set these dates to now, to avoid inexpected rendering
        """

        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)

        fields_to_update = set()

        now = datetime.utcnow()
        skip_update_issues = kwargs.pop('skip_update_issues', False)

        if self.authored_at and self.authored_at > now:
            self.authored_at = now
            fields_to_update.add('authored_at')

        if self.committed_at and self.committed_at > now:
            self.committed_at = now
            fields_to_update.add('committed_at')

        if self.pk and not self.nb_changed_files:
            self.nb_changed_files = self.files.count()
            fields_to_update.add('nb_changed_files')

        if update_fields is not None:
            update_fields.update(fields_to_update)
            kwargs['update_fields'] = list(update_fields)

        super(Commit, self).save(*args, **kwargs)

        if not skip_update_issues:
            if update_fields is None or 'comments_count' in update_fields:
                self.update_issues_comments_count()

        head_pull_requests = self.get_head_pull_requests()
        self.update_pull_requests_head(pull_requests=head_pull_requests)
        self.update_pull_requests_last_status(pull_requests=head_pull_requests)

        if update_fields is None or 'message' in update_fields:
            from gim.core.models import Mention
            Mention.objects.set_for_commit(self)

    def update_pull_requests_head(self, pull_requests=None):
        if pull_requests is None:
            pull_requests = self.get_head_pull_requests()

        for pr in pull_requests:
            for issue_commit in pr.related_commits.filter(commit=self, pull_request_head_at__isnull=True):
                issue_commit.pull_request_head_at = self.committed_at or self.authored_at or datetime.utcnow()
                issue_commit.save(update_fields=['pull_request_head_at'])

    def update_issues_comments_count(self):
        for issue in self.issues.all():
            issue.update_commits_comments_count()

    @property
    def github_callable_identifiers_for_commit_comments(self):
        return self.github_callable_identifiers + [
            'comments',
        ]

    @property
    def github_callable_identifiers_for_commit_statuses(self):
        return self.github_callable_identifiers + [
            'statuses',
        ]

    def fetch_comments(self, gh, force_fetch=False, parameters=None):
        from .comments import CommitComment

        final_parameters = {
            'sort': CommitComment.github_date_field[1],
            'direction': CommitComment.github_date_field[2],
        }

        if not force_fetch:
            final_parameters['page'] = self.commit_comments_last_page or 1

        if CommitComment.github_reverse_order:
            force_fetch = True

        if parameters:
            final_parameters.update(parameters)

        return self._fetch_many('commit_comments', gh,
                                defaults={
                                    'fk': {
                                        'commit': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'commit': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=final_parameters,
                                force_fetch=force_fetch)

    def fetch_commit_statuses(self, gh, force_fetch=False, parameters=None, refetch_for_pending=False):
        final_parameters = {
            'sort': CommitStatus.github_date_field[1],
            'direction': CommitStatus.github_date_field[2],
        }

        if parameters:
            final_parameters.update(parameters)

        result = self._fetch_many('commit_statuses', gh,
                                  defaults={
                                      'fk': {
                                          'commit': self,
                                          'repository': self.repository
                                      },
                                      'related': {'*': {
                                          'fk': {
                                              'commit': self,
                                              'repository': self.repository
                                          }
                                      }}
                                 },
                                 parameters=final_parameters,
                                 force_fetch=force_fetch)

        self.update_last_status(fetch_pending=refetch_for_pending)

        return result

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        super(Commit, self).fetch_all(gh, force_fetch=force_fetch)
        self.fetch_commit_statuses(gh, force_fetch=force_fetch, refetch_for_pending=True)
        self.fetch_comments(gh, force_fetch=force_fetch)

    def get_last_statuses(self):
        """Get a list of statuses with only the last for each context"""
        result = OrderedDict()
        # Assume ordering by -updated-at
        for status in self.commit_statuses.all():
            if status.context in result:
                continue
            result[status.context] = status
        return result.values()

    def has_pending_statuses(self, last_statuses=None):
        if last_statuses is None:
            last_statuses = self.get_last_statuses()
        return bool(sum(s.state == GITHUB_COMMIT_STATUS_CHOICES.PENDING for s in last_statuses))

    def delay_fetch_pending_statuses(self, delayed_for=60, force_requeue=False, force_fetch=False):
        from gim.core.tasks.commit import FetchCommitStatuses

        FetchCommitStatuses.add_job(self.pk, delayed_for=delayed_for,
                                             force_requeue=force_requeue,
                                             force_fetch=force_fetch)

    def get_head_pull_requests(self):
        """Returns all pull requests having this commit sha as head sha"""
        return self.repository.issues.filter(is_pull_request=True, head_sha=self.sha)

    def update_last_status(self, fetch_pull_requests=True, fetch_pending=True):

        last_statuses = self.get_last_statuses()
        last_status = min(s.state for s in last_statuses) if last_statuses \
            else GITHUB_COMMIT_STATUS_CHOICES.NOTHING

        if last_status != self.last_status:
            self.last_status = last_status
            self.save(update_fields=['last_status'])
            self.update_pull_requests_last_status(fetch_pull_requests=fetch_pull_requests)

        if fetch_pending and self.has_pending_statuses(last_statuses):
            self.delay_fetch_pending_statuses()

        # Convert from int to IntChoiceAttribute
        return GITHUB_COMMIT_STATUS_CHOICES.for_value(last_status).value

    def update_pull_requests_last_status(self, fetch_pull_requests=True, pull_requests=None):
        from gim.core.tasks import FetchIssueByNumber

        if pull_requests is None:
            pull_requests = self.get_head_pull_requests()

        for pr in pull_requests:
            update_fields = []
            if pr.update_last_head_commit(commit=self, save=False):
                update_fields.append('last_head_commit')
            if pr.update_last_head_status(commit=self, save=False):
                update_fields.append('last_head_status')
            if update_fields:
                pr.save(update_fields=update_fields)
                if fetch_pull_requests:
                    FetchIssueByNumber.add_job('%s#%s' % (self.repository.pk, pr.number))

    def get_all_commit_statuses(self):
        """
        Return all the commit statuses in a format usable in template:
        A dict with `as_old_logs` being a boolean indicating if there is something to expand
        for at least one context, and `contexts` being a list with one entry by `context`,
        ordered by last `updated_at`, each entry being a list with all statuses for this context,
        ordered by last `updated_at`
        """
        result = OrderedDict()
        is_last = {}

        for status in self.commit_statuses.all():

            if status.context not in is_last:
                is_last[status.context] = True
            elif is_last[status.context]:
                if status.state in GITHUB_COMMIT_STATUS_CHOICES.FINISHED:
                    is_last[status.context] = False
            status.is_last = is_last[status.context]

            result.setdefault(status.context, []).append(status)

        return {
            'as_old_logs': any(len(c) > 1 for c in result.values()),
            'contexts': result.values()
        }

    @property
    def last_status_constant(self):
        return GITHUB_COMMIT_STATUS_CHOICES.for_value(self.last_status).constant

class IssueCommits(models.Model):
    """
    The table to list commits related to issues, keeping commits not referenced
    anymore in the issues by setting the 'deleted' attribute to True.
    It allows to still display commit-comments on old commits (replaced via a
    rebase for example)
    """
    issue = models.ForeignKey('Issue', related_name='related_commits')
    commit = models.ForeignKey('Commit', related_name='related_commits')
    deleted = models.BooleanField(default=False, db_index=True)
    pull_request_head_at = models.DateTimeField(db_index=True, blank=True, null=True)

    delete_missing_after_fetch = False

    objects = IssueCommitsManager()

    class Meta:
        app_label = 'core'

    def __unicode__(self):
        result = u'%s on %s'
        if self.deleted:
            result += u' (deleted)'
        return result % (self.commit.sha, self.issue.number)


class CommitStatus(GithubObjectWithId):

    repository = models.ForeignKey('Repository', related_name='commit_statuses')
    commit = models.ForeignKey('Commit', related_name='commit_statuses')
    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)
    state = models.PositiveSmallIntegerField(db_index=True,
                                             default=GITHUB_COMMIT_STATUS_CHOICES.NOTHING,
                                             choices=GITHUB_COMMIT_STATUS_CHOICES)
    description = models.TextField(blank=True, null=True)
    context = models.TextField(db_index=True, default='default')
    target_url = models.URLField(max_length=512, blank=True, null=True)

    GITHUB_COMMIT_STATUS_CHOICES = GITHUB_COMMIT_STATUS_CHOICES

    github_date_field = ('updated_at', 'updated', 'desc')
    github_per_page = {'min': 100, 'max': 100}

    objects = CommitStatusManager()

    class Meta:
        app_label = 'core'
        ordering = ['-updated_at', 'context']

    def __unicode__(self):
        return u'[%s] %s' % (self.context, self.get_state_display())

    @property
    def state_constant(self):
        return GITHUB_COMMIT_STATUS_CHOICES.for_value(self.state).constant

    @property
    def target_domain(self):
        if not self.target_url:
            return None
        try:
            return urlparse(self.target_url).netloc or None
        except Exception:
            return None

    def save(self, *args, **kwargs):
        super(CommitStatus, self).save(*args, **kwargs)

        # Flag the repository as accepting commit statuses. To be used on UI to show differently
        # pull requests with no statuses
        if not self.repository.has_commit_statuses:
            self.repository.has_commit_statuses = True
            self.repository.save(update_fields=['has_commit_statuses'])


