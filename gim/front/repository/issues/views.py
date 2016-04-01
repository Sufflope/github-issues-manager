# -*- coding: utf-8 -*-
from collections import OrderedDict
from datetime import datetime
import os
import json
from math import ceil
from time import sleep
from urlparse import unquote, urlparse, urlunparse
from uuid import uuid4

from django.contrib import messages
from django.core.handlers.wsgi import WSGIRequest
from django.core.urlresolvers import reverse, reverse_lazy, resolve, Resolver404
from django.http import Http404, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, render
from django.test.client import FakePayload
from django.utils.datastructures import SortedDict
from django.utils.encoding import force_str
from django.utils.functional import cached_property
from django.utils.http import is_safe_url
from django.views.generic import UpdateView, CreateView, TemplateView, DetailView

from limpyd_jobs import STATUSES

from gim.core.models import (Issue, GithubUser, LabelType, Milestone,
                             PullRequestCommentEntryPoint, IssueComment,
                             PullRequestComment, CommitComment,
                             GithubNotification)
from gim.core.tasks.issue import (IssueEditStateJob, IssueEditTitleJob,
                                  IssueEditBodyJob, IssueEditMilestoneJob,
                                  IssueEditAssigneeJob, IssueEditLabelsJob,
                                  IssueCreateJob, FetchIssueByNumber, UpdateIssueCacheTemplate)
from gim.core.tasks.comment import (IssueCommentEditJob, PullRequestCommentEditJob,
                                    CommitCommentEditJob)

from gim.subscriptions.models import SUBSCRIPTION_STATES, Subscription

from gim.front.github_notifications.views import GithubNotifications

from gim.front.mixins.views import (LinkedToRepositoryFormViewMixin,
                                    LinkedToIssueFormViewMixin,
                                    LinkedToUserFormViewMixin,
                                    LinkedToCommitFormViewMixin,
                                    DeferrableViewPart,
                                    WithSubscribedRepositoryViewMixin,
                                    WithAjaxRestrictionViewMixin,
                                    DependsOnIssueViewMixin,
                                    CacheControlMixin,
                                    WithIssueViewMixin,
                                    get_querystring_context,
                                    )

from gim.front.models import GroupedCommits
from gim.front.repository.views import BaseRepositoryView
from gim.front.mixins.views import BaseIssuesView

from gim.front.utils import make_querystring

from .forms import (IssueStateForm, IssueTitleForm, IssueBodyForm,
                    IssueMilestoneForm, IssueAssigneeForm, IssueLabelsForm,
                    IssueCreateForm, IssueCreateFormFull,
                    IssueCommentCreateForm, PullRequestCommentCreateForm, CommitCommentCreateForm,
                    IssueCommentEditForm, PullRequestCommentEditForm, CommitCommentEditForm,
                    IssueCommentDeleteForm, PullRequestCommentDeleteForm, CommitCommentDeleteForm)

LIMIT_ISSUES = 300
LIMIT_USERS = 30


class UserFilterPart(DeferrableViewPart, WithSubscribedRepositoryViewMixin, TemplateView):
    auto_load = False
    relation = None

    def get_usernames(self):
        qs = getattr(self.repository, self.relation).order_by()
        return sorted(qs.values_list('username', flat=True), key=unicode.lower)

    def count_usernames(self):
        if not hasattr(self, '_count'):
            self._count = getattr(self.repository, self.relation).count()
        return self._count

    @property
    def part_url(self):
        return reverse_lazy('front:repository:%s' % self.url_name,
                            kwargs=self.repository.get_reverse_kwargs())

    @cached_property
    def is_ajax(self):
        # as we can load the view that load the deferred part in ajax, we cannot rely only on
        # request.is_ajax
        return self.request.is_ajax() and 'if.user_filter_type' in self.request.GET

    def get_context_data(self, **kwargs):
        context = super(UserFilterPart, self).get_context_data(**kwargs)

        if self.is_ajax:
            # we get variables via the url
            context['list_uuid'] = self.request.GET['if.list_uuid']
            context['current_issues_url'] = self.request.GET['if.current_issues_url']
            context['issues_filter'] = {
                'parts': {
                    self.request.GET['if.user_filter_type']: self.request.GET.get('if.username')
                }
            }
            context.update(
                get_querystring_context(self.request.GET.get('if.querystring'))
            )
        else:
            # we already have variables in the contexct via the caller
            if context.get('issues_filter', {}).get('parts'):
                context['qs_parts_for_ttags'] = context['issues_filter']['parts']

        usernames = self.get_usernames()

        context.update({
            'current_repository': self.repository,

            'usernames': usernames,
            'count': len(usernames),

            'MAX_USERS': LIMIT_USERS,
            'MIN_FOR_FILTER': 20,

            'list_open': self.is_ajax,
        })


        return context

    def get_deferred_context_data(self, **kwargs):
        context = super(UserFilterPart, self).get_deferred_context_data(**kwargs)

        if context.get('issues_filter', {}).get('parts'):
            context['qs_parts_for_ttags'] = context['issues_filter']['parts']

        context.update({
            'count': self.count_usernames(),
            'MAX_USERS': LIMIT_USERS,
        })
        return context

    def get_template_names(self):
        if self.is_ajax:
            return [self.list_template_name]
        else:
            return [self.template_name]

    def inherit_from_view(self, view):
        super(UserFilterPart, self).inherit_from_view(view)


class IssuesFilterCreators(UserFilterPart):
    relation = 'issues_creators'
    url_name = 'issues.filter.creators'
    template_name = 'front/repository/issues/filters/include_creators.html'
    deferred_template_name = template_name
    list_template_name = 'front/repository/issues/filters/include_creators_list.html'
    title = 'Creators'


class IssuesFilterAssigned(UserFilterPart):
    relation = 'issues_assigned'
    url_name = 'issues.filter.assigned'
    template_name = 'front/repository/issues/filters/include_assigned.html'
    deferred_template_name = template_name
    list_template_name = 'front/repository/issues/filters/include_assigned_list.html'
    title = 'Assignees'


class IssuesFilterClosers(UserFilterPart):
    relation = 'issues_closers'
    url_name = 'issues.filter.closers'
    template_name = 'front/repository/issues/filters/include_closers.html'
    deferred_template_name = template_name
    list_template_name = 'front/repository/issues/filters/include_closers_list.html'
    title = 'Closed by'


