from collections import OrderedDict
from datetime import datetime
from time import sleep
from uuid import uuid4

from django.contrib import messages
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import render, get_object_or_404
from django.http import Http404
from django.http.response import HttpResponse, HttpResponseRedirect, HttpResponseBadRequest
from django.utils.functional import cached_property
from django.views.generic import UpdateView, CreateView, TemplateView, DetailView, DeleteView

from gim.subscriptions.models import SUBSCRIPTION_STATES

from gim.core.models.projects import Card, Column, Project
from gim.core.tasks import (
    IssueEditProjectsJob,
    MoveCardJob, CardNoteEditJob,
    ColumnEditJob, ColumnMoveJob,
    ProjectEditJob,
)

from gim.front.mixins.views import LinkedToUserFormViewMixin, WithAjaxRestrictionViewMixin, WithIssueViewMixin, WithSubscribedRepositoryViewMixin, DependsOnRepositoryViewMixin, WithRepositoryViewMixin, \
    LinkedToRepositoryFormViewMixin
from gim.front.repository.dashboard.views import LabelsEditor
from gim.front.utils import make_querystring, forge_request
from gim.front.repository.views import BaseRepositoryView, RepositoryViewMixin
from gim.front.repository.issues.views import IssuesView, IssueEditAssignees, IssueEditLabels, \
    IssueEditMilestone, IssueEditState, IssueEditProjects, IssuesFilters

from .forms import (
    CardNoteCreateForm, CardNoteDeleteForm, CardNoteEditForm,
    ColumnCreateForm, ColumnEditForm, ColumnDeleteForm,
    ProjectEditForm, ProjectDeleteForm, ProjectCreateForm
)

DEFAULT_BOARDS = OrderedDict((
    ('auto-state', {
        'mode': 'auto',
        'key': 'state',
        'name': u'issue state',
        'description': u'two columns board: open and closed issues',
        'columns': OrderedDict((
            ('open', {
                'key': 'open',
                'name': u'open',
                'description': u'Open issues',
                'qs': ('state', 'open'),
            }),
            ('closed', {
                'key': 'closed',
                'name': u'closed',
                'description': u'Closed issues',
                'qs': ('state', 'closed'),
            }),
        )),
    }),
    ('auto-assigned', {
        'mode': 'auto',
        'key': 'assigned',
        'name': u'assignees',
        'description': u'one column per assignee',
    }),
    ('auto-open-milestones', {
        'mode': 'auto',
        'key': 'open-milestones',
        'name': u'open milestones',
        'description': u'one column per open milestone',
    }),
    ('auto-all-milestones', {
        'mode': 'auto',
        'key': 'all-milestones',
        'name': u'all milestones',
        'description': u'one column per milestone',
    }),
))


class BoardMixin(object):

    LIMIT_ISSUES = 30
    default_qs = 'state=open'
    raise_if_no_current_board = True

    def __init__(self):
        super(BoardMixin, self).__init__()
        self.current_board = None
        self.current_column = None

    @cached_property
    def collaborators(self):
        return self.repository.collaborators.all()

    def get_boards(self):
        boards = OrderedDict(DEFAULT_BOARDS)

        # Fill assigned columns
        boards['auto-assigned']['columns'] = OrderedDict([
            ('__none__', {
                'key': '__none__',
                'name': u'(No one assigned)',
                'description': u'',
                'qs': ('assigned', '__none__'),
            })
        ] + [
            (user.username, {
                'key': user.username,
                'name': user.username,
                'description': user.full_name,
                'qs': ('assigned', user.username),
                'object': user,
            })
            for user in self.collaborators
        ])
        # No board on assigned if no collaborators
        if len(boards['auto-assigned']['columns']) < 2:
            del boards['auto-assigned']

        # Fill milestone columns
        for milestone_filter in ('open', 'all'):
            column_name = 'auto-%s-milestones' % milestone_filter
            boards[column_name]['columns'] = OrderedDict([
                ('__none__', {
                    'key': '__none__',
                    'name': u'(No milestone)',
                    'description': u'',
                    'qs': ('milestone', '__none__'),
                })
            ] + [
                (str(milestone.number), {
                    'key': str(milestone.number),
                    'name': '#%d - %s (%s)' % (milestone.number, milestone.title, milestone.state),
                    'description': milestone.description,
                    'qs': ('milestone', str(milestone.number)),
                    'object': milestone,
                })
                for milestone in reversed(list(self.milestones))
                if milestone_filter == 'all' or milestone.is_open
            ])
            # No board on milestones if no milestones
            if len(boards[column_name]['columns']) < 2:
                del boards[column_name]

        # Add projects
        if self.repository.has_some_projects:
            if self.subscription.state in SUBSCRIPTION_STATES.WRITE_RIGHTS:
                projects = self.projects_including_empty
            else:
                projects = self.projects
            for project in projects:
                if not project.number:
                    continue
                columns = OrderedDict([
                    ('__none__', {
                        'key': '__none__',
                        'name': u'(Not in the project)',
                        'description': u'not in this project',
                        'qs': ('project_%s' % project.number, '__none__')
                    })
                ] + [
                        (str(column.pk), {
                            'key': str(column.pk),
                            'name': column.name,
                            'description': u'',
                            'qs': ('project_%s' % project.number, column.id),
                            'object': column,
                        })
                        for column in project.columns.all()
                ])
                if len(columns) > 1 or self.subscription.state in SUBSCRIPTION_STATES.WRITE_RIGHTS:
                    boards['project-%d' % project.number] = {
                        'mode': 'project',
                        'key': str(project.number),
                        'name': project.name,
                        'description': u'Github project with all its columns',
                        'object': project,
                        'columns': columns,
                        'default_qs': 'sort=position&direction=asc'
                    }

        # Add label types
        for label_type in self.label_types:
            columns = OrderedDict([
                ('__none__', {
                    'key': '__none__',
                    'name': u'(Not set)',
                    'description': u'no labels for this type',
                    'qs': ('labels', '%s:__none__' % label_type.name)
                })
            ] + [
                (str(label.pk), {
                    'key': str(label.pk),
                    'name': label.lower_typed_name,
                    'description': u'',
                    'qs': ('labels', label.name),
                    'object': label,
                })
                for label in label_type.labels.all()
            ])
            if len(columns) > 1:
                boards['labels-%d' % label_type.pk] = {
                    'mode': 'labels',
                    'key': str(label_type.pk),
                    'name': label_type.name,
                    'description': u'one column for each label of this type',
                    'object': label_type,
                    'columns': columns
                }

        for board_key, board in boards.items():
            board['board_url'] = reverse(
                'front:repository:board',
                kwargs=dict(self.repository.get_reverse_kwargs(),
                            board_mode=board['mode'],
                            board_key=board['key'])
            )
            board['base_url'] = board['board_url']
            if board.get('default_qs'):
                board['board_url'] += '?' + board['default_qs']
            elif self.default_qs:
                board['board_url'] += '?' + self.default_qs
            board['visible_count'] = len(list(c for c in board['columns'].values() if not c.get('hidden', False)))

        return boards

    def get_boards_context(self):
        context = {'boards': self.get_boards()}


        current_board_key = self.kwargs.get('board_key')
        if current_board_key:
            current_board_key = '%s-%s' % (self.kwargs.get('board_mode'), current_board_key)
            if current_board_key not in context['boards']:
                current_board_key = None

        if self.raise_if_no_current_board and not current_board_key:
            raise Http404('No board here')

        context['current_board_key'] = current_board_key

        if current_board_key:
            self.current_board = context['current_board'] = context['boards'][current_board_key]

        context['labels_editor_url'] = reverse_lazy( 'front:repository:%s' % LabelsEditor.url_name, kwargs=self.repository.get_reverse_kwargs())

        return context


