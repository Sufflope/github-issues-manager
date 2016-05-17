from collections import OrderedDict
from uuid import uuid4

from django.contrib import messages
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import render
from django.http import Http404
from django.http.response import HttpResponse, HttpResponseRedirect
from django.utils.functional import cached_property

from gim.subscriptions.models import SUBSCRIPTION_STATES

from gim.front.mixins.views import WithAjaxRestrictionViewMixin, WithIssueViewMixin
from gim.front.repository.dashboard.views import LabelsEditor
from gim.front.utils import make_querystring, forge_request
from gim.front.repository.views import BaseRepositoryView
from gim.front.repository.issues.views import IssuesView, IssueEditAssignee, IssueEditLabels, \
    IssueEditMilestone, IssueEditState, IssuesFilters

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
        return self.repository.collaborators.all().order_by('username')

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
            if self.default_qs:
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
                view = IssueEditAssignee
                url = self.issue.edit_field_url('assignee')

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


class BoardCanMoveIssueView(BoardMoveIssueMixin, BoardMixin):
    url_name = 'board-can-move'

    def post(self, request, *args, **kwargs):
        self.get_boards_context()

        view,  url = self.get_post_view_info()

        current_job, who = view.get_job_for_issue(self.issue)

        if current_job:
            if who == self.request.user.username:
                who = 'yourself'
            messages.warning(request, view.get_not_editable_user_message(self.issue, who))
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

        elif view == IssueEditAssignee:
            skip_reset_front_uuid = False
            data = {'assignee': '' if self.new_column['key'] == '__none__' else self.new_column['object'].pk}

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


class BoardColumnView(WithAjaxRestrictionViewMixin, BoardColumnMixin, IssuesView):
    url_name = 'board-column'

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
            })

        return context

    def get_querystring_context(self, querystring=None):
        qs_context = super(BoardColumnView, self).get_querystring_context(querystring)
        qs_parts = qs_context['querystring_parts']

        mode = self.current_board['mode']
        qs_name, qs_value = self.current_column['qs']

        if mode == 'auto':
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

