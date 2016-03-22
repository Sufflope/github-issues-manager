import json
from collections import OrderedDict

from async_messages import messages
from django.core.urlresolvers import reverse
from django.http.response import HttpResponse, HttpResponseRedirect
from django.utils.dateformat import format
from django.utils.functional import cached_property
from django.views.generic.base import TemplateView
from django.views.generic.edit import UpdateView

from gim.core.models import Issue, GithubNotification
from gim.front.mixins.views import BaseIssuesView

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
    url_name = 'front:github-notifications:home'

    issue_item_template_name = 'front/dashboard/include_issue_item_for_cache.html'

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

    reasons = {
        'assign': {
            'name': u'assigned',
            'description': u'issues you were assigned to',
            'description_one': u'you were assigned to this issue',
        },
        'author': {
            'name': u'authored',
            'description': u'issues you authored',
            'description_one': u'you are the author of this issue',
        },
        'comment': {
            'name': u'commented',
            'description': u'issues you commented',
            'description_one': u'you commented on this issue',
        },
        'manual': {
            'name': u'manual',
            'description': u'issues you subscribed to',
            'description_one': u'you manually subscribed to this issue',
        },
        'mention': {
            'name': u'mentioned',
            'description': u'issues you were mentioned in',
            'description_one': u'you were mentioned in this issue',
        },
        'state_change': {
            'name': u'changed state',
            'description': u'issues you changed the state',
            'description_one': u'you changed the state of this issue',
        },
        'subscribed': {
            'name': u'subscribed',
            'description': u'issues in one of your watched repositories',
            'description_one': u'you watch the repository this issue is in',
        },
        'team_mention': {
            'name': u'team',
            'description': u'issues you were, as part of a team, mentioned in',
            'description_one': u'you are in a team that were mentioned in this issue',
        },
    }


    def get_base_queryset(self):
        return Issue.objects.filter(githubnotification__user=self.request.user,
                                    githubnotification__ready=True).distinct()

    def get_base_url(self):
        return reverse(self.url_name)

    @classmethod
    def get_default_url(cls):
        url = reverse(cls.url_name)
        if cls.default_qs:
            url += '?' + cls.default_qs
        return url

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
            'reasons': self.reasons,
        })

        context['sorts']['notification'] = {
            'name': u'notification date',
            'description': u'date the notification last appeared',
        }

        if context['issues_filter']['objects'].get('group_by_field') == 'githubnotification__repository':
            context['force_hide_repositories'] = True

        return context


class GithubNotificationEditView(UpdateView):
    model = GithubNotification
    fields = ['unread', 'subscribed']
    http_method_names = ['post']
    pk_url_kwarg = 'notif_id'

    def get_queryset(self):
        return self.request.user.github_notifications.all()

    def get_form_kwargs(self):
        kwargs = super(GithubNotificationEditView, self).get_form_kwargs()
        kwargs['data'] = {
            'unread': not bool(self.request.POST.get('read')),
            'subscribed': bool(self.request.POST.get('active')),
        }

        return kwargs

    def get_success_url(self):
        return GithubNotifications.get_default_url()

    def get_ajax_reponse_value(self, status, error_msg=None):
        data = {
            'status': status,
            'values': {
                'read': not self.object.unread,
                'active': self.object.subscribed,
            },
            'count': self.request.user.unread_notifications_count,
            'last': self.request.user.last_unread_notification_date,
        }
        if data['last']:
            data['last'] = format(data['last'], 'r')
        if error_msg:
            data['error_msg'] = error_msg
        return json.dumps(data)

    def form_valid(self, form):
        self.object = form.save()

        from gim.core.tasks.githubuser import GithubNotificationEditJob
        GithubNotificationEditJob.add_job(self.object.pk, gh=self.request.user.get_connection())

        if self.request.is_ajax():
            return HttpResponse(self.get_ajax_reponse_value('OK'), content_type='application/json')

        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        error_msg = 'Internal problem: we were unable to update your notification (on %s, issue #%d)' % (
            self.object.repository, self.object.issue.number)

        if self.request.is_ajax():
            return HttpResponse(
                self.get_ajax_reponse_value('KO', error_msg=error_msg),
                content_type='application/json',
            )

        messages.error(self.request.user, error_msg)

        return HttpResponseRedirect(self.get_success_url())