class BoardSelectorView(BoardMixin, BaseRepositoryView):
    name = 'Board'
    url_name = 'board-selector'
    template_name = 'front/repository/board/base.html'
    raise_if_no_current_board = False
    auto_open_selector = True

    display_in_menu = True

    def get_context_data(self, **kwargs):
        context = super(BoardSelectorView, self).get_context_data(**kwargs)
        context.update(self.get_boards_context())
        return context


class BoardView(BoardMixin, IssuesFilters, BaseRepositoryView):
    name = 'Board'

    url_name = 'board'
    main_url_name = 'board-selector'  # to mark the link in the main menu as current

    template_name = 'front/repository/board/board.html'
    filters_template_name = 'front/repository/board/include_filters.html'
    options_template_name = 'front/repository/board/include_options.html'

    display_in_menu = False

    def __init__(self):
        self.list_uuid = 'board-main'  # used for the filters
        super(BoardView, self).__init__()

    def _can_add_position_sorting(self, qs_parts):
        if self.current_board['mode'] == 'project':
            return True
        return super(BoardView, self)._can_add_position_sorting(qs_parts)

    @cached_property
    def base_url(self):
        # used for the filters
        return self.current_board['base_url']

    def get_pre_context_data(self, **kwargs):
        context = super(BoardView, self).get_pre_context_data(**kwargs)
        context.update(self.get_boards_context())
        return context

    def get_context_data(self, **kwargs):
        context = super(BoardView, self).get_context_data(**kwargs)

        if not self.current_board:
            # Will be redirected in ``render_to_response`` so no need for more context
            return context

        if not self.request.is_ajax():
            for column_key, column in self.current_board['columns'].items():
                column['url'] = reverse_lazy(
                    'front:repository:%s' % BoardColumnView.url_name,
                    kwargs=dict(
                        self.repository.get_reverse_kwargs(),
                        board_mode=self.current_board['mode'],
                        board_key=self.current_board['key'],
                        column_key=column_key,
                    )
                )

            context.update({
                'can_add_issues': True,
                'all_metrics': list(self.repository.all_metrics()),
            })

            context.update(self.repository.get_milestones_for_select(key='number', with_graph_url=True))

        context.update({
            'list_uuid': self.list_uuid,
            'current_issues_url': self.base_url,
            'filters_title': 'Filters for all columns',
            'can_show_shortcuts': True,
            'can_multiselect': context['current_repository_edit_level'] == 'full',
            'force_display_groups_options': True,
        })

        return context

    def get_template_names(self):
        """
        Use a specific template if the request is an ajax one
        """

        if self.request.is_ajax():
            return 'front/repository/board/board_ajax.html'

        return super(BoardView, self).get_template_names()

    def render_to_response(self, context, **response_kwargs):
        if not self.current_board:
            return HttpResponseRedirect(self.repository.get_view_url('board-selector'))
        return super(BoardView, self).render_to_response(context, **response_kwargs)


class BoardColumnMixin(BoardMixin):

    @cached_property
    def base_url(self):
        return reverse_lazy('front:repository:%s' % self.url_name, kwargs=dict(
            self.repository.get_reverse_kwargs(),
            board_mode=self.kwargs['board_mode'],
            board_key=self.kwargs['board_key'],
            column_key=self.kwargs['column_key']
        ))

    def get_column_key_from_kwarg(self, name):
        column_key = self.kwargs[name]
        if column_key not in self.current_board['columns']:
            raise Http404
        return column_key, self.current_board['columns'][column_key]

    def get_boards_context(self):
        context = super(BoardColumnMixin, self).get_boards_context()

        if not context.get('current_board', None):
            raise Http404

        current_column_key, current_column = self.get_column_key_from_kwarg('column_key')

        context.update({
            'current_column_key': current_column_key,
            'current_column': current_column
        })
        self.current_column = current_column

        context['current_column']['url'] = self.base_url

        return context