GROUP_BY_CHOICES = dict(BaseIssuesView.GROUP_BY_CHOICES, **{group_by[0]: group_by for group_by in [
    ('created_by', {
        'field': 'user',
        'name': 'creator',
        'description': u'author of the issue',
    }),
    ('assigned', {
        'field': 'assignee',
        'name': 'assigned',
        'description': u'user assigned to the issue',
    }),
    ('closed_by', {
        'field': 'closed_by',
        'name': 'closed by',
        'description': u'user who closed the issue',
    }),
    ('milestone', {
        'field': 'milestone',
        'name': 'milestone',
        'description': u'milestone the issue is in',
    }),
]})


class IssuesView(BaseIssuesView, BaseRepositoryView):
    name = 'Issues'
    url_name = 'issues'
    template_name = 'front/repository/issues/base.html'
    default_qs = 'state=open'
    display_in_menu = True

    filters_and_list_template_name = 'front/repository/issues/include_filters_and_list.html'


    GROUP_BY_CHOICES = GROUP_BY_CHOICES

    allowed_group_by = OrderedDict(GROUP_BY_CHOICES[name] for name in [
        'state',
        'created_by',
        'assigned',
        'closed_by',
        'milestone',
        'pr',
    ])

    user_filter_types_matching = {'created_by': 'user', 'assigned': 'assignee', 'closed_by': 'closed_by'}

    def get_base_queryset(self):
        return self.repository.issues.ready()

    def get_base_url(self):
        return self.repository.get_view_url(self.url_name)

    def _get_milestone(self, qs_parts):
        """
        Return the valid milestone to use, or None.
        A valid milestone can be '__none__' or a real Milestone object, based on a
        milestone number found in the querystring
        """
        milestone_number = qs_parts.get('milestone', None)
        if milestone_number and isinstance(milestone_number, basestring):
            if milestone_number.isdigit():
                try:
                    milestone = self.repository.milestones.ready().get(number=milestone_number)
                except Milestone.DoesNotExist:
                    pass
                else:
                    return milestone
            elif milestone_number == '__none__':
                return '__none__'
        return None

    def _get_labels(self, qs_parts):
        """
        Return a tuple with two lists:
        - the list of canceled types (tuples of (id, name))
        - the list of valid labels to use. The result is a list of Label
        objects, based on names found on the querystring
        """
        label_names = qs_parts.get('labels', None)
        if label_names:
            if not isinstance(label_names, list):
                label_names = [label_names]
            label_names = [l for l in label_names if l]
        if not label_names:
            return (None, None)

        canceled_types = set()
        real_label_names = set()

        for label_name in label_names:
            if label_name.endswith(':__none__'):
                canceled_types.add(label_name[:-9])
            else:
                real_label_names.add(label_name)

        qs = self.repository.labels.ready().filter(name__in=real_label_names)
        if canceled_types:
            canceled_types = list(self.repository.label_types.filter(name__in=canceled_types)
                                                             .values_list('id', 'name'))
            qs = qs.exclude(label_type_id__in=([t[0] for t in canceled_types]))

        return canceled_types, list(qs.prefetch_related('label_type'))

    def _get_group_by(self, qs_parts):
        """
        Return the group_by field to use, and the direction.
        The group_by field can be either an allowed string, or an existing
        LabelType
        """
        group_by = qs_parts.get('group_by', None)

        if group_by and group_by.startswith('type:'):

            # group by a label type
            label_type_name = group_by[5:]
            try:
                label_type = self.repository.label_types.get(name=label_type_name)
            except LabelType.DoesNotExist:
                return None, None
            else:
                return label_type, self._get_group_by_direction(qs_parts)

        return super(IssuesView, self)._get_group_by(qs_parts)

    def _get_user_filter(self, qs_parts, filter_type):
        if filter_type not in self.user_filter_types_matching:
            return None

        username = qs_parts.get(filter_type, None)

        if username:
            if username == '__none__' and filter_type == 'assigned':
                return '__none__'
            elif username == '__any__' and filter_type == 'assigned':
                return '__any__'
            try:
                user = GithubUser.objects.get(username=username)
            except GithubUser.DoesNotExist:
                pass
            else:
                return user

        return None

    def _prepare_group_by(self, group_by, group_by_direction,
                          qs_parts, qs_filters, filter_objects, order_by):
        if isinstance(group_by, LabelType):
            qs_filters['group_by'] = 'type:%s' % group_by.name
            filter_objects['group_by'] = group_by
            filter_objects['group_by_field'] = 'label_type_grouper'
        else:
            super(IssuesView, self)._prepare_group_by(group_by, group_by_direction, qs_parts,
                                                      qs_filters, filter_objects, order_by)

    def get_filter_parts(self, qs_parts):
        query_filters, order_by, filter_objects, qs_filters, group_by, group_by_direction =  \
            super(IssuesView, self).get_filter_parts(qs_parts)

        # filter by milestone
        milestone = self._get_milestone(qs_parts)
        if milestone is not None:
            filter_objects['milestone'] = milestone
            if milestone == '__none__':
                qs_filters['milestone'] = '__none__'
                query_filters['milestone_id__isnull'] = True
            else:
                qs_filters['milestone'] = '%s' % milestone.number
                query_filters['milestone__number'] = milestone.number

        # filter by author/assigned/closer
        for filter_type, filter_field in self.user_filter_types_matching.items():
            user = self._get_user_filter(qs_parts, filter_type)
            if user is not None:
                filter_objects[filter_type] = user
                qs_filters[filter_type] = user
                if user == '__none__':
                    query_filters['%s_id__isnull' % filter_field] = True
                elif user == '__any__':
                    query_filters['%s_id__isnull' % filter_field] = False
                else:
                    qs_filters[filter_type] = user.username
                    query_filters[filter_field] = user.id

        # now filter by labels
        label_types_to_ignore, labels = self._get_labels(qs_parts)
        if label_types_to_ignore or labels:
            qs_filters['labels'] = []
            filter_objects['current_label_types'] = {}

        if label_types_to_ignore:
            query_filters['-labels__label_type_id__in'] = [t[0] for t in label_types_to_ignore]
            # we can set, and not update, as we are first to touch this
            qs_filters['labels'] = ['%s:__none__' % t[1] for t in label_types_to_ignore]
            filter_objects['current_label_types'] = {t[0]: '__none__' for t in label_types_to_ignore}

        if labels:
            filter_objects['labels'] = labels
            filter_objects['current_labels'] = []
            for label in labels:
                qs_filters['labels'].append(label.name)
                if label.label_type_id and label.label_type_id not in filter_objects['current_label_types']:
                    filter_objects['current_label_types'][label.label_type_id] = label
                elif not label.label_type_id:
                    filter_objects['current_labels'].append(label)
                query_filters['labels'] = label.id

        return query_filters, order_by, filter_objects, qs_filters, group_by, group_by_direction

    def select_and_prefetch_related(self, queryset, group_by):
        if not group_by:
            return queryset

        # TODO: select/prefetch only the stuff needed for grouping
        return queryset.select_related(
            'repository__owner',  # default
            'user',  # we may have a lot of different ones
        ).prefetch_related(
            'assignee', 'closed_by', 'milestone',  # we should have only a few ones for each
            'labels__label_type'
        )

    @cached_property
    def label_types(self):
        return self.repository.label_types.all().prefetch_related('labels').order_by('name')

    @cached_property
    def milestones(self):
        return self.repository.milestones.all()

    def get_context_data(self, **kwargs):
        """
        Set default content for the issue views
        """
        context = super(IssuesView, self).get_context_data(**kwargs)

        # final context
        context.update({
            'label_types': self.label_types,
            'milestones': self.milestones,
        })

        for user_filter_view in (IssuesFilterCreators, IssuesFilterAssigned, IssuesFilterClosers):
            view = user_filter_view()
            view.inherit_from_view(self)
            count = view.count_usernames()
            context[view.relation] = {
                'count': count
            }
            if count:
                part_kwargs = {
                    'issues_filter': context['issues_filter'],
                    'current_issues_url': context['current_issues_url'],
                    'list_uuid': context['list_uuid'],
                }
                context[view.relation]['view'] = view
                if count > LIMIT_USERS:
                    context[view.relation]['part'] = view.render_deferred(**part_kwargs)
                else:
                    context[view.relation]['part'] = view.render_part(**part_kwargs)

        context['can_add_issues'] = True

        return context

    def prepare_issues_filter_context(self, filter_context):
        """
        Update from the parent call to include the base querystring (without user information
        ), and the full querystring (with user information if a assigned/created
        filter is used)
        """

        context = super(IssuesView, self).prepare_issues_filter_context(filter_context)

        # we need a querystring without the created/assigned parts
        querystring = dict(filter_context['qs_filters'])  # make a copy!
        querystring.pop('user_filter_type', None)
        querystring.pop('username', None)

        context['querystring'] = make_querystring(querystring)

        return context

    def finalize_issues(self, issues, context):
        """
        Return a final list of issues usable in the view.
        Actually simply order ("group") by a label_type if asked
        """

        issues, total_count, limit_reached = super(IssuesView, self).finalize_issues(issues, context)

        label_type = context['issues_filter']['objects'].get('group_by', None)
        attribute = context['issues_filter']['objects'].get('group_by_field', None)
        if label_type and isinstance(label_type, LabelType) and attribute:

            # regroup issues by label from the lab
            issues_dict = {}
            for issue in issues:
                add_to = None

                for label in issue.labels.ready():  # thanks prefetch_related
                    if label.label_type_id == label_type.id:
                        # found a label for the wanted type, mark it and stop
                        # checking labels for this issue
                        add_to = label.id
                        setattr(issue, attribute, label)
                        break

                # add in a dict, with one entry for each label of the type (and one for None)
                issues_dict.setdefault(add_to, []).append(issue)

            # for each label of the type, append matching issues to the final
            # list
            issues = []
            label_type_labels = [None] + list(label_type.labels.ready())
            if context['issues_filter']['parts'].get('group_by_direction', 'asc') == 'desc':
                label_type_labels.reverse()
            for label in label_type_labels:
                label_id = None if label is None else label.id
                if label_id in issues_dict:
                    issues += issues_dict[label_id]

        return issues, total_count, limit_reached


