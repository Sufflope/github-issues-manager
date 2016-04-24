# coding: utf-8

import json
import time
from collections import Counter, OrderedDict
from datetime import datetime, timedelta
from itertools import groupby
from operator import attrgetter, itemgetter

from django.conf import settings
from django.core.urlresolvers import reverse_lazy, reverse
from django.http.response import Http404
from django.shortcuts import redirect
from django.template import Context, Template
from django.template.defaultfilters import date as convert_date
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.views.generic import UpdateView, CreateView, DeleteView, DetailView, FormView
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib import messages
from django.utils.functional import cached_property

from gim.subscriptions.models import Subscription, SUBSCRIPTION_STATES

from gim.core.models import (LabelType, LABELTYPE_EDITMODE, Label,
                             GITHUB_STATUS_CHOICES, Milestone, Issue)
from gim.core.tasks.label import LabelEditJob
from gim.core.tasks.milestone import MilestoneEditJob

from gim.front.mixins.views import (DeferrableViewPart, SubscribedRepositoryViewMixin,
                                    LinkedToSubscribedRepositoryFormViewMixin,
                                    LinkedToUserFormViewMixin, WithAjaxRestrictionViewMixin,
                                    WithRepositoryViewMixin, get_querystring_context)

from gim.front.activity.views import ActivityViewMixin

from gim.front.repository.views import BaseRepositoryView
from gim.front.utils import get_metric, get_metric_stats

from .forms import (LabelTypeEditForm, LabelTypePreviewForm, LabelEditForm,
                    TypedLabelEditForm, MilestoneEditForm, MilestoneCreateForm,
                    HookToggleForm, MainMetricForm)


class RepositoryDashboardPartView(DeferrableViewPart, SubscribedRepositoryViewMixin, DetailView):
    @property
    def part_url(self):
        reverse_kwargs = self.repository.get_reverse_kwargs()
        return reverse_lazy('front:repository:%s' % self.url_name, kwargs=reverse_kwargs)

    def inherit_from_view(self, view):
        super(RepositoryDashboardPartView, self).inherit_from_view(view)
        self.object = self.repository = view.repository
        self.subscription = view.subscription

    def get_object(self, queryset=None):
        if getattr(self, 'object', None):
            return self.object
        return super(RepositoryDashboardPartView, self).get_object(queryset)


class MilestonesPart(RepositoryDashboardPartView):
    template_name = 'front/repository/dashboard/include_milestones.html'
    deferred_template_name = 'front/repository/dashboard/include_milestones_deferred.html'
    url_name = 'dashboard.milestones'

    def get_milestones(self):
        queryset = self.repository.milestones.all()

        show_closed = self.request.GET.get('show-closed-milestones', False)
        show_empty = self.request.GET.get('show-empty-milestones', False)

        if not show_closed:
            queryset = queryset.filter(state='open')

        all_milestones = list(queryset)

        main_metric = self.repository.main_metric

        milestones = []
        for milestone in all_milestones:

            issues = milestone.issues
            milestone.issues_count = issues.count()

            if milestone.issues_count:
                milestones.append(milestone)

                milestone.non_assigned_issues_count = issues.filter(state='open', assignee_id__isnull=True).count()
                milestone.open_issues_count = issues.filter(state='open').count()
                milestone.assigned_issues_count = milestone.open_issues_count - milestone.non_assigned_issues_count
                milestone.closed_issues_count = milestone.issues_count - milestone.open_issues_count

                if milestone.non_assigned_issues_count:
                    milestone.non_assigned_issues_percent = 100.0 * milestone.non_assigned_issues_count / milestone.issues_count

                if milestone.assigned_issues_count:
                    milestone.assigned_issues_percent = 100.0 * milestone.assigned_issues_count / milestone.issues_count

                if milestone.closed_issues_count:
                    milestone.closed_issues_percent = 100.0 * milestone.closed_issues_count / milestone.issues_count

                if main_metric:
                    milestone.main_metric_stats = get_metric_stats(
                        issues.filter(state='open'),
                        main_metric,
                        milestone.open_issues_count
                    )

            elif show_empty:
                milestones.append(milestone)

                milestone.non_assigned_issues_count = milestone.assigned_issues_count = \
                    milestone.open_issues_count = milestone.closed_issues_count = 0

        return milestones

    def get_context_data(self, **kwargs):
        context = super(MilestonesPart, self).get_context_data(**kwargs)
        context.update({
            'milestones': self.get_milestones(),
            'show_closed_milestones': self.request.GET.get('show-closed-milestones', False),
            'show_empty_milestones': self.request.GET.get('show-empty-milestones', False),
            'all_metrics': list(self.repository.label_types.filter(is_metric=True))
        })
        reverse_kwargs = self.repository.get_reverse_kwargs()
        context['milestone_create_url'] = reverse_lazy(
                'front:repository:%s' % MilestoneCreate.url_name, kwargs=reverse_kwargs)

        return context