class BoardMoveIssueMixin(WithAjaxRestrictionViewMixin, WithIssueViewMixin, BaseRepositoryView):
    allowed_rights = SUBSCRIPTION_STATES.WRITE_RIGHTS
    display_in_menu = False
    ajax_only = True

    def get_post_view_info(self):
        board = self.current_board
        view, url = None, None

        if board['mode'] == 'auto':
            if board['key'] == 'state':
                view = IssueEditState
                url = self.issue.edit_field_url('state')

            elif board['key'] == 'assigned':
                view = IssueEditAssignees
                url = self.issue.edit_field_url('assignees')

            elif 'milestone' in board['key']:
                view = IssueEditMilestone
                url = self.issue.edit_field_url('milestone')

        elif board['mode'] == 'labels':
            view = IssueEditLabels
            url = self.issue.edit_field_url('labels')

        if not view:
            raise Http404

        return view, url

    def render_messages(self, **kwargs):
        return render(self.request, 'front/messages.html', **kwargs)


class BoardCanMoveIssueView(BoardMoveIssueMixin, BoardColumnMixin):
    url_name = 'board-can-move'

    def post(self, request, *args, **kwargs):
        self.get_boards_context()

        view,  url = self.get_post_view_info()

        current_job, who = view.get_job_for_issue(self.issue)

        if current_job:
            if who == self.request.user.username:
                who = 'yourself'
            messages.error(request, view.get_not_editable_user_message(self.issue, who))
            return self.render_messages(status=409)

        return self.render_messages()


class BoardMoveProjectCardMixin(object):
    @cached_property
    def issue_or_card(self):
        from gim.core.models import Card, Issue

        if self.kwargs.get('is_note'):
            return get_object_or_404(Card,
                pk=self.kwargs['issue_number'],
                column=self.current_column['object'],
            )

        return self.issue


class BoardCanMoveProjectCardView(BoardMoveProjectCardMixin, BoardCanMoveIssueView):
    url_name = 'board-can-move-project-card'

    @classmethod
    def get_job_for_object(cls, obj):

        current_job = cls.get_current_job_for_object(obj)

        if current_job:
            for i in range(0, 3):
                sleep(0.1)  # wait a little, it may be fast
                current_job = cls.get_current_job_for_object(obj)
                if not current_job:
                    break

            if current_job:
                who = current_job.gh_args.hget('username')
                return current_job, who

        return None, None

    @classmethod
    def get_current_job_for_object(cls, obj):
        from gim.core.models import Issue

        if isinstance(obj, Issue):
            to_check = [(IssueEditProjectsJob, 'identifier'), (MoveCardJob, 'issue_id')]
        else:
            to_check = [(MoveCardJob, 'identifier')]

        for job_model, field in to_check:
            try:
                job = job_model.collection(**{field: obj.pk, 'queued': 1}).instances()[0]
            except IndexError:
                pass
            else:
                return job

        return None

    def post(self, request, *args, **kwargs):
        self.get_boards_context()

        from gim.core.models import Card, Issue

        obj = self.issue_or_card

        current_job, who = self.get_job_for_object(obj)

        if current_job:
            if who == self.request.user.username:
                who = 'yourself'

            if isinstance(current_job, IssueEditProjects):
                message = u"""The <strong>projects</strong> for the %s <strong>#%d</strong> are
                    currently being updated (asked by <strong>%s</strong>), please
                    wait a few seconds and retry""" % (self.issue.type, self.issue.number, who)
            else:
                if isinstance(obj, Issue):
                    message = u"""A previous move for the %s <strong>#%d</strong> is
                        currently being saved (asked by <strong>%s</strong>), please
                        wait a few seconds and retry""" % (self.issue.type, self.issue.number, who)
                else:
                    message = u"""A previous move for this note is
                        currently being saved (asked by <strong>%s</strong>), please
                        wait a few seconds and retry""" % who

            messages.error(request, message)
            return self.render_messages(status=409)

        return self.render_messages()


