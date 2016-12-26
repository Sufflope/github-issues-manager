from django.db import models


class _Repository(models.Model):
    class Meta:
        abstract = True

    @property
    def graphs(self):
        if not hasattr(self, '_graphs_limpyd_object'):
            from .limpyd_models import GraphData
            self._graphs_limpyd_object, created = GraphData.get_or_connect(repository_id=self.id)
        return self._graphs_limpyd_object


from gim.graphs.tasks import *
