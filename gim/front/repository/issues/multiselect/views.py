from collections import defaultdict
from datetime import datetime, timedelta
from time import sleep
import json

from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import TemplateView

from gim.core.tasks.issue import (
    IssueEditAssigneesJob,
    IssueEditLabelsJob,
    IssueEditMilestoneJob,
    IssueEditProjectsJob,
)
from gim.front.repository.issues.forms import update_columns
from gim.front.repository.views import RepositoryViewMixin
from gim.front.mixins.views import WithAjaxRestrictionViewMixin
from gim.subscriptions.models import SUBSCRIPTION_STATES
from gim.ws import sign


class MultiSelectViewBase(WithAjaxRestrictionViewMixin, RepositoryViewMixin):

    http_method_names = ['post']
    ajax_only = True
    allowed_rights = SUBSCRIPTION_STATES.WRITE_RIGHTS

    def get_issues_from_ids(self, ids):
        return self.repository.issues.filter(
            id__in=set(ids)
        )


class ListViewBase(MultiSelectViewBase, TemplateView):

    def post(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def get_issues_from_post(self):
        return self.get_issues_from_ids(self.request.POST.getlist('issues[]'))

    @staticmethod
    def get_issues_info(issues):
        issues_pks = sorted([issue.pk for issue in issues])
        issues_pks_json = json.dumps(issues_pks)
        return {
            'issues_pks': issues_pks_json,
            'issues_count': len(issues_pks),
            'issues_hash': sign(issues_pks),
        }


class MultiSelectListAssigneesView(ListViewBase):

    template_name = 'front/repository/issues/multiselect/list_assignees.html'
    url_name = 'list-assignees'

    def get_context_data(self, **kwargs):
        context = super(MultiSelectListAssigneesView, self).get_context_data(**kwargs)

        issues = self.get_issues_from_post().prefetch_related('assignees')

        collaborators = list(self.repository.collaborators.all())

        issues_assignees = defaultdict(int)
        for issue in issues:
            for collaborator in issue.assignees.all():
                issues_assignees[collaborator.pk] += 1

        for collaborator in collaborators:
            collaborator.multiselect_pre_count = issues_assignees.get(collaborator.pk)

        context.update({
            'collaborators': collaborators,
            'has_data': True,  # always at least the current user
            'data_count': len(collaborators),
        })
        context.update(self.get_issues_info(issues))

        return context


class MultiSelectListLabelsView(ListViewBase):

    template_name = 'front/repository/issues/multiselect/list_labels.html'
    url_name = 'list-labels'

    def get_context_data(self, **kwargs):
        context = super(MultiSelectListLabelsView, self).get_context_data(**kwargs)

        issues = self.get_issues_from_post().prefetch_related('labels')

        label_types = list(self.label_types)
        simple_labels = list(self.repository.labels.filter(label_type_id__isnull=True).order_by('lower_name'))

        has_data = False
        data_count = 0

        if label_types or simple_labels:
            has_data = True
            data_count = len(simple_labels) + sum([len(label_type.labels.all()) for label_type in label_types])

            issues_labels = defaultdict(int)
            for issue in issues:
                for label in issue.labels.all():
                    issues_labels[label.pk] += 1

            for label_type in label_types:
                for label in label_type.labels.all():
                    label.multiselect_pre_count = issues_labels.get(label.pk)

            for label in simple_labels:
                label.multiselect_pre_count = issues_labels.get(label.pk)

        context.update({
            'label_types': label_types,
            'simple_labels': simple_labels,
            'has_data': has_data,
            'data_count': data_count,
        })
        context.update(self.get_issues_info(issues))

        return context


class MultiSelectListMilestonesView(ListViewBase):

    template_name = 'front/repository/issues/multiselect/list_milestones.html'
    url_name = 'list-milestones'

    def get_context_data(self, **kwargs):
        context = super(MultiSelectListMilestonesView, self).get_context_data(**kwargs)

        issues = self.get_issues_from_post()

        milestones = list(self.milestones)
        milestones_by_pk = {milestone.pk: milestone for milestone in milestones}
        count_without_milestones = 0

        for issue in issues:
            if not issue.milestone_id:
                count_without_milestones += 1
                continue
            milestone = milestones_by_pk[issue.milestone_id]
            if not hasattr(milestone, 'multiselect_pre_count'):
                milestone.multiselect_pre_count = 0
            milestone.multiselect_pre_count += 1

        context.update({
            'count_without_milestones': count_without_milestones,
            'milestones': {
                'open': [milestone for milestone in milestones if milestone.state == 'open'],
                'closed': [milestone for milestone in milestones if milestone.state == 'closed'],
            },
            'has_data': True,  # always the "no milestone" entry
            'data_count': len(milestones),
        })
        context.update(self.get_issues_info(issues))

        return context


class MultiSelectListProjectsView(ListViewBase):

    template_name = 'front/repository/issues/multiselect/list_projects.html'
    url_name = 'list-projects'

    def get_context_data(self, **kwargs):

        context = super(MultiSelectListProjectsView, self).get_context_data(**kwargs)

        issues = self.get_issues_from_post().prefetch_related('cards__column')

        projects = list(self.projects)

        has_data = False
        data_count = 0

        if projects:
            has_data = True
            data_count = sum([project.num_columns for project in projects])
            nb_issues = len(issues)
            count_not_in_projects = {project.pk: nb_issues for project in projects}

            issues_columns = defaultdict(int)
            for issue in issues:
                for card in issue.cards.all():
                    issues_columns[card.column_id] += 1
                    if card.column.project_id in count_not_in_projects:
                        count_not_in_projects[card.column.project_id] -= 1

            for project in projects:
                project.multiselect_absent_count = count_not_in_projects[project.pk]
                for column in project.columns.all():
                    column.multiselect_pre_count = issues_columns.get(column.pk)

        context.update({
            'projects': projects,
            'has_data': has_data,
            'data_count': data_count,
        })
        context.update(self.get_issues_info(issues))

        return context


class ApplyViewBase(MultiSelectViewBase, View):

    repository_relation = None
    job_model = None
    field_name = None
    is_related_field = False
    change_updated_at = 'exact'
    fuzzy_delta = timedelta(seconds=120)

    def post(self, request, *args, **kwargs):
        issues, to_set, to_unset, front_uuid = self.get_data()
        count_success, failures = self.process_data(issues, to_set, to_unset, front_uuid)
        return HttpResponse(
            json.dumps({
                'count_success': count_success,
                'failures': sorted(failures),
            }),
            content_type='application/json',
        )

    @staticmethod
    def verify_issues_info(issues_pks, issues_hash):
        try:
            issues_pks = sorted([int(issue_pk) for issue_pk in issues_pks])
        except (ValueError, TypeError):
            raise SuspiciousOperation
        if sign(issues_pks) != issues_hash:
            raise SuspiciousOperation
        return issues_pks

    def verify_related(self, pks):
        if not self.repository_relation:
            raise NotImplementedError
        objects = getattr(self.repository, self.repository_relation).filter(pk__in=pks)
        if len(pks) != len(objects):
            raise SuspiciousOperation
        return objects

    def get_data(self):
        issues_pks = self.request.POST.getlist('issues[]')
        issues_hash = self.request.POST.get('hash')

        issues_pks = self.verify_issues_info(issues_pks, issues_hash)
        if not issues_pks:
            raise SuspiciousOperation

        try:
            to_set = self.verify_related([int(value) for value in self.request.POST.getlist('set[]')])
            to_unset = self.verify_related([int(value) for value in self.request.POST.getlist('unset[]')])
        except (ValueError, TypeError):
            raise SuspiciousOperation

        return (
            self.get_issues_from_ids(issues_pks),
            to_set,
            to_unset,
            str(self.request.POST.get('front_uuid', '') or '')[:36]
        )

    def process_data(self, issues, to_set, to_unset, front_uuid):
        raise NotImplementedError

    @classmethod
    def get_current_job_for_issue(cls, issue):
        try:
            job = cls.job_model.collection(identifier=issue.pk, queued=1).instances()[0]
        except IndexError:
            return None, None
        else:
            who = job.gh_args.hget('username')
            return job, who

    @cached_property
    def user_gh(self):
        return self.request.user.get_connection()

    def save_value(self, issue, value):
        if self.field_name is None:
            raise NotImplementedError
        if self.is_related_field:
            getattr(issue, self.field_name).set(value)
        else:
            setattr(issue, self.field_name, value)

        return value

    def update_issue(self, issue, value, front_uuid):

        iteration = 0
        while True:
            current_job, who = self.get_current_job_for_issue(issue)
            if not current_job:
                break
            else:
                if iteration >= 2:
                    return who
                else:
                    sleep(0.1)
                    iteration += 1

        revert_status = None

        if self.is_related_field:
            if issue.github_status == issue.GITHUB_STATUS_CHOICES.FETCHED:
                # We'll wait to have m2m saved to run signals
                issue.github_status = issue.GITHUB_STATUS_CHOICES.SAVING
                revert_status = issue.GITHUB_STATUS_CHOICES.FETCHED

        if self.change_updated_at is not None:
            now = datetime.utcnow()
            if not issue.updated_at:
                issue.updated_at = now
            elif self.change_updated_at == 'fuzzy':
                if now > issue.updated_at + self.fuzzy_delta:
                    issue.updated_at = now
            else:  # 'exact'
                if now > issue.updated_at:
                    issue.updated_at = now

        issue.front_uuid = front_uuid
        issue.skip_reset_front_uuid = True

        value_for_job = self.save_value(issue, value)
        issue.save()

        if revert_status:
            # Ok now the signals could work
            issue.github_status = revert_status
            issue.save()

        self.job_model.add_job(issue.pk, gh=self.user_gh, value=self.format_value_for_job(value_for_job))

    def format_value_for_job(self, value):
        raise NotImplementedError


class MultiSelectApplyAssigneesView(ApplyViewBase):
    url_name = 'apply-assignees'
    repository_relation = 'collaborators'
    job_model = IssueEditAssigneesJob
    field_name = 'assignees'
    is_related_field = True
    change_updated_at = 'fuzzy'

    def process_data(self, issues, to_set, to_unset, front_uuid):
        issues = issues.prefetch_related('assignees')

        count_success = 0
        failures = []

        for issue in issues:
            assignees = set(issue.assignees.all())
            touched = False
            for assignee in to_set:
                if assignee not in assignees:
                    assignees.add(assignee)
                    touched = True
            for assignee in to_unset:
                if assignee in assignees:
                    assignees.remove(assignee)
                    touched = True
            if touched:
                current_update_by = self.update_issue(issue, assignees, front_uuid)
                if current_update_by:
                    failures.append((issue.number, current_update_by))
                else:
                    count_success += 1

        return count_success, failures

    def format_value_for_job(self, value):
        return json.dumps([user.username for user in value] if value else [])


class MultiSelectApplyLabelsView(ApplyViewBase):
    url_name = 'apply-labels'
    repository_relation = 'labels'
    job_model = IssueEditLabelsJob
    field_name = 'labels'
    is_related_field = True
    change_updated_at = 'fuzzy'

    def process_data(self, issues, to_set, to_unset, front_uuid):
        issues = issues.prefetch_related('labels')

        count_success = 0
        failures = []

        for issue in issues:
            labels = set(issue.labels.all())
            touched = False
            for label in to_set:
                if label not in labels:
                    labels.add(label)
                    touched = True
            for label in to_unset:
                if label in labels:
                    labels.remove(label)
                    touched = True
            if touched:
                current_update_by = self.update_issue(issue, labels, front_uuid)
                if current_update_by:
                    failures.append((issue.number, current_update_by))
                else:
                    count_success += 1

        return count_success, failures

    def format_value_for_job(self, value):
        return json.dumps([label.name for label in value] if value else [])


class MultiSelectApplyMilestoneView(ApplyViewBase):
    url_name = 'apply-milestone'
    repository_relation = 'milestones'
    job_model = IssueEditMilestoneJob
    field_name = 'milestone'
    is_related_field = False
    change_updated_at = 'fuzzy'

    def process_data(self, issues, to_set, to_unset, front_uuid):
        issues = issues.select_related('milestone')

        count_success = 0
        failures = []

        new_milestone = None if not to_set else to_set[0]
        for issue in issues:
            if issue.milestone != new_milestone:
                current_update_by = self.update_issue(issue, new_milestone, front_uuid)
                if current_update_by:
                    failures.append((issue.number, current_update_by))
                else:
                    count_success += 1

        return count_success, failures

    def format_value_for_job(self, value):
        return value.number if value else ''


class MultiSelectApplyProjectsView(ApplyViewBase):
    url_name = 'apply-projects'
    repository_relation = 'project_columns'
    is_related_field = True
    job_model = IssueEditProjectsJob
    change_updated_at = 'fuzzy'

    def process_data(self, issues, to_set, to_unset, front_uuid):
        issues = issues.prefetch_related('cards__column')

        count_success = 0
        failures = []

        for issue in issues:
            columns = set([card.column for card in issue.cards.all()])
            touched = False
            for column in to_set:
                if column not in columns:
                    columns.add(column)
                    touched = True
            for column in to_unset:
                if column in columns:
                    columns.remove(column)
                    touched = True
            if touched:
                current_update_by = self.update_issue(issue, columns, front_uuid)
                if current_update_by:
                    failures.append((issue.number, current_update_by))
                else:
                    count_success += 1

        return count_success, failures

    def save_value(self, issue, value):
        return update_columns(issue, value)

    def format_value_for_job(self, value):
        return json.dumps(value)  # result of `update_columns` called in `save_value`