class CountersPart(RepositoryDashboardPartView):
    template_name = 'front/repository/dashboard/include_counters.html'
    url_name = 'dashboard.counters'

    def get_counters(self):
        counters = {}

        base_filter = self.repository.issues.ready().filter(state='open')

        counters['all'] = base_filter.count()

        # count non assigned/prs only if we have issues (no issues = no non-assigned)
        if counters['all']:
            counters['all_na'] = base_filter.filter(assignee_id__isnull=True).count()
            counters['all_prs'] = base_filter.filter(is_pull_request=True).count()
        else:
            counters['all_na'] = counters['all_prs'] = 0

        counters['created'] = base_filter.filter(user=self.request.user).count()

        # count prs only if we have issues (no issues = no prs)
        if counters['created']:
            counters['prs'] = base_filter.filter(is_pull_request=True, user=self.request.user).count()
        else:
            counters['prs'] = 0

        # count assigned only if owner or collaborator
        if self.subscription.state in SUBSCRIPTION_STATES.WRITE_RIGHTS:
            counters['assigned'] = base_filter.filter(assignee=self.request.user).count()

        return counters

    def get_context_data(self, **kwargs):
        context = super(CountersPart, self).get_context_data(**kwargs)
        context.update({
            'counters': self.get_counters(),
        })
        return context


class LabelsPart(RepositoryDashboardPartView):
    template_name = 'front/repository/dashboard/include_labels.html'
    url_name = 'dashboard.labels'

    def group_labels(self, labels):

        groups = [
            (
                label_type,
                sorted(label_type_labels, key=lambda l: l.name.lower())
            )
            for label_type, label_type_labels
            in groupby(
                labels,
                attrgetter('label_type')
            )
        ]

        if len(groups) > 1 and groups[0][0] is None:
            groups = groups[1:] + groups[:1]

        return groups

    def get_labels_groups(self):
        show_empty = self.request.GET.get('show-empty-labels', False)

        counts = Counter(self.repository.issues.filter(state='open').values_list('labels', flat=True))
        count_without_labels = counts.pop(None, 0)

        labels_with_count = []
        for label in self.repository.labels.ready().select_related('label_type'):
            if label.id in counts:
                label.issues_count = counts[label.id]
                labels_with_count.append(label)
            elif show_empty:
                label.issues_count = 0
                labels_with_count.append(label)

        return self.group_labels(labels_with_count), count_without_labels

    def get_context_data(self, **kwargs):
        context = super(LabelsPart, self).get_context_data(**kwargs)

        reverse_kwargs = self.repository.get_reverse_kwargs()

        labels_groups, count_without_labels = self.get_labels_groups()

        context.update({
            'show_empty_labels': self.request.GET.get('show-empty-labels', False),
            'labels_groups': labels_groups,
            'without_labels': count_without_labels,
            'labels_editor_url': reverse_lazy(
                'front:repository:%s' % LabelsEditor.url_name, kwargs=reverse_kwargs),
        })

        return context