class IssueView(WithIssueViewMixin, TemplateView):
    url_name = 'issue'
    ajax_template_name = 'front/repository/issues/issue.html'

    def get_referer_issues_view(self):
        referer = self.request.GET.get('referer')
        if referer:
            referer = unquote(referer)
        else:
            # No way to have this in https, but...
            referer = self.request.META.get('HTTP_REFERER')

        if not referer:
            return None, None, None

        if not is_safe_url(referer, self.request.get_host()):
            return None, None, None

        try:
            url_info = urlparse(referer)
            resolved_url = resolve(url_info.path)
        except Resolver404:
            return None, None, None
        else:
            url_name = resolved_url.url_name
            if resolved_url.namespace:
                url_name = resolved_url.namespace + ':' + url_name
            if url_name == GithubNotifications.url_name:
                return GithubNotifications, url_info, resolved_url
            elif resolved_url.namespace == u'front:repository'\
                    and resolved_url.url_name == IssuesView.url_name:
                # Check that we are on the same repository
                if resolved_url.kwargs.get('owner_username') == self.kwargs['owner_username']\
                        and resolved_url.kwargs.get('repository_name') == self.kwargs['repository_name']:
                    return IssuesView, url_info, resolved_url

        return None, None, None

    def get_redirect_url(self):

        redirect_to = None

        # Will raise a 404 if not found
        issue = self.issue

        try:
            notification = self.request.user.github_notifications.get(issue=issue)
        except GithubNotification.DoesNotExist:
            notification = None

        try:
            subscription = self.request.user.subscriptions.exclude(state=Subscription.STATES.NORIGHTS).get(repository=issue.repository)
        except Subscription.DoesNotExist:
            subscription = None

        fragment = 'issue-%d' % issue.pk

        view, url_info, resolved_url = self.get_referer_issues_view()

        if view == GithubNotifications and notification:
            redirect_to = url_info
        elif view and subscription:
            redirect_to = url_info

        if redirect_to:
            redirect_to = urlunparse(list(url_info[:-1]) + [fragment])
        else:
            if subscription:
                view = IssuesView
                redirect_to = issue.repository.get_view_url(view.url_name)
            elif notification:
                view = GithubNotifications
                redirect_to = reverse(view.url_name)
            else:
                raise Http404

            if getattr(view, 'default_qs', None):
                redirect_to = '%s?%s#%s' % (redirect_to, view.default_qs, fragment)
            else:
                redirect_to = '%s#%s' % (redirect_to, fragment)

        return redirect_to

    def get(self, request, *args, **kwargs):
        """
        Redirect to a full issues view if not in ajax mode
        """
        if self.request.is_ajax():
            return super(IssueView, self).get(request, *args, **kwargs)

        return HttpResponseRedirect(self.get_redirect_url())

    def get_base_queryset(self):
        return self.repository.issues.ready()

    @cached_property
    def current_issue(self):
        """
        Based on the informations from the url, try to return
        the wanted issue
        """
        issue = None
        if 'issue_number' in self.kwargs:
            qs = self.get_base_queryset().select_related(
                'user',  'assignee', 'closed_by', 'milestone', 'repository__owner'
            ).prefetch_related(
                'labels__label_type'
            )
            issue = get_object_or_404(qs, number=self.kwargs['issue_number'])
        return issue

    def get_involved_people(self, issue, activity, collaborators_ids):
        """
        Return a list with a dict for each people involved in the issue, with
        the submitter first, the assignee, the the closed_by, and all comments
        authors, with only one entry per person, with, for each dict, the
        user, the comment's count as "count", and a list of types (one or many
        of "owner", "collaborator", "submitter") as "types"
        """
        involved = SortedDict()

        def add_involved(user, is_comment=False, is_commit=False):
            real_user = not isinstance(user, basestring)
            if real_user:
                key = user.username
                val = user
            else:
                key = user
                val = {'username': user}

            d = involved.setdefault(key, {
                                    'user': val, 'comments': 0, 'commits': 0})
            if real_user:
                d['user'] = val  # override if user was a dict
            if is_comment:
                d['comments'] += 1
            if is_commit:
                d['commits'] += 1

        add_involved(issue.user)

        if issue.assignee_id and issue.assignee_id not in involved:
            add_involved(issue.assignee)

        if issue.state == 'closed' and issue.closed_by_id and issue.closed_by_id not in involved:
            add_involved(issue.closed_by)

        for entry in activity:
            if isinstance(entry, PullRequestCommentEntryPoint):
                for pr_comment in entry.comments.all():
                    add_involved(pr_comment.user, is_comment=True)
            elif isinstance(entry, IssueComment):
                add_involved(entry.user, is_comment=True)
            elif isinstance(entry, GroupedCommits):
                for pr_commit in entry:
                    add_involved(pr_commit.author if pr_commit.author_id
                                                  else pr_commit.author_name,
                                 is_commit=True)

        involved = involved.values()
        for involved_user in involved:
            if isinstance(involved_user['user'], dict):
                continue
            involved_user['types'] = []
            if involved_user['user'].id == self.repository.owner_id:
                involved_user['types'].append('owner')
            elif collaborators_ids and involved_user['user'].id in collaborators_ids:
                involved_user['types'].append('collaborator')
            if involved_user['user'].id == issue.user_id:
                involved_user['types'].append('submitter')

        return involved

    def get_context_data(self, **kwargs):
        """
        Add the selected issue in the context
        """
        context = super(IssueView, self).get_context_data(**kwargs)

        # check which issue to display
        current_issue_state = 'ok'
        current_issue = None
        try:
            current_issue = self.current_issue
        except Http404:
            current_issue_state = 'notfound'
        else:
            if not current_issue:
                current_issue_state = 'undefined'

        # fetch other useful data
        edit_level = self.get_edit_level(current_issue)
        if current_issue:
            activity = current_issue.get_activity()
            involved = self.get_involved_people(current_issue, activity,
                                                    self.collaborators_ids)

            if current_issue.is_pull_request:
                context['entry_points_dict'] = self.get_entry_points_dict(
                                                current_issue.all_entry_points)

        else:
            activity = []
            involved = []

        # final context
        context.update({
            'current_issue': current_issue,
            'current_issue_state': current_issue_state,
            'current_issue_activity': activity,
            'current_issue_involved': involved,
            'current_issue_edit_level':  edit_level,
        })

        return context

    def get_edit_level(self, issue):
        """
        Return the edit level of the given issue. It may be None (read only),
        "self" or "full"
        """
        edit_level = None
        if issue and issue.number:
            if self.subscription.state in SUBSCRIPTION_STATES.WRITE_RIGHTS:
                edit_level = 'full'
            elif self.subscription.state == SUBSCRIPTION_STATES.READ\
                                    and issue.user == self.request.user:
                edit_level = 'self'

        return edit_level

    def get_entry_points_dict(self, entry_points):
        """
        Return a dict that will be used in the issue files template to display
        pull request comments (entry points).
        The first level of the dict contains path of the file with entry points.
        The second level contains the position of the entry point, with the
        PullRequestCommentEntryPoint object as value
        """
        entry_points_dict = {}
        for entry_point in entry_points:
            if not entry_point.position:
                continue
            entry_points_dict.setdefault(entry_point.path, {})[entry_point.position] = entry_point
        return entry_points_dict

    def get_template_names(self):
        """
        Use a specific template if the request is an ajax one
        """
        if self.request.is_ajax():
            self.template_name = self.ajax_template_name
        return super(IssueView, self).get_template_names()