class BoardMoveIssueView(BoardMoveIssueMixin, BoardColumnMixin):
    url_name = 'board-move'

    def get_post_view_info(self):
        view, url = super(BoardMoveIssueView, self).get_post_view_info()

        data = {}
        skip_reset_front_uuid = False

        if view == IssueEditState:
            skip_reset_front_uuid = True
            data = {'state': self.new_column['key']}

        elif view == IssueEditAssignees:
            skip_reset_front_uuid = False
            assignees = self.issue.assignees.all()

            if self.new_column['key'] != self.current_column['key']:

                assignees = list(assignees.values_list('pk', flat=True))

                if self.new_column['key'] != '__none__':
                    try:
                        if self.current_column['key'] == '__none__':
                            raise ValueError
                        existing_index = assignees.index(self.current_column['object'].pk)
                        assignees[existing_index] = self.new_column['object'].pk
                    except ValueError:
                        assignees.append(self.new_column['object'].pk)

            data = {'assignees': assignees}

        elif view == IssueEditMilestone:
            skip_reset_front_uuid = True
            data = {'milestone': '' if self.new_column['key'] == '__none__' else  self.new_column['object'].pk}

        elif view == IssueEditLabels:
            skip_reset_front_uuid = False
            labels = self.issue.labels.all()

            if self.new_column['key'] != self.current_column['key']:

                if self.new_column['key'] == '__none__':
                    labels = labels.exclude(label_type_id=self.current_column['object'].label_type_id)

                labels = list(labels.values_list('pk', flat=True))

                if self.new_column['key'] != '__none__':
                    try:
                        if self.current_column['key'] == '__none__':
                            raise ValueError
                        existing_index = labels.index(self.current_column['object'].pk)
                        labels[existing_index] = self.new_column['object'].pk
                    except ValueError:
                        labels.append(self.new_column['object'].pk)

            data = {'labels': labels}

        else:
            raise Http404

        data['front_uuid'] = self.request.POST['front_uuid']

        class InternalBoardMoveView(view):
            def form_valid(self, form):
                form.instance.skip_reset_front_uuid = skip_reset_front_uuid
                self.object = form.save()
                self.after_form_valid(form)
                return HttpResponse('OK')

        return InternalBoardMoveView, data, url

    def get_boards_context(self):
        context =  super(BoardMoveIssueView, self).get_boards_context()

        new_column_key, new_column = self.get_column_key_from_kwarg('to_column_key')

        context.update({
            'current_column_key': new_column_key,
            'current_column': new_column
        })

        self.new_column = new_column

        return context

    def post(self, request, *args, **kwargs):
        self.get_boards_context()

        view, data, url = self.get_post_view_info()

        new_request = forge_request(path=url, method='POST', post_data=data,
                                    source_request=self.request, headers={
                                        'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'
                                    }, pass_user=True)

        response = view.as_view()(new_request, **self.issue.get_reverse_kwargs())

        if response.status_code == 200:
            return self.render_messages()

        return response


class BoardMoveProjectCardView(BoardMoveProjectCardMixin, BoardMoveIssueView):
    url_name = 'board-move-project-card'

    def post(self, request, *args, **kwargs):
        self.get_boards_context()

        project = self.current_board['object']
        from_column = self.current_column.get('object')
        to_column = self.new_column.get('object')
        position = self.request.POST.get('position', None)
        if position is not None:
            try:
                position = int(position)
                if position < 1:
                    raise ValueError()
            except ValueError:
                return HttpResponseBadRequest()

        # here choice is done to not update the positions in db but let the job do it

        from gim.core.models import Card, Issue

        obj = self.issue_or_card

        if isinstance(obj, Card):
            card = obj
        else:
            if to_column:
                # we're asked to move a card from a column to another, or add it to the project
                try:
                    card = self.issue.cards.get(column__project=project)
                except Card.DoesNotExist:
                    now = datetime.utcnow()
                    card = Card.objects.create(
                        type=Card.CARDTYPE.ISSUE,
                        created_at=now,
                        updated_at=now,
                        issue=self.issue,
                        column=to_column,
                        position=position,
                    )
            else:
                # the card is in a column but is asked to be removed from the project
                card = self.issue.cards.get(column__project=project)

        card.front_uuid = self.request.POST['front_uuid']
        card.save(update_fields=['front_uuid'])

        job_args = {}

        if isinstance(obj, Issue):
            job_args['issue_id'] = obj.pk
        if to_column:
            job_args['column_id'] = to_column.pk
            if from_column == to_column:
                job_args['direction'] = 1 if position > card.position else -1
            if position:
                job_args['position'] = position

        MoveCardJob.add_job(
            card.pk,
            gh=self.request.user.get_connection(),
            **job_args
        )

        return self.render_messages()


class BoardColumnView(WithAjaxRestrictionViewMixin, BoardColumnMixin, IssuesView):
    url_name = 'board-column'

    MIN_FILTER_KEYS = 3

    display_in_menu = False
    ajax_only = True

    filters_template_name = 'front/repository/board/include_filters.html'
    options_template_name = 'front/repository/board/include_options.html'
    filters_and_list_template_name = 'front/repository/board/include_filters_and_list.html'
    template_name = filters_and_list_template_name

    def get_pre_context_data(self, **kwargs):
        context = self.get_boards_context()
        context.update(super(BoardColumnView, self).get_pre_context_data(**kwargs))
        return context

    def get_context_data(self, **kwargs):
        context = super(BoardColumnView, self).get_context_data()

        if not self.needs_only_queryset:
            context.update({
                'list_key': self.current_column['key'],
                'list_title': self.current_column['name'],
                'list_description': self.current_column['description'],
                'filters_title': 'Filters for this column',
                'can_show_shortcuts': False,
                'can_add_issues': False,
                'can_handle_positions': False,
                'include_board_column_icons': self.request.GET.get('with-icons', False),
            })

        return context

    def get_querystring_context(self, querystring=None):
        qs_context = super(BoardColumnView, self).get_querystring_context(querystring)
        qs_parts = qs_context['querystring_parts']

        mode = self.current_board['mode']
        qs_name, qs_value = self.current_column['qs']

        if mode in ('auto', 'project'):
            qs_parts[qs_name] = qs_value

        elif mode == 'labels':
            qs_label_names = qs_parts.get('labels', None) or []

            if qs_label_names:
                label_type = [lt for lt in self.label_types if str(lt.pk) == self.current_board['key']][0]
                label_names = {l.lower_name for l in label_type.labels.all()}

                if not isinstance(qs_label_names, list):
                    qs_label_names = [qs_label_names]
                qs_label_names = [l for l in qs_label_names if l and l.lower() not in label_names]

            qs_parts['labels'] = qs_label_names + [qs_value]

        return {
            'querystring_parts': qs_parts,
            'querystring': make_querystring(qs_parts)[1:],
        }


