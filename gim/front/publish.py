from operator import itemgetter
from threading import local

from gim.core import models as core_models
from gim.ws import publisher

thread_data = local()


def unify_messages(store, topic, *args, **kwargs):
    """Keep only the last message for a topic/instance each time we receive one in the store"""

    store['__order__'] = store.get('__order__', 0) + 1

    message = {
        'message': {
            'topic': topic,
            'args': args,
            'kwargs': kwargs,
        },
        'order': store['__order__']
    }

    if 'model' in kwargs and 'id' in kwargs:
        model, pk = kwargs['model'], kwargs['id']
        store.setdefault('__instances__', {}).setdefault(model, {})

        # If it's the first time, we register the 'previous hash'
        if pk not in store.setdefault('__hashes__', {}).setdefault(model, {}):
            # Store the previous hash, or None
            store['__hashes__'][model][pk] = kwargs.get('previous_hash', None)

        # Else, we check if we have the same hash as the original one
        elif store['__hashes__'][model][pk] is not None and kwargs.get('hash') == store['__hashes__'][model][pk]:
            # In this case we skip the message, because we're back to the original
            message = None
            # And we don't send the stored message either
            if pk in store['__instances__'][model]:
                del store['__instances__'][model][pk]

        # We are allowed to store the message (because no hash or the hash is not the original one)
        if message:
            store['__instances__'][model].setdefault(pk, {})[topic] = message

    else:
        # Not an instance, we store the message (but avoid duplication)
        store.setdefault('__others__', {})[hash(frozenset(message['message']))] = message


def send_unified_messages(store):
    if not store:
        return

    messages = []
    for model in store.get('__instances__', {}):
        for pk in store['__instances__'][model]:
            messages.extend(store['__instances__'][model][pk].values())
    messages.extend(store.get('__others__', {}).values())

    for container in sorted(messages, key=itemgetter('order')):
        message = container['message']
        publisher.publish(
            topic=message['topic'],
            repository_id=message['kwargs'].pop('repository_id', None),
            *message['args'],
            **message['kwargs']
        )


PUBLISHABLE = {
    core_models.IssueComment: {
        'self': False,
        'parents': [
            ('Issue', 'issue', lambda self: [self.issue_id], None),
        ],
    },
    core_models.PullRequestComment: {
        'self': False,
        'parents': [
            ('Issue', 'issue', lambda self: [self.issue_id], None),
        ],
    },
    core_models.CommitComment: {
        'self': False,
        'parents': [
            ('Issue', 'issues',
             lambda self: self.commit.issues.all().select_related('commit', 'repository__owner'),
             lambda self, issue: {'url': str(self.get_absolute_url_for_issue(issue))}
             ),
        ],
    },
    core_models.PullRequestReview: {
        'self': False,
        'parents': [
            ('Issue', 'issue', lambda self: [self.issue_id], None),
        ],
    },
    # core_models.Commit: {
    #     'self': False,
    #     'parents': [
    #         ('Issue', 'issues',
    #          lambda self: self.issues.all().select_related('repository__owner'),
    #          lambda self, issue: {'url': self.get_absolute_url_for_issue(issue)}
    #          ),
    #     ],
    # },
    core_models.Issue: {
        'self': True,
        'pre_publish_action': lambda self: setattr(self, 'signal_hash_changed', self.hash_changed()),
        'more_data': lambda self: {'is_pr': self.is_pull_request, 'number': self.number}
    },
    core_models.Card: {
        'self': True,
        'pre_publish_action': lambda self: setattr(self.issue, 'signal_hash_changed', self.issue.hash_changed()) if self.issue_id else None,
        'more_data': lambda self: {
            'project_number': self.column.project.number,
            'column_id': self.column_id,
            'position': self.position,
            'url': self.get_absolute_url(),
            'issue': {  # used by the front if the issue needs to be fetched when the card changed, for example a change of column
                        # model and front_uuid will be set by the front
                'id': self.issue.id,
                'url': str(self.issue.get_websocket_data_url()),
                'hash': self.issue.saved_hash,
                'is_new': getattr(self.issue, 'is_new', False),
                'is_pr': self.issue.is_pull_request,
                'number': self.issue.number,
            } if self.issue_id else None,
        }
    },
    core_models.Column: {
        'self': True,
        'more_data': lambda self: {
            'project_number': self.project.number,
            'position': self.position,
            'name': self.name,
            'url': str(self.get_absolute_url()),
        }
    },
    core_models.Project: {
        'self': True,
        'more_data': lambda self: {
            'name': self.name,
            'number': self.number,
            'url': str(self.get_absolute_url()),
            'nb_columns': self.columns.count(),
        }
    },
    # core_models.Repository: {
    #     'self': True,
    # },
}
PUBLISHABLE_MODELS = tuple(PUBLISHABLE.keys())