class ActivityPart(ActivityViewMixin, RepositoryDashboardPartView):
    template_name = 'front/repository/dashboard/include_activity.html'
    deferred_template_name = 'front/repository/dashboard/include_activity_deferred.html'
    url_name = 'dashboard.timeline'

    def get_context_data(self, *args, **kwargs):
        context = super(ActivityPart, self).get_context_data(**kwargs)
        activity_obj = self.repository.activity
        activity, has_more = activity_obj.get_activity(**self.activity_args)
        context.update({
            'activity': activity_obj.load_objects(activity),
            'more_activity': has_more,
            'activity_mode': 'issues',
        })
        return context


class DashboardView(BaseRepositoryView):
    name = 'Dashboard'
    url_name = 'dashboard'
    template_name = 'front/repository/dashboard/dashboard.html'
    display_in_menu = True


    def get_context_data(self, **kwargs):
        context = super(DashboardView, self).get_context_data(**kwargs)

        context['parts'] = {
            'milestones': MilestonesPart().get_as_deferred(self),
            'counters': CountersPart().get_as_part(self),
            'labels': LabelsPart().get_as_part(self),
            'hook': HookPart().get_as_part(self),
            'activity': ActivityPart().get_as_deferred(self),
        }

        all_milestones = self.repository.milestones.all()
        all_milestones_data = {m.number: {
                'id': m.id,
                'number': m.number,
                'due_on': convert_date(m.due_on, settings.DATE_FORMAT) if m.due_on else None,
                'title': escape(m.title),
                'state': m.state,
                'graph_url': str(m.get_graph_url()),
              }
            for m in self.repository.milestones.all()
        }

        grouped_milestones = {}
        for milestone in all_milestones:
            grouped_milestones.setdefault(milestone.state, []).append(milestone)

        context['all_milestones'] = grouped_milestones
        context['all_milestones_json'] = json.dumps(all_milestones_data)
        context['all_metrics'] = list(self.repository.label_types.filter(is_metric=True))
        context['default_graph_metric'] = get_metric(self.repository, None, first_if_none=True)

        context['can_add_issues'] = True

        return context


class LabelsEditor(BaseRepositoryView):
    url_name = 'dashboard.labels.editor'
    template_name = 'front/repository/dashboard/labels-editor/base.html'
    template_name_ajax = 'front/repository/dashboard/labels-editor/include-content.html'
    label_type_include_template = 'front/repository/dashboard/labels-editor/include-label-type.html'
    allowed_rights = SUBSCRIPTION_STATES.WRITE_RIGHTS

    def get_context_data(self, **kwargs):
        context = super(LabelsEditor, self).get_context_data(**kwargs)

        label_types = self.repository.label_types.all().prefetch_related('labels')
        for label_type in label_types:
            label_type.visible_labels = [l for l in label_type.labels.all() if l.github_status != GITHUB_STATUS_CHOICES.WAITING_DELETE]

        context.update({
            'label_types': label_types,
            'labels_without_type': self.repository.labels.exclude_deleting().order_by('lower_name').filter(label_type_id__isnull=True),
            'label_type_include_template': self.label_type_include_template,
        })

        reverse_kwargs = self.repository.get_reverse_kwargs()
        context['label_type_create_url'] = reverse_lazy(
                'front:repository:%s' % LabelTypeCreate.url_name, kwargs=reverse_kwargs)

        label_reverse_kwargs = dict(reverse_kwargs, label_id=0)
        context['base_label_edit_url'] = reverse_lazy(
                'front:repository:%s' % LabelEdit.url_name, kwargs=label_reverse_kwargs)
        context['base_label_delete_url'] = reverse_lazy(
                'front:repository:%s' % LabelDelete.url_name, kwargs=label_reverse_kwargs)
        context['label_create_url'] = reverse_lazy(
                'front:repository:%s' % LabelCreate.url_name, kwargs=reverse_kwargs)

        context['main_metric_form'] = MainMetricForm(instance=self.repository)
        context['main_metric_set_url'] = reverse_lazy(
                'front:repository:%s' % MainMetricView.url_name, kwargs=reverse_kwargs)
        return context

    def get_template_names(self):
        if self.request.is_ajax():
            return [self.template_name_ajax]
        return super(LabelsEditor, self).get_template_names()