class IssueSummaryView(WithAjaxRestrictionViewMixin, IssueView):
    url_name = 'issue.summary'

    ajax_only = True
    http_method_names = ['get']
    ajax_template_name = 'front/repository/issues/include_issue_item_for_cache.html'

    def get_referer_issues_view(self):
        self.referer_view, url_info, resolved_url = super(IssueSummaryView, self).get_referer_issues_view()
        return self.referer_view, url_info, resolved_url

    def get_referer_issues_queryset(self):

        view, url_info, resolved_url = self.get_referer_issues_view()
        if not view:
            return None

        environ = dict(os.environ)

        environ.update({
            'PATH_INFO':       unquote(force_str(url_info.path)),
            'QUERY_STRING':    force_str(url_info.query),
            'REQUEST_METHOD':  str('GET'),
            'wsgi.input': FakePayload(b''),
        })

        for key in ('wsgi.multiprocess', 'wsgi.multithread', 'wsgi.run_once', 'wsgi.url_scheme', 'wsgi.version'):
            if key in self.request.META:
                environ[key] = self.request.META[key]

        request = WSGIRequest(environ)
        request.user = self.request.user

        view = view(request=request, args=resolved_url.args, kwargs=resolved_url.kwargs)
        querystring_context = view.get_querystring_context()
        issues_queryset, self.referer_filter_context = view.get_issues_for_context(querystring_context)

        return issues_queryset

    def get_base_queryset(self):
        queryset = self.get_referer_issues_queryset()
        if queryset is None:
            return super(IssueSummaryView, self).get_base_queryset()
        return queryset

    def get_context_data(self, **kwargs):
        """
        Add the issue in the context
        """
        context = super(IssueSummaryView, self).get_context_data(**kwargs)

        current_issue = self.current_issue

        # Force rerender if there is a job waiting to do it
        try:
            job = UpdateIssueCacheTemplate.collection(identifier=current_issue.pk,
                                           status=STATUSES.WAITING).instances()[0]
        except IndexError:
            pass
        else:
            if job.status.hget() == STATUSES.WAITING:
                job.status.hset(STATUSES.CANCELED)

        context['issue'] = current_issue

        referer_view = getattr(self, 'referer_view')

        if referer_view == GithubNotifications:
            context['reasons'] = referer_view.reasons
            current_issue.github_notification = self.request.user.github_notifications.get(issue_id=current_issue.pk)
            try:
                current_issue.repository.subscription = self.request.user.subscriptions.get(repository_id=current_issue.repository_id)
            except:
                current_issue.repository.subscription = None
            if self.referer_filter_context['filter_objects'].get('group_by_field') == 'githubnotification__repository':
                context['force_hide_repositories'] = True

        return context

    def get_template_names(self):
        referer_view = getattr(self, 'referer_view')
        if referer_view and hasattr(referer_view, 'issue_item_template_name'):
            return [referer_view.issue_item_template_name]
        return super(IssueSummaryView, self).get_template_names()


