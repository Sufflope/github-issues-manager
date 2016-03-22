from collections import OrderedDict
from math import ceil

from django.core.urlresolvers import reverse_lazy
from django.db import DatabaseError
from django.http import HttpResponseRedirect
from django.views.generic import TemplateView

from gim.front.utils import make_querystring
from gim.front.mixins.views import WithQueryStringViewMixin


class HomeView(TemplateView):
    template_name = 'front/home.html'
    redirect_authenticated_url = reverse_lazy('front:dashboard:home')

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated():
            return HttpResponseRedirect(self.redirect_authenticated_url)
        return super(HomeView, self).get(request, *args, **kwargs)


GROUP_BY_CHOICES = {group_by[0]: group_by for group_by in [
    ('state', {
        'field': 'state',
        'name': u'issue state',
        'description': u'is an issue open or closed',
    }),
    ('pr', {
        'field': 'is_pull_request',
        'name': u'pull-request',
        'description': u'is it a pull-request or a simple issue',
    }),
]}


class BaseIssuesView(WithQueryStringViewMixin):
    allowed_states = ['open', 'closed']
    allowed_prs = ['no', 'yes']
    allowed_mergeables = ['no', 'yes']
    allowed_sort_fields = ['created', 'updated', ]
    allowed_sort_orders = ['asc', 'desc']

    default_sort = ('updated', 'desc')

    default_qs = ''

    LIMIT_ISSUES = 300
    GROUP_BY_CHOICES = GROUP_BY_CHOICES

    issue_item_template_name = 'front/repository/issues/include_issue_item_for_cache.html'

    allowed_group_by = OrderedDict(GROUP_BY_CHOICES[name] for name in [
        'state',
        'pr',
    ])

    def get_base_queryset(self):
        raise NotImplementedError

    def _get_state(self, qs_parts):
        """
        Return the valid state to use, or None
        """
        state = qs_parts.get('state', None)
        if state in self.allowed_states:
            return state
        return None

    def _get_is_pull_request(self, qs_parts):
        """
        Return the valid "is_pull_request" flag to use, or None
        """
        is_pull_request = qs_parts.get('pr', None)
        if is_pull_request in self.allowed_prs:
            return True if is_pull_request == 'yes' else False
        return None

    def _get_is_mergeable(self, qs_parts):
        """
        Return the valid "is_mergeable" flag to use, or None
        Will return None if current filter is not on Pull requests
        """
        is_mergeable = qs_parts.get('mergeable', None)
        if is_mergeable in self.allowed_mergeables:
            if self._get_is_pull_request(qs_parts):
                return True if is_mergeable == 'yes' else False
        return None

    def _get_group_by_direction(self, qs_parts):
        """
        Return the direction to apply to the group_by
        """
        direction = qs_parts.get('group_by_direction', 'asc')
        if direction not in ('asc', 'desc'):
            direction = 'asc'
        return direction

    def _get_group_by(self, qs_parts):
        """
        Return the group_by field to use, and the direction.
        """
        group_by = qs_parts.get('group_by', None)

        if group_by in self.allowed_group_by:
            return (
                self.allowed_group_by[group_by]['field'],
                self._get_group_by_direction(qs_parts),
            )

        return None, None

    def _get_sort(self, qs_parts):
        """
        Return the sort field to use, and the direction. If one or both are
        invalid, the default ones are used
        """
        sort = qs_parts.get('sort', None)
        direction = qs_parts.get('direction', None)
        if sort not in self.allowed_sort_fields:
            sort = self.default_sort[0]
        if direction not in self.allowed_sort_orders:
            direction = self.default_sort[1]
        return sort, direction

    def _get_sort_field(self, sort):
        return '%s_at' % sort

    def _prepare_group_by(self, group_by, group_by_direction, qs_parts,
                          qs_filters, filter_objects, order_by):
        filter_objects['group_by_direction'] = qs_filters['group_by_direction'] = group_by_direction
        qs_filters['group_by'] = qs_parts['group_by']
        filter_objects['group_by'] = qs_parts['group_by']
        filter_objects['group_by_field'] = group_by
        order_by.append('%s%s' % ('-' if group_by_direction == 'desc' else '', group_by))

    def get_issues_for_context(self, context):
        """
        Read the querystring from the context, already cut in parts,
        and check parts that can be applied to filter issues, and return
        an issues queryset ready to use, with some context
        """
        qs_parts = self.get_qs_parts(context)

        qs_filters = {}
        filter_objects = {}

        query_filters = {}

        # filter by state
        state = self._get_state(qs_parts)
        if state is not None:
            qs_filters['state'] = filter_objects['state'] = query_filters['state'] = state

        # filter by pull request status
        is_pull_request = self._get_is_pull_request(qs_parts)
        if is_pull_request is not None:
            qs_filters['pr'] = self.allowed_prs[is_pull_request]
            filter_objects['pr'] = query_filters['is_pull_request'] = is_pull_request

        # filter by mergeable status
        if qs_filters.get('pr') == 'yes':
            is_mergeable = self._get_is_mergeable(qs_parts)
            if is_mergeable is not None:
                qs_filters['mergeable'] = self.allowed_mergeables[is_mergeable]
                filter_objects['mergeable'] = query_filters['mergeable'] = is_mergeable

        # the base queryset with the current filters
        queryset = self.get_base_queryset().filter(**query_filters)

        # prepare order, by group then asked ordering
        order_by = []

        # do we need to group by a field ?
        group_by, group_by_direction = self._get_group_by(qs_parts)
        if group_by is not None:
            self._prepare_group_by(group_by, group_by_direction, qs_parts,
                                   qs_filters, filter_objects, order_by)

        # Do we need to select/prefetch related stuff ? If not grouping, no
        # because we assume all templates are already cached
        queryset = self.select_and_prefetch_related(queryset, group_by)

        # and finally, asked ordering
        sort, sort_direction = self._get_sort(qs_parts)
        qs_filters['sort'] = filter_objects['sort'] = sort
        qs_filters['direction'] = filter_objects['direction'] = sort_direction
        order_by.append('%s%s' % ('-' if sort_direction == 'desc' else '', self._get_sort_field(sort)))

        # final order by, with group and wanted order
        queryset = queryset.order_by(*order_by)

        # return the queryset and some context
        filter_context = {
            'filter_objects': filter_objects,
            'qs_filters': qs_filters,
        }
        return queryset, filter_context

    def select_and_prefetch_related(self, queryset, group_by):
        return queryset.select_related('repository__owner')

    def get_base_url(self):
        raise NotImplementedError

    def get_context_data(self, **kwargs):
        """
        Set default content for the issue views
        """
        context = super(BaseIssuesView, self).get_context_data(**kwargs)

        # get the list of issues
        issues, filter_context = self.get_issues_for_context(context)

        # final context
        issues_url = self.get_base_url()

        issues_filter = self.prepare_issues_filter_context(filter_context)
        context.update({
            'root_issues_url': issues_url,
            'current_issues_url': issues_url,
            'issues_filter': issues_filter,
            'qs_parts_for_ttags': issues_filter['parts'],
            'sorts': {
                'created': {
                    'name': u'created',
                    'description': u'issue creation date',
                },
                'updated': {
                    'name': u'updated',
                    'description': u'issue last update date',
                },
            },
        })

        context['issues'], context['issues_count'], context['limit_reached'] = self.finalize_issues(issues, context)

        return context

    def prepare_issues_filter_context(self, filter_context):
        """
        Prepare a dict to use in the template, with many information about the
        current filter: parts (as found in the querystring), objects (to use for
        display in the template), the full querystring
        """
        return {
            'parts': filter_context['qs_filters'],
            'objects': filter_context['filter_objects'],
            'querystring': make_querystring(filter_context['qs_filters']),
        }

    def finalize_issues(self, issues, context):
        """
        Return a final list of issues usable in the view.
        """
        total_count = issues_count = issues.count()

        if not issues_count:
            return [], 0, False

        if self.request.GET.get('limit') != 'no' and issues_count > self.LIMIT_ISSUES:
            issues_count = self.LIMIT_ISSUES
            issues = issues[:self.LIMIT_ISSUES]
            limit_reached = True
        else:
            limit_reached = False

        try:
            issues = list(issues.all())
        except DatabaseError as e:
            # sqlite limits the vars passed in the request to 999, and
            # prefetch_related use a in(...), and with more than 999 issues
            # sqlite raises an error.
            # In this case, we loop on the data by slice of 999 issues
            if u'%s' % e != 'too many SQL variables':
                raise
            queryset = issues
            issues = []
            per_fetch = 999

            iterations = int(ceil(issues_count / float(per_fetch)))
            for iteration in range(0, iterations):
                issues += list(queryset[iteration * per_fetch:(iteration + 1) * per_fetch])

        return issues, total_count, limit_reached
