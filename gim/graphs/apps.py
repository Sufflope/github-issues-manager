from django.apps import AppConfig
from django.db.models.signals import post_save

from gim.core.utils import contribute_to_model


class GraphsConfig(AppConfig):
    name = 'gim.graphs'

    def ready(self):
        from gim.core import models as core_models
        from . import models as graph_models
        from . import signals

        contribute_to_model(graph_models._Repository, core_models.Repository)

        post_save.connect(signals.update_graphs_data, sender=core_models.Issue, dispatch_uid='update_graphs_data', weak=False)