class IssuePreviewView(CacheControlMixin, WithAjaxRestrictionViewMixin, IssueView):
    url_name = 'issue.preview'

    ajax_only = True
    http_method_names = ['get']

    @cached_property
    def current_issue(self):

        issue = super(IssuePreviewView, self).current_issue
        if not issue:
            return None

        # Always ok for public repositories
        if not issue.repository.private:
            return issue

        # If he is the owner, it's ok
        if issue.repository.owner_id == self.request.user.id:
            return issue

        # If a private repository, we must have a subscription
        allowed_private = self.request.user.subscriptions.filter(
            repository__private=True,
            state__in=Subscription.STATES.READ_RIGHTS
        ).values_list('repository_id', flat=True)
        if issue.repository_id in allowed_private:
            return issue

        # If not, it should be in a notification. It will be displayed in notifications anyway
        notified = self.request.user.github_notifications.values_list('issue_id', flat=True)
        if issue.id in notified:
            return issue

        raise Http404

    def get_context_data(self, **kwargs):
        """
        Add the issue in the context
        """
        context = super(IssuePreviewView, self).get_context_data(**kwargs)

        current_issue = self.current_issue

        activity = current_issue.get_activity()
        involved = self.get_involved_people(current_issue, activity,
                                                self.collaborators_ids)

        context.update({
            'current_issue': current_issue,
            'current_issue_edit_level': None,
            'current_issue_involved': involved,
        })

        return context


    def get_template_names(self):
        """
        We'll only display messages to the user
        """
        return ['front/repository/issues/issue_no_details.html']


class AskFetchIssueView(WithAjaxRestrictionViewMixin, IssueView):
    url_name = 'issue.ask-fetch'
    ajax_only = True
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        """
        Get the issue and add a new job to fetch it
        """
        try:
            issue = self.current_issue
        except Exception:
            messages.error(self.request,
                'The issue from <strong>%s</strong> you asked to fetch from Github could doesn\'t exist anymore!' % (
                    self.repository))
        else:
            self.add_job(issue)

        return self.render_to_response(context={})

    def add_job(self, issue):
        """
        Add a job to fetch the issue and inform the current user
        """
        identifier = '%s#%s' % (self.repository.id, issue.number)
        user_pk_str = str(self.request.user.id)
        users_to_inform = set(user_pk_str)
        tries = 0
        while True:
            # add a job to fetch the issue, informing
            job = FetchIssueByNumber.add_job(
                    identifier=identifier,
                    priority=5,  # higher priority
                    gh=self.request.user.get_connection(),
                    users_to_inform=users_to_inform,
            )
            # we may already have this job queued
            if user_pk_str in job.users_to_inform.smembers():
                # if it has already the correct user to inform, we're good
                break
            else:
                # the job doesn't have the correct user to inform
                if tries >= 10:
                    # we made enough tries, stop now
                    messages.error(self.request,
                        'The %s <strong>#%d</strong> from <strong>%s</strong> you asked to fetch from Github couldn\'t be fetched!' % (
                            issue.type, issue.number, self.repository.full_name))
                    return
                # ok let's cancel this job and try again
                tries += 1
                job.status.hset('c')
                job.queued.delete()
                # adding users we already have to inform to the new job
                existing_users = job.users_to_inform.smembers()
                if existing_users:
                    users_to_inform.update(existing_users)

        # ok the job was added, tell to the user...
        messages.success(self.request,
            'The %s <strong>#%d</strong> from <strong>%s</strong> you asked to fetch from Github will be updated soon' % (
                issue.type, issue.number, self.repository.full_name))

    def get_template_names(self):
        """
        We'll only display messages to the user
        """
        return ['front/messages.html']


class CreatedIssueView(IssueView):
    url_name = 'issue.created'

    def redirect_to_created_issue(self, wait_if_failure=0):
        """
        If the issue doesn't exists anymore, a new one may have been created by
        dist_edit, so redirect to the new one. Wait a little if no issue found.
        """
        try:
            job = IssueCreateJob.get(identifier=self.kwargs['issue_pk'])
            issue = Issue.objects.get(pk=job.created_pk.hget())
        except:
            if wait_if_failure > 0:
                sleep(0.1)
                return self.redirect_to_created_issue(wait_if_failure-0.1)
            else:
                raise Http404
        else:
            return HttpResponsePermanentRedirect(issue.get_absolute_url())

    def get(self, request, *args, **kwargs):
        """
        `dist-edit` delete the issue create by the user to replace it by the
        one created on github that we fetched back, but it has a new PK, saved
        in the job, so use it to get the new issue and redirect it back to its
        final url.
        Redirect to the final url too if with now have a number
        """
        try:
            issue = self.current_issue
        except Http404:
            # ok, deleted/recreated by dist_edit...
            return self.redirect_to_created_issue(wait_if_failure=0.3)
        else:
            if issue.number:
                return HttpResponsePermanentRedirect(issue.get_absolute_url())

        try:
            return super(CreatedIssueView, self).get(request, *args, **kwargs)
        except Http404:
            # existed just before, but not now, just deleted/recreated by dist_edit
            return self.redirect_to_created_issue(wait_if_failure=0.3)

    @cached_property
    def current_issue(self):
        """
        Based on the informations from the url, try to return the wanted issue
        """
        issue = None
        if 'issue_pk' in self.kwargs:
            qs = self.repository.issues.ready().select_related(
                'user',  'assignee', 'closed_by', 'milestone',
            ).prefetch_related(
                'labels__label_type'
            )
            issue = get_object_or_404(qs, pk=self.kwargs['issue_pk'])
        return issue


class SimpleAjaxIssueView(WithAjaxRestrictionViewMixin, IssueView):
    """
    A base class to fetch some parts of an issue via ajax.
    If not directly overriden, the template must be specified when using this
    view in urls.py
    """
    ajax_only = True

    def get_context_data(self, **kwargs):
        """
        Add the issue and its files in the context
        """
        context = super(IssueView, self).get_context_data(**kwargs)

        current_issue = self.current_issue

        context['current_issue'] = current_issue
        context['current_issue_edit_level'] = self.get_edit_level(current_issue)

        return context


