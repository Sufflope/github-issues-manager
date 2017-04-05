
__all__ = [
    'CommitFile',
    'LocallyReviewedHunk',
    'LocalHunkSplit',
    'PullRequestFile',
]

from django.db import models, IntegrityError
from django.utils.functional import cached_property

from ..managers import (
    PullRequestFileManager,
    WithCommitManager,
)

from ..diffutils import (
    get_encoded_hunks_from_patch,
    encode_hunk,
)
from ..utils import JSONField

from .base import (
    GithubObject,
    GithubObjectWithId,
)

from .mixins import (
    WithIssueMixin,
    WithCommitMixin,
)


class LocallyReviewedHunk(models.Model):

    repository = models.ForeignKey('Repository', related_name='local_reviewed_files')
    author = models.ForeignKey('GithubUser', related_name='local_reviewed_files')
    path = models.TextField(blank=True, null=True)
    patch_sha = models.CharField(max_length=40)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'core'
        unique_together = [
            ('repository', 'author', 'path', 'patch_sha'),
        ]


class LocalHunkSplit(models.Model):
    repository = models.ForeignKey('Repository', related_name='local_hunks_splits')
    author = models.ForeignKey('GithubUser', related_name='local_hunks_splits')
    path = models.TextField(blank=True, null=True)
    line = models.TextField(blank=True, null=True)

    class Meta:
        app_label = 'core'
        unique_together = [
            ('repository', 'author', 'path', 'line'),
        ]

    @staticmethod
    def can_split_on_line(line, index, diff_len):
        return (2 <= index < diff_len - 2) and len(line.strip()) > 5

class FileMixin(models.Model):
    path = models.TextField(blank=True, null=True, db_index=True)
    status = models.CharField(max_length=32, blank=True, null=True)
    nb_additions = models.PositiveIntegerField(blank=True, null=True)
    nb_deletions = models.PositiveIntegerField(blank=True, null=True)
    patch = models.TextField(blank=True, null=True)
    sha = models.CharField(max_length=40, blank=True, null=True, db_index=True)
    patch_sha = models.CharField(max_length=40, blank=True, null=True)
    hunk_shas = JSONField(blank=True, null=True)

    github_matching = dict(GithubObject.github_matching)
    github_matching.update({
        'additions': 'nb_additions',
        'deletions': 'nb_deletions',
        'filename': 'path'
    })

    class Meta:
        abstract = True

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):

        patch_sha = encode_hunk(self.patch)

        if patch_sha != self.patch_sha:
            self.patch_sha = patch_sha
            if update_fields and 'patch_sha' not in update_fields:
                update_fields = list(update_fields) + ['patch_sha']
            hunk_shas = list(get_encoded_hunks_from_patch(self.patch).keys())
            if hunk_shas != self.hunk_shas and (hunk_shas or self.hunk_shas):  # avoid changing if one is None and the other []
                self.hunk_shas = hunk_shas
                if update_fields and 'hunk_shas' not in update_fields:
                    update_fields = list(update_fields) + ['hunk_shas']

        super(FileMixin, self).save(force_insert, force_update, using, update_fields)

    def get_locally_reviewed_filters_for_user(self, user, patch_sha=None):
        return {
            'repository': self.repository,
            'author': user,
            'path': self.path,
            'patch_sha': patch_sha or self.patch_sha,
        }

    def get_hunks_locally_reviewed_by_user(self, user):
        if not self.hunk_shas:
            return {}

        filters = self.get_locally_reviewed_filters_for_user(user)
        del filters['patch_sha']
        filters['patch_sha__in'] = self.hunk_shas

        reviewed_shas = set(LocallyReviewedHunk.objects.filter(**filters).values_list('patch_sha', flat=True))

        return {sha: sha in reviewed_shas for sha in self.hunk_shas}

    def is_locally_reviewed_by_user(self, user, patch_sha=None):
        if patch_sha is None:
            patch_sha = self.patch_sha

        if not patch_sha:
            return None

        return LocallyReviewedHunk.objects.filter(
            **self.get_locally_reviewed_filters_for_user(user, patch_sha)
        ).exists()

    def update_locally_reviewed_by_user_from_hunks(self, user):
        all_shas = self.get_hunks_locally_reviewed_by_user(user)
        if all(all_shas.values()):
            self.mark_locally_reviewed_by_user(user)
        else:
            self.unmark_locally_reviewed_by_user(user, propagate=False)

    def mark_locally_reviewed_by_user(self, user, patch_sha=None, propagate=True):

        whole_file = False
        if patch_sha is None:
            whole_file = True
            patch_sha = self.patch_sha

        if not patch_sha:
            return False

        try:
            LocallyReviewedHunk.objects.create(
                **self.get_locally_reviewed_filters_for_user(user, patch_sha)
            )
        except IntegrityError:
            return False
        else:
            return True
        finally:
            if propagate:
                if whole_file:
                    for hunk_sha in self.hunk_shas:
                        self.mark_locally_reviewed_by_user(user, hunk_sha, propagate=False)
                else:
                    self.update_locally_reviewed_by_user_from_hunks(user)

    def unmark_locally_reviewed_by_user(self, user, patch_sha=None, propagate=True):

        whole_file = False
        if patch_sha is None:
            whole_file = True
            patch_sha = self.patch_sha

        if not patch_sha:
            return False

        try:
            LocallyReviewedHunk.objects.get(
                **self.get_locally_reviewed_filters_for_user(user, patch_sha)
            ).delete()
        except LocallyReviewedHunk.DoesNotExist:
            return False
        else:
            return True
        finally:
            if propagate:
                if whole_file:
                    for hunk_sha in self.hunk_shas:
                        self.unmark_locally_reviewed_by_user(user, hunk_sha, propagate=False)
                else:
                    self.unmark_locally_reviewed_by_user(user, propagate=False)

    def get_split_lines_filters_for_user(self, user, line=None):
        filters = {
            'repository': self.repository,
            'author': user,
            'path': self.path,
        }
        if line is not None:
            filters['line'] = line
        return filters

    def get_split_lines_for_user(self, user):
        filters = self.get_split_lines_filters_for_user(user)
        return LocalHunkSplit.objects.filter(**filters).values_list('line', flat=True)

    def add_split_for_user(self, user, line):
        try:
            LocalHunkSplit.objects.create(
                **self.get_split_lines_filters_for_user(user, line)
            )
        except IntegrityError:
            return False
        else:
            return True

    def remove_split_for_user(self, user, line):
        try:
            LocalHunkSplit.objects.get(
                **self.get_split_lines_filters_for_user(user, line)
            ).delete()
        except LocalHunkSplit.DoesNotExist:
            return False
        else:
            return True


