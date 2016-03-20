from collections import OrderedDict

from django.utils.functional import cached_property
from django.views.generic import TemplateView
from django.core.urlresolvers import reverse_lazy, reverse

from gim.activity.limpyd_models import RepositoryActivity
from gim.core.models import Issue

from gim.front.activity.views import ActivityViewMixin
from gim.front.mixins.views import WithSubscribedRepositoriesViewMixin, DeferrableViewPart
from gim.front.views import BaseIssuesView


class DashboardActivityPart(ActivityViewMixin, DeferrableViewPart, WithSubscribedRepositoriesViewMixin, TemplateView):
    part_url = reverse_lazy('front:dashboard:activity')
    template_name = 'front//dashboard/include_activity.html'
    deferred_template_name = 'front/dashboard/include_activity_deferred.html'

    repository_pks = None

    def inherit_from_view(self, view):
        super(DashboardActivityPart, self).inherit_from_view(view)
        self.repository_pks = view.repository_pks

    def get_pks(self):
        return [s.repository_id for s in self.subscriptions]

    def get_context_data(self, *args, **kwargs):
        context = super(DashboardActivityPart, self).get_context_data(**kwargs)

        activity, has_more = RepositoryActivity.get_for_repositories(
                                    pks=self.repository_pks or self.get_pks(),
                                    **self.activity_args
                                )
        context.update({
            'activity': RepositoryActivity.load_objects(activity),
            'more_activity': has_more,
            'activity_mode': 'repositories',
        })

        return context


class DashboardHome(WithSubscribedRepositoriesViewMixin, TemplateView):
    template_name = 'front/dashboard/home.html'
    url_name = 'front:dashboard:home'

    def get_context_data(self, **kwargs):
        context = super(DashboardHome, self).get_context_data(**kwargs)

        repositories = context['subscribed_repositories']
        subscription_by_repo_id = dict((s.repository_id, s) for s in self.subscriptions)

        for repository in repositories:
            repository.user_counts_open = repository.counters.get_user_counts(self.request.user.pk)

        context['subscription_by_repo_id'] = subscription_by_repo_id

        self.repository_pks = subscription_by_repo_id.keys()
        context['parts'] = {
            'activity': DashboardActivityPart().get_as_deferred(self),
        }

        return context

GROUP_BY_CHOICES = dict(BaseIssuesView.GROUP_BY_CHOICES, **{group_by[0]: group_by for group_by in [
    ('unread', {
        'field': 'githubnotification__unread',
        'name': 'read status',
        'description': u'is the notification read or not',
    }),
    ('active', {
        'field': 'githubnotification__subscribed',
        'name': 'active status',
        'description': u'is the issue actively followed',
    }),
    ('reason', {
        'field': 'githubnotification__reason',
        'name': 'notification reason',
        'description': u'why were you notified',
    }),
    ('repository', {
        'field': 'githubnotification__repository',
        'name': 'repository',
        'description': u'repository hosting the notified issue',
    }),
]})


