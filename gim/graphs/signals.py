from datetime import timedelta

from gim.core.models import Issue


def update_graphs_data(sender, instance, created, **kwargs):
    if not isinstance(instance, Issue):
        return
    from gim.graphs.tasks import UpdateGraphsData
    UpdateGraphsData.add_job(instance.repository_id, delayed_for=timedelta(minutes=15))