class FilesAjaxIssueView(SimpleAjaxIssueView):
    """
    Override SimpleAjaxIssueView to add comments in files (entry points)
    """
    ajax_template_name = 'front/repository/issues/code/include_issue_files.html'

    def get_context_data(self, **kwargs):
        context = super(FilesAjaxIssueView, self).get_context_data(**kwargs)
        context['entry_points_dict'] = self.get_entry_points_dict(
                                    context['current_issue'].all_entry_points)
        return context


class CommitViewMixin(object):
    """
    A simple mixin with a `commit` property to get the commit matching the sha
    in the url
    """
    issue_related_name = 'commit__issues'
    repository_related_name = 'commit__issues__repository'

    def get_queryset(self):
        """
        Return a queryset based on the current repository and allowed rights.
        Override the one from DependsOnIssueViewMixin to only depends on the
        repository, not the issue, to allow managing comment on commits not in
        the current issue.
        """
        return self.model._default_manager.filter(repository=self.repository)

    def set_comment_urls(self, comment, issue, kwargs=None):
        if not kwargs:
            kwargs = issue.get_reverse_kwargs()
            kwargs['commit_sha'] = self.commit.sha

        kwargs = kwargs.copy()
        kwargs['comment_pk'] = comment.id
        comment.get_edit_url = reverse_lazy('front:repository:' + CommitCommentEditView.url_name, kwargs=kwargs)
        comment.get_delete_url = reverse_lazy('front:repository:' + CommitCommentDeleteView.url_name, kwargs=kwargs)
        comment.get_absolute_url = reverse_lazy('front:repository:' + CommitCommentView.url_name, kwargs=kwargs)

    @cached_property
    def commit(self):
        return get_object_or_404(self.repository.commits, sha=self.kwargs['commit_sha'])

    def get_context_data(self, **kwargs):
        context = super(CommitViewMixin, self).get_context_data(**kwargs)
        context['current_commit'] = self.commit
        return context


class CommitAjaxIssueView(CommitViewMixin, SimpleAjaxIssueView):
    """
    Override SimpleAjaxIssueView to add commit and its comments
    """

    url_name = 'issue.commit'
    ajax_template_name = 'front/repository/issues/code/include_commit_files.html'

    issue_related_name = 'commit__issues'
    repository_related_name = 'commit__issues__repository'

    def get_context_data(self, **kwargs):
        context = super(CommitAjaxIssueView, self).get_context_data(**kwargs)
        context['current_commit'] = self.commit

        entry_points = self.commit.all_entry_points

        # force urls, as we are in an issue
        kwargs = context['current_issue'].get_reverse_kwargs()
        kwargs['commit_sha'] = self.commit.sha
        for entry_point in entry_points:
            for comment in entry_point.comments.all():
                self.set_comment_urls(comment, context['current_issue'], kwargs)

        context['entry_points_dict'] = self.get_entry_points_dict(entry_points)

        try:
            context['final_entry_point'] = [ep for ep in entry_points if ep.path is None][0]
        except IndexError:
            context['final_entry_point'] = None

        context['commit_comment_create_url'] = \
            context['current_issue'].commit_comment_create_url().replace('0' * 40, self.commit.sha)

        return context


class BaseIssueEditViewSubscribed(LinkedToRepositoryFormViewMixin):
    model = Issue
    allowed_rights = SUBSCRIPTION_STATES.READ_RIGHTS
    http_method_names = [u'get', u'post']
    ajax_only = True

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        filters = {
            'number': self.kwargs['issue_number'],
        }

        return queryset.get(**filters)

    def get_success_url(self):
        return self.object.get_absolute_url()


class IssueEditFieldMixin(BaseIssueEditViewSubscribed, UpdateView):
    field = None
    job_model = None
    url_name = None
    form_class = None
    template_name = 'front/one_field_form.html'

    def form_valid(self, form):
        """
        Override the default behavior to add a job to update the issue on the
        github side
        """
        response = super(IssueEditFieldMixin, self).form_valid(form)
        value = self.get_final_value(form.cleaned_data[self.field])

        self.job_model.add_job(self.object.pk,
                          gh=self.request.user.get_connection(),
                          value=value)

        messages.success(self.request, self.get_success_user_message(self.object))

        return response

    def get_final_value(self, value):
        """
        Return the value that will be pushed to githubs
        """
        return value

    def form_invalid(self, form):
        return self.render_form_errors_as_messages(form, show_fields=False)

    def get_success_user_message(self, issue):
        return u"""The <strong>%s</strong> for the %s <strong>#%d</strong> will
                be updated shortly""" % (self.field, issue.type, issue.number)

    def get_context_data(self, **kwargs):
        context = super(IssueEditFieldMixin, self).get_context_data(**kwargs)
        context['form_action'] = self.object.edit_field_url(self.field)
        context['form_classes'] = "issue-edit-field issue-edit-%s" % self.field
        return context

    def get_object(self, queryset=None):
        # use current self.object if we have it
        if getattr(self, 'object', None):
            return self.object
        return super(IssueEditFieldMixin, self).get_object(queryset)

    def current_job(self):
        self.object = self.get_object()
        try:
            job = self.job_model.collection(identifier=self.object.id, queued=1).instances()[0]
        except IndexError:
            return None
        else:
            return job

    def dispatch(self, request, *args, **kwargs):
        current_job = self.current_job()

        if current_job:
            for i in range(0, 3):
                sleep(0.1)  # wait a little, it may be fast
                current_job = self.current_job()
                if not current_job:
                    break

            if current_job:
                who = current_job.gh_args.hget('username')
                return self.render_not_editable(request, who)

        return super(IssueEditFieldMixin, self).dispatch(request, *args, **kwargs)

    def render_not_editable(self, request, who):
        if who == request.user.username:
            who = 'yourself'
        messages.warning(request, self.get_not_editable_user_message(self.object, who))
        return render(self.request, 'front/messages.html')

    def get_not_editable_user_message(self, issue, who):
        return u"""The <strong>%s</strong> for the %s <strong>#%d</strong> is
                currently being updated (asked by <strong>%s</strong>), please
                wait a few seconds and retry""" % (
                                    self.field, issue.type, issue.number, who)


