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

from gim.core.models.projects import Card, Project
from gim.core.tasks import IssueEditProjectsJob, MoveCardJob, CardNoteEditJob

from gim.front.mixins.views import LinkedToUserFormViewMixin, WithAjaxRestrictionViewMixin, WithIssueViewMixin, WithSubscribedRepositoryViewMixin, DependsOnRepositoryViewMixin, WithRepositoryViewMixin
from gim.front.repository.dashboard.views import LabelsEditor
from gim.front.utils import make_querystring, forge_request
from gim.front.repository.views import BaseRepositoryView
from gim.front.repository.issues.views import IssuesView, IssueEditAssignees, IssueEditLabels, \
    IssueEditMilestone, IssueEditState, IssueEditProjects, IssuesFilters

from .forms import CardNoteCreateForm, CardNoteDeleteForm, CardNoteEditForm

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
    ('auto-milestone', {
        'mode': 'auto',
        'key': 'milestone',
        'name': u'milestone',
        'description': u'one column per milestone (only open ones displayed by default)',
    }),
))


class BoardMixin(object):

    LIMIT_ISSUES = 30

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
        boards['auto-milestone']['columns'] = OrderedDict([
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
                'hidden': milestone.state == 'closed',
            })
            for milestone in reversed(list(self.milestones))
        ])
        # No board on milestones if no milestones
        if len(boards['auto-milestone']['columns']) < 2:
            del boards['auto-milestone']

        # Add projects
        if self.repository.has_projects():
            for project in self.projects:
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
                if len(columns) > 1:
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

        context['current_board_key'] = current_board_key

        if current_board_key:
            self.current_board = context['current_board'] = context['boards'][current_board_key]

        context['labels_editor_url'] = reverse_lazy( 'front:repository:%s' % LabelsEditor.url_name, kwargs=self.repository.get_reverse_kwargs())

        return context


class BoardSelectorView(BoardMixin, BaseRepositoryView):
    name = 'Board'
    url_name = 'board-selector'
    template_name = 'front/repository/board/base.html'

    default_qs = 'state=open'

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

    default_qs = 'state=open'
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

            elif board['key'] == 'milestone':
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
        """
        return get_object_or_404(
            Project.objects.select_related('repository__owner'),
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
    ajax_only = False  # TODO: CHANGE TO TRUE
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
    ajax_only = False  # TODO: CHANGE TO TRUE
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
