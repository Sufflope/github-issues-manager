from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = 'gim.events'

    def ready(self):
        from .trackers import IssueTracker
        IssueTracker.connect()
