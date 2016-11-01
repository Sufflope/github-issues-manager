__all__ = [
    'Card',
    'Column',
    'Project',
]

from django.db import models
from extended_choices import Choices

from .base import (
    GithubObjectWithId,
)

from ..managers import CardManager, ColumnManager, ProjectManager

from .mixins import (
    WithRepositoryMixin,
)


class Project(WithRepositoryMixin, GithubObjectWithId):
    repository = models.ForeignKey('Repository', related_name='projects')

    creator = models.ForeignKey('GithubUser', related_name='projects')

    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)

    name = models.TextField()
    number = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    body = models.TextField(blank=True, null=True)

    columns_fetched_at = models.DateTimeField(blank=True, null=True)
    columns_etag = models.CharField(max_length=64, blank=True, null=True)

    github_per_page = {'min': 30, 'max': 30}  # forced to 30 by github
    github_date_field = None  # we always need all if something changed
    github_ignore = GithubObjectWithId.github_ignore + ('owner_url', 'url', )
    github_api_version = 'inertia-preview'

    objects = ProjectManager()

    class Meta:
        app_label = 'core'
        ordering = ('number', )
        unique_together = (
            ('repository', 'number'),
        )

    @property
    def github_url(self):
        return self.repository.github_url + '/projects/%s' % self.number

    def __unicode__(self):
        return u'#%s %s' % (self.number or '??', self.name)

    @property
    def github_callable_identifiers(self):
        return ['projects', self.github_id]

    @property
    def github_callable_identifiers_for_columns(self):
        return self.github_callable_identifiers + [
            'columns',
        ]

    def fetch_columns(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('columns', gh,
                                defaults={
                                    'fk': {'project': self},
                                    'related': {'*': {'fk': {'project': self}}},
                                },
                                force_fetch=force_fetch,
                                parameters=parameters)

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        super(Project, self).fetch_all(gh, force_fetch=force_fetch)
        self.fetch_columns(gh, force_fetch=force_fetch)
        self.fetch_all_cards(gh, force_fetch=force_fetch)

    def fetch_all_cards(self, gh, force_fetch=False, **kwargs):
        for column in self.columns.all():
            column.fetch_cards(gh, force_fetch)


class Column(GithubObjectWithId):
    project = models.ForeignKey(Project, related_name='columns')

    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)

    name = models.TextField()

    position = models.PositiveIntegerField(null=True)

    cards_fetched_at = models.DateTimeField(blank=True, null=True)
    cards_etag = models.CharField(max_length=64, blank=True, null=True)

    github_per_page = {'min': 30, 'max': 30}  # forced to 30 by github
    github_date_field = None  # we always need all if something changed
    github_ignore = GithubObjectWithId.github_ignore + ('project_url', )
    github_api_version = 'inertia-preview'

    objects = ColumnManager()

    class Meta:
        app_label = 'core'
        ordering = ('position', )

    @property
    def github_url(self):
        return self.project.github_url + '/projects/columns/%s' % self.github_id

    def __unicode__(self):
        return u'%s | col[%s] %s' % (self.project, self.position, self.name)

    @property
    def github_callable_identifiers(self):
        return ['projects', 'columns', self.github_id]

    @property
    def github_callable_identifiers_for_cards(self):
        return self.github_callable_identifiers + [
            'cards',
        ]

    def fetch_cards(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('cards', gh,
                                defaults={
                                    'fk': {'column': self},
                                    'related': {'*': {'fk': {'column': self}}},
                                },
                                force_fetch=force_fetch,
                                parameters=parameters)

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        super(Column, self).fetch_all(gh, force_fetch=force_fetch)
        self.fetch_cards(gh, force_fetch=force_fetch)


CARDTYPE = Choices(
    ('NOTE', 1, u'Note'),
    ('ISSUE', 2, u'Issue/Pull request'),
)


class Card(GithubObjectWithId):
    CARDTYPE = CARDTYPE

    column = models.ForeignKey(Column, related_name='cards')

    type = models.PositiveSmallIntegerField(choices=CARDTYPE.CHOICES)

    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)

    note = models.TextField(blank=True, null=True)
    issue = models.ForeignKey('Issue', related_name='cards', blank=True, null=True)

    position = models.PositiveIntegerField(null=True)

    github_per_page = {'min': 30, 'max': 30}  # forced to 30 by github
    github_date_field = None  # we always need all if something changed
    github_ignore = GithubObjectWithId.github_ignore + ('column_url', )
    github_api_version = 'inertia-preview'

    objects = CardManager()

    class Meta:
        app_label = 'core'
        ordering = ('position', )

    @property
    def github_url(self):
        return self.project.github_url + '/projects/cards/%s' % self.github_id

    def __unicode__(self):
        return u'%s | [%s] %s' % (self.column, self.position, '#%s' % self.issue.number if self.issue_id else "note")

    @property
    def github_callable_identifiers(self):
        return ['projects', 'columns', 'cards', self.github_id]

    @property
    def github_callable_create_identifiers(self):
        return self.column.github_callable_identifiers_for_cards

    @property
    def github_callable_create_identifiers_for_moves(self):
        return self.github_callable_identifiers + [
            'moves',
        ]

    @property
    def repository_id(self):
        return self.column.project.repository_id

    @property
    def repository(self):
        return self.column.project.repository

    @property
    def is_note(self):
        return self.type == CARDTYPE.NOTE
