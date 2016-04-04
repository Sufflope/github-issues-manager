from collections import OrderedDict
from copy import deepcopy
import json
from math import ceil
from urlparse import parse_qs
from uuid import uuid4

from django.contrib import messages
from django.db.utils import DatabaseError
from django.forms.forms import NON_FIELD_ERRORS
from django.http import HttpResponse
from django.http.response import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.cache import patch_response_headers
from django.utils.functional import cached_property

from gim.front.utils import make_querystring
from gim.core.models import Repository, Issue
from gim.subscriptions.models import Subscription, SUBSCRIPTION_STATES


class WithAjaxRestrictionViewMixin(object):
    """
    If the "ajax_only" attribute is set to True, posting to the form will raise
    a "method not allowed" error to the user
    """
    ajax_only = False

    def dispatch(self, request, *args, **kwargs):
        if self.ajax_only and not request.is_ajax():
            return self.http_method_not_allowed(self.request)
        return super(WithAjaxRestrictionViewMixin, self).dispatch(request, *args, **kwargs)

    def render_messages(self, **kwargs):
        return render(self.request, 'front/messages.html', **kwargs)

    def render_form_errors_as_json(self, form, code=422):
        """
        To be used in form_invalid to return the errors in json format to be
        used by the js
        """
        json_data = json.dumps({
            'errors': form._errors
        })
        return HttpResponse(
            json_data,
            content_type='application/json',
            status=code,
        )

    def render_form_errors_as_messages(self, form, show_fields=True, **kwargs):
        """
        To be used in form_invalid to return nothing but messages (added to the
        content via a middleware)
        """
        for field, errors in form._errors.items():
            for error in errors:
                msg = error
                if show_fields and field != NON_FIELD_ERRORS:
                    msg = '%s: %s' % (field, error)
                messages.error(self.request, msg)
        return self.render_messages(**kwargs)


