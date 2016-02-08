from threading import local

from limpyd.contrib.database import PipelineDatabase

from django.conf import settings

GITHUB_HOST = 'https://github.com/'

thread_data = local()


def get_main_limpyd_database():
    if not hasattr(thread_data, 'main_limpyd_database'):
        thread_data.main_limpyd_database = PipelineDatabase(**settings.LIMPYD_DB_CONFIG)
    return thread_data.main_limpyd_database
