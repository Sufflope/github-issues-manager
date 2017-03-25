import json
from collections import OrderedDict

from async_messages import messages

from django.db import models
from django.core.urlresolvers import reverse
from django.http.response import HttpResponse, HttpResponseRedirect
from django.utils.dateformat import format
from django.utils.functional import cached_property
from django.views.generic.base import TemplateView
from django.views.generic.edit import UpdateView

from gim.core.models import Issue, GithubNotification
from gim.front.mixins.views import BaseIssuesView, BaseIssuesFilters, WithAjaxRestrictionViewMixin


GROUP_BY_CHOICES = dict(BaseIssuesFilters.GROUP_BY_CHOICES, **{group_by[0]: group_by for group_by in [
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
        'field': 'repository',
        'name': 'repository',
        'description': u'repository hosting the notified issue',
    }),
]})

SORT_CHOICES = dict(BaseIssuesFilters.SORT_CHOICES, **{sort[0]: sort for sort in [
    ('notification', {
        'name': u'notification date',
        'description': u'date the notification last appeared',
    }),
]})


class GithubNotificationsFilters(BaseIssuesFilters):

    filters_template_name = 'front/github_notifications/include_filters.html'

    GROUP_BY_CHOICES = GROUP_BY_CHOICES
    allowed_group_by = OrderedDict(GROUP_BY_CHOICES[name] for name in [
        'unread',
        'reason',
        'state',
        'pr',
        'repository',
        'active',
    ])

    SORT_CHOICES = SORT_CHOICES
    allowed_sort = OrderedDict(SORT_CHOICES[name] for name in [
        'created',
        'updated',
        'notification',
    ])

    allowed_reads = ['no', 'yes']
    allowed_actives = ['no', 'yes']
    allowed_reasons = ['assign', 'author', 'comment', 'manual', 'mention', 'state_change', 'subscribed', 'team_mention']

    reasons = OrderedDict([
        ('assign', {
            'name': u'assigned',
            'description': u'issues you were assigned to',
            'description_one': u'you were assigned to this issue',
        }),
        ('author', {
            'name': u'authored',
            'description': u'issues you authored',
            'description_one': u'you are the author of this issue',
        }),
        ('comment', {
            'name': u'commented',
            'description': u'issues you commented',
            'description_one': u'you commented on this issue',
        }),
        ('manual', {
            'name': u'manual',
            'description': u'issues you subscribed to',
            'description_one': u'you manually subscribed to this issue',
        }),
        ('mention', {
            'name': u'mentioned',
            'description': u'issues you were mentioned in',
            'description_one': u'you were mentioned in this issue',
        }),
        ('state_change', {
            'name': u'changed state',
            'description': u'issues you changed the state',
            'description_one': u'you changed the state of this issue',
        }),
        ('subscribed', {
            'name': u'subscribed',
            'description': u'issues in one of your watched repositories',
            'description_one': u'you watch the repository this issue is in',
        }),
        ('team_mention', {
            'name': u'team',
            'description': u'issues you were, as part of a team, mentioned in',
            'description_one': u'you are in a team that were mentioned in this issue',
        }),
    ])

    def __init__(self):
        super(GithubNotificationsFilters, self).__init__()
        self.read_filter = None

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
    def github_notifications(self):
        return self.request.user.github_notifications.all().select_related('repository__owner')

    @cached_property
    def allowed_repositories(self):
        if self.read_filter is None:
            repositories = set(n.repository.full_name for n in self.github_notifications)
        else:
            repositories = set(n.repository.full_name for n in self.github_notifications if n.unread is not self.read_filter)
        return sorted(repositories, key=lambda full_name: full_name.lower())

    def _get_repository(self, qs_parts):
        repository = qs_parts.get('repository', None)
        if repository in self.allowed_repositories:
            return repository
        return None

    def _get_sort_field(self, sort):
        if sort == 'notification':
            return 'githubnotification__updated_at'
        return super(GithubNotificationsFilters, self)._get_sort_field(sort)

    def get_filter_parts(self, qs_parts):
        query_filters, order_by, group_by, filter_objects, qs_filters =  \
            super(GithubNotificationsFilters, self).get_filter_parts(qs_parts)

        # filter by unread status
        self.read_filter = self._get_read(qs_parts)
        if self.read_filter is not None:
            qs_filters['read'] = self.allowed_reads[self.read_filter]
            filter_objects['read'] = self.read_filter
            query_filters['githubnotification__unread'] = not self.read_filter

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

        return query_filters, order_by, group_by, filter_objects, qs_filters