class BoardProjectColumnView(BoardColumnView):
    """A board column for a project column"""

    url_name = 'board-project-column'
    filters_and_list_template_name = 'front/repository/board/projects/include_filters_and_list.html'

    def can_handle_positions(self, filter_parts):
        return self.current_column['key'] != '__none__' and \
               filter_parts.get('sort') == 'position' and \
               not filter_parts.get('group_by')

    def can_display_notes(self, filter_parts):
        if  self.current_column['key'] != '__none__' and \
               filter_parts.get('sort') == 'position' and \
               not filter_parts.get('group_by'):

            # we may be able to display notes, but only if no filters

            allowed_keys = {'direction', 'sort', 'project_%s' % self.current_board['object'].number}
            return set(filter_parts.keys()) == allowed_keys

        else:
            return None

    def get_context_data(self, **kwargs):
        context = super(BoardProjectColumnView, self).get_context_data(**kwargs)

        if not self.needs_only_queryset:
            context['can_handle_positions'] = self.can_handle_positions(context['issues_filter']['parts'])
            context['can_display_notes'] = self.can_display_notes(context['issues_filter']['parts'])

        return context

    def finalize_issues(self, issues, context):
        issues, total_count, limit_reached, original_queryset = \
            super(BoardProjectColumnView, self).finalize_issues(issues, context)

        if self.can_display_notes(context['issues_filter']['parts']):
            from gim.core.models import Card

            incr_order = context['issues_filter']['parts']['direction'] == 'asc'
            column = self.current_column['object']

            issues = list(issues)
            issues_by_id = {issue.id: issue for issue in issues}

            # get all the cards to display
            filters = {}
            if limit_reached:
                max_position = issues[-1].cards.get(column=column).position
                filters['position__lte' if incr_order else 'position__gte'] = max_position

            cards = column.cards.filter(**filters).order_by('position' if incr_order else '-position')

            # compose the list from the cards
            issues = []
            for card in cards:
                if card.type == Card.CARDTYPE.ISSUE:
                    if card.issue_id in issues_by_id:
                        issues.append(issues_by_id[card.issue_id])
                else:
                    issues.append(card)

            if limit_reached:
                issues = issues[:self.LIMIT_ISSUES]
                total_count = column.cards.count()
            else:
                total_count = len(issues)
                if not context['no_limit'] and total_count > self.LIMIT_ISSUES + self.LIMIT_ISSUES_TOLERANCE:
                    issues = issues[:self.LIMIT_ISSUES]
                    limit_reached = True

        return issues, total_count, limit_reached, original_queryset

    def get_template_names(self):
        if self.current_column['object'].github_status in Column.GITHUB_STATUS_CHOICES.NOT_READY:
            return 'front/repository/board/projects/include_not_ready_column.html'

        return super(BoardProjectColumnView, self).get_template_names()


class WithProjectViewMixin(WithRepositoryViewMixin):
    """
    A mixin that is meant to be used when a view depends on a project.
    Provides stuff provided by WithSubscribedRepositoryViewMixin, plus:
    - a "project" property that'll get the project depending on the repository and
    the "number" url params
    - a "get_project_filter_args" to use to filter a model on a repository's name,
    its owner's username, and an project number
    And finally, put the project in the context
    """

    exclude_waiting_delete = True

    def get_project_filter_args(self, filter_root=''):
        """
        Return a dict with attribute to filter a model for a given repository's
        name, its owner's username and an project number as given in the url.
        Use the "filter_root" to prefix the filter.
        """

        if filter_root and not filter_root.endswith('__'):
            filter_root += '__'
        return {
            '%srepository_id' % filter_root: self.repository.id,
            '%snumber' % filter_root: self.kwargs['project_number']
        }

    @cached_property
    def project(self):
        """
        Return (and cache) the project. Raise a 404 if the current user is
        not allowed to use this repository, or if the project is not found
        or waiting for deletion
        """

        queryset = Project.objects.select_related('repository__owner')
        if self.exclude_waiting_delete:
            queryset = queryset.exclude(github_status=Project.GITHUB_STATUS_CHOICES.WAITING_DELETE)

        return get_object_or_404(
            queryset,
            **self.get_project_filter_args()
        )

    def get_context_data(self, **kwargs):
        """
        Put the current project in the context
        """
        context = super(WithProjectViewMixin, self).get_context_data(**kwargs)
        context['current_project'] = self.project
        context['current_project_edit_level'] = self.get_edit_level(self.project)
        return context

    def get_edit_level(self, project):
        """
        Return the edit level of the given project. It may be None (read only),
        or "full"
        """
        edit_level = None
        if project and project.number:
            if self.subscription.state in SUBSCRIPTION_STATES.WRITE_RIGHTS:
                edit_level = 'full'
        return edit_level


class DependsOnProjectViewMixin(WithProjectViewMixin, DependsOnRepositoryViewMixin):
    """
    A simple mixin to use for views when the main object depends on a project
    Will limit entries to ones matching the project fetched using url params
    and the "allowed_rights" attribute.
    The "project_related_name" attribute is the name to use to filter only
    on the current project.
    """
    project_related_name = 'project'
    repository_related_name = 'project__repository'

    def get_queryset(self):
        """
        Return a queryset based on the current repository, project, and allowed
        rights.
        """
        return self.model._default_manager.filter(**{
                self.project_related_name: self.project
            })


class LinkedToProjectFormViewMixin(WithAjaxRestrictionViewMixin, DependsOnProjectViewMixin):
    """
    A mixin for form views when the main object depends on a project, and
    using a form which is a subclass of LinkedToProjectFormMixin, to have the
    current project passed to the form
    """

    def get_form_kwargs(self):
        kwargs = super(LinkedToProjectFormViewMixin, self).get_form_kwargs()
        kwargs['project'] = self.project
        return kwargs