class PullRequestFile(FileMixin, WithIssueMixin, GithubObject):
    repository = models.ForeignKey('Repository', related_name='pr_files')
    issue = models.ForeignKey('Issue', related_name='files')
    tree = models.CharField(max_length=40, blank=True, null=True, db_index=True)

    objects = PullRequestFileManager()
    github_ignore = GithubObjectWithId.github_ignore + ('nb_additions', 'nb_deletions',
                                'path') + ('raw_url', 'contents_url', 'blob_url', 'changes')
    github_identifiers = {
        'repository__github_id': ('repository', 'github_id'),
        'issue__number': ('issue', 'number'),
        'tree': 'tree',
        'sha': 'sha',
        'path': 'path',
    }

    class Meta:
        app_label = 'core'
        ordering = ('path', )
        unique_together = (
            ('repository', 'issue', 'tree', 'sha', 'path',)
        )

    def __unicode__(self):
        return u'"%s" on Issue #%d' % (self.path, self.issue.number if self.issue_id else '?')

    @property
    def github_url(self):
        return self.repository.github_url + '/blob/%s/%s' % (self.tree, self.path)


class CommitFile(FileMixin, WithCommitMixin, GithubObject):
    repository = models.ForeignKey('Repository', related_name='commit_files')
    commit = models.ForeignKey('Commit', related_name='files')

    objects = WithCommitManager()
    github_ignore = GithubObjectWithId.github_ignore + ('nb_additions', 'nb_deletions',
                                'path') + ('raw_url', 'contents_url', 'blob_url', 'changes')
    github_identifiers = {
        'repository__github_id': ('repository', 'github_id'),
        'commit__sha': ('commit', 'sha'),
        'sha': 'sha',
        'path': 'path',
    }

    class Meta:
        app_label = 'core'
        ordering = ('path', )
        unique_together = (
            ('repository', 'commit', 'sha', 'path',)
        )

    def __unicode__(self):
        return u'"%s" on Commit #%s' % (self.path, self.commit.sha if self.commit_id else '?')

    @property
    def github_url(self):
        return self.repository.github_url + '/blob/%s/%s' % (self.commit.sha, self.path)

    @cached_property
    def tree(self):
        return self.commit.sha
