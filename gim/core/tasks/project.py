__all__ = [
    'FetchProjects',
    'MoveCardJob',
]

from random import randint

from gim.core.managers import CardIssueNotAvailable
from gim.core.models import Card, Column, Project

from async_messages import messages

from limpyd import fields
from limpyd_jobs import STATUSES

from gim.core.ghpool import ApiError, ApiNotFoundError

from .base import DjangoModelJob
from .issue import FetchIssueByNumber
from .repository import RepositoryJob


class FetchProjects(RepositoryJob):
    """
    Job that will do an unforced full fetch of the repository projects to update all that
    needs to.
    When done:
    - clone the job to be done again 1 min later (+-15s)
    """
    queue_name = 'fetch-projects'
    permission = 'read'
    clonable_fields = ('gh', )

    def run(self, queue):
        """
        Fetch the whole repository projects stuff
        """
        super(FetchProjects, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        try:
            self.repository.fetch_all_projects(gh)
        except CardIssueNotAvailable as e:
            FetchIssueByNumber.add_job('%s#%s' % (
                e.repository_id,
                e.issue_number
            ))
            raise

    def on_success(self, queue, result):
        """
        Go fetch again in 1mn +- 15
        """
        self.clone(delayed_for=int(60 * .75) + randint(0, 30 * 1))


class ProjectJob(DjangoModelJob):
    """
    Abstract job model for jobs based on the Project model
    """
    abstract = True
    model = Project

    @property
    def project(self):
        if not hasattr(self, '_project'):
            self._project = self.object
        return self._project

    @property
    def repository(self):
        if not hasattr(self, '_repository'):
            self._repository = self.project.repository
        return self._repository


class MoveCardJob(DjangoModelJob):

    queue_name = 'move-project-card'
    model = Card
    permission = 'self'
    issue_id = fields.InstanceHashField(indexable=True)
    column_id = fields.InstanceHashField()
    position = fields.InstanceHashField()
    direction = fields.InstanceHashField()

    @property
    def card(self):
        if not hasattr(self, '_card'):
            self._card = self.object
        return self._card

    @property
    def project(self):
        if not hasattr(self, '_project'):
            self._project = self.card.column.project
        return self._project

    def run(self, queue):
        """
        Move the card from a github column to another, creating it in this column if not existing, or
        deleting it if exists but asked to move out of the project (column_id not set)
        """
        super(MoveCardJob, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        try:
            card = self.card
        except Card.DoesNotExist:
            # the card doesn't exist anymore, stop here
            self.status.hset(STATUSES.CANCELED)
            messages.error(self.gh_user, 'The project card you wanted to move seems to have been deleted')
            return False

        column_id = self.column_id.hget()
        if not column_id:
            # we remove the card from the project
            try:
                card.dist_delete(gh)
            except ApiNotFoundError:
                # card already deleted, we can ignore
                pass

        else:
            try:
                column = self.project.columns.get(id=column_id)
            except Column.DoesNotExist:
                # the column doesn't exist anymore, stop here
                self.status.hset(STATUSES.CANCELED)
                messages.error(self.gh_user, 'The column in which you wanted to move a project card seems to have been deleted')
                return False

            position = self.position.hget()

            if not card.github_id:
                # we must first create the card on the github side
                try:
                    if card.type == card.CARDTYPE.ISSUE:
                        data = {
                            'content_type': 'PullRequest' if card.issue.is_pull_request else 'Issue',
                            'content_id': card.issue.github_pr_id if card.issue.is_pull_request else card.issue.github_id
                        }
                    else:
                        data = {
                            'note': card.note
                        }
                    card = card.dist_edit(gh, mode='create', fields=data.keys(), values=data)
                except ApiError, e:
                    if e.code == 422:
                        # a card for this issue may already exists in this column on github
                        pass
                    else:
                        raise
            else:
                # to avoid the fetch of the old column to remove the card, and the new column to create it again
                card.github_status = card.GITHUB_STATUS_CHOICES.FETCHED # yes, I know it's not True
                if position:
                    card.position = position
                card.column = column
                card.save(update_fields=['position', 'column'])

            if not position:
                # no position, we move it to the bottom
                github_position = 'bottom'
            else:
                try:
                    position = int(position)
                except ValueError:
                    github_position = 'bottom'
                else:
                    if position == 1:
                        github_position = 'top'
                    else:
                        going_down = self.direction.hget() == '1'
                        if going_down:
                            position_filter = 'position__lte'
                        else:
                            position_filter = 'position__lt'
                        sibling_card = column.cards.filter(**{position_filter:position}).exclude(id=card.id).order_by('-position').first()
                        if not sibling_card:
                            github_position = 'top'
                        else:
                            github_position = 'after:%s' % sibling_card.github_id

            # we can now move the card
            data = {
                'position': github_position,
                'column_id': column.github_id
            }

            # now we can ask github to do the move
            card.dist_edit(gh, mode='create', fields=data.keys(), values=data,
                           meta_base_name='moves', update_object=False)

        # now we have to update the projects
        self.project.repository.fetch_all_projects(gh)
