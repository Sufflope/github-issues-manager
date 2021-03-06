# -*- coding: utf-8 -*-

__all__ = [
    'FetchIssueByNumber',
    'UpdateIssueCacheTemplate',
    'IssuePRBranchDeleteJob',
    'IssueCreateJob',
    'IssueEditStateJob',
    'IssueEditTitleJob',
    'IssueEditBodyJob',
    'IssueEditMilestoneJob',
    'IssueEditAssigneesJob',
    'IssueEditLabelsJob',
    'IssueEditProjectsJob',
]

import json
import time
from datetime import datetime

from async_messages import message_users, constants, messages

from limpyd import fields
from limpyd_jobs import STATUSES

from gim.core.models import Issue, Repository, GithubUser, Card, Column
from gim.core.ghpool import ApiError, ApiNotFoundError

from .base import DjangoModelJob, Job


class FetchIssueByNumber(Job):
    """
    Fetch the whole issue for a repository, given only the issue's number
    """
    queue_name = 'fetch-issue-by-number'
    deleted = fields.InstanceHashField()
    force_fetch = fields.InstanceHashField()  # will only force the issue/pr api call
    force_fetch_all = fields.InstanceHashField()  # will be used for fetch_all
    users_to_inform = fields.SetField()

    permission = 'read'

    @property
    def repository(self):
        if not hasattr(self, '_repository'):
            repository_id, issue_number = self.identifier.hget().split('#')
            try:
                self._repository = Repository.objects.get(id=repository_id)
            except Repository.DoesNotExist:
                # We can cancel the job if the repository does not exist anymore
                self.hmset(status=STATUSES.CANCELED, cancel_on_error=1)
                raise
        return self._repository

    def run(self, queue):
        """
        Fetch the issue with the given number for the current repository
        """
        super(FetchIssueByNumber, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        repository_id, issue_number = self.identifier.hget().split('#')

        repository = self.repository

        users_to_inform = self.users_to_inform.smembers()
        if users_to_inform:
            try:
                users_to_inform = GithubUser.objects.filter(id__in=users_to_inform)
            except GithubUser.DoesNotExist:
                users_to_inform = []

        try:
            issue = repository.issues.get(number=issue_number)
        except Issue.DoesNotExist:
            issue = Issue(repository=repository, number=issue_number)

        force_fetch = self.force_fetch.hget() == '1'
        force_fetch_all = self.force_fetch_all.hget() == '1'
        try:
            issue.fetch_all(gh, force_fetch=force_fetch or force_fetch_all) # both flags for legacy jobs
        except ApiNotFoundError, e:
            # we have a 404, but... check if it's the issue itself
            try:
                issue.fetch(gh)
            except ApiNotFoundError:
                # ok the issue doesn't exist anymore, delete id
                if users_to_inform:
                    message_users(users_to_inform,
                        'The %s <strong>#%d</strong> from <strong>%s</strong> you asked to fetch from Github doesn\'t exist anymore!' % (
                            issue.type, issue.number, issue.repository.full_name),
                        constants.ERROR)
                if issue.pk:
                    issue.delete()
                self.deleted.hset(1)
                return False
            else:
                if users_to_inform:
                    message_users(users_to_inform,
                        'The %s <strong>#%d</strong> from <strong>%s</strong> you asked to fetch from Github couldn\'t be fetched!' % (
                            issue.type, issue.number, issue.repository.full_name),
                        constants.ERROR)

                raise e
        else:
            if users_to_inform:
                message_users(users_to_inform,
                    'The %s <strong>#%d</strong> from <strong>%s</strong> you asked to fetch from Github was updated' % (
                        issue.type, issue.number, issue.repository.full_name),
                    constants.SUCCESS)

        return True

    def success_message_addon(self, queue, result):
        result = ''
        if self.force_fetch_all.hget() == '1':
            result += ' [force_fetch=all]'
        elif self.force_fetch.hget() == '1':
            result += ' [force_fetch=1]'
        if result is False:
            result += ' [deleted]'
        return result


class IssueJob(DjangoModelJob):
    """
    Abstract job model for jobs based on the Issue model
    """
    abstract = True
    model = Issue

    @property
    def issue(self):
        if not hasattr(self, '_issue'):
            self._issue = self.object
        return self._issue

    @property
    def repository(self):
        if not hasattr(self, '_repository'):
            self._repository = self.issue.repository
        return self._repository


class UpdateIssueCacheTemplate(IssueJob):
    """
    Job that update the cached template of an issue
    """
    queue_name = 'update-issue-tmpl'

    force_regenerate = fields.InstanceHashField()
    update_duration = fields.InstanceHashField()

    def run(self, queue):
        """
        Update the cached template of the issue and save the spent duration
        """
        super(UpdateIssueCacheTemplate, self).run(queue)

        start_time = time.time()

        try:
            issue = self.issue
        except Issue.DoesNotExist:
            # the issue doesn't exist anymore, stop here
            self.status.hset(STATUSES.CANCELED)
            return False

        issue.update_saved_hash()
        issue.update_cached_template(
                                force_regenerate=self.force_regenerate.hget())

        duration = '%.2f' % ((time.time() - start_time) * 1000)

        self.update_duration.hset(duration)

        return duration

    def success_message_addon(self, queue, result):
        """
        Display the duration of the cached template update
        """
        msg = 'duration=%sms' % self.update_duration.hget()

        if self.force_regenerate.hget():
            return ' [forced=True, %s]' % msg
        else:
            return ' [%s]' % msg


class IssuePRBranchDeleteJob(IssueJob):
    queue_name = 'delete-pr-branch'
    permission = 'push'

    def run(self, queue):
        super(IssuePRBranchDeleteJob, self).run(queue)

        issue = self.issue

        branch = issue.pr_head_branch

        if branch:

            gh = self.gh
            if not gh:
                return  # it's delayed !

            try:
                branch.dist_delete(gh)
            except ApiNotFoundError:
                # already deleted !
                if branch.pk:
                    branch.delete()

            except ApiError, e:
                message = None

                if e.code == 422:

                    if e.response.get('json', {}).get('message', '') == u'Reference does not exist':
                        if branch.pk:
                            branch.delete()
                        return

                    message = u'Github refused to delete the branch <strong>%s</strong> on <strong>%s</strong>' % (
                        branch.ref, issue.repository.full_name)
                    self.status.hset(STATUSES.CANCELED)

                elif e.code in (401, 403):
                    tries = self.tries.hget()
                    if tries and int(tries) >= 5:
                        message = u'You seem to not have the right to delete the branch <strong>%s</strong> on <strong>%s</strong>' % (
                            branch.ref, issue.repository.full_name)
                        self.status.hset(STATUSES.CANCELED)

                if message:
                    messages.error(self.gh_user, message)
                    return None

                else:
                    raise


class BaseIssueEditJob(IssueJob):
    abstract = True

    permission = 'self'
    editable_fields = None
    values = None
    edited_issue = None

    @property
    def action_verb(self):
        return self.edit_mode

    @property
    def action_done(self):
        return self.edit_mode + 'd'

    def get_issue_title_for_message(self, issue, number=True):
        if number and issue.number:
            return '<strong>#%d</strong>' % issue.number
        else:
            title = issue.title
            if len(title) > 30:
                title = title[:30] + u'…'
        return '"<strong>%s</strong>"' % title

    def do_action(self, issue, gh):
        self.edited_issue = issue.dist_edit(mode=self.edit_mode, gh=gh, fields=self.editable_fields, values=self.values)
        return self.edited_issue

    def run(self, queue):
        """
        Get the issue and update it
        """
        super(BaseIssueEditJob, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        try:
            issue = self.issue
        except Issue.DoesNotExist:
            # the issue doesn't exist anymore, stop here
            self.status.hset(STATUSES.CANCELED)
            messages.error(self.gh_user, 'The issue you wanted to %s seems to have been deleted' % self.action_verb)
            return False

        try:
            issue = self.do_action(issue, gh)

            if issue.github_status != issue.GITHUB_STATUS_CHOICES.FETCHED:
                # Maybe it was still in saving mode but we didn't have anything new to get
                # We need to be sure to have the right status to trigger the signals
                issue.github_status = issue.GITHUB_STATUS_CHOICES.FETCHED
                issue.save(update_fields=['github_status'])

        except ApiError, e:
            message = None

            if e.code == 422:
                message = u'Github refused to %s the %s %s on <strong>%s</strong>' % (
                    self.action_verb, issue.type, self.get_issue_title_for_message(issue),
                    issue.repository.full_name)
                self.status.hset(STATUSES.CANCELED)

            elif e.code in (401, 403):
                tries = self.tries.hget()
                if tries and int(tries) >= 5:
                    message = u'You seem to not have the right to %s the %s %s on <strong>%s</strong>' % (
                        self.action_verb, issue.type, self.get_issue_title_for_message(issue),
                        issue.repository.full_name)
                    self.status.hset(STATUSES.CANCELED)

            if message:
                messages.error(self.gh_user, message)
                try:
                    # don't use "issue" cache
                    self.object.fetch(gh, force_fetch=True)
                except Exception:
                    pass
                return None

            else:
                raise

        messages.success(self.gh_user, self.get_success_user_message(issue))

        # ask for fresh data
        FetchIssueByNumber.add_job('%s#%s' % (issue.repository_id, issue.number), gh=gh)

        return None

    def get_success_user_message(self, issue):
        return u'The %s %s on <strong>%s</strong> was correctly %s' % (
                    issue.type,
                    self.get_issue_title_for_message(issue),
                    issue.repository.full_name,
                    self.action_done
                )


class IssueEditFieldJob(BaseIssueEditJob):
    abstract = True
    edit_mode = 'update'

    value = fields.InstanceHashField()

    def get_field_value(self):
        return self.value.hget()

    @property
    def values(self):
        return {
            self.editable_fields[0]: self.get_field_value()
        }

    def get_success_user_message(self, issue):
        message = super(IssueEditFieldJob, self).get_success_user_message(issue)
        return message + u' (updated: <strong>%s</strong>)' % self.editable_fields[0]


class IssueEditStateJob(IssueEditFieldJob):
    queue_name = 'edit-issue-state'
    editable_fields = ['state']

    @property
    def action_done(self):
        value = self.value.hget()
        return 'reopened' if value == 'open' else 'closed'

    @property
    def action_verb(self):
        value = self.value.hget()
        return 'reopen' if value == 'open' else 'close'

    def get_success_user_message(self, issue):
        # call the one from BaseIssueEditJob
        super(IssueEditFieldJob, self).get_success_user_message(issue)


class IssueEditTitleJob(IssueEditFieldJob):
    queue_name = 'edit-issue-title'
    editable_fields = ['title']


class IssueEditBodyJob(IssueEditFieldJob):
    queue_name = 'edit-issue-body'
    editable_fields = ['body']


class IssueEditMilestoneJob(IssueEditFieldJob):
    queue_name = 'edit-issue-milestone'
    editable_fields = ['milestone']

    def get_field_value(self):
        return self.value.hget() or None


class IssueEditAssigneesJob(IssueEditFieldJob):
    queue_name = 'edit-issue-assignees'
    editable_fields = ['assignees']

    def get_field_value(self):
        usernames = self.value.hget() or '[]'
        return json.loads(usernames)


class IssueEditLabelsJob(IssueEditFieldJob):
    queue_name = 'edit-issue-labels'
    editable_fields = ['labels']

    def get_field_value(self):
        labels = self.value.hget() or '[]'
        return json.loads(labels)


class IssueEditProjectsJob(IssueEditFieldJob):
    queue_name = 'edit-issue-projects'
    editable_fields = ['projects']

    def get_field_value(self):
        columns = self.value.hget() or '[]'
        return json.loads(columns)

    def send_error_message_removed_column(self, issue, action):
        direction = {
            'removing': 'from',
            'adding': 'to',
            'moving': 'to',  # we only check destination column
        }
        messages.error(
            self.gh_user,
            "There was a problem %s the %s %s on <strong>%s</strong> %s a project's column that do "
            "not exist anymore" % (
                action,
                issue.type,
                self.get_issue_title_for_message(issue),
                issue.repository.full_name,
                direction[action]
            )
        )

    def do_action(self, issue, gh):
        actions = self.values['projects']

        all_columns_by_id = {
            c.id: c
            for c in Column.objects.filter(
                project__repository=issue.repository
            ).select_related('project')
        }

        cards_qs = issue.cards

        # start by removing cards from projects
        if actions.get('remove_from_columns'):
            for column_id, github_id in actions['remove_from_columns'].items():
                if not github_id:
                    continue

                column_id = int(column_id)

                try:
                    column = all_columns_by_id[column_id]
                except KeyError:
                    # the column doesn't exist anymore, we can't do anything
                    self.send_error_message_removed_column(issue, 'removing')
                    continue

                # do we have an existing card?
                try:
                    card = cards_qs.get(github_id=github_id)
                except Card.DoesNotExist:
                    try:
                        card = cards_qs.get(column_id=column_id)
                    except Card.DoesNotExist:
                        # make a fake card to use dist_delete
                        card = Card(github_id=github_id, column=column)

                try:
                    card.dist_delete(gh)
                except ApiNotFoundError:
                    # card already deleted, we can ignore
                    pass

        # now add new cards
        if actions.get('add_to_columns'):
            for column_id in actions['add_to_columns']:
                column_id = int(column_id)
                try:
                    column = all_columns_by_id[column_id]
                except KeyError:
                    # the column doesn't exist anymore, we can't do anything
                    self.send_error_message_removed_column(issue, 'adding')
                    continue

                # do we have an existing card?
                try:
                    card = cards_qs.get(column__project_id=column.project_id)
                except Card.DoesNotExist:
                    # make a fake card to use dist_edit
                    card = Card(
                        column=column,
                        type=Card.CARDTYPE.ISSUE,
                        issue=issue,
                    )

                if card.github_id:
                    # we have a github_id, so we cannot add it
                    if card.column_id == column_id:
                        # already in the correct column, nothing to do
                        continue
                else:
                    data = {
                        'content_type': 'PullRequest' if issue.is_pull_request else 'Issue',
                        'content_id': issue.github_pr_id if issue.is_pull_request else issue.github_id
                    }
                    try:
                        card = card.dist_edit(gh, mode='create', fields=data.keys(), values=data)
                    except ApiError, e:
                        if e.code == 422:
                            # a card for this issue may already exists in this column on github
                            pass
                        else:
                            raise

                # move the card to the bottom
                data = {
                    'position': 'bottom',
                    'column_id': column.github_id
                }
                card.dist_edit(gh, mode='create', fields=data.keys(), values=data,
                               meta_base_name='moves', update_object=False)

        # and finally move cards between columns
        if actions.get('move_between_columns'):
            for old_column_id, new_column_id in actions['move_between_columns'].items():
                new_column_id = int(new_column_id)
                try:
                    column = all_columns_by_id[new_column_id]
                except KeyError:
                    # the column doesn't exist anymore, we can't do anything
                    self.send_error_message_removed_column(issue, 'moving')
                    continue

                # we should have a card
                try:
                    card = cards_qs.get(column__project_id=column.project_id)
                except Card.DoesNotExist:
                    # it was removed in the meantime
                    continue

                # we can move
                data = {
                    'position': 'bottom',
                    'column_id': column.github_id
                }
                card.dist_edit(gh, mode='create', fields=data.keys(), values=data,
                               meta_base_name='moves', update_object=False)

        # now we have to update the projects
        issue.repository.fetch_all_projects(gh)

        return issue


class IssueCreateJob(BaseIssueEditJob):
    queue_name = 'create-issue'
    edit_mode = 'create'

    created_pk = fields.InstanceHashField(indexable=True)

    @property
    def issue(self):
        issue = super(IssueCreateJob, self).issue
        issue.is_new = True
        return issue

    def run(self, queue):
        result = super(IssueCreateJob, self).run(queue)
        if self.edited_issue:
            self.created_pk.hset(self.edited_issue.pk)
        return result

    def get_issue_title_for_message(self, issue, number=False):
        # dont use the number in create mode, but the title
        return super(IssueCreateJob, self).get_issue_title_for_message(issue, number)

    def do_action(self, issue, gh):

        # get the projects to save it on github after
        columns = list(Column.objects.filter(cards__issue=issue))

        issue = super(IssueCreateJob, self).do_action(issue, gh)

        # now save the columns
        if columns:
            job_data = {
                'add_to_columns': []
            }
            now = datetime.utcnow()

            # locally
            for column in columns:
                last_card = column.cards.order_by('position').only('position').last()
                Card.objects.create(
                    type=Card.CARDTYPE.ISSUE,
                    created_at=now,
                    updated_at=now,
                    issue=issue,
                    column=column,
                    position=last_card.position + 1 if last_card is not None else 1,
                )
                job_data['add_to_columns'].append(column.id)

            # and on github
            IssueEditProjectsJob.add_job(
                self.object.pk,
                gh=gh,
                value=json.dumps(job_data)
            )

        return issue
