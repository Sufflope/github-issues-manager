__all__ = [
    'FetchProjects',
]

from random import randint

from .repository import RepositoryJob


class FetchProjects(RepositoryJob):
    """
    Job that will do an unforced full fetch of the repository projects to update all that
    needs to.
    When done:
    - clone the job to be done again 3 min later (+-30s)
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

        self.repository.fetch_all_projects(gh)

    def on_success(self, queue, result):
        """
        Go fetch again in 3mn +- 30s
        """
        self.clone(delayed_for=int(60 * 2.5) + randint(0, 60 * 1))
