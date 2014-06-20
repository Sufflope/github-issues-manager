__all__ = [
    'Commit',
    'IssueCommits',
]

from django.db import models

from ..managers import (
    CommitManager,
    IssueCommitsManager,
)

from .base import (
    GithubObject,
    GithubObjectWithId,
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
    })
    github_ignore = GithubObject.github_ignore + ('deleted', 'comments_count',
        ) + ('url', 'parents', 'comments_url', 'html_url', 'commit', )

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

    def update_comments_count(self):
        self.comments_count = self.commit_comments.count()
        self.save(update_fields=['comments_count'])


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

    delete_missing_after_fetch = False

    objects = IssueCommitsManager()

    class Meta:
        app_label = 'core'

    def __unicode__(self):
        result = u'%s on %s'
        if self.deleted:
            result += u' (deleted)'
        return result % (self.commit.sha, self.issue.number)
