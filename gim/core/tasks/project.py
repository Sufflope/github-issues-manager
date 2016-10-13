__all__ = [
    'FetchProjects',
]

from random import randint

from gim.core.managers import CardIssueNotAvailable
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
