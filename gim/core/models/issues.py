
__all__ = [
    'LABELTYPE_EDITMODE',
    'Issue',
    'IssueEvent',
    'LabelType',
    'Label',
    'Milestone',
]

from collections import OrderedDict
import re

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property

from extended_choices import Choices
from jsonfield import JSONField

from ..managers import (
    IssueEventManager,
    IssueManager,
    LabelTypeManager,
    WithRepositoryManager,
)

from .base import (
    GithubObject,
    GithubObjectWithId,
    GITHUB_COMMIT_STATUS_CHOICES,
)

from .mixins import (
    WithIssueMixin,
    WithRepositoryMixin,
)


class Issue(WithRepositoryMixin, GithubObjectWithId):
    repository = models.ForeignKey('Repository', related_name='issues')
    number = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    title = models.TextField(db_index=True)
    body = models.TextField(blank=True, null=True)
    body_html = models.TextField(blank=True, null=True)
    labels = models.ManyToManyField('Label', related_name='issues')
    user = models.ForeignKey('GithubUser', related_name='created_issues')
    assignee = models.ForeignKey('GithubUser', related_name='assigned_issues', blank=True, null=True)
    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)
    closed_at = models.DateTimeField(blank=True, null=True, db_index=True)
    milestone = models.ForeignKey('Milestone', related_name='issues', blank=True, null=True)
    state = models.CharField(max_length=10, db_index=True)
    comments_count = models.PositiveIntegerField(blank=True, null=True)
    closed_by = models.ForeignKey('GithubUser', related_name='closed_issues', blank=True, null=True, db_index=True)
    closed_by_fetched = models.BooleanField(default=False, db_index=True)
    comments_fetched_at = models.DateTimeField(blank=True, null=True)
    comments_etag = models.CharField(max_length=64, blank=True, null=True)
    events_fetched_at = models.DateTimeField(blank=True, null=True)
    events_etag = models.CharField(max_length=64, blank=True, null=True)
    # pr stuff
    is_pull_request = models.BooleanField(default=False, db_index=True)
    pr_fetched_at = models.DateTimeField(blank=True, null=True, db_index=True)
    pr_comments_count = models.PositiveIntegerField(blank=True, null=True)
    pr_comments_fetched_at = models.DateTimeField(blank=True, null=True)
    pr_comments_etag = models.CharField(max_length=64, blank=True, null=True)
    base_label = models.TextField(blank=True, null=True)
    base_sha = models.CharField(max_length=256, blank=True, null=True)
    head_label = models.TextField(blank=True, null=True)
    head_sha = models.CharField(max_length=256, blank=True, null=True, db_index=True)
    last_head_commit = models.ForeignKey('Commit', related_name='', blank=True, null=True)
    last_head_status = models.PositiveSmallIntegerField(
        default=GITHUB_COMMIT_STATUS_CHOICES.NOTHING, choices=GITHUB_COMMIT_STATUS_CHOICES)
    merged_at = models.DateTimeField(blank=True, null=True)
    merged_by = models.ForeignKey('GithubUser', related_name='merged_prs', blank=True, null=True)
    github_pr_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    mergeable = models.NullBooleanField()
    mergeable_state = models.CharField(max_length=20, null=True, blank=True)
    merged = models.NullBooleanField()
    nb_commits = models.PositiveIntegerField(blank=True, null=True)
    nb_additions = models.PositiveIntegerField(blank=True, null=True)
    nb_deletions = models.PositiveIntegerField(blank=True, null=True)
    nb_changed_files = models.PositiveIntegerField(blank=True, null=True)
    commits_comments_count = models.PositiveIntegerField(blank=True, null=True)
    commits_fetched_at = models.DateTimeField(blank=True, null=True)
    commits_etag = models.CharField(max_length=64, blank=True, null=True)
    commits = models.ManyToManyField('Commit', related_name='issues', through='IssueCommits')
    files_fetched_at = models.DateTimeField(blank=True, null=True)
    files_etag = models.CharField(max_length=64, blank=True, null=True)
    user_mentions = models.ManyToManyField('GithubUser', related_name='issues_mentioned',
                                           through='Mention')

    GITHUB_COMMIT_STATUS_CHOICES = GITHUB_COMMIT_STATUS_CHOICES

    objects = IssueManager()

    github_matching = dict(GithubObjectWithId.github_matching)
    github_matching.update({
        'comments': 'comments_count',
        'review_comments': 'pr_comments_count',
        'commits': 'nb_commits',
        'additions': 'nb_additions',
        'deletions': 'nb_deletions',
        'changed_files': 'nb_changed_files'
    })
    github_ignore = GithubObjectWithId.github_ignore + ('is_pull_request', 'closed_by_fetched',
        'github_pr_id', 'pr_comments_count', 'nb_commits', 'nb_additions', 'nb_deletions',
        'nb_changed_files', ) + ('head', 'commits_url', 'body_text', 'url', 'labels_url',
        'events_url', 'comments_url', 'html_url', 'merge_commit_sha', 'review_comments_url',
        'review_comment_url', 'base', 'patch_url', 'pull_request', 'diff_url',
        'statuses_url', 'issue_url', 'last_head_status')

    github_format = '.full+json'
    github_edit_fields = {
        'create': (
            'title',
            'body',
            ('assignee', 'assignee__username'),
            ('milestone', 'milestone__number'),
            ('labels', 'labels__name', )
        ),
        'create': (
            'title',
            'body',
            'state',
            ('assignee', 'assignee__username'),
            ('milestone', 'milestone__number'),
            ('labels', 'labels__name', )
        ),
    }

    # fetch from repo + number because we can have PRs but no issues from github
    github_identifiers = {'repository__github_id': ('repository', 'github_id'), 'number': 'number'}

    github_date_field = ('updated_at', 'updated', 'desc')

    MERGEABLE_STATES = {
        'mergeable': ('clean', 'stable'),
        'unmergeable': ('unknown', 'checking', 'dirty', 'unstable'),
        'unknown': ('unknown', 'checking'),
    }

    class Meta:
        app_label = 'core'
        unique_together = (
            ('repository', 'number'),
        )

    @property
    def github_url(self):
        return self.repository.github_url + '/issues/%s' % self.number

    def __unicode__(self):
        return u'#%s %s' % (self.number or '??', self.title)

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_issues + [
            self.number,
        ]

    @property
    def github_callable_identifiers_for_pr(self):
        return self.repository.github_callable_identifiers_for_prs + [
            self.number,
        ]

    @property
    def github_callable_create_identifiers(self):
        return self.repository.github_callable_identifiers_for_issues

    @property
    def github_callable_identifiers_for_events(self):
        return self.github_callable_identifiers + [
            'events',
        ]

    @property
    def github_callable_identifiers_for_comments(self):
        return self.github_callable_identifiers + [
            'comments',
        ]

    @property
    def github_callable_identifiers_for_pr_comments(self):
        return self.github_callable_identifiers_for_pr + [
            'comments'
        ]

    def fetch(self, gh, defaults=None, force_fetch=False, parameters=None,
                                                        meta_base_name=None):
        if not self.repository.has_issues:
            # do not use the issues api endpoint if repos with PRs only
            meta_base_name = 'pr'
        return super(Issue, self).fetch(gh, defaults, force_fetch, parameters, meta_base_name)

    def fetch_pr(self, gh, defaults=None, force_fetch=False, parameters=None):
        if defaults is None:
            defaults = {}
        if 'simple' not in defaults:
            defaults['simple'] = {}
        defaults['simple'].update({
            'is_pull_request': True,
            'mergeable_state': 'checking',
        })
        return self.fetch(gh=gh, defaults=defaults, force_fetch=force_fetch,
                                    parameters=parameters, meta_base_name='pr')

    def fetch_events(self, gh, force_fetch=True, parameters=None):
        """
        force_fetch is forced to True because for an issue events are in the
        reverse order (first created first, last created last, maybe on an other
        page)
        """
        if not self.repository.has_issues:
            # bug in the github api, not able to retrieve issue events if only PRs
            return

        return self._fetch_many('events', gh,
                                defaults={
                                    'fk': {
                                        'issue': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'issue': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=parameters,
                                force_fetch=True)

    def fetch_comments(self, gh, force_fetch=False, parameters=None):
        """
        Don't fetch comments if the previous fetch of the issue told us there
        is not comments for it
        """
        from .comments import IssueComment

        if not force_fetch and self.comments_count == 0:
            return 0

        final_parameters = {
            'sort': IssueComment.github_date_field[1],
            'direction': IssueComment.github_date_field[2],
        }
        if parameters:
            final_parameters.update(parameters)

        return self._fetch_many('comments', gh,
                                defaults={
                                    'fk': {
                                        'issue': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'issue': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=final_parameters,
                                force_fetch=force_fetch)

    def fetch_pr_comments(self, gh, force_fetch=False, parameters=None):
        """
        Don't fetch comments if the previous fetch of the issue told us there
        is not pr comments for it
        """
        from .comments import PullRequestComment

        if not force_fetch and self.pr_comments_count == 0:
            return 0

        final_parameters = {
            'sort': PullRequestComment.github_date_field[1],
            'direction': PullRequestComment.github_date_field[2],
        }
        if parameters:
            final_parameters.update(parameters)

        return self._fetch_many('pr_comments', gh,
                                defaults={
                                    'fk': {
                                        'issue': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'issue': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=final_parameters,
                                force_fetch=force_fetch)

    @property
    def github_callable_identifiers_for_labels(self):
        return self.github_callable_identifiers + [
            'labels',
        ]

    def fetch_labels(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('labels', gh,
                                defaults={
                                    'fk': {'repository': self.repository},
                                    'related': {'*': {'fk': {'repository': self.repository}}},
                                },
                                force_fetch=force_fetch,
                                parameters=parameters)

    @property
    def github_callable_identifiers_for_commits(self):
        return self.github_callable_identifiers_for_pr + [
            'commits'
        ]

    @property
    def github_callable_identifiers_for_files(self):
        return self.github_callable_identifiers_for_pr + [
            'files'
        ]

    def fetch_commits(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('commits', gh,
                                defaults={
                                    'fk': {'repository': self.repository},
                                    'related': {'*': {'fk': {'repository': self.repository}}},
                                },
                                parameters=parameters,
                                force_fetch=force_fetch)

    def fetch_files(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('files', gh,
                                defaults={
                                    'fk': {
                                        'issue': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'issue': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=parameters,
                                force_fetch=force_fetch)

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        super(Issue, self).fetch_all(gh, force_fetch=force_fetch)
        # self.fetch_labels(gh, force_fetch=force_fetch)  # already retrieved via self.fetch

        if self.is_pull_request:
            # fetch commits first because they may be used as references in comments
            self.fetch_commits(gh, force_fetch=force_fetch)
            # Neded actions may already be done in paralelle because the fetch of the commits
            # may launch a `FetchCommitBySha` job for each commit.
            # But as we need info about the very last one in the list, we may be faster by doing it
            # now.
            self.fetch_head_commit_statuses(gh, force_fetch)

        # Force fetch because of reverse order
        self.fetch_events(gh, force_fetch=True)
        self.fetch_comments(gh, force_fetch=True)

        if self.is_pull_request:
            self.fetch_pr(gh, force_fetch=force_fetch)
            self.fetch_pr_comments(gh, force_fetch=force_fetch)
            self.fetch_files(gh, force_fetch=force_fetch)

    def get_head_commit(self, force=False):
        if not hasattr(self, '_head_commits'):
            self._head_commits = {}

        if force or self.head_sha not in self._head_commits:
            from gim.core.models import Commit
            try:
                self._head_commits[self.head_sha] = self.repository.commits.get(sha=self.head_sha)
            except Commit.DoesNotExist:
                from gim.core.tasks.commit import FetchCommitBySha
                FetchCommitBySha.add_job('%s#%s' % (self.repository_id, self.head_sha))
                self._head_commits[self.head_sha] = None

        return self._head_commits[self.head_sha]

    def fetch_head_commit_statuses(self, gh, force_fetch=None):
        head_commit = self.get_head_commit()
        if not head_commit:
            return

        already_fetched = bool(head_commit.commit_statuses_fetched_at)

        if not already_fetched:
            # On the first time, we may not have any statuses yet, they may come later
            head_commit.delay_fetch_pending_statuses(delayed_for=60, force_requeue=1, force_fetch=force_fetch)

        # If it's the first fetch, don't refetch if pending statuses because we just did it
        # We had to do this because the first job for an identifier defines the arguments,
        # and here we want `force_requeued` to be set
        head_commit.fetch_commit_statuses(gh, force_fetch, refetch_for_pending=already_fetched)

    def get_all_head_commits(self):
        """
        Return all present and past head commits
        """
        return [ic.commit for ic in self.related_commits.filter(pull_request_head_at__isnull=False)
            .select_related('commit').order_by('pull_request_head_at')]

    @property
    def total_comments_count(self):
        return ((self.comments_count or 0)
              + (self.pr_comments_count or 0)
              + (self.commits_comments_count or 0))

    def update_commits_comments_count(self):
        if self.is_pull_request:
            count = sum(
                self.related_commits
                    .exclude(deleted=True)
                    .values_list('commit__comments_count', flat=True)
            )
        else:
            count = 0

        if self.commits_comments_count != count:
            self.commits_comments_count = count
            self.save(update_fields=['commits_comments_count'])

    def save(self, *args, **kwargs):
        """
        If the user, which is mandatory, is not defined, use (and create if
        needed) a special user named 'user.deleted'

        Also check that if the issue is reopened, we'll be able to fetch the
        future closed_by

        Also update the `last_head_status` if the head_sha changed.
        The new head commit may not be here or may not have statuses, in this case we simple
        set the last status as not set, this will be done later.
        """
        from .users import GithubUser

        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)

        fields_to_update = set()

        if self.user_id is None:
            self.user = GithubUser.objects.get_deleted_user()
            fields_to_update.add('user')

        if self.state != 'closed' and self.closed_by_fetched:
            self.closed_by_fetched = False
            fields_to_update.add('closed_by_fetched')

        if update_fields is None or 'head_sha' in update_fields:
            if self.update_last_head_commit(save=False):
                fields_to_update.add('last_head_commit')

            if self.update_last_head_status(self.last_head_commit, save=False):
                fields_to_update.add('last_head_status')

        if update_fields is not None:
            update_fields.update(fields_to_update)
            kwargs['update_fields'] = list(update_fields)

        super(Issue, self).save(*args, **kwargs)

        if update_fields is None or 'body_html' in update_fields or 'title' in update_fields:
            IssueEvent.objects.check_references(self, ['body_html', 'title'])
            from gim.core.models import Mention
            Mention.objects.set_for_issue(self)

    def delete(self, using=None):
        from gim.core.models import Mention
        Mention.objects.set_for_issue(self, forced_users=[])
        super(Issue, self).delete(using)

    def update_last_head_commit(self, commit=models.NOT_PROVIDED, save=True):
        if commit is models.NOT_PROVIDED:
            commit = self.get_head_commit(force=True)

        if commit == self.last_head_commit:
            return False

        self.last_head_commit = commit

        if save:
            self.save(update_fields=['last_head_commit'])

        return True

    def update_last_head_status(self, commit=models.NOT_PROVIDED, save=True):
        if commit is models.NOT_PROVIDED:
            commit = self.get_head_commit(force=True)

        if not commit or not commit.last_status or commit.last_status == self.last_head_status:
            # Note: we keep the previous status if we had one and the new commit doesn't
            return False

        self.last_head_status = commit.last_status

        if save:
            self.save(update_fields=['last_head_status'])

        return True

    @property
    def last_head_status_constant(self):
        return GITHUB_COMMIT_STATUS_CHOICES.for_value(self.last_head_status).constant

    @property
    def is_mergeable(self):
        if not self.is_pull_request:
            return False
        if self.state == 'closed':
            return False
        if self.mergeable:
            return True
        return self.mergeable_state in self.MERGEABLE_STATES['mergeable']


class IssueEvent(WithIssueMixin, GithubObjectWithId):
    repository = models.ForeignKey('Repository', related_name='issues_events')
    issue = models.ForeignKey('Issue', related_name='events')
    user = models.ForeignKey('GithubUser', related_name='issues_events', blank=True, null=True)
    event = models.CharField(max_length=256, blank=True, null=True, db_index=True)
    commit_sha = models.CharField(max_length=40, blank=True, null=True)
    created_at = models.DateTimeField(db_index=True)

    related_content_type = models.ForeignKey(ContentType, blank=True, null=True)
    related_object_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    related_object = generic.GenericForeignKey('related_content_type',
                                               'related_object_id')

    objects = IssueEventManager()

    github_matching = dict(GithubObjectWithId.github_matching)
    github_matching.update({
        'actor': 'user',
        'commit_id': 'commit_sha',
    })
    github_ignore = GithubObjectWithId.github_ignore + ('related_object_id',
            'related_content_type', 'related_object', 'commit_sha') + ('url', )
    github_date_field = ('created_at', None, None)

    class Meta:
        app_label = 'core'
        ordering = ('created_at', 'github_id')

    def __unicode__(self):
        return u'"%s" on Issue #%d' % (self.event, self.issue.number if self.issue else '?')

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_issues_events + [
            self.github_id,
        ]

    @property
    def github_url(self):
        if self.commit_sha:
            return self.repository.github_url + '/commit/%s' % self.commit_sha
        elif self.related_object_id:
            return self.related_object.github_url

    def save(self, *args, **kwargs):
        """
        Check for the related Commit object if the event is a reference to a
        commit. If not found, a job is created to search it later
        """
        from .commits import Commit

        needs_comit = False

        if self.commit_sha and not self.related_object_id:

            try:
                self.related_object = Commit.objects.filter(
                    authored_at__lte=self.created_at,
                    sha=self.commit_sha,
                    author=self.user
                ).order_by('-authored_at')[0]
            except IndexError:
                needs_comit = True

        super(IssueEvent, self).save(*args, **kwargs)

        if needs_comit:
            from gim.core.tasks.commit import FetchCommitBySha
            FetchCommitBySha.add_job('%s#%s' % (self.repository_id, self.commit_sha),
                                     fetch_comments=1)
            from gim.core.tasks.event import SearchReferenceCommitForEvent
            SearchReferenceCommitForEvent.add_job(self.id, delayed_for=30)


LABELTYPE_EDITMODE = Choices(
    ('LIST', 3, u'List of labels'),
    ('FORMAT', 2, u'Simple format'),
    ('REGEX', 1, u'Regular expression'),
)
LABELTYPE_EDITMODE.add_subset('MAYBE_METRIC', ('FORMAT', 'REGEX'))


class LabelType(models.Model):
    LABELTYPE_EDITMODE = LABELTYPE_EDITMODE

    repository = models.ForeignKey('Repository', related_name='label_types')
    regex = models.TextField(
        help_text=u'Must contain at least this part: <strong>(?P&lt;label&gt;visible-part-of-the'
                  u'-label)</strong>, and can include <strong>(?P&lt;order&gt;\d+)</strong> for '
                  u'ordering<br/>If you want the order to be the label, simply do: <strong>'
                  u'(?P&lt;label&gt;(?P&lt;order&gt;\d+))</strong>',
        validators=[
            validators.RegexValidator(
                re.compile('\(\?\P<label>.+\)'),
                u'Must contain a "label" part: "(?P<label>visible-part-of-the-label)"',
                'no-label'
            ),
            validators.RegexValidator(
                re.compile('^(?!.*\(\?P<order>(?!\\\d\+\))).*$'),
                u'If an order is present, it must math a number: the exact part must be: '
                u'"(?P<order>\d+)"',
                'invalid-order'
            ),
        ]
    )
    name = models.CharField(max_length=250)
    lower_name = models.CharField(max_length=250, db_index=True)
    edit_mode = models.PositiveSmallIntegerField(choices=LABELTYPE_EDITMODE.CHOICES, default=LABELTYPE_EDITMODE.REGEX)
    edit_details = JSONField(blank=True, null=True)
    is_metric = models.BooleanField(default=False,
        help_text=u'Only valid for "Simple format" or "Regular expression" groups with an "order". '
                  u'The order will be used as a value to do different kind of computations.<br />'
                  u'It can be used for example if the values are estimates, to get the '
                  u'total/mean/median for a list of issues')

    objects = LabelTypeManager()

    class Meta:
        app_label = 'core'
        verbose_name = u'Group'
        ordering = ('lower_name', )

    @cached_property
    def model_name(self):
        return self.__class__.__name__

    def __unicode__(self):
        return u'%s' % self.name

    def __str__(self):
        return unicode(self).encode('utf-8')

    @property
    def r(self):
        if not hasattr(self, '_regex'):
            self._regex = re.compile(self.regex)
        return self._regex

    def match(self, name):
        return self.r.search(name)

    def get_name_and_order(self, name):
        d = self.match(name).groupdict()
        return d['label'], d.get('order', None)

    def create_from_format(self, typed_name, order=None):
        """
        If the current type has the mode "format", then we try to use the given
        name and order to create a full label name
        """
        if self.edit_mode != self.LABELTYPE_EDITMODE.FORMAT:
            raise ValidationError('Cannot create a typed label for this group mode')

        result = self.edit_details['format_string']

        if order is not None and '{ordered-label}' in result:
            raise ValidationError('The order is not expected for this group')

        if order is not None and '{order}' not in result:
            raise ValidationError('The order is not expected for this group')
        elif order is None and '{order}' in result:
            raise ValidationError('An order is expected for this group')

        typed_name = typed_name.strip()
        if not typed_name:
            raise ValidationError('A label name is expected for this group')

        if '{label}' in result:
            result = result.replace('{label}', typed_name)
            if order:
                result = result.replace('{order}', str(order))
        elif '{ordered-label}' in result:
            result = result.replace('{ordered-label}', typed_name)

        if not self.match(result):
            raise ValidationError('Impossible to create a label for this group with these values')

        return result

    def save(self, *args, **kwargs):
        """
        Check validity, save the label-type, and apply label-type search for
        all labels of the repository
        """
        self.lower_name = self.name.lower()

        # validate that the regex is ok
        self.clean_fields()

        # clear the cached compiled regex
        if hasattr(self, '_regex'):
            del self._regex

        super(LabelType, self).save(*args, **kwargs)

        # reset the cache for this label, for all names
        LabelType.objects._reset_cache(self.repository)

        # update all labels for the repository
        for label in self.repository.labels.all():
            label.save()

    def delete(self, *args, **kwargs):
        LabelType.objects._reset_cache(self.repository)
        super(LabelType, self).delete(*args, **kwargs)

    @staticmethod
    def regex_from_format(format_string):
        return '^%s$' % re.escape(format_string)\
                          .replace('\\{label\\}', '(?P<label>.+)', 1) \
                          .replace('\\{order\\}', '(?P<order>\d+)', 1) \
                          .replace('\\{ordered\\-label\\}', '(?P<label>(?P<order>\d+))', 1)

    @staticmethod
    def regex_from_list(labels_list):
        if isinstance(labels_list, basestring):
            labels_list = labels_list.split(u',')
        return '^(?P<label>%s)$' % u'|'.join(map(re.escape, labels_list))

    def can_be_metric(self):
        if self.edit_mode == LABELTYPE_EDITMODE.LIST:
            return False

        if self.edit_mode == LABELTYPE_EDITMODE.FORMAT:
            format_string = self.edit_details['format_string']
            return bool(format_string) and ('{order}' in format_string or
                                            '{ordered-label}' in format_string)

        return bool(self.regex) and '(?P<order>\d+)' in self.regex


class Label(WithRepositoryMixin, GithubObject):
    repository = models.ForeignKey('Repository', related_name='labels')
    name = models.TextField(db_index=True)
    lower_name = models.TextField(db_index=True)
    color = models.CharField(max_length=6)
    api_url = models.TextField(blank=True, null=True)
    label_type = models.ForeignKey('LabelType', related_name='labels', blank=True, null=True, on_delete=models.SET_NULL)
    typed_name = models.TextField(db_index=True)
    lower_typed_name = models.TextField(db_index=True)
    order = models.IntegerField(blank=True, null=True, db_index=True)

    objects = WithRepositoryManager()

    github_matching = dict(GithubObject.github_matching)
    github_matching.update({
        'url': 'api_url'
    })
    github_ignore = GithubObject.github_ignore + ('api_url', 'label_type', 'typed_name', 'order', )
    github_identifiers = {'repository__github_id': ('repository', 'github_id'), 'name': 'name'}
    github_edit_fields = {
        'create': ('color', 'name', ),
        'update': ('color', 'name', )
    }
    github_per_page = {'min': 100, 'max': 100}

    class Meta:
        app_label = 'core'
        unique_together = (
            ('repository', 'name'),
        )
        index_together = (
            ('repository', 'label_type', 'order'),
        )
        ordering = ('label_type', 'order', 'lower_typed_name', 'lower_name')

    @property
    def github_url(self):
        return self.repository.github_url + '/issues?labels=%s' % self.name

    def __unicode__(self):
        if self.label_type_id:
            if self.order is not None:
                return u'%s: #%d %s' % (self.label_type.name, self.order, self.typed_name)
            else:
                return u'%s: %s' % (self.label_type.name, self.typed_name)
        else:
            return u'%s' % self.name

    @property
    def github_callable_identifiers(self):
        """
        If we have the api url of the label, use it as the normal way to get
        identifiers will fail since it's based on the name which may have been
        changed by the user
        """
        if self.api_url:
            return [self.api_url.replace('https://api.github.com/', '')]

        return self.repository.github_callable_identifiers_for_labels + [
            self.name,
        ]

    @property
    def github_callable_create_identifiers(self):
        return self.repository.github_callable_identifiers_for_labels

    def save(self, *args, **kwargs):
        label_type_infos = LabelType.objects.get_for_name(self.repository, self.name)
        if label_type_infos:
            self.label_type, self.typed_name, self.order = label_type_infos
        else:
            self.label_type, self.typed_name, self.order = None, self.name, None

        self.lower_name = self.name.lower()
        self.lower_typed_name = None if self.typed_name is None else self.typed_name.lower()

        if kwargs.get('update_fields', None) is not None:
            kwargs['update_fields'] += ['label_type', 'typed_name', 'order']

        super(Label, self).save(*args, **kwargs)

    def unique_error_message(self, model_class, unique_check):
        if unique_check == ('repository', 'name'):
            return 'A label with this name already exists for this repository'
        return super(Label, self).unique_error_message(model_class, unique_check)


class Milestone(WithRepositoryMixin, GithubObjectWithId):
    repository = models.ForeignKey('Repository', related_name='milestones')
    number = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    title = models.TextField(db_index=True)
    description = models.TextField(blank=True, null=True)
    state = models.CharField(max_length=10, db_index=True)
    created_at = models.DateTimeField(db_index=True, blank=True, null=True)
    due_on = models.DateTimeField(db_index=True, blank=True, null=True)
    creator = models.ForeignKey('GithubUser', related_name='milestones')

    objects = WithRepositoryManager()

    github_ignore = GithubObjectWithId.github_ignore + ('url', 'labels_url',
                                'updated_at', 'closed_issues', 'open_issues', )
    github_edit_fields = {
        'create': ('title', 'state', 'description', 'due_on', ),
        'update': ('title', 'state', 'description', 'due_on', )
    }
    github_per_page = {'min': 100, 'max': 100}

    class Meta:
        app_label = 'core'
        ordering = ('-number', )

    @property
    def github_url(self):
        return self.repository.github_url + '/issues?milestone=%s' % self.number

    def __unicode__(self):
        return u'%s' % self.title

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_milestones + [
            self.number,
        ]

    @property
    def github_callable_create_identifiers(self):
        return self.repository.github_callable_identifiers_for_milestones

    def save(self, *args, **kwargs):
        """
        If the creator, which is mandatory, is not defined, use (and create if
        needed) a special user named 'user.deleted'
        """
        from .users import GithubUser

        if self.creator_id is None:
            self.creator = GithubUser.objects.get_deleted_user()
            if kwargs.get('update_fields'):
                kwargs['update_fields'].append('creator')
        super(Milestone, self).save(*args, **kwargs)

        if not kwargs.get('updated_field')\
                or 'description' in kwargs['updated_field']\
                or 'title' in kwargs['updated_field']:
            IssueEvent.objects.check_references(self, ['description', 'title'], 'creator')