class LabelTypeFormBaseViewSubscribed(LinkedToSubscribedRepositoryFormViewMixin):
    model = LabelType
    pk_url_kwarg = 'label_type_id'
    form_class = LabelTypeEditForm
    allowed_rights = SUBSCRIPTION_STATES.WRITE_RIGHTS

    def get_success_url(self):
        reverse_kwargs = self.repository.get_reverse_kwargs()
        return reverse('front:repository:%s' % LabelsEditor.url_name, kwargs=reverse_kwargs)


class LabelTypeEditBase(LabelTypeFormBaseViewSubscribed):
    template_name = 'front/repository/dashboard/labels-editor/label-type-edit.html'

    def get_context_data(self, **kwargs):
        context = super(LabelTypeEditBase, self).get_context_data(**kwargs)

        reverse_kwargs = self.repository.get_reverse_kwargs()

        context.update({
            'preview_url': reverse_lazy(
                    'front:repository:%s' % LabelTypePreview.url_name, kwargs=reverse_kwargs),
            'label_type_create_url': reverse_lazy(
                    'front:repository:%s' % LabelTypeCreate.url_name, kwargs=reverse_kwargs),
        })

        return context


class LabelTypeEdit(LabelTypeEditBase, UpdateView):
    url_name = 'dashboard.labels.editor.label_type.edit'

    def get_success_url(self):
        url = super(LabelTypeEdit, self).get_success_url()

        messages.success(self.request,
            u'The group <strong>%s</strong> was successfully updated' % self.object.name)

        return '%s?group_just_edited=%d' % (url, self.object.id)


class LabelTypeCreate(LabelTypeEditBase, CreateView):
    url_name = 'dashboard.labels.editor.label_type.create'
    initial = {
        'edit_mode': LABELTYPE_EDITMODE.FORMAT
    }

    def get_success_url(self):
        url = super(LabelTypeCreate, self).get_success_url()

        messages.success(self.request,
            u'The group <strong>%s</strong> was successfully created' % self.object.name)

        return '%s?group_just_created=%d' % (url, self.object.id)


class LabelTypePreview(LabelTypeFormBaseViewSubscribed, UpdateView):
    url_name = 'dashboard.labels.editor.label_type.edit'
    template_name = 'front/repository/dashboard/labels-editor/label-type-preview.html'
    http_method_names = [u'post']
    form_class = LabelTypePreviewForm

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        return LabelType(repository=self.repository)

    def get_form(self, form_class):
        form = super(LabelTypePreview, self).get_form(form_class)
        form.fields['name'].required = False
        return form

    def form_invalid(self, form):
        context = {
            'form': form,
            'error': True,
        }
        return self.render_to_response(context)

    def form_valid(self, form):
        context = {
            'form': form,
            'error': False
        }

        labels = self.repository.labels.exclude_deleting().order_by('lower_name')

        matching_labels = []
        has_order = True

        for label in labels:
            if self.object.match(label.name):
                typed_name, order = self.object.get_name_and_order(label.name)
                label_data = {
                    'name': label.name,
                    'typed_name': typed_name,
                    'lower_typed_name': label.lower_typed_name,
                    'color': label.color,
                }
                if order is None:
                    has_order = False
                else:
                    label_data['order'] = order

                matching_labels.append(label_data)

        matching_labels.sort(key=itemgetter('order' if has_order else 'lower_typed_name'))

        context['matching_labels'] = matching_labels

        return self.render_to_response(context)


class LabelTypeDelete(LabelTypeFormBaseViewSubscribed, DeleteView):
    url_name = 'dashboard.labels.editor.label_type.delete'
    http_method_names = [u'post']

    def post(self, *args, **kwargs):
        if not self.request.is_ajax():
            return self.http_method_not_allowed(self.request)
        return super(LabelTypeDelete, self).post(*args, **kwargs)

    def get_success_url(self):
        url = super(LabelTypeDelete, self).get_success_url()

        messages.success(self.request,
            u'The group <strong>%s</strong> was successfully deleted' % self.object.name)

        return url