class IssueEditState(LinkedToUserFormViewMixin, IssueEditFieldMixin):
    field = 'state'
    job_model = IssueEditStateJob
    url_name = 'issue.edit.state'
    form_class = IssueStateForm
    http_method_names = [u'post']

    def get_success_user_message(self, issue):
        new_state = 'reopened' if issue.state == 'open' else 'closed'
        return u'The %s <strong>#%d</strong> will be %s shortly' % (
                                            issue.type, issue.number, new_state)

    def get_not_editable_user_message(self, issue, who):
        new_state = 'reopened' if issue.state == 'open' else 'closed'
        return u"""The %s <strong>#%d</strong> is currently being %s (asked by
                <strong>%s</strong>), please wait a few seconds and retry""" % (
                                    issue.type, issue.number, new_state, who)


class IssueEditTitle(IssueEditFieldMixin):
    field = 'title'
    job_model = IssueEditTitleJob
    url_name = 'issue.edit.title'
    form_class = IssueTitleForm


class IssueEditBody(IssueEditFieldMixin):
    field = 'body'
    job_model = IssueEditBodyJob
    url_name = 'issue.edit.body'
    form_class = IssueBodyForm
    template_name = 'front/one_field_form_real_buttons.html'


class IssueEditMilestone(IssueEditFieldMixin):
    field = 'milestone'
    job_model = IssueEditMilestoneJob
    url_name = 'issue.edit.milestone'
    form_class = IssueMilestoneForm

    def get_final_value(self, value):
        """
        Return the value that will be pushed to githubs
        """
        return value.number if value else ''


class IssueEditAssignee(IssueEditFieldMixin):
    field = 'assignee'
    job_model = IssueEditAssigneeJob
    url_name = 'issue.edit.assignee'
    form_class = IssueAssigneeForm

    def get_final_value(self, value):
        """
        Return the value that will be pushed to githubs
        """
        return value.username if value else ''


class IssueEditLabels(IssueEditFieldMixin):
    field = 'labels'
    job_model = IssueEditLabelsJob
    url_name = 'issue.edit.labels'
    form_class = IssueLabelsForm

    def get_final_value(self, value):
        """
        Return the value that will be pushed to githubs. We encode the list of
        labels as json to be stored in the job single field
        """
        labels = [l.name for l in value] if value else []
        return json.dumps(labels)

    def get_not_editable_user_message(self, issue, who):
        return u"""The <strong>%s</strong> for the %s <strong>#%d</strong> are
                currently being updated (asked by <strong>%s</strong>), please
                wait a few seconds and retry""" % (
                                    self.field, issue.type, issue.number, who)


class IssueCreateView(LinkedToUserFormViewMixin, BaseIssueEditViewSubscribed, CreateView):
    url_name = 'issue.create'
    template_name = 'front/repository/issues/create.html'
    ajax_only = False

    def get_form_class(self):
        """
        Not the same form depending of the rights
        """
        if self.subscription.state in SUBSCRIPTION_STATES.WRITE_RIGHTS:
            return IssueCreateFormFull
        return IssueCreateForm

    def get_success_url(self):
        if self.object.number:
            return super(IssueCreateView, self).get_success_url()
        return self.object.get_created_url()

    def form_valid(self, form):
        """
        Override the default behavior to add a job to create the issue on the
        github side
        """
        response = super(IssueCreateView, self).form_valid(form)

        # create the job
        job = IssueCreateJob.add_job(self.object.pk,
                               gh=self.request.user.get_connection())

        # try to wait just a little for the job to be done
        for i in range(0, 3):
            sleep(0.1)  # wait a little, it may be fast
            if job.status.hget() == STATUSES.SUCCESS:
                self.object = Issue.objects.get(pk=job.created_pk.hget())
                break

        if self.object.number:
            # if job done, it would have create the message itself
            # and we want to be sure to redirect to the good url now that the
            # issue was created
            return HttpResponseRedirect(self.get_success_url())
        else:
            messages.success(self.request, self.get_success_user_message(self.object))
            return response

    def get_success_user_message(self, issue):
        title = issue.title
        if len(title) > 30:
            title = title[:30] + u'…'
        return u"""The %s "<strong>%s</strong>" will
                be created shortly""" % (issue.type, title)


class BaseIssueCommentView(WithAjaxRestrictionViewMixin, DependsOnIssueViewMixin, DetailView):
    context_object_name = 'comment'
    pk_url_kwarg = 'comment_pk'
    http_method_names = ['get']
    ajax_only = True

    def get_context_data(self, **kwargs):
        context = super(BaseIssueCommentView, self).get_context_data(**kwargs)

        context.update({
            'use_current_user': False,
            'include_create_form': self.request.GET.get('include_form', False),
        })

        return context

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()

        pk = self.kwargs['comment_pk']
        object = None

        try:
            object = queryset.get(pk=pk)
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
                        object = queryset.get(pk=created_pk)
                        break
                    sleep(0.1)

        if not object:
            raise Http404("No comment found matching the query")

        return object


class IssueCommentView(BaseIssueCommentView):
    url_name = 'issue.comment'
    model = IssueComment
    template_name = 'front/repository/issues/comments/include_issue_comment.html'
    job_model = IssueCommentEditJob


class PullRequestCommentView(BaseIssueCommentView):
    url_name = 'issue.pr_comment'
    model = PullRequestComment
    template_name = 'front/repository/issues/comments/include_code_comment.html'
    job_model = PullRequestCommentEditJob

    def get_context_data(self, **kwargs):
        context = super(PullRequestCommentView, self).get_context_data(**kwargs)

        context.update({
            'entry_point': self.object.entry_point,
        })

        return context


class CommitCommentView(CommitViewMixin, BaseIssueCommentView):
    url_name = 'issue.commit_comment'
    model = CommitComment
    template_name = 'front/repository/issues/comments/include_commit_comment.html'
    job_model = CommitCommentEditJob

    repository_related_name = 'commit__issues__repository'

    def get_object(self, *args, **kwargs):
        obj = super(CommitCommentView, self).get_object(*args, **kwargs)
        if obj:
            # force urls, as we are in an issue
            self.set_comment_urls(obj, self.issue)
        return obj

    def get_context_data(self, **kwargs):
        context = super(CommitCommentView, self).get_context_data(**kwargs)

        context.update({
            'current_commit': self.commit,
            'entry_point': self.object.entry_point,
        })

        return context


class IssueCommentEditMixin(object):
    model = IssueComment
    job_model = IssueCommentEditJob


class PullRequestCommentEditMixin(object):
    model = PullRequestComment
    job_model = PullRequestCommentEditJob