class CardNoteView(WithAjaxRestrictionViewMixin, DependsOnProjectViewMixin, DetailView):
    context_object_name = 'note'
    pk_url_kwarg = 'card_pk'
    http_method_names = ['get']
    ajax_only = True
    url_name = 'project.note'
    model = Card
    template_name = 'front/repository/board/projects/include_note.html'
    job_model = CardNoteEditJob
    project_related_name = 'column__project'
    repository_related_name = 'column__project__repository'

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()

        pk = self.kwargs['card_pk']
        obj = None

        try:
            obj = queryset.get(pk=pk)
        except self.model.DoesNotExist:
            # maybe the object was deleted and recreated by dist_edit
            try:
                job = self.job_model.get(identifier=pk, mode='create')
            except self.job_model.DoesNotExist:
                pass
            else:
                to_wait = 0.3
                while to_wait > 0:
                    created_pk = job.created_pk.hget()
                    if created_pk:
                        obj = queryset.get(pk=created_pk)
                        break
                    sleep(0.1)

        if not obj:
            raise Http404("No note found matching the query")

        return obj


class CardNoteEditMixin(LinkedToUserFormViewMixin, LinkedToProjectFormViewMixin):
    model = Card
    job_model = CardNoteEditJob
    project_related_name = 'column__project'
    repository_related_name = 'column__project__repository'
    ajax_only = True  # TODO: CHANGE TO TRUE
    http_method_names = ['get', 'post']
    edit_mode = None

    def form_valid(self, form):
        """
        Override the default behavior to add a job to edit the note on the
        github side
        """
        response = super(CardNoteEditMixin, self).form_valid(form)

        job_kwargs = {}
        if self.object.front_uuid:
            job_kwargs = {'extra_args': {
                'front_uuid': self.object.front_uuid,
                'skip_reset_front_uuid': 1,
            }}

        self.job_model.add_job(self.object.pk,
                               mode=self.edit_mode,
                               gh=self.request.user.get_connection(),
                               **job_kwargs)

        return response


class CardNoteCreateView(CardNoteEditMixin, CreateView):
    edit_mode = 'create'
    verb = 'created'
    template_name = 'front/repository/board/projects/include_note_create.html'
    url_name = 'project.note.create'
    form_class = CardNoteCreateForm
    context_object_name = 'note'

    @cached_property
    def column(self):
        """
        Return (and cache) the column. Raise a 404 if the current user is
        not allowed to use this repository, or if the column is not found
        """

        return get_object_or_404(
            self.project.columns,
            pk=self.kwargs['column_id']
        )

    def get_form_kwargs(self):
        self.object = Card(column=self.column)
        return super(CardNoteCreateView, self).get_form_kwargs()

    def get_context_data(self, **kwargs):
        context = super(CardNoteCreateView, self).get_context_data(**kwargs)
        context['current_column'] = self.column
        context['create_note_uuid'] = self.request.POST.get('front_uuid', None) or uuid4()
        return context


class BaseCardNoteEditView(CardNoteEditMixin, UpdateView):
    context_object_name = 'note'
    pk_url_kwarg = 'card_pk'

    def get_object(self, queryset=None):
        """
        Early check that the user has enough rights to edit this note
        """
        obj = super(BaseCardNoteEditView, self).get_object(queryset)
        if self.subscription.state not in SUBSCRIPTION_STATES.WRITE_RIGHTS:
            raise Http404
        return obj

    @classmethod
    def get_current_job_for_card(cls, card):
        try:
            job = cls.job_model.collection(identifier=card.id, queued=1).instances()[0]
        except IndexError:
            return None
        else:
            return job

    @classmethod
    def get_job_for_card(cls, card):

        current_job = cls.get_current_job_for_card(card)

        if current_job:
            for i in range(0, 3):
                sleep(0.1)  # wait a little, it may be fast
                current_job = cls.get_current_job_for_card(card)
                if not current_job:
                    break

            if current_job:
                who = current_job.gh_args.hget('username')
                return current_job, who

        return None, None

    @classmethod
    def get_not_editable_user_message(cls, card, edit_mode, who):
        message = u"This note is currently being %sd (asked by <strong>%s</strong>)"  % (edit_mode or 'update', who)
        if edit_mode != 'delete':
            message += u", please wait a few seconds and retry"
        return message

    def render_not_editable(self, request, edit_mode, who):
        if who == request.user.username:
            who = 'yourself'
        messages.error(request, self.get_not_editable_user_message(self.object, edit_mode, who))
        # 409 Conflict Indicates that the request could not be processed because of
        # conflict in the request, such as an edit conflict between multiple simultaneous updates.
        return self.render_messages(status=409)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()

        current_job, who = self.get_job_for_card(self.object)

        if current_job:
            return self.render_not_editable(request, current_job.mode.hget(), who)

        return super(CardNoteEditMixin, self).dispatch(request, *args, **kwargs)


class CardNoteEditView(BaseCardNoteEditView):
    edit_mode = 'update'
    verb = 'updated'
    template_name = 'front/repository/board/projects/include_note_edit.html'
    url_name = 'project.note.edit'
    form_class = CardNoteEditForm


class CardNoteDeleteView(BaseCardNoteEditView):
    edit_mode = 'delete'
    verb = 'deleted'
    template_name = 'front/repository/board/projects/include_note_delete.html'
    url_name = 'project.note.delete'
    form_class = CardNoteDeleteForm


class ColumnEditMixin(LinkedToProjectFormViewMixin):
    model = Column
    job_model = ColumnEditJob
    project_related_name = 'project'
    repository_related_name = 'project__repository'
    ajax_only = True
    http_method_names = ['get', 'post']
    edit_mode = None

    def form_valid(self, form):
        """
        Override the default behavior to add a job to edit the column on the
        github side
        """
        response = super(ColumnEditMixin, self).form_valid(form)

        job_kwargs = {}
        if self.object.front_uuid:
            job_kwargs = {'extra_args': {
                'front_uuid': self.object.front_uuid,
                'skip_reset_front_uuid': 1,
            }}

        self.job_model.add_job(self.object.pk,
                               mode=self.edit_mode,
                               gh=self.request.user.get_connection(),
                               **job_kwargs)

        return response