class LabelFormBaseViewSubscribed(LinkedToSubscribedRepositoryFormViewMixin):
    model = Label
    pk_url_kwarg = 'label_id'
    form_class = LabelEditForm
    allowed_rights = SUBSCRIPTION_STATES.WRITE_RIGHTS
    http_method_names = [u'post']
    ajax_only = True

    def form_valid(self, form):
        """
        Override the default behavior to add a job to create/update the label
        on the github side
        """
        response = super(LabelFormBaseViewSubscribed, self).form_valid(form)

        edit_mode = 'update'
        if self.object.github_status == GITHUB_STATUS_CHOICES.WAITING_CREATE:
            edit_mode = 'create'

        LabelEditJob.add_job(self.object.pk,
                             mode=edit_mode,
                             gh=self.request.user.get_connection())

        messages.success(self.request,
            u'The label <strong>%s</strong> will be %sd shortly' % (
                                                self.object.name, edit_mode))

        return response

    def get_success_url(self):
        reverse_kwargs = self.repository.get_reverse_kwargs()
        return reverse('front:repository:%s' % LabelsEditor.url_name, kwargs=reverse_kwargs)


class LabelEditBase(LabelFormBaseViewSubscribed):
    template_name = 'front/repository/dashboard/labels-editor/form-errors.html'

    @cached_property
    def is_typed_label(self):
        return self.request.method in ('POST', 'PUT') and self.request.POST.get('label_type', None)

    def get_form_class(self):
        if self.is_typed_label:
            return TypedLabelEditForm
        return self.form_class

    def get_form_kwargs(self):
        kwargs = super(LabelEditBase, self).get_form_kwargs()
        if self.is_typed_label:
            kwargs['data'] = kwargs['data'].copy()
            kwargs['data']['typed_name'] = kwargs['data']['name']
        return kwargs


class LabelEdit(LabelEditBase, UpdateView):
    url_name = 'dashboard.labels.editor.label.edit'

    def get_success_url(self):
        url = super(LabelEdit, self).get_success_url()
        return '%s?label_just_edited=%d' % (url, self.object.id)


class LabelCreate(LabelEditBase, CreateView):
    url_name = 'dashboard.labels.editor.label.create'

    def get_success_url(self):
        url = super(LabelCreate, self).get_success_url()
        return '%s?label_just_created=%s' % (url, self.object.name)


class LabelDelete(LabelFormBaseViewSubscribed, DeleteView):
    url_name = 'dashboard.labels.editor.label.delete'

    def delete(self, request, *args, **kwargs):
        """
        Don't delete the object but update its status
        """
        self.object = self.get_object()
        self.object.github_status = GITHUB_STATUS_CHOICES.WAITING_DELETE
        self.object.save(update_fields=['github_status'])

        LabelEditJob.add_job(self.object.pk,
                             mode='delete',
                             gh=self.request.user.get_connection())

        messages.success(self.request,
            u'The label <strong>%s</strong> will be deleted shortly' % self.object.name)

        return HttpResponseRedirect(self.get_success_url())


class MilestoneFormBaseViewSubscribed(LinkedToSubscribedRepositoryFormViewMixin):
    model = Milestone
    pk_url_kwarg = 'milestone_id'
    form_class = MilestoneEditForm
    allowed_rights = SUBSCRIPTION_STATES.WRITE_RIGHTS

    def form_valid(self, form):
        """
        Override the default behavior to add a job to create/update the milestone
        on the github side, and simple return 'OK', not a redirect.
        """
        self.object = form.save()

        edit_mode = 'update'
        if self.object.github_status == GITHUB_STATUS_CHOICES.WAITING_CREATE:
            edit_mode = 'create'

        MilestoneEditJob.add_job(self.object.pk,
                                 mode=edit_mode,
                                 gh=self.request.user.get_connection())

        messages.success(self.request,
            u'The milestone <strong>%s</strong> will be %sd shortly' % (
                                                self.object.short_title, edit_mode))

        return HttpResponse('OK')


