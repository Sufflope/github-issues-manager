
__all__ = [
    'CommitFile',
    'LocalReviewedFile',
    'PullRequestFile',
]

import hashlib

from django.db import models, IntegrityError
from django.utils.functional import cached_property

from ..managers import (
    PullRequestFileManager,
    WithCommitManager,
)

from .base import (
    GithubObject,
    GithubObjectWithId,
)

from .mixins import (
    WithIssueMixin,
    WithCommitMixin,
)


class LocalReviewedFile(models.Model):

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


class FileMixin(models.Model):
    path = models.TextField(blank=True, null=True, db_index=True)
    status = models.CharField(max_length=32, blank=True, null=True)
    nb_additions = models.PositiveIntegerField(blank=True, null=True)
    nb_deletions = models.PositiveIntegerField(blank=True, null=True)
    patch = models.TextField(blank=True, null=True)
    sha = models.CharField(max_length=40, blank=True, null=True, db_index=True)
    patch_sha = models.CharField(max_length=40, blank=True, null=True)

    github_matching = dict(GithubObject.github_matching)
    github_matching.update({
        'additions': 'nb_additions',
        'deletions': 'nb_deletions',
        'filename': 'path'
    })

    class Meta:
        abstract = True

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):

        patch_sha = None
        if self.patch:
            try:
                patch_sha = hashlib.sha1(
                    '\n'.join(
                        '@@' if l.startswith('@@') else l
                        for l in self.patch.encode('utf-8').split('\n')
                    )
                ).hexdigest()
            except:
                # ignore patch sha that cannot be computed
                pass

        if patch_sha != self.patch_sha:
            self.patch_sha = patch_sha
            if update_fields and 'patch_sha' not in update_fields:
                update_fields = list(update_fields) + ['patch_sha']

        super(FileMixin, self).save(force_insert, force_update, using, update_fields)

    def get_locally_reviewed_filters_for_user(self, user):
        return {
            'repository': self.repository,
            'author': user,
            'path': self.path,
            'patch_sha': self.patch_sha,
        }

    def is_locally_reviewed_by_user(self, user):
        if not self.patch_sha:
            return None

        return LocalReviewedFile.objects.filter(
            **self.get_locally_reviewed_filters_for_user(user)
        ).exists()

    def mark_locally_reviewed_by_user(self, user):
        if not self.patch_sha:
            return False

        try:
            LocalReviewedFile.objects.create(
                **self.get_locally_reviewed_filters_for_user(user)
            )
        except IntegrityError:
            return False

        return True

    def unmark_locally_reviewed_by_user(self, user):
        if not self.patch_sha:
            return False

        try:
            LocalReviewedFile.objects.get(
                **self.get_locally_reviewed_filters_for_user(user)
            ).delete()
        except LocalReviewedFile.DoesNotExist:
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