class ColumnInfoView(LinkedToProjectFormViewMixin, DetailView):
    model = Column
    ajax_only = True
    repository_related_name = 'project__repository'
    http_method_names = ['get']
    template_name = 'front/repository/board/projects/minimal_column_info.html'
    context_object_name = 'column'
    pk_url_kwarg = 'column_id'
    url_name = 'project.column.info'


class ColumnCreateView(ColumnEditMixin, CreateView):
    edit_mode = 'create'
    verb = 'created'
    template_name = 'front/repository/board/projects/include_column_create.html'
    url_name = 'project.column.create'
    form_class = ColumnCreateForm
    context_object_name = 'column'

    def get_context_data(self, **kwargs):
        context = super(ColumnCreateView, self).get_context_data(**kwargs)
        context['current_project'] = self.project
        return context


class BaseColumnEditView(ColumnEditMixin, UpdateView):
    context_object_name = 'column'
    pk_url_kwarg = 'column_id'
    default_edit_mode = 'update'

    def get_object(self, queryset=None):
        """
        Early check that the user has enough rights to edit this column
        """
        obj = super(BaseColumnEditView, self).get_object(queryset)
        if self.subscription.state not in SUBSCRIPTION_STATES.WRITE_RIGHTS:
            raise Http404
        return obj

    @classmethod
    def get_current_job_for_column(cls, column):
        try:
            job = cls.job_model.collection(identifier=column.id, queued=1).instances()[0]
        except IndexError:
            return None
        else:
            return job

    @classmethod
    def get_job_for_column(cls, column):

        current_job = cls.get_current_job_for_column(column)

        if current_job:
            for i in range(0, 3):
                sleep(0.1)  # wait a little, it may be fast
                current_job = cls.get_current_job_for_column(column)
                if not current_job:
                    break

            if current_job:
                who = current_job.gh_args.hget('username')
                return current_job, who

        return None, None

    @classmethod
    def get_not_editable_user_message(cls, column, edit_mode, who):
        message = u"This column is currently being %sd (asked by <strong>%s</strong>)"  % (edit_mode or 'update', who)
        if edit_mode != 'delete':
            message += u", please wait a few seconds and retry"
        return message

    def render_not_editable(self, request, edit_mode, who):
        if who == request.user.username:
            who = 'yourself'
        messages.error(request, self.get_not_editable_user_message(self.object, edit_mode, who))
        # 409 Conflict Indicates that the request could not be processed because of
        # conflict in the request, such as an edit conflict between multiple simultaneous updates.
        return self.render_messages(status=409)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()

        current_job, who = self.get_job_for_column(self.object)

        if current_job:
            try:
                mode = current_job.mode.hget()
            except:
                mode = self.default_edit_mode
            return self.render_not_editable(request, mode, who)

        return super(BaseColumnEditView, self).dispatch(request, *args, **kwargs)


class ColumnEditView(BaseColumnEditView):
    edit_mode = 'update'
    verb = 'updated'
    template_name = 'front/repository/board/projects/include_column_edit.html'
    url_name = 'project.column.edit'
    form_class = ColumnEditForm

    def get_success_url(self):
        return self.object.get_info_url()


class ColumnDeleteView(BaseColumnEditView):
    edit_mode = 'delete'
    verb = 'deleted'
    template_name = 'front/repository/board/projects/include_column_delete.html'
    url_name = 'project.column.delete'
    form_class = ColumnDeleteForm


class ColumnCanMoveView(BaseColumnEditView):
    job_model = ColumnMoveJob
    http_method_names = ['post']
    url_name = 'project.column.can-move'
    default_edit_mode = 'move'

    def post(self, request, *args, **kwargs):

        column = self.get_object()

        current_job, who = self.get_job_for_column(column)

        if current_job:
            if who == self.request.user.username:
                who = 'yourself'
            messages.error(request, self.get_not_editable_user_message(column, 'move', who))
            return self.render_messages(status=409)

        return self.render_messages()


class ColumnMoveView(ColumnCanMoveView):
    url_name = 'project.column.move'

    def get_success_url(self):
        return self.object.get_info_url()

    def post(self, request, *args, **kwargs):

        # check if we can move the column
        response = super(ColumnMoveView, self).post(request, *args, **kwargs)
        if response.status_code >= 300:
            return response

        # ok we can move
        position = self.request.POST.get('position', None)
        if position is not None:
            try:
                position = int(position)
                if position < 1:
                    raise ValueError()
            except ValueError:
                return HttpResponseBadRequest()

        column = self.get_object()
        old_position = column.position

        if position != old_position:

            if position > old_position:  # going right
                # we move to the left all columns between the old position and the new one
                # excluding the old position (it's the column we move) and including the new one
                # (the column we move takes its place and the old one is on the left)
                to_move = column.project.columns.filter(position__gt=old_position, position__lte=position)
                for column_to_move in to_move:
                    column_to_move.position -= 1
                    column_to_move.save(update_fields=['position'])
            else:
                # we move to the right all columns between the old position and the new one
                # including the new position (the column we move takes its place and the old one
                # is on the right) and excluding the old position (it's the column we move)
                to_move = column.project.columns.filter(position__gte=position, position__lt=old_position)
                for column_to_move in to_move:
                    column_to_move.position += 1
                    column_to_move.save(update_fields=['position'])

            # and update the column
            column.position = position
            column.front_uuid = self.request.POST['front_uuid']
            fields = ['position']
            if column.front_uuid:
                fields.append('front_uuid')
            column.save(update_fields=fields)

            # now we can create the job

            job_kwargs = {}
            if column.front_uuid:
                job_kwargs = {'extra_args': {
                    'front_uuid': column.front_uuid,
                }}

            self.job_model.add_job(column.pk,
                                   gh=self.request.user.get_connection(),
                                   **job_kwargs)

        return HttpResponseRedirect(self.get_success_url())