class MilestoneEditBase(MilestoneFormBaseViewSubscribed):
    template_name = 'front/repository/dashboard/milestone-edit.html'

    def get_context_data(self, **kwargs):
        context = super(MilestoneEditBase, self).get_context_data(**kwargs)

        reverse_kwargs = self.repository.get_reverse_kwargs()

        context.update({
            'milestone_create_url': reverse_lazy(
                'front:repository:%s' % MilestoneCreate.url_name, kwargs=reverse_kwargs),
        })

        return context


class MilestoneEdit(MilestoneEditBase, UpdateView):
    url_name = 'dashboard.milestone.edit'


class MilestoneCreate(LinkedToUserFormViewMixin, MilestoneEditBase, CreateView):
    url_name = 'dashboard.milestone.create'
    form_class = MilestoneCreateForm


class MilestoneDelete(MilestoneFormBaseViewSubscribed, DeleteView):
    url_name = 'dashboard.milestone.delete'

    def delete(self, request, *args, **kwargs):
        """
        Don't delete the object but update its status, and return a simple "OK",
        not a redirect
        """
        self.object = self.get_object()
        self.object.github_status = GITHUB_STATUS_CHOICES.WAITING_DELETE
        self.object.save(update_fields=['github_status'])

        MilestoneEditJob.add_job(self.object.pk,
                             mode='delete',
                             gh=self.request.user.get_connection())

        messages.success(self.request,
            u'The milestone <strong>%s</strong> will be deleted shortly' % self.object.short_title)

        return HttpResponse('OK')


class HookPart(RepositoryDashboardPartView):
    template_name = 'front/repository/dashboard/include_hook.html'
    url_name = 'hook'

    def get_context_data(self, **kwargs):
        context = super(HookPart, self).get_context_data(**kwargs)
        context['hook_toggle_form'] = HookToggleForm(initial={'hook_set': not self.repository.hook_set})
        reverse_kwargs = self.repository.get_reverse_kwargs()
        context['hook_toggle_url'] = reverse_lazy(
                'front:repository:%s' % HookToggle.url_name, kwargs=reverse_kwargs)
        return context


class HookToggle(SubscribedRepositoryViewMixin, WithAjaxRestrictionViewMixin, FormView):
    url_name = 'hook.toggle'
    form_class = HookToggleForm
    allowed_rights = (SUBSCRIPTION_STATES.ADMIN, )
    ajax_only = True

    def form_invalid(self, form):
        return self.render_form_errors_as_messages(form, show_fields=False, status=422)

    def form_valid(self, form):
        to_set = form.cleaned_data['hook_set']
        method = 'set_hook' if to_set else 'remove_hook'
        gh = self.request.user.get_connection()

        try:
            getattr(self.repository, method)(gh)
        except:
            messages.error(self.request, u'We were unable to update the hook on your behalf')
            return self.render_messages(status=422)

        if self.repository.hook_set != to_set:
            messages.error(self.request, u'We were unable to update the hook on your behalf')
            return self.render_messages(status=422)

        if to_set:
            message = u'The hook was correctly set on Github for %s'
        else:
            message = u'The hook was correctly removed from Github for %s'

        messages.success(self.request, message % self.repository)

        reverse_kwargs = self.repository.get_reverse_kwargs()
        return HttpResponseRedirect(reverse_lazy('front:repository:%s' % HookPart.url_name,
                                                 kwargs=reverse_kwargs))