class LinkedToUserFormViewMixin(object):
    """
    A mixin for form views when the main object depends on a user, and
    using a form which is a subclass of LinkedToUserFormMixin, to have the
    current user passed to the form
    """
    def get_form_kwargs(self):
        kwargs = super(LinkedToUserFormViewMixin, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


def get_querystring_context(querystring):
    # put querystring parts in a dict
    qs_dict = parse_qs(querystring)
    qs_parts = {}
    for key, values in qs_dict.items():
        if not len(values):
            continue
        if len(values) > 1:
            qs_parts[key] = values
        elif ',' in values[0]:
            qs_parts[key] = values[0].split(',')
        else:
            qs_parts[key] = values[0]

    return {
        'querystring_parts': qs_parts,
        'querystring': querystring,
    }


class WithQueryStringViewMixin(object):

    def get_qs_parts(self, context):
        """
        Get the querystring parts from the context
        """
        if 'querystring_parts' not in context:
            context['querystring_parts'] = {}
        return deepcopy(context['querystring_parts'])

    def get_querystring_context(self, querystring=None):
        if querystring is None:
            querystring = self.request.META.get('QUERY_STRING', '')
        return get_querystring_context(querystring)

    def get_context_data(self, **kwargs):
        """
        By default, simply split the querystring in parts for use in other
        views, and put the parts and the whole querystring in the context
        """
        context = super(WithQueryStringViewMixin, self).get_context_data(**kwargs)
        context.update(self.get_querystring_context())
        return context


class DependsOnSubscribedViewMixin(object):
    """
    A simple mixin with a "get_allowed_repositories" method which returns a
    queryset with allowed repositories for the user given the "allowed_rights"
    attribute of the class.
    Depends on nothing
    """
    allowed_rights = SUBSCRIPTION_STATES.READ_RIGHTS

    def get_allowed_repositories(self, rights=None):
        """
        Limit repositories to the ones subscribed by the user
        """
        if rights is None:
            rights = self.allowed_rights
        filters = {
            'subscriptions__user': self.request.user
        }
        if rights != SUBSCRIPTION_STATES.ALL_RIGHTS:
            filters['subscriptions__state__in'] = rights

        return Repository.objects.filter(**filters)

    def is_repository_allowed(self, repository):
        # Always True because already filtered in `get_allowed_repositories`
        # Overridden in WithRepositoryViewMixin that allow all repositories by default
        return True


class WithSubscribedRepositoriesViewMixin(DependsOnSubscribedViewMixin):
    """
    A mixin that will put the list of all subscribed repositories in the context.
    Depends only on DependsOnSubscribedViewMixin to get the list of allowed
    repositories
    Provides also a list of all the subscriptions as a cached property
    """
    subscriptions_list_rights = SUBSCRIPTION_STATES.READ_RIGHTS

    @cached_property
    def subscriptions(self):
        """
        Return (and cache) the list of all subscriptions of the current user
        based on the "subscriptions_list_rights" attribute
        """
        subscriptions = self.request.user.subscriptions.all()
        if self.subscriptions_list_rights != SUBSCRIPTION_STATES.ALL_RIGHTS:
            subscriptions = subscriptions.filter(state__in=self.subscriptions_list_rights)
        return subscriptions

    def get_context_data(self, **kwargs):
        """
        Add the list of subscribed repositories in the context, in a variable
        named "subscribed_repositories".
        """
        context = super(WithSubscribedRepositoriesViewMixin, self).get_context_data(**kwargs)

        context['subscribed_repositories'] = self.get_allowed_repositories(
                rights=self.subscriptions_list_rights
           ).extra(select={
                    'lower_name': 'lower(name)',
                    'lower_owner': 'lower(username)',
                }
            ).select_related('owner').order_by('lower_owner', 'lower_name')

        return context


class WithRepositoryViewMixin(object):
    """
    A mixin that is meant to be used when a view depends on a repository.
    Provides
    - a "repository" property that'll get the repository depending on
    the ones allowed by the "allowed_rights" attribute and the url params.
    - a "get_repository_filter_args" to use to filter a model on a repository's name
    and its owner's username
    And finally, put the repository and its related subscription in the context
    """

    allowed_rights = SUBSCRIPTION_STATES.READ_RIGHTS

    def get_repository_filter_args(self, filter_root=''):
        """
        Return a dict with attribute to filter a model for a given repository's
        name and its owner's username as given in the url.
        Use the "filter_root" to prefix the filter.
        """
        if filter_root and not filter_root.endswith('__'):
            filter_root += '__'
        return {
            '%sowner__username' % filter_root: self.kwargs['owner_username'],
            '%sname' % filter_root: self.kwargs['repository_name'],
        }

    def get_allowed_repositories(self):
        # By default all repositories. The `repository` property will do the real check
        return Repository.objects.all()

    def is_repository_allowed(self, repository):
        state = repository.get_subscription_state_for_user(self.request.user)

        if state.subscription:
            # Will avoid a fetch ;)
            self.subscription = state.subscription
        else:
            # Create a fake one
            self.subscription = Subscription(
                user=self.request.user,
                repository=repository,
                state=state.value,
            )

        return state.value in self.allowed_rights

    @cached_property
    def repository(self):
        """
        Return (and cache) the repository. Raise a 404 if the current user is
        not allowed to use it, depending on the "allowed_rights" attribute
        """
        qs = self.get_allowed_repositories()
        repository = get_object_or_404(qs.select_related('owner'),
                                              **self.get_repository_filter_args())
        # Additional check
        if not self.is_repository_allowed(repository):
            raise Http404

        return repository

    @cached_property
    def subscription(self):
        """
        Return (and cache) the subscription for the current user/repository
        """
        state = self.repository.get_subscription_state_for_user(self.request.user)
        if state.subscription:
            return state.subscription

        # Create a fake one
        return Subscription(
            user=self.request.user,
            repository=self.repository,
            state=state.value,
        )

    def get_context_data(self, **kwargs):
        """
        Put the current repository and its related subscription in the context
        """
        context = super(WithRepositoryViewMixin, self).get_context_data(**kwargs)
        context['current_repository'] = self.repository
        context['current_subscription'] = self.subscription
        return context

    @cached_property
    def collaborators_ids(self):
        """
        Return the ids of all collaborators
        """
        return self.repository.collaborators.all().values_list('id', flat=True)


class WithSubscribedRepositoryViewMixin(DependsOnSubscribedViewMixin, WithRepositoryViewMixin):
    """
    Subclass of WithRepositoryViewMixin that will only allow subscribed repositories.
    """
    pass


class RepositoryViewMixin(WithRepositoryViewMixin):
    """
    A simple mixin to use for views when the main object is a repository.
    Use the kwargs in the url to fetch it from database, using the
    "allowed_rights" attribute to limit to these rights for the current user.
    """
    model = Repository
    context_object_name = 'current_repository'

    def get_object(self, queryset=None):
        """
        Full overwrite of the method to return the repository got matching url
        params and the "allowed_rights" attribute for the current user
        """
        return self.repository


class SubscribedRepositoryViewMixin(DependsOnSubscribedViewMixin, RepositoryViewMixin):
    """
    Subclass of RepositoryViewMixin that will only allow subscribed repositories.
    """
    pass


class DependsOnRepositoryViewMixin(WithRepositoryViewMixin):
    """
    A simple mixin to use for views when the main object depends on a repository
    Will limit entries to ones matching the repository fetched using url params
    and the "allowed_rights" attribute.
    The "repository_related_name" attribute is the name to use to filter only
    on the current repository.
    """
    repository_related_name = 'repository'

    def get_queryset(self):
        """
        Return a queryset based on the current repository and allowed rights.
        """
        return self.model._default_manager.filter(**{
                self.repository_related_name: self.repository
            })


class DependsOnSubscribedRepositoryViewMixin(DependsOnSubscribedViewMixin, RepositoryViewMixin):
    """
    Subclass of DependsOnRepositoryViewMixin that will only allow subscribed repositories.
    """
    pass


class LinkedToRepositoryFormViewMixin(WithAjaxRestrictionViewMixin, DependsOnRepositoryViewMixin):
    """
    A mixin for form views when the main object depends on a repository, and
    using a form which is a subclass of LinkedToRepositoryFormMixin, to have the
    current repository passed to the form
    """
    def get_form_kwargs(self):
        kwargs = super(LinkedToRepositoryFormViewMixin, self).get_form_kwargs()
        kwargs['repository'] = self.repository
        return kwargs


class LinkedToSubscribedRepositoryFormViewMixin(DependsOnSubscribedViewMixin, LinkedToRepositoryFormViewMixin):
    """
    Subclass of LinkedToRepositoryFormViewMixin that will only allow subscribed repositories.
    """
    pass


class WithIssueViewMixin(WithRepositoryViewMixin):
    """
    A mixin that is meant to be used when a view depends on a issue.
    Provides stuff provided by WithSubscribedRepositoryViewMixin, plus:
    - a "issue" property that'll get the issue depending on the repository and
    the "number" url params
    - a "get_issue_filter_args" to use to filter a model on a repository's name,
    its owner's username, and an issue number
    And finally, put the issue in the context
    """
    def get_issue_filter_args(self, filter_root=''):
        """
        Return a dict with attribute to filter a model for a given repository's
        name, its owner's username and an issue number as given in the url.
        Use the "filter_root" to prefix the filter.
        """
        if filter_root and not filter_root.endswith('__'):
            filter_root += '__'
        return {
            '%srepository_id' % filter_root: self.repository.id,
            '%snumber' % filter_root: self.kwargs['issue_number']
        }

    @cached_property
    def issue(self):
        """
        Return (and cache) the issue. Raise a 404 if the current user is
        not allowed to use its repository, or if the issue is not found
        """
        return get_object_or_404(
            Issue.objects.select_related('repository__owner'),
            **self.get_issue_filter_args()
        )

    def get_context_data(self, **kwargs):
        """
        Put the current issue in the context
        """
        context = super(WithIssueViewMixin, self).get_context_data(**kwargs)
        context['current_issue'] = self.issue
        return context


class DependsOnIssueViewMixin(WithIssueViewMixin, DependsOnRepositoryViewMixin):
    """
    A simple mixin to use for views when the main object depends on a issue
    Will limit entries to ones mathing the issue fetched using url params
    and the "allowed_rights" attribute.
    The "issue_related_name" attribute is the name to use to filter only
    on the current issue.
    """
    issue_related_name = 'issue'
    repository_related_name = 'issue__repository'

    def get_queryset(self):
        """
        Return a queryset based on the current repository, issue, and allowed
        rights.
        """
        return self.model._default_manager.filter(**{
                self.issue_related_name: self.issue
            })


class LinkedToIssueFormViewMixin(WithAjaxRestrictionViewMixin, DependsOnIssueViewMixin):
    """
    A mixin for form views when the main object depends on an issue, and
    using a form which is a subclass of LinkedToIssueFormMixin, to have the
    current issue passed to the form
    """
    def get_form_kwargs(self):
        kwargs = super(LinkedToIssueFormViewMixin, self).get_form_kwargs()
        kwargs['issue'] = self.issue
        return kwargs


class LinkedToCommitFormViewMixin(WithAjaxRestrictionViewMixin):
    """
    A mixin for form views when the main object depends on a commit, and
    using a form which is a subclass of LinkedToCommitFormMixin, to have the
    current commit passed to the form
    """
    def get_form_kwargs(self):
        kwargs = super(LinkedToCommitFormViewMixin, self).get_form_kwargs()
        kwargs['commit'] = self.commit
        return kwargs


class DeferrableViewPart(object):
    deferred_template_name = 'front/base_deferred_block.html'
    auto_load = True

    @property
    def part_url(self):
        # must be defined in the final class
        raise NotImplementedError()

    def inherit_from_view(self, view):
        self.args = view.args
        self.kwargs = view.kwargs
        self.request = view.request

    def get_context_data(self, **kwargs):
        context = super(DeferrableViewPart, self).get_context_data(**kwargs)
        context.update({
            'defer_url': self.part_url,
        })
        return context

    def get_as_part(self, main_view, **kwargs):
        self.inherit_from_view(main_view)
        return self.render_part(**kwargs)

    def render_part(self, **kwargs):
        response = self.get(self.request, **kwargs)
        response.render()
        return response.content

    def get_deferred_context_data(self, **kwargs):
        kwargs.update({
            'view': self,
            'deferred': True,
            'defer_url': self.part_url,
            'auto_load': self.auto_load,
        })
        return kwargs

    def get_deferred_template_names(self):
        return [self.deferred_template_name]

    def get_as_deferred(self, main_view, **kwargs):
        self.inherit_from_view(main_view)
        return self.render_deferred(**kwargs)

    def render_deferred(self, **kwargs):
        response = self.response_class(
            request = self.request,
            template = self.get_deferred_template_names(),
            context = self.get_deferred_context_data(**kwargs),
            content_type = self.content_type,
        )
        response.render()
        return response.content


class CacheControlMixin(object):
    cache_timeout = 60

    def get_cache_timeout(self):
        return self.cache_timeout

    def dispatch(self, *args, **kwargs):
        response = super(CacheControlMixin, self).dispatch(*args, **kwargs)
        patch_response_headers(response, self.get_cache_timeout())
        return response


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

    filters_and_list_template_name = 'front/issues/include_filters_and_list.html'
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

    def get_filter_parts(self, qs_parts):

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

        # prepare order, by group then asked ordering
        order_by = []

        # do we need to group by a field ?
        group_by, group_by_direction = self._get_group_by(qs_parts)
        if group_by is not None:
            self._prepare_group_by(group_by, group_by_direction, qs_parts,
                                   qs_filters, filter_objects, order_by)

        # and finally, asked ordering
        sort, sort_direction = self._get_sort(qs_parts)
        qs_filters['sort'] = filter_objects['sort'] = sort
        qs_filters['direction'] = filter_objects['direction'] = sort_direction
        order_by.append('%s%s' % ('-' if sort_direction == 'desc' else '', self._get_sort_field(sort)))

        return query_filters, order_by, filter_objects, qs_filters, group_by, group_by_direction

    def get_queryset(self, queryset, filters, order_by):
        if filters:
            excludes = {key[1:]: value for key, value in filters.items() if key.startswith('-')}
            filters = {key: value for key, value in filters.items() if not key.startswith('-')}
            if filters:
                queryset = queryset.filter(**filters)
            if excludes:
                queryset = queryset.exclude(**excludes)
        if order_by:
            queryset = queryset.order_by(*order_by)

        return queryset

    def get_issues_for_context(self, context):
        """
        Read the querystring from the context, already cut in parts,
        and check parts that can be applied to filter issues, and return
        an issues queryset ready to use, with some context
        """

        qs_parts = self.get_qs_parts(context)

        query_filters, order_by, filter_objects, qs_filters, group_by, group_by_direction = \
            self.get_filter_parts(qs_parts)

        queryset = self.get_queryset(self.get_base_queryset(), query_filters, order_by)
        queryset = self.select_and_prefetch_related(queryset, group_by)

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
            'list_uuid': str(uuid4()),
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
            'can_show_shortcuts': True,
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

        if self.request.GET.get('limit') != 'no' and issues_count > self.LIMIT_ISSUES + 5:  # tolerance
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

    def get_template_names(self):
        """
        Use a specific template if the request is an ajax one
        """

        if self.request.is_ajax():
            return self.filters_and_list_template_name

        return super(BaseIssuesView, self).get_template_names()
