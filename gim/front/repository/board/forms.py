from datetime import datetime
from functools import partial

from django import forms
from django.db.models import Max

from gim.front.mixins.forms import LinkedToUserFormMixin, LinkedToRepositoryFormMixin
from gim.core.models import GITHUB_STATUS_CHOICES, Card, Column, Project
from gim.front.repository.issues.forms import validate_filled_string


class LinkedToProjectFormMixin(LinkedToRepositoryFormMixin):
    """
    A simple mixin that get the "project" argument passed as parameter and
    save it in the "project" instance's attribute.
    Will also set the project as attribute of the form's instance if there
    is any, unless "project_attribute" is None
    Do the same the repository, as its a subclass of LinkedToRepositoryFormMixin
    """
    project_attribute = 'project'

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project')

        # pass the repository to the parent class
        kwargs['repository'] = self.project.repository
        super(LinkedToProjectFormMixin, self).__init__(*args, **kwargs)

        attr = '%s_id' % self.project_attribute
        if self.project_attribute and getattr(self, 'instance', None) and hasattr(self.instance, attr):
            if not getattr(self.instance, attr):
                setattr(self.instance, self.project_attribute, self.project)

    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        if exclude:
            if 'repository' in exclude:
                exclude.remove('repository')
            if 'project' in exclude:
                exclude.remove('project')
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)


class BaseCardNoteEditForm(LinkedToUserFormMixin, LinkedToProjectFormMixin):
    user_attribute = None
    project_attribute = None

    class Meta:
        model = Card
        fields = ['note', 'front_uuid', ]

    def __init__(self, *args, **kwargs):
        super(BaseCardNoteEditForm, self).__init__(*args, **kwargs)
        self.fields['note'].validators = [partial(validate_filled_string, name='note')]
        self.fields['note'].required = True

    def save(self, commit=True):
        if self.instance.pk:
            self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_UPDATE
        else:
            self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_CREATE
        self.instance.note_html = None
        self.instance.updated_at = datetime.utcnow()
        if not self.instance.created_at:
            self.instance.created_at = self.instance.updated_at
        return super(BaseCardNoteEditForm, self).save(commit)


class CardNoteCreateForm(BaseCardNoteEditForm):
    user_attribute = 'creator'

    def save(self, commit=True):
        # its a new note...
        self.instance.is_new = True
        self.instance.type = Card.CARDTYPE.NOTE

        # ...at the first position
        self.instance.position = 1

        # so we need to increment position of all other cards
        for index, card in enumerate(self.instance.column.cards.all()):
            card.position = index + 2  # index starts at 0, but we start our position at 2
            card.save(update_fields=['position'])

        return super(CardNoteCreateForm, self).save(commit)


class CardNoteEditForm(BaseCardNoteEditForm):
    pass


class CardNoteDeleteForm(LinkedToUserFormMixin, LinkedToProjectFormMixin):
    user_attribute = None
    project_attribute = None

    class Meta:
        model = Card
        fields = ['front_uuid', ]

    def save(self, commit=True):
        self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_DELETE
        return super(CardNoteDeleteForm, self).save(commit)


class BaseColumnEditForm(LinkedToProjectFormMixin):
    class Meta:
        model = Column
        fields = ['name', 'front_uuid', ]

    def __init__(self, *args, **kwargs):
        super(BaseColumnEditForm, self).__init__(*args, **kwargs)
        self.fields['name'].validators = [partial(validate_filled_string, name='name')]
        self.fields['name'].required = True
        self.fields['name'].widget = forms.TextInput()

    def save(self, commit=True):
        if self.instance.pk:
            self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_UPDATE
        else:
            self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_CREATE
        self.instance.updated_at = datetime.utcnow()
        if not self.instance.created_at:
            self.instance.created_at = self.instance.updated_at
        return super(BaseColumnEditForm, self).save(commit)


class ColumnCreateForm(BaseColumnEditForm):

    def save(self, commit=True):
        # its a new column...
        self.instance.is_new = True

        # ...at the last position
        self.instance.position = (self.project.columns.aggregate(Max('position'))['position__max'] or 0) + 1

        return super(ColumnCreateForm, self).save(commit)


class ColumnEditForm(BaseColumnEditForm):
    pass


class ColumnDeleteForm(LinkedToProjectFormMixin):

    class Meta:
        model = Column
        fields = ['front_uuid', ]

    def save(self, commit=True):
        self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_DELETE
        return super(ColumnDeleteForm, self).save(commit)


class BaseProjectEditForm(LinkedToRepositoryFormMixin):
    class Meta:
        model = Project
        fields = ['front_uuid', 'name', 'body']

    def __init__(self, *args, **kwargs):
        super(BaseProjectEditForm, self).__init__(*args, **kwargs)
        self.fields['name'].validators = [partial(validate_filled_string, name='name')]
        self.fields['name'].required = True
        self.fields['name'].widget = forms.TextInput()
        self.fields['body'].validators = [partial(validate_filled_string, name='body')]
        self.fields['body'].required = False
        self.fields['body'].label = 'Description'

    def save(self, commit=True):
        if self.instance.pk:
            self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_UPDATE
        else:
            self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_CREATE
        self.instance.updated_at = datetime.utcnow()
        if not self.instance.created_at:
            self.instance.created_at = self.instance.updated_at
        return super(BaseProjectEditForm, self).save(commit)


class ProjectEditForm(BaseProjectEditForm):
    pass


class ProjectDeleteForm(LinkedToRepositoryFormMixin):

    class Meta:
        model = Project
        fields = ['front_uuid', ]

    def save(self, commit=True):

        for column in self.instance.columns.all():
            column.delete()

        self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_DELETE
        return super(ProjectDeleteForm, self).save(commit)


class ProjectCreateForm(LinkedToUserFormMixin, BaseProjectEditForm):
    user_attribute = 'creator'

    def save(self, commit=True):
        # its a new column...
        self.instance.is_new = True

        return super(ProjectCreateForm, self).save(commit)
