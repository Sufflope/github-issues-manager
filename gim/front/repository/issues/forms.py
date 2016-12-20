
from datetime import datetime, timedelta
from functools import partial
from collections import OrderedDict

import json

from django import forms

from gim.core.models import (Issue, GITHUB_STATUS_CHOICES, Card, Column,
                             IssueComment, PullRequestComment, CommitComment,
                             PullRequestReview)

from gim.front.mixins.forms import (LinkedToUserFormMixin, LinkedToIssueFormMixin,
                                    LinkedToCommitFormMixin, LinkedToRepositoryFormMixin)


def validate_filled_string(value, name='comment'):
    if not value or not value.strip():
        raise forms.ValidationError('You must enter a %s' % name)


class IssueFormMixin(LinkedToRepositoryFormMixin):
    change_updated_at = 'exact'  # 'fuzzy' / None

    fuzzy_delta = timedelta(seconds=120)

    class Meta:
        model = Issue

    def __init__(self, *args, **kwargs):
        super(IssueFormMixin, self).__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = None

    def save(self, commit=True):
        """
        Update the updated_at to create a new event at the correct time.
        The real update time from github will be saved via dist_edit which
        does a forced update.
        """
        revert_status = None
        if self.instance.github_status == GITHUB_STATUS_CHOICES.FETCHED:
            # We'll wait to have m2m saved (in super) to run signals
            self.instance.github_status = GITHUB_STATUS_CHOICES.SAVING
            revert_status = GITHUB_STATUS_CHOICES.FETCHED

        if self.change_updated_at is not None:
            now = datetime.utcnow()
            if not self.instance.updated_at:
                self.instance.updated_at = now
            elif self.change_updated_at == 'fuzzy':
                if now > self.instance.updated_at + self.fuzzy_delta:
                    self.instance.updated_at = now
            else:  # 'exact'
                if now > self.instance.updated_at:
                    self.instance.updated_at = now

        instance = super(IssueFormMixin, self).save(commit)

        if revert_status:
            # Ok now the signals could work
            instance.github_status = revert_status
            instance.save()

        return instance


class IssueStateForm(LinkedToUserFormMixin, IssueFormMixin):
    user_attribute = None  # don't update issue's user

    class Meta(IssueFormMixin.Meta):
        fields = ['state', 'front_uuid']

    def clean_state(self):
        new_state = self.cleaned_data.get('state')
        if new_state not in ('open', 'closed'):
            raise forms.ValidationError('Invalide state')
        if new_state == self.instance.state:
            raise forms.ValidationError('The %s was already %s, please reload.' %
                (self.instance.type, 'reopened' if new_state == 'open' else 'closed'))
        return new_state

    def save(self, commit=True):
        self.instance.state = self.cleaned_data['state']
        if self.instance.state == 'closed':
            self.instance.closed_by = self.user
            self.instance.closed_at = datetime.utcnow()
        else:
            self.instance.closed_by = None
            self.instance.closed_at = None
        return super(IssueStateForm, self).save(commit)


class IssueTitleFormPart(object):
    def __init__(self, *args, **kwargs):
        super(IssueTitleFormPart, self).__init__(*args, **kwargs)
        self.fields['title'].validators = [partial(validate_filled_string, name='title')]
        self.fields['title'].widget = forms.TextInput(attrs={'placeholder': 'Title'})


class IssueBodyFormPart(object):
    def __init__(self, *args, **kwargs):
        super(IssueBodyFormPart, self).__init__(*args, **kwargs)
        self.fields['body'].widget.attrs.update({
            'placeholder': 'Description',
            'cols': None,
            'rows': None,
        })

    def save(self, commit=True):
        self.instance.body_html = None  # will be reset with data from github
        return super(IssueBodyFormPart, self).save(commit)


