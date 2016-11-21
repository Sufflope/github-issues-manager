__all__ = [
    'ManageDeletedInstancesJob',
]

from random import randint

from gim.core.limpyd_models import DeletedInstance
from gim.core.tasks.base import Job


class ManageDeletedInstancesJob(Job):
    queue_name = 'manage-deleted-instances'

    def run(self, queue):
        super(ManageDeletedInstancesJob, self).run(queue)

        DeletedInstance.manage_undeleted()
        DeletedInstance.clear_old()

    def on_success(self, queue, result):
        """ Clean again in 30s +- 10 """

        self.clone(delayed_for=20 + randint(0, 20))