def publish_update(instance, message_type, extra_data=None):
    """Publish a message when something happen to an instance."""

    conf = PUBLISHABLE[instance.__class__]

    try:
        previous_saved_hash = instance.saved_hash
    except Exception:
        previous_saved_hash = None

    if conf.get('pre_publish_action'):
        conf['pre_publish_action'](instance)

    # try:
    #     from pprint import pformat
    #     extra_data['hashable_values'] = pformat(instance.hash_values)
    # except Exception:
    #     pass
    # try:
    #     extra_data["github_status"] = instance.get_github_status_display()
    # except Exception:
    #     pass

    base_data = {
        'model': str(instance.model_name),
        'id': str(instance.pk),
    }
    if 'more_data' in conf:
        base_data.update(conf['more_data'](instance))
    if extra_data:
        base_data.update(extra_data)

    try:
        base_data['hash'] = instance.saved_hash
        if previous_saved_hash != base_data['hash']:
            base_data['previous_hash'] = previous_saved_hash
    except Exception:
        pass

    if isinstance(instance, core_models.Repository):
        repository_id = instance.pk
    else:
        repository_id = getattr(instance, 'repository_id', None)

    if getattr(instance, 'front_uuid', None):
        base_data['front_uuid'] = str(instance.front_uuid)

    try:
        if hasattr(instance, 'get_websocket_data_url'):
            base_data['url'] = str(instance.get_websocket_data_url())
        else:
            base_data['url'] = str(instance.get_absolute_url())
    except Exception:
        pass

    parents = [
        (
            model_name,
            str(getattr(obj, 'pk', obj)),
            field_name,
            dict(base_data, **more_data(instance, obj)) if more_data else base_data
        )
        for model_name, field_name, get_objects, more_data
        in conf.get('parents', [])
        for obj in get_objects(instance)
    ]

    to_publish = [
        (
            'front.Repository.%(repository_id)s.model.%(message_type)s.isRelatedTo.%(parent_model)s.%(parent_id)s',
            'front.model.%(message_type)s.isRelatedTo.%(parent_model)s.%(parent_id)s',
            dict(
                parent_model=parent_model,
                parent_id=parent_id,
                parent_field=parent_field,
                **parent_data
            )
        )
        for (parent_model, parent_id, parent_field, parent_data)
        in parents
    ]

    if conf.get('self'):
        to_publish += [
            (
                'front.Repository.%(repository_id)s.model.%(message_type)s.is.%(model)s.%(id)s',
                'front.model.%(message_type)s.is.%(model)s.%(id)s',
                base_data
            )
        ]

    for topic_with_repo, topic_without_repo, data in to_publish:
        message_repository_id = repository_id
        if data.get('parent_model', 'None') == 'Repository' and data['parent_field'] == 'repository':
            message_repository_id = data['parent_id']

        topic = topic_with_repo if message_repository_id else topic_without_repo

        publisher.publish(
            topic=topic % dict(
                message_type=message_type, repository_id=message_repository_id, **data),
            repository_id=message_repository_id,
            **data
        )

    # If we published about an issue that have some notifications, publish the notifications
    issue_to_notif = None
    if isinstance(instance, core_models.Issue):
        issue_to_notif = instance
    else:
        for topic_with_repo, topic_without_repo, data in to_publish:
            if data.get('parent_model') == 'Issue':
                try:
                    issue_to_notif = core_models.Issue.objects.get(id=data['parent_id'])
                except core_models.Issue.DoesNotExist:
                    pass
    if issue_to_notif:
        issue_to_notif.publish_notifications()

    # No we can remove the front_uuid field and the is_new flag
    if hasattr(instance, 'is_new'):
        del instance.is_new
    if getattr(instance, 'front_uuid', None) and not getattr(instance, 'skip_reset_front_uuid', False):
        instance.front_uuid = None
        from .models import FrontEditable
        if instance.pk and FrontEditable.isinstance(instance):
            instance.clear_front_uuid()