class IssueMilestoneFormPart(object):

    def __init__(self, *args, **kwargs):
        super(IssueMilestoneFormPart, self).__init__(*args, **kwargs)

        milestones = self.repository.milestones.all()
        self.fields['milestone'].queryset = milestones

        milestones_data = self.repository.get_milestones_for_select(milestones=milestones)

        self.fields['milestone'].widget.choices = [('', 'No milestone')] + [
            (
                state,
                [(milestone.id, milestone.title) for milestone in state_milestones]
            )
            for state, state_milestones
            in milestones_data['grouped_milestones'].items()
        ]

        self.fields['milestone'].widget.attrs.update({
            'data-milestones': milestones_data['milestones_json'],
            'placeholder': 'Choose a milestone',
        })


class IssueAssigneesFormPart(object):
    def __init__(self, *args, **kwargs):
        super(IssueAssigneesFormPart, self).__init__(*args, **kwargs)
        collaborators = self.repository.collaborators.all()
        self.fields['assignees'].required = False
        self.fields['assignees'].queryset = collaborators
        self.fields['assignees'].widget.choices = self.get_collaborators_choices(collaborators)
        self.fields['assignees'].widget.attrs.update({
            'data-collaborators': self.get_collaborators_json(collaborators),
            'placeholder': 'Choose some assignees',
        })

    def get_collaborators_json(self, collaborators):
        data = {u.id: {
                        'id': u.id,
                        'full_avatar_url': u.full_avatar_url,
                        'username': u.username,
                      }
                for u in collaborators}
        return json.dumps(data)

    def get_collaborators_choices(self, collaborators):
        return [('', 'No one assigned')] + [(u.id, u.username) for u in collaborators]


class IssueLabelsFormPart(object):
    simple_label_name = 'Labels'

    def __init__(self, *args, **kwargs):
        super(IssueLabelsFormPart, self).__init__(*args, **kwargs)
        labels = self.repository.labels.select_related('label_type')
        self.fields['labels'].required = False
        self.fields['labels'].queryset = labels
        self.fields['labels'].widget.choices = self.get_labels_choices(labels)
        self.fields['labels'].widget.attrs.update({
            'data-labels': self.get_labels_json(labels),
            'placeholder': 'Choose some labels',
        })

    def get_labels_json(self, labels):
        data = {l.id: {
                        'id': l.id,
                        'name': l.name,
                        'color': l.color,
                        'type': l.label_type.name if l.label_type_id else None,
                        'typed_name': l.typed_name,
                        'search': '%s: %s' % (l.label_type.name, l.typed_name)
                                            if l.label_type_id else l.name,
                      }
                for l in labels}
        return json.dumps(data)

    def get_labels_choices(self, labels):
        data = OrderedDict()
        for label in labels:
            type_name = label.label_type.name if label.label_type_id else self.simple_label_name
            data.setdefault(type_name, []).append(
                (label.id, label.typed_name)
            )
        # move Others at the end
        if self.simple_label_name in data:
            data[self.simple_label_name] = data.pop(self.simple_label_name)
        return data.items()