class MainMetricView(BaseRepositoryView, UpdateView):
    url_name = 'main_metric.set'
    allowed_rights = SUBSCRIPTION_STATES.WRITE_RIGHTS
    http_method_names = [u'post']

    form_class = MainMetricForm

    def get_object(self, queryset=None):
        return self.repository

    def form_invalid(self, form):
        messages.error(
            self.request,
            form.errors.get('main_metric', form.errors.get('__all__', ['Unexpected error']))[0]
        )
        return redirect(self.get_success_url())

    def form_valid(self, form):
        main_metric = form.cleaned_data.get('main_metric')
        if not main_metric:
            messages.success(self.request, u'The main metric was unset')
        else:
            messages.success(self.request, u'The main metric was set to "%s"' % main_metric)

        return super(MainMetricView, self).form_valid(form)

    def get_success_url(self):
        reverse_kwargs = self.repository.get_reverse_kwargs()
        return reverse('front:repository:%s' % LabelsEditor.url_name, kwargs=reverse_kwargs)


class MilestoneGraph(WithRepositoryViewMixin, DetailView):
    model = Milestone
    slug_url_kwarg = 'milestone_number'
    slug_field = 'number'
    allowed_rights = SUBSCRIPTION_STATES.READ_RIGHTS
    template_name = 'front/repository/dashboard/milestone-graph.html'
    url_name = 'dashboard.milestone.graph'

    point_template = Template(u"""Date: <b>{{ date|date:'F j (l)' }}</b>
{{ metric.name }} closed: <b>{{ point.total }}</b>
{{ metric.name }} remaining: <b>{{ point.remaining }}</b>
{{ point.issues|length }} issue{{ point.issues|length|pluralize }} closed: {% for issue in point.issues %}
  • <b>#{{ issue.number }}</b> "<i>{{ issue.title }}</i>"{% if issue.closed_by_id %} closed by <b>{{ issue.closed_by }}</b>{% endif %} ({% if issue.graph_value %}{{ metric.name }}: <b>{{ issue.graph_value }}</b>{% else %}<b>No {{ metric.name }}</b>{% endif %}){% endfor %}""")

    one_day = timedelta(days=1)

    def get_queryset(self):
        return self.repository.milestones

    def get_graph(self):

        metric_label_type_name = self.request.GET.get('metric', None)
        metric = get_metric(self.repository, metric_label_type_name, first_if_none=True)

        if not metric:
            raise Http404

        milestone = self.object

        # Get issues
        all_issues = milestone.issues.all()
        closed_issues = sorted(
            [i for i in all_issues if i.state == 'closed'],
            key=attrgetter('closed_at')
        )

        # Get metric stats for all the issues
        stats = get_metric_stats(all_issues, metric)
        total = stats.get('sum') or 0

        # Get the metric value for each closed issue
        for issue in closed_issues:
            issue.graph_value = stats['issues_with_metric'].get(issue.pk, 0)

        # Regroup closed issues by closing day
        closed_by_day = OrderedDict()
        remaining = total
        for issue in closed_issues:
            if not issue.closed_at:
                continue
            day = issue.closed_at.date()
            if day not in closed_by_day:
                closed_by_day[day] = {'total': 0, 'issues': [], 'remaining': 0}
            closed_by_day[day]['issues'].append(issue)
            closed_by_day[day]['total'] += issue.graph_value
            remaining -= issue.graph_value
            closed_by_day[day]['remaining'] = remaining

        start_date = milestone.created_at.date()

        today = datetime.utcnow().date()
        if milestone.due_on and milestone.due_on.date() > start_date:
            end_date = milestone.due_on.date()
        else:
            end_date = today

        nb_days = (end_date - start_date).days

        all_days = [start_date + timedelta(days=i) for i in range(0, nb_days + 1)]

        data = []
        data_axis = []
        current = total
        for index, day in enumerate(all_days):
            if day > today:
                break
            if day not in closed_by_day:
                continue

            current -= closed_by_day[day]['total']
            data.append(current)
            data_axis.append(all_days[index])

        def convert_date(d):
            return time.mktime(d.timetuple()) * 1000

        graphs = []

        green = '140, 192, 121'  # 8CC079
        red = '179, 93, 93'   # b35d5d

        if closed_issues:
            if data_axis[0] > start_date:
                # Line from start of the graph to first closed issue
                graphs.append({
                    "x": [convert_date(day) for day in [start_date, data_axis[0]]],
                    "y": [data[0], data[0]],
                    "name": "Sart",
                    "mode": "lines",
                    "fillcolor": "rgba(%s, 0.1)" % green,
                    "hoverinfo": "none",
                    "line": {
                        "color": "rgb(%s)" % green,
                        "width": 2,
                    },
                    "type": "scatter",
                    "fill": "tozeroy"
                })

            today_or_end_date = min(today, end_date)
            if data_axis[-1] < today_or_end_date:
                # Line from the last closed issue to today
                graphs.append({
                    "x": [convert_date(day) for day in [data_axis[-1], today_or_end_date]],
                    "y": [data[-1], data[-1]],
                    "name": "Today",
                    "mode": "lines",
                    "fillcolor": "rgba(%s, 0.1)" % green,
                    "hoverinfo": "none",
                    "line": {
                        "color": "rgb(%s)" % green,
                        "width": 2,
                    },
                    "type": "scatter",
                    "fill": "tozeroy"
                })

            # Graph for remaining, for each closed issue
            graphs.append({
                "x": [convert_date(day) for day in data_axis],
                "y": data,
                "text": [self.point_template.render(Context({
                    'metric': metric,
                    'date': date,
                    'point': point,
                })) for date, point in closed_by_day.iteritems()],
                "name": "Remaining",
                "marker": {
                    "line": {
                        "color": "#fff",
                        "width": 2
                    },
                    "symbol": "circle",
                    "size": 12,
                },
                "hoverinfo": "text",
                "hovermode": "closest",
                "fillcolor": "rgba(%s, 0.1)" % green,
                "line": {
                    "color": "rgb(%s)" % green,
                    "shape": "hv",
                    "width": 2,
                },
                "fill": "tozeroy",
                "type": "scatter",
                "mode": "lines+markers"
            })

            if today < end_date:
                # Dotted line from today until 0, the end of the graph
                graphs.append({
                    "x": [convert_date(day) for day in [today, end_date]],
                    "y": [data[-1], 0],
                    "name": "Future",
                    "mode": "lines",
                    "hoverinfo": "none",
                    "line": {
                        "color": "rgba(%s, 0.5)" % red,
                        "dash": "dot",
                        "width": 1
                    },
                    "type": "scatter"
                })

        graphs.append({
            # Ideal line: dotted line from the top, start of the graph, to 0, its end
            "x": [convert_date(day) for day in [all_days[0], all_days[-1]]],
            "y": [total, 0],
            "name": "Ideal",
            "mode": "lines",
            "hoverinfo": "none",
            "line": {
                "color": "rgb(%s)" % green,
                "dash": "dot",
                "width": 1
            },
            "type": "scatter"
        })

        layout = {
            "showlegend": False,
            "xaxis": {
                "hoverformat": "%B %-d (%A)",
                "type": "date",
                "fixedrange": True,
                "zeroline": True,
                "zerolinewidth": 2,
            },
            "yaxis": {
                "fixedrange": True,
                "showline": True,
                "linewidth": 1,
                "range": [-1, max(20, 10*(total/10+1))]
            },
        }

        return {
            'metric': metric,
            'graphs': mark_safe(json.dumps(graphs)),
            'layout': mark_safe(json.dumps(layout)),
            'points': closed_by_day,
            'all_stats': stats,
        }

    def get_context_data(self, **kwargs):
        context = super(MilestoneGraph, self).get_context_data(**kwargs)

        milestone = self.object
        graph = self.get_graph()

        context.update({
            'graph': graph,
            'current_metric': graph['metric'],
            'current_issues_url': self.repository.get_view_url('issues'),
            'all_stats': graph['all_stats'],
            'open_stats': get_metric_stats(milestone.issues.filter(state='open'), graph['metric']),
            'all_querystring_parts': get_querystring_context('milestone=%d' % milestone.number)['querystring_parts'],
            'open_querystring_parts': get_querystring_context('state=open&milestone=%d' % milestone.number)['querystring_parts'],
        })

        return context


