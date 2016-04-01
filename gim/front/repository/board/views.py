from collections import OrderedDict

from django.core.urlresolvers import reverse, reverse_lazy
from django.http import Http404
from django.utils.functional import cached_property

from gim.front.utils import make_querystring
from gim.front.repository.views import BaseRepositoryView
from gim.front.repository.issues.views import IssuesView


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
            del boards['auto-assigned']['columns']

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
            del boards['auto-milestone']['columns']

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

        return context


class BoardView(BoardMixin, BaseRepositoryView):
    name = 'Board'
    url_name = 'board'
    template_name = 'front/repository/board/base.html'

    default_qs = 'state=open'
    display_in_menu = True

    def get_context_data(self, **kwargs):
        context = super(BoardView, self).get_context_data(**kwargs)

        context.update(self.get_boards_context())

        if context.get('current_board', None):
            for column_key, column in context['current_board']['columns'].items():
                column['url'] = reverse_lazy(
                    'front:repository:%s' % BoardColumnView.url_name,
                    kwargs=dict(
                        self.repository.get_reverse_kwargs(),
                        board_mode=context['current_board']['mode'],
                        board_key=context['current_board']['key'],
                        column_key=column_key,
                    )
                )

        context['can_add_issues'] = True

        return context


class BoardColumnView(BoardMixin, IssuesView):
    url_name = 'board-column'

    display_in_menu = False

    filters_and_list_template_name = 'front/repository/board/include_filters_and_list.html'
    template_name = filters_and_list_template_name

    def get_base_url(self):
        return reverse_lazy('front:repository:%s' % self.url_name, kwargs=dict(
            self.repository.get_reverse_kwargs(),
            board_mode=self.kwargs['board_mode'],
            board_key=self.kwargs['board_key'],
            column_key=self.kwargs['column_key']
        ))

    def get_context_data(self, **kwargs):

        context = self.get_boards_context()

        if not context.get('current_board', None):
            raise Http404

        current_column_key = self.kwargs['column_key']
        if current_column_key not in context['current_board']['columns']:
            raise Http404

        context.update({
            'current_column_key': current_column_key,
            'current_column': context['current_board']['columns'][current_column_key]
        })
        self.current_column = context['current_column']

        context['current_column']['url'] = self.get_base_url()

        context.update({
            'list_key': current_column_key,
            'list_title': self.current_column['name'],
            'list_description': self.current_column['description'],
        })

        return super(BoardColumnView, self).get_context_data(**context)

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