class ProjectSummaryView(WithAjaxRestrictionViewMixin, DependsOnRepositoryViewMixin, DetailView):
    model = Project
    ajax_only = True
    http_method_names = ['get']
    template_name = 'front/repository/board/projects/project_modal.html'
    context_object_name = 'project'
    slug_field = 'number'
    slug_url_kwarg = 'project_number'
    url_name = 'project.summary'
    exclude_waiting_delete = False


class NewProjectSummaryView(ProjectSummaryView):
    pk_url_kwarg = 'project_id'
    slug_url_kwarg = None
    slug_field = None
    url_name = 'project.summary.new'


class ProjectEditMixin(LinkedToRepositoryFormViewMixin):
    model = Project
    job_model = ProjectEditJob
    ajax_only=True
    http_method_names = ['get', 'post']
    edit_mode = None

    def form_valid(self, form):
        """
        Override the default behavior to add a job to edit the project on the
        github side
        """
        response = super(ProjectEditMixin, self).form_valid(form)

        job_kwargs = {}
        if self.object.front_uuid:
            job_kwargs = {'extra_args': {
                'front_uuid': self.object.front_uuid,
                'skip_reset_front_uuid': 1,
            }}

        self.job_model.add_job(self.object.pk,
                               mode=self.edit_mode,
                               gh=self.request.user.get_connection(),
                               **job_kwargs)

        message = u"The project <strong>%s</strong> will be updated shortly" % self.object.name

        messages.success(self.request, message)

        return response


class BaseProjectEditView(ProjectEditMixin, UpdateView):
    context_object_name = 'project'
    slug_field = 'number'
    slug_url_kwarg = 'project_number'
    default_edit_mode = 'update'

    def get_object(self, queryset=None):
        """
        Early check that the user has enough rights to edit this column
        """
        obj = super(BaseProjectEditView, self).get_object(queryset)
        if self.subscription.state not in SUBSCRIPTION_STATES.WRITE_RIGHTS:
            raise Http404
        return obj

    @classmethod
    def get_current_job_for_project(cls, project):
        try:
            job = cls.job_model.collection(identifier=project.id, queued=1).instances()[0]
        except IndexError:
            return None
        else:
            return job

    @classmethod
    def get_job_for_project(cls, project):

        current_job = cls.get_current_job_for_project(project)

        if current_job:
            for i in range(0, 3):
                sleep(0.1)  # wait a little, it may be fast
                current_job = cls.get_current_job_for_project(project)
                if not current_job:
                    break

            if current_job:
                who = current_job.gh_args.hget('username')
                return current_job, who

        return None, None

    @classmethod
    def get_not_editable_user_message(cls, column, edit_mode, who):
        message = u"This project is currently being %sd (asked by <strong>%s</strong>)"  % (edit_mode or 'update', who)
        if edit_mode != 'delete':
            message += u", please wait a few seconds and retry"
        return message

    def render_not_editable(self, request, edit_mode, who):
        if who == request.user.username:
            who = 'yourself'
        messages.error(request, self.get_not_editable_user_message(self.object, edit_mode, who))
        # 409 Conflict Indicates that the request could not be processed because of
        # conflict in the request, such as an edit conflict between multiple simultaneous updates.
        return self.render_messages(status=409)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()

        current_job, who = self.get_job_for_project(self.object)

        if current_job:
            try:
                mode = current_job.mode.hget()
            except:
                mode = self.default_edit_mode
            return self.render_not_editable(request, mode, who)

        return super(BaseProjectEditView, self).dispatch(request, *args, **kwargs)


class ProjectEditView(BaseProjectEditView):
    edit_mode = 'update'
    verb = 'updated'
    template_name = 'front/repository/board/projects/include_project_edit.html'
    url_name = 'project.edit'
    form_class = ProjectEditForm

    def get_success_url(self):
        return self.object.get_summary_url()


class ProjectDeleteView(BaseProjectEditView):
    edit_mode = 'delete'
    verb = 'deleted'
    template_name = 'front/repository/board/projects/include_project_edit.html'
    url_name = 'project.column.delete'
    form_class = ProjectDeleteForm

    def get_success_url(self):
        return self.object.get_summary_url()


class ProjectCreateView(ProjectEditMixin, LinkedToUserFormViewMixin, CreateView):
    edit_mode = 'create'
    verb = 'created'
    template_name = 'front/repository/board/projects/include_project_create.html'
    url_name = 'project.create'
    form_class = ProjectCreateForm
    context_object_name = 'project'

    def dispatch(self, request, *args, **kwargs):
        if not request.is_ajax() and self.__class__ != ProjectCreateHomeView:
            return ProjectCreateHomeView.as_view()(request, *args, **kwargs)
        return super(ProjectCreateView, self).dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return self.object.get_summary_url()


class ProjectCreateHomeView(ProjectCreateView, BoardMixin, RepositoryViewMixin):
    template_name = 'front/repository/board/projects/project_create.html'
    ajax_only = False
    auto_open_selector = False
    raise_if_no_current_board = False

    def get_context_data(self, **kwargs):
        context = super(ProjectCreateView, self).get_context_data(**kwargs)
        context.update(self.get_boards_context())
        return context