class GithubNotifications(BaseIssuesView, TemplateView):

    template_name = 'front/dashboard/github_notifications.html'
    url_name = 'front:dashboard:github-notifications'

    default_qs = 'read=no&sort=notification&direction=desc'

    GROUP_BY_CHOICES = GROUP_BY_CHOICES
    allowed_group_by = OrderedDict(GROUP_BY_CHOICES[name] for name in [
        'unread',
        'reason',
        'state',
        'pr',
        'repository',
        'active',
    ])

    allowed_sort_fields = ['created', 'updated', 'notification']

    allowed_reads = ['no', 'yes']
    allowed_actives = ['no', 'yes']
    allowed_reasons = ['assign', 'author', 'comment', 'manual', 'mention', 'state_change', 'subscribed', 'team_mention']

    def get_base_queryset(self):
        return Issue.objects.filter(githubnotification__user=self.request.user)

    def get_base_url(self):
        return reverse(self.url_name)

    @cached_property
    def github_notifications(self):
        return self.request.user.github_notifications.all().select_related('repository__owner')

    @cached_property
    def subscriptions(self):
        return self.request.user.subscriptions.filter(
            repository_id__in=set(n.repository_id for n in self.github_notifications)
        )

    def finalize_issues(self, issues, context):
        """
        Return a final list of issues usable in the view.
        Actually simply add the notification to each issue, the subscription to the repositories,
        and the group field if any
        """

        issues, total_count, limit_reached = super(GithubNotifications, self).finalize_issues(issues, context)

        notifications = {n.issue_id: n for n in self.github_notifications}
        subscriptions = {s.repository_id: s for s in self.subscriptions}
        for issue in issues:
            issue.github_notification = notifications.get(issue.pk)
            issue.repository.subscription = subscriptions.get(issue.repository_id)

        group_by_field = context['issues_filter']['objects'].get('group_by_field', None)
        if group_by_field and group_by_field.startswith('githubnotification__'):
            field = group_by_field[20:]
            for issue in issues:
                setattr(issue, group_by_field, getattr(issue.github_notification, field))

        return issues, total_count, limit_reached

    def _get_read(self, qs_parts):
        """
        Return the valid "read status" flag to use, or None
        """
        read = qs_parts.get('read', None)
        if read in self.allowed_reads:
            return True if read == 'yes' else False
        return None

    def _get_reason(self, qs_parts):
        """
        Return the valid "read status" flag to use, or None
        """
        reason = qs_parts.get('reason', None)
        if reason in self.allowed_reasons:
            return reason
        return None

    def _get_active(self, qs_parts):
        """
        Return the valid "active status" flag to use, or None
        """
        active = qs_parts.get('active', None)
        if active in self.allowed_actives:
            return True if active == 'yes' else False
        return None

    @cached_property
    def allowed_repositories(self):
        repositories = set(n.repository.full_name for n in self.github_notifications)
        return sorted(repositories, key=lambda full_name: full_name.lower())

    def _get_repository(self, qs_parts):
        repository = qs_parts.get('repository', None)
        if repository in self.allowed_repositories:
            return repository
        return None

    def _get_sort_field(self, sort):
        if sort == 'notification':
            return 'githubnotification__updated_at'
        return super(GithubNotifications, self)._get_sort_field(sort)

    def get_issues_for_context(self, context):
        """
        In addition to parent call, apply notification filtering
        """
        qs_parts = self.get_qs_parts(context)
        queryset, filter_context = super(GithubNotifications, self).get_issues_for_context(context)
        qs_filters = filter_context['qs_filters']
        filter_objects = filter_context['filter_objects']

        query_filters = {}

        # filter by unread status
        is_read = self._get_read(qs_parts)
        if is_read is not None:
            qs_filters['read'] = self.allowed_reads[is_read]
            filter_objects['read'] = is_read
            query_filters['githubnotification__unread'] = not is_read

        # filter by subscribed status
        is_active = self._get_active(qs_parts)
        if is_active is not None:
            qs_filters['active'] = self.allowed_actives[is_active]
            filter_objects['active'] = is_active
            query_filters['githubnotification__subscribed'] = is_active

        # filter by reason
        reason = self._get_reason(qs_parts)
        if reason is not None:
            qs_filters['reason'] = filter_objects['reason'] = \
                query_filters['githubnotification__reason'] = reason

        # filter by repository
        repository = self._get_repository(qs_parts)
        if repository is not None:
            qs_filters['repository'] = filter_objects['repository'] = repository
            owner_name, repo_name = repository.split('/')
            query_filters['githubnotification__repository__name'] = repo_name
            query_filters['githubnotification__repository__owner__username'] = owner_name

        # apply the new filter
        queryset = queryset.filter(**query_filters)

        return queryset, filter_context

    def get_context_data(self, **kwargs):
        """
        Add readable reasons and sorts
        """
        context = super(GithubNotifications, self).get_context_data(**kwargs)

        context.update({
            'reasons': {
                'assign': {
                    'name': u'assigned',
                    'description': u'issues you were assigned to',
                },
                'author': {
                    'name': u'authored',
                    'description': u'issues you authored',
                },
                'comment': {
                    'name': u'commented',
                    'description': u'issues you commented',
                },
                'manual': {
                    'name': u'manual',
                    'description': u'issues you subscribed to',
                },
                'mention': {
                    'name': u'mentioned',
                    'description': u'issues you were mentioned in',
                },
                'state_change': {
                    'name': u'changed state',
                    'description': u'issues you changed the state',
                },
                'subscribed': {
                    'name': u'subscribed',
                    'description': u'issues on your watched repositories',
                },
                'team_mention': {
                    'name': u'team',
                    'description': u'issues you were, as part of a team, mentioned in',
                },
            }
        })

        context['sorts']['notification'] = {
            'name': u'notification date',
            'description': u'date the notification last appeared',
        }

        if context['issues_filter']['objects'].get('group_by_field') == 'githubnotification__repository':
            context['force_hide_repositories'] = True

        return context