class CommitCommentEditMixin(LinkedToCommitFormViewMixin, CommitViewMixin):
    model = CommitComment
    job_model = CommitCommentEditJob

    def obj_message_part(self):
        return 'commit <strong>#%s</strong> (%s <strong>#%s</strong>)' % (
            self.commit.sha[:7], self.issue.type, self.issue.number)

    def get_success_url(self):
        kwargs = self.issue.get_reverse_kwargs()
        kwargs['commit_sha'] = self.commit.sha
        kwargs['comment_pk'] = self.object.id
        return reverse_lazy('front:repository:' + CommitCommentView.url_name, kwargs=kwargs)

    def get_object(self, *args, **kwargs):
        obj = super(CommitCommentEditMixin, self).get_object(*args, **kwargs)
        if obj:
            # force urls, as we are in an issue
            self.set_comment_urls(obj, self.issue)
        return obj


class BaseCommentEditMixin(LinkedToUserFormViewMixin, LinkedToIssueFormViewMixin):
    ajax_only = True
    http_method_names = ['get', 'post']
    edit_mode = None

    def obj_message_part(self):
        return '%s <strong>#%s</strong>' % (self.issue.type, self.issue.number)

    def form_valid(self, form):
        """
        Override the default behavior to add a job to create the comment on the
        github side
        """
        response = super(BaseCommentEditMixin, self).form_valid(form)

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


class BaseCommentCreateView(BaseCommentEditMixin, CreateView):
    edit_mode = 'create'
    verb = 'created'
    http_method_names = ['post']

    def get_success_url(self):
        url = super(BaseCommentCreateView, self).get_success_url()
        return url + '?include_form=1'


class IssueCommentCreateView(IssueCommentEditMixin, BaseCommentCreateView):
    url_name = 'issue.comment.create'
    form_class = IssueCommentCreateForm


class CommentWithEntryPointCreateViewMixin(BaseCommentCreateView):
    null_path_allowed = False
    sha_field = ''

    def get_diff_hunk(self, file, position):
        if not file:
            return ''
        return'\n'.join(file.patch.split('\n')[:position+1])

    @property
    def parent_object(self):
        raise NotImplementedError()

    def get_entry_point(self, sha=None):
        obj = self.parent_object

        if 'entry_point_id' in self.request.POST:
            entry_point_id = self.request.POST['entry_point_id']
            self.entry_point = getattr(obj, self.entry_point_related_name).get(id=entry_point_id)
        else:
            # get and check entry-point params

            if self.request.POST.get('position', None) is None and self.null_path_allowed:
                position = None
            elif len(self.request.POST['position']) < 10:
                position = int(self.request.POST['position'])
            else:
                raise KeyError('position')

            if sha is None:
                if len(self.request.POST['sha']) == 40:
                    sha = self.request.POST['sha']
                else:
                    raise KeyError('sha')

            if self.request.POST.get('path', None) is None and self.null_path_allowed:
                path = None
                file = None
            else:
                path = self.request.POST['path']
                try:
                    file = obj.files.get(path=path)
                except obj.files.model.DoesNotExist:
                    file = None

            # get or create the entry_point
            now = datetime.utcnow()
            self.entry_point, created = getattr(obj, self.entry_point_related_name)\
                .get_or_create(**{
                    self.sha_field: sha,
                    'path': path,
                    self.position_field: position,
                    'defaults': {
                        'repository': obj.repository,
                        'commit_sha': sha,
                        'position': position,
                        'created_at': now,
                        'updated_at': now,
                        'diff_hunk': self.get_diff_hunk(file, position)
                    }
                })

    def post(self, *args, **kwargs):
        self.entry_point = None
        try:
            self.get_entry_point()
        except Exception:
            return self.http_method_not_allowed(self.request)
        return super(CommentWithEntryPointCreateViewMixin, self).post(*args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(CommentWithEntryPointCreateViewMixin, self).get_form_kwargs()
        kwargs['entry_point'] = self.entry_point
        return kwargs


class PullRequestCommentCreateView(PullRequestCommentEditMixin, CommentWithEntryPointCreateViewMixin):
    url_name = 'issue.pr_comment.create'
    form_class = PullRequestCommentCreateForm

    null_path_allowed = False
    sha_field = 'original_commit_sha'
    position_field = 'original_position'
    entry_point_related_name = 'pr_comments_entry_points'

    @property
    def parent_object(self):
        return self.issue


class CommitCommentCreateView(CommitCommentEditMixin, CommentWithEntryPointCreateViewMixin):
    url_name = 'issue.commit_comment.create'
    form_class = CommitCommentCreateForm

    null_path_allowed = True
    sha_field = 'commit_sha'
    position_field = 'position'
    entry_point_related_name = 'commit_comments_entry_points'

    @property
    def parent_object(self):
        return self.commit

    def get_entry_point(self):
        return super(CommitCommentCreateView, self).get_entry_point(self.commit.sha)

    def get_success_url(self):
        url = super(CommitCommentCreateView, self).get_success_url()
        return url + '?include_form=1'


class CommentCheckRightsMixin(object):

    def get_object(self, queryset=None):
        """
        Early check that the user has enough rights to edit this comment
        """
        obj = super(CommentCheckRightsMixin, self).get_object(queryset)
        if self.subscription.state not in SUBSCRIPTION_STATES.WRITE_RIGHTS:
            if obj.user != self.request.user:
                raise Http404
        return obj


class BaseCommentEditView(CommentCheckRightsMixin, BaseCommentEditMixin, UpdateView):
    edit_mode = 'update'
    verb = 'updated'
    context_object_name = 'comment'
    pk_url_kwarg = 'comment_pk'
    template_name = 'front/repository/issues/comments/include_comment_edit.html'


class IssueCommentEditView(IssueCommentEditMixin, BaseCommentEditView):
    url_name = 'issue.comment.edit'
    form_class = IssueCommentEditForm


class PullRequestCommentEditView(PullRequestCommentEditMixin, BaseCommentEditView):
    url_name = 'issue.pr_comment.edit'
    form_class = PullRequestCommentEditForm


class CommitCommentEditView(CommitCommentEditMixin, BaseCommentEditView):
    url_name = 'issue.commit_comment.edit'
    form_class = CommitCommentEditForm


class BaseCommentDeleteView(BaseCommentEditView):
    edit_mode = 'delete'
    verb = 'deleted'
    template_name = 'front/repository/issues/comments/include_comment_delete.html'


class IssueCommentDeleteView(IssueCommentEditMixin, BaseCommentDeleteView):
    url_name = 'issue.comment.delete'
    form_class = IssueCommentDeleteForm


class PullRequestCommentDeleteView(PullRequestCommentEditMixin, BaseCommentDeleteView):
    url_name = 'issue.pr_comment.delete'
    form_class = PullRequestCommentDeleteForm


class CommitCommentDeleteView(CommitCommentEditMixin, BaseCommentDeleteView):
    url_name = 'issue.commit_comment.delete'
    form_class = CommitCommentDeleteForm