class GithubNotifications(BaseIssuesView, GithubNotificationsFilters, TemplateView):

    template_name = 'front/github_notifications/base.html'
    url_name = 'front:github-notifications:home'

    filters_and_list_template_name = 'front/github_notifications/include_filters_and_list.html'
    issue_item_template_name = 'front/github_notifications/include_issue_item_for_cache.html'

    default_qs = 'read=no&sort=notification&direction=desc'

    def get_base_queryset(self):
        return Issue.objects

    @cached_property
    def base_url(self):
        return reverse(self.url_name)

    @classmethod
    def get_default_url(cls):
        url = reverse(cls.url_name)
        if cls.default_qs:
            url += '?' + cls.default_qs
        return url

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

        issues, total_count, limit_reached, original_queryset = \
            super(GithubNotifications, self).finalize_issues(issues, context)

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

        return issues, total_count, limit_reached, original_queryset

    def get_distinct(self, order_by):
        result = super(GithubNotifications, self).get_distinct(order_by)
        if not self.needs_only_queryset:
            result.append('ordering')
        return result

    def get_queryset(self, base_queryset, filters, order_by):

        queryset = base_queryset

        notifications_queryset = self.github_notifications

        notifications_filters = {}
        notifications_excludes = {
            'issue_id__isnull': True
        }

        if filters:

            for key, value in dict(**filters).items():
                if key.startswith('githubnotification__'):
                    notifications_filters[key[20:]] = filters.pop(key)
                elif key.startswith('-githubnotification__'):
                    notifications_excludes[key[21:]] = filters.pop(key)

        if notifications_filters:
            notifications_queryset = notifications_queryset.filter(**notifications_filters)
        if notifications_excludes:
            notifications_queryset = notifications_queryset.exclude(**notifications_excludes)

        if order_by and not self.needs_only_queryset:
            notifications_orders = []
            for order in list(order_by):
                if 'githubnotification__' in order:
                    notifications_orders.append(order.replace('githubnotification__', ''))
                    order_by.remove(order)

            if not notifications_orders:
                # There is another order, but not on the notifications, so we keep them ordered
                notifications_orders = ['-updated_at']

            if notifications_orders:
                notifications_queryset = notifications_queryset.order_by(*notifications_orders)

        filters['id__in'] = list(notifications_queryset.values_list('issue_id', flat=True))

        if not self.needs_only_queryset:
            # http://blog.mathieu-leplatre.info/django-create-a-queryset-from-a-list-preserving-order.html
            queryset = queryset.annotate(
                ordering=models.Case(
                    *[
                        models.When(id=pk, then=models.Value(i))
                        for i, pk
                        in enumerate(filters['id__in'])
                    ],
                    **dict(
                        default=models.Value(0),
                        output_field=models.IntegerField(),
                    )
                )
            )
            order_by += ['ordering']

        return super(GithubNotifications, self).get_queryset(queryset, filters, order_by)

    def get_context_data(self, **kwargs):
        """
        Add readable reasons
        """
        context = super(GithubNotifications, self).get_context_data(**kwargs)

        if not self.needs_only_queryset:
            context.update({
                'reasons': self.reasons,
            })

            if context['issues_filter']['objects'].get('group_by_field') == 'githubnotification__repository':
                context['force_hide_repositories'] = True

        return context

    def get_select_and_prefetch_related(self, queryset, group_by):
        select_related, prefetch_related =\
            super(GithubNotifications, self).get_select_and_prefetch_related(queryset, group_by)

        # displayed for each issue
        select_related.append('repository__owner')

        return select_related, prefetch_related


class GithubNotificationsLastForMenu(WithAjaxRestrictionViewMixin, TemplateView):
    template_name = 'front/github_notifications/include_notifications_menu_list.html'
    ajax_only = True


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
            'unread': not bool(int(self.request.POST.get('read', 0) or 0)),
            'subscribed': bool(int(self.request.POST.get('active', 0) or 0)),
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
            'manual_unread': self.object.manual_unread,
            'count': self.request.user.unread_notifications_count,
            'last': self.request.user.last_unread_notification_date,
            'hash': self.request.user.last_github_notifications_hash,
        }
        if data['last']:
            data['last'] = format(data['last'], 'r')
        if error_msg:
            data['error_msg'] = error_msg
        return json.dumps(data)

    def get_object(self, queryset=None):
        obj = super(GithubNotificationEditView, self).get_object(queryset)
        self.original_unread = obj.unread
        return obj

    def form_valid(self, form):

        # If a read notification is marked unread by the user, mark it as "manually_unread"
        if self.original_unread != form.cleaned_data['unread']:
            self.object.manual_unread = form.cleaned_data['unread']
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