class IssueProjectsFormPart(object):

    columns = forms.ModelMultipleChoiceField(queryset=Column.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super(IssueProjectsFormPart, self).__init__(*args, **kwargs)
        columns = Column.objects.filter(
            project__repository=self.repository
        ).select_related(
            'project'
        ).order_by('project__number', 'position')
        self.fields['columns'].queryset = columns
        if self.instance and self.instance.pk:
            self.fields['columns'].initial = Column.objects.filter(cards__issue=self.instance)
        self.fields['columns'].widget.choices = self.get_columns_choices(columns)
        self.fields['columns'].widget.attrs.update({
            'data-columns': self.get_columns_json(columns),
            'placeholder': 'Assign to projects',
        })
        self.fields['columns'].error_messages['invalid_choice'] =\
            self.fields['columns'].error_messages['invalid_pk_value'] =\
            'At least one of the choices is invalid'
        self.fields['columns'].help_text = 'When selecting a new column, the issue will be ' \
                                           'appended at the bottom of that column.'

    def get_columns_choices(self, columns):
        data = OrderedDict()
        for column in columns:
            data.setdefault(column.project.name, []).append(
                (column.id, column.name)
            )
        return data.items()

    def get_columns_json(self, columns):
        data = {c.id: {
                        'id': c.id,
                        'name': c.name,
                        'project_number': c.project.number,
                        'project_name': c.project.name,
                        'search': '%s: %s' % (c.project.name, c.name),
                      }
                for c in columns}
        return json.dumps(data)

    def clean_columns(self):
        """Validate that there is no more than one selected column for a given project"""
        columns = self.cleaned_data['columns']
        seen_projects = set()
        for column in columns:
            if column.project.number in seen_projects:
                raise forms.ValidationError('You can only select one column for a given project')
            seen_projects.add(column.project.number)
        return columns

    def update_columns(self, instance):

        actual_columns =  Column.objects.filter(cards__issue=instance)
        actual_columns_by_id = {c.id: c for c in actual_columns}
        actual_projects_ids = {c.project_id for c in actual_columns}

        new_columns = self.cleaned_data['columns']
        new_columns_by_id = {c.id: c for c in new_columns}
        new_projects_ids = {c.project_id for c in new_columns}


        projects_to_add = new_projects_ids - actual_projects_ids
        projects_to_remove = actual_projects_ids - new_projects_ids
        projects_to_move = new_projects_ids.intersection(actual_projects_ids)

        columns_to_add = {c.id for c in new_columns if c.project_id in projects_to_add}
        columns_to_remove = {c.id for c in actual_columns if c.project_id in projects_to_remove}
        columns_to_move = {}
        for project_id in projects_to_move:
            actual_column_id = [c.id for c in actual_columns if c.project_id == project_id][0]
            new_column_id = [c.id for c in new_columns if c.project_id == project_id][0]
            if actual_column_id != new_column_id:
                columns_to_move[actual_column_id] = new_column_id

        update_data = {
            'remove_from_columns': {},
            'add_to_columns': list(columns_to_add),  # a set cannot be saved as json for the job
            'move_between_columns': columns_to_move,
        }

        cards_to_remove = {}
        if columns_to_remove:
            cards_to_remove = instance.cards.filter(column_id__in=columns_to_remove)
            update_data['remove_from_columns'] = dict(cards_to_remove.values_list('column_id', 'github_id'))

        now = datetime.utcnow()

        def update_card(card, position_delta=None, position_exact=None, status=GITHUB_STATUS_CHOICES.WAITING_UPDATE):
            card.position = position_exact if position_exact else card.position + position_delta
            card.updated_at = now
            card.github_status = status
            card.front_uuid = instance.front_uuid,
            card.skip_status_check_to_publish = True
            card.save()

        if columns_to_remove:
            for card in cards_to_remove:
                # decrement cards position after the current one in the original column
                if card.position:
                    cards_to_update = card.column.cards.filter(position__gt=card.position)
                    for sibling_card in cards_to_update:
                        update_card(sibling_card, position_delta=-1)
                # and delete the card
                card.front_uuid = instance.front_uuid,
                card.skip_status_check_to_publish = True
                card.delete()

        if columns_to_add:
            for column_id in columns_to_add:
                column = new_columns_by_id[column_id]
                last_card = column.cards.order_by('position').only('position').last()
                position = last_card.position + 1 if last_card is not None else 1
                card = Card(
                    type=Card.CARDTYPE.ISSUE,
                    created_at=now,
                    issue=instance,
                    column=column,
                )
                card.is_new = True
                card.skip_status_check_to_publish = True
                update_card(card, position_exact=position, status=GITHUB_STATUS_CHOICES.WAITING_CREATE)
                # and we increment all the cards after this one
                cards_to_update = column.cards.filter(position__gte=position).exclude(id=card.id)
                for sibling_card in cards_to_update:
                    update_card(sibling_card, position_delta=1)

        if columns_to_move:
            for actual_column_id, new_column_id in columns_to_move.items():
                actual_column = actual_columns_by_id[actual_column_id]
                new_column = new_columns_by_id[new_column_id]
                card = instance.cards.get(column_id=actual_column_id)
                actual_position = card.position
                last_card = new_column.cards.order_by('position').only('position').last()
                new_position = last_card.position + 1 if last_card is not None else 1
                # update card
                card.column = new_column
                update_card(card, position_exact=new_position)
                # increment cards position after the current one in the new column
                if new_position:
                    cards_to_update = new_column.cards.filter(position__gte=new_position).exclude(id=card.id)
                    for sibling_card in cards_to_update:
                        update_card(sibling_card, position_delta=1)
                # decrement cards position after the current one in the original column
                if actual_position:
                    cards_to_update = actual_column.cards.filter(position__gt=actual_position)
                    for sibling_card in cards_to_update:
                        update_card(sibling_card, position_delta=-1)

        return update_data

    def save(self, commit=True):
        is_new = not bool(self.instance.pk)

        update_data = {}

        if not is_new:
            update_data = self.update_columns(self.instance)

        instance = super(IssueProjectsFormPart, self).save(commit=commit)

        if is_new:
            update_data = self.update_columns(instance)

        instance._columns_to_update = update_data

        return instance


class IssueTitleForm(IssueTitleFormPart, IssueFormMixin):
    class Meta(IssueFormMixin.Meta):
        fields = ['title', 'front_uuid']


class IssueBodyForm(IssueBodyFormPart, IssueFormMixin):
    class Meta(IssueFormMixin.Meta):
        fields = ['body', 'front_uuid']


class IssueMilestoneForm(IssueMilestoneFormPart, IssueFormMixin):
    change_updated_at = 'fuzzy'

    class Meta(IssueFormMixin.Meta):
        fields = ['milestone', 'front_uuid']


class IssueAssigneesForm(IssueAssigneesFormPart, IssueFormMixin):
    change_updated_at = 'fuzzy'

    class Meta(IssueFormMixin.Meta):
        fields = ['assignees', 'front_uuid']


class IssueLabelsForm(IssueLabelsFormPart, IssueFormMixin):
    change_updated_at = 'fuzzy'

    class Meta(IssueFormMixin.Meta):
        fields = ['labels', 'front_uuid']


class IssueProjectsForm(IssueProjectsFormPart, IssueFormMixin):
    change_updated_at = 'fuzzy'

    columns = IssueProjectsFormPart.columns

    def __init__(self, *args, **kwargs):
        super(IssueProjectsForm, self).__init__(*args, **kwargs)
        self.fields = OrderedDict(
            (name, self.fields[name]) for name in ['columns', 'front_uuid']
        )

    class Meta(IssueFormMixin.Meta):
        # 'columns' is not a model fields, and is added directly by `IssueProjectsFormPart` so
        # we must not set it in `fields` which represents only model fields
        fields = ['front_uuid']


class IssueCreateForm(IssueTitleFormPart, IssueBodyFormPart,
                      LinkedToUserFormMixin, IssueFormMixin):

    class Meta(IssueFormMixin.Meta):
        fields = ['title', 'body', ]

    user_attribute = 'user'

    def save(self, commit=True):
        self.instance.state = 'open'
        self.instance.comments_count = 0
        self.instance.is_pull_request = False
        self.instance.created_at = datetime.utcnow()
        return super(IssueCreateForm, self).save(commit)


class IssueCreateFormFull(IssueMilestoneFormPart, IssueAssigneesFormPart,
                          IssueLabelsFormPart, IssueProjectsFormPart, IssueCreateForm):

    columns = IssueProjectsFormPart.columns  # will be at the end by default

    class Meta(IssueCreateForm.Meta):
        fields = ['title', 'body', 'milestone', 'assignees', 'labels', 'front_uuid']


class BaseCommentEditForm(LinkedToUserFormMixin, LinkedToIssueFormMixin):
    class Meta:
        fields = ['body', 'front_uuid', ]

    body_always_required = True
    updated_date_field = 'updated_at'
    created_date_field = 'created_at'

    def __init__(self, *args, **kwargs):
        super(BaseCommentEditForm, self).__init__(*args, **kwargs)
        if self.body_always_required:
            self.add_filled_body_validator()

    def add_filled_body_validator(self):
        self.fields['body'].validators = [validate_filled_string]
        self.fields['body'].required = True

    def save(self, commit=True):

        if self.instance.pk:
            self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_UPDATE
        else:
            self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_CREATE

        self.instance.body_html = None

        now = datetime.utcnow()
        if self.updated_date_field:
            setattr(self.instance, self.updated_date_field, now)
        if self.created_date_field and not getattr(self.instance, self.created_date_field, None):
            setattr(self.instance, self.created_date_field, now)

        return super(BaseCommentEditForm, self).save(commit)


class IssueCommentCreateForm(BaseCommentEditForm):
    class Meta(BaseCommentEditForm.Meta):
        model = IssueComment


class IssueCommentEditForm(BaseCommentEditForm):
    user_attribute = None

    class Meta(BaseCommentEditForm.Meta):
        model = IssueComment


class PullRequestReviewCreateForm(BaseCommentEditForm):

    body_always_required = False
    updated_date_field = 'submitted_at'
    created_date_field = None
    user_attribute = 'author'

    class Meta(BaseCommentEditForm.Meta):
        model = PullRequestReview
        fields = BaseCommentEditForm.Meta.fields + ['state']

    def __init__(self, *args, **kwargs):
        super(PullRequestReviewCreateForm, self).__init__(*args, **kwargs)
        self.fields['state'].choices = PullRequestReview.REVIEW_STATES.CREATE_STATES

    def _clean_fields(self):
        state_field = self.fields['state']
        state = state_field.widget.value_from_datadict(self.data, self.files, self.add_prefix('state'))
        if state == PullRequestReview.REVIEW_STATES.CHANGES_REQUESTED:
            self.add_filled_body_validator()
        return super(PullRequestReviewCreateForm, self)._clean_fields()


class PullRequestReviewEditForm(BaseCommentEditForm):
    user_attribute = None

    class Meta(BaseCommentEditForm.Meta):
        model = PullRequestReview


class PullRequestCommentCreateForm(BaseCommentEditForm):
    class Meta(BaseCommentEditForm.Meta):
        model = PullRequestComment

    def __init__(self, *args, **kwargs):
        self.entry_point = kwargs.pop('entry_point')
        super(PullRequestCommentCreateForm, self).__init__(*args, **kwargs)
        if not self.instance.entry_point_id:
            self.instance.entry_point = self.entry_point


class PullRequestCommentEditForm(BaseCommentEditForm):
    user_attribute = None

    class Meta(BaseCommentEditForm.Meta):
        model = PullRequestComment


class CommitCommentCreateForm(LinkedToCommitFormMixin, BaseCommentEditForm):
    class Meta(BaseCommentEditForm.Meta):
        model = CommitComment

    def __init__(self, *args, **kwargs):
        self.entry_point = kwargs.pop('entry_point')
        super(CommitCommentCreateForm, self).__init__(*args, **kwargs)
        if not self.instance.entry_point_id:
            self.instance.entry_point = self.entry_point


class CommitCommentEditForm(LinkedToCommitFormMixin, BaseCommentEditForm):
    user_attribute = None

    class Meta(BaseCommentEditForm.Meta):
        model = CommitComment


class BaseCommentDeleteForm(LinkedToUserFormMixin, LinkedToIssueFormMixin):
    user_attribute = None

    class Meta:
        fields = ['front_uuid', ]

    def save(self, commit=True):
        self.instance.github_status = GITHUB_STATUS_CHOICES.WAITING_DELETE
        return super(BaseCommentDeleteForm, self).save(commit)


class IssueCommentDeleteForm(BaseCommentDeleteForm):
    class Meta(BaseCommentDeleteForm.Meta):
        model = IssueComment


class PullRequestCommentDeleteForm(BaseCommentDeleteForm):
    class Meta(BaseCommentDeleteForm.Meta):
        model = PullRequestComment


class CommitCommentDeleteForm(LinkedToCommitFormMixin, BaseCommentDeleteForm):
    class Meta(BaseCommentDeleteForm.Meta):
        model = CommitComment
