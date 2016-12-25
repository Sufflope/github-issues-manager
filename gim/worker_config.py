import django

from limpyd_jobs.workers import WorkerConfig


class GimWorkerConfig(WorkerConfig):
    def __init__(self, argv=None):
        django.setup()
        super(GimWorkerConfig, self).__init__(argv)
