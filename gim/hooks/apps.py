from django.apps import AppConfig

from gim.core.utils import contribute_to_model


class HooksConfig(AppConfig):
    name = 'gim.hooks'

    def ready(self):
        from gim.core import models as core_models
        from . import models as hooks_models

        contribute_to_model(hooks_models._Repository, core_models.Repository)

