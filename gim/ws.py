import json
import logging
import re
import time
import uuid
from itertools import chain

import txredisapi as txredis

from autobahn.twisted.util import sleep as txsleep
from crossbarhttp import Client
from redis.exceptions import LockError
from redis.lock import Lock
from twisted.internet.defer import inlineCallbacks, returnValue

from limpyd import model as lmodel, fields as lfields
from limpyd_extensions.dynamic.model import ModelWithDynamicFieldMixin
from limpyd_extensions.dynamic.fields import DynamicSortedSetField

from django.conf import settings
from django.core.signing import Signer
from django.utils.functional import cached_property

from gim import hashed_version
from gim.core import get_main_limpyd_database


signer = Signer(salt='wamp-signer:%s' % hashed_version)


logger = logging.getLogger('gim.ws')

TOPIC_TYPE_EXACT = 'exact'
TOPIC_TYPE_PREFIX = 'prefix'
TOPIC_TYPE_WILDCARD = 'wildcard'


def sign(value):
    return signer.sign('%s' % value).split(':', 1)[1]


def serialize(msg_id, topic, *args, **kwargs):
    return json.dumps({
        'msg_id': msg_id,
        'topic': topic,
        'args': args,
        'kwargs': kwargs,
    })


def normalize_topic(topic):
    if not topic.startswith('gim.'):
        topic = 'gim.' + topic
    return topic


def add_ws_extra_details(kwargs, topic, msg_id):
    kwargs['ws_extra'] = {
        'topic': topic,
        'msg_id': msg_id,
    }


def prepare_rules(rules):
    if not rules:
        return rules

    if isinstance(rules, dict):
        # already prepared
        return rules

    normalized_rules = {
        TOPIC_TYPE_EXACT: [],
        TOPIC_TYPE_PREFIX: [],
        TOPIC_TYPE_WILDCARD: [],
    }

    for topic, topic_type in rules:
        if topic_type == TOPIC_TYPE_WILDCARD:
            # The rule is a regex to check a topic
            pattern = topic.replace('.', r'\.').replace(r'\.\.', r'\.[^\.]+\.')
            start = r'^[^\.]+' if topic.startswith('.') else '^'
            end = r'[^\.]+$' if topic.endswith('.') else '$'
            rule = re.compile(start + pattern + end)
        else:
            rule = topic
        # Get the original, and the rule
        normalized_rules[topic_type].append((topic, rule))

    return normalized_rules


def restrict_topics(all_topics, rules):
    if rules is None:
        return {topic:[] for topic in all_topics}

    if not rules:
        return {}

    rules = prepare_rules(rules)

    valid_topics = {}
    for topic in all_topics:
        for original_topic, rule_topic in rules[TOPIC_TYPE_EXACT]:
            if topic == rule_topic:
                valid_topics.setdefault(topic, []).append((original_topic, TOPIC_TYPE_EXACT))

        for original_topic, rule_prefix in rules[TOPIC_TYPE_PREFIX]:
            if topic.startswith(rule_prefix):
                valid_topics.setdefault(topic, []).append((original_topic, TOPIC_TYPE_PREFIX))

        for original_topic, rule_regex in rules[TOPIC_TYPE_WILDCARD]:
            if rule_regex.search(topic):
                valid_topics.setdefault(topic, []).append((original_topic, TOPIC_TYPE_WILDCARD))

    return valid_topics


def prepare_zrangebyscore_bounds(first_msg_id, last_msg_id):
    return (
        '-inf' if first_msg_id is None else first_msg_id,
        '+inf' if last_msg_id is None else last_msg_id,
    )


class HistoryMixin(ModelWithDynamicFieldMixin, lmodel.RedisModel):
    namespace = 'ws2'  # `2` for protocol version number
    database = get_main_limpyd_database()
    abstract = True

    pk = lfields.PKField()
    messages = DynamicSortedSetField()
    last_msg_id = lfields.StringField()
    last_msg_id_sent = lfields.StringField()

    auto_inc_msg_id = False

    @classmethod
    def get_for(cls, source_pk, async=False):
        source_pk = str(source_pk)
        if async:
            obj = cls.lazy_connect(pk=source_pk)
        else:
            obj = cls.get_or_connect(pk=source_pk)[0]

        return obj

    def all_topics(self):
        return self.messages._inventory.smembers()

    def save_message(self, msg_id, topic, *args, **kwargs):
        """Add the message in the list of messages for this topic."""
        message = serialize(msg_id, topic, *args, **kwargs)
        self.messages.get_for(topic).zadd(msg_id, message)
        if not self.auto_inc_msg_id:
            self.last_msg_id.set(msg_id)

    def get_last_msg_id(self):
        """Return the last used message id."""
        return int(self.last_msg_id.get() or 0)

    def get_new_msg_id(self):
        """Increment in redis and get the new ``last_msg_id`` value."""
        return int(self.last_msg_id.incr())

    def get_last_msg_id_sent(self):
        """Return the last used message id."""
        return int(self.last_msg_id_sent.get() or 0)

    def save_last_sent_message(self, msg_id):
        self.last_msg_id_sent.set(msg_id)

    def get_messages(self, first_msg_id=None, last_msg_id=None, topics_rules=None):
        if first_msg_id is not None and last_msg_id is not None and first_msg_id > last_msg_id:
            return []

        all_topics = self.all_topics()
        topics = sorted(restrict_topics(all_topics, topics_rules).items())

        if not topics:
            return []

        first, last = prepare_zrangebyscore_bounds(first_msg_id, last_msg_id)

        with self.database.pipeline() as pipeline:
            for topic, __ in topics:
                self.messages.get_for(topic).zrangebyscore(first, last, withscores=True)
            pipeline_result = pipeline.execute()

        messages = []
        for index, topic_rule in enumerate(topics):
            topic_messages = pipeline_result[index]
            messages += [
                (int(msg_id), json.loads(message) , topic_rule[0], topic_rule[1])
                for message, msg_id in topic_messages
            ]

        return sorted(messages)

    def get_all_message_ids(self):

        all_topics = self.all_topics()
        first, last = prepare_zrangebyscore_bounds(None, None)

        with self.database.pipeline() as pipeline:
            for topic in all_topics:
                self.messages.get_for(topic).zrangebyscore(first, last, withscores=True)
            pipeline_result = pipeline.execute()

        ids = []
        for index, topic_rule in enumerate(all_topics):
            ids += [int(msg_id) for message, msg_id in pipeline_result[index]]

        return ids

    def clean(self, min_msg_id_to_keep):
        all_topics = self.all_topics()
        with self.database.pipeline() as pipeline:
            for topic in all_topics:
                self.messages.get_for(topic).zremrangebyscore(0, '(%s' % min_msg_id_to_keep)
            return sum(pipeline.execute()) if all_topics else 0


class AsyncHistoryMixin(object):

    redis_connection = None

    source_model = None

    def __init__(self):
        self.source_object = None
        self.connect_redis()

    @classmethod
    @inlineCallbacks
    def get_for(cls, source_pk, pipeline=None, **kwargs):
        obj = cls(**kwargs)
        obj.source_object = cls.source_model.get_for(source_pk, async=True)
        if pipeline:
            pipeline.sadd(obj.source_object.pk.collection_key, [source_pk])
        else:
            yield cls.redis_connection.sadd(obj.source_object.pk.collection_key, [source_pk])
        returnValue(obj)

    @classmethod
    def connect_redis(cls):
        if not getattr(cls, 'redis_connection', None):
            cls.redis_connection = txredis.lazyConnection(
                host=settings.LIMPYD_DB_CONFIG['host'],
                port=settings.LIMPYD_DB_CONFIG['port'],
                dbid=settings.LIMPYD_DB_CONFIG['db'],
            )

    @inlineCallbacks
    def all_topics(self):
        topics = yield self.redis_connection.smembers(self.source_object.messages._inventory.key)
        returnValue(topics)

    @inlineCallbacks
    def save_message(self, msg_id, topic, *args, **kwargs):
        """Add the message in the list of messages for this topic."""
        pipeline = kwargs.pop('pipeline', None)

        message = serialize(msg_id, topic, *args, **kwargs)

        if pipeline:
            pipeline.sadd(self.source_object.messages._inventory.key, [topic])
            pipeline.zadd(self.source_object.messages.get_for(topic).key, msg_id, message)
            if not self.source_object.auto_inc_msg_id:
                pipeline.set(self.source_object.last_msg_id.key, msg_id)
        else:
            yield self.redis_connection.sadd(self.source_object.messages._inventory.key, [topic])
            yield self.redis_connection.zadd(self.source_object.messages.get_for(topic).key,
                                             msg_id, message)
            if not self.source_object.auto_inc_msg_id:
                yield self.redis_connection.set(self.source_object.last_msg_id.key, msg_id)

    @inlineCallbacks
    def get_last_msg_id(self):
        msg_id = yield self.redis_connection.get(self.source_object.last_msg_id.key)
        returnValue(int(msg_id or 0))

    @inlineCallbacks
    def get_new_msg_id(self):
        """Increment in redis and get the new ``last_msg_id`` value."""
        msg_id = yield self.redis_connection.incr(self.source_object.last_msg_id.key)
        returnValue(int(msg_id))

    @inlineCallbacks
    def get_last_msg_id_sent(self):
        """Return the last used message id."""
        msg_id = yield self.redis_connection.get(self.source_object.last_msg_id_sent.key)
        returnValue(int(msg_id or 0))

    @inlineCallbacks
    def save_last_sent_message(self, msg_id, pipeline=None):
        if pipeline:
            pipeline.set(self.source_object.last_msg_id_sent.key, msg_id)
        else:
            yield self.redis_connection.set(self.source_object.last_msg_id_sent.key, msg_id)

    @inlineCallbacks
    def get_messages(self, first_msg_id=None, last_msg_id=None, topics_rules=None):
        if first_msg_id is not None and last_msg_id is not None and first_msg_id > last_msg_id:
            returnValue([])

        all_topics = yield self.all_topics()
        topics = sorted(restrict_topics(all_topics, topics_rules).items())

        if not topics:
            returnValue([])

        first, last = prepare_zrangebyscore_bounds(first_msg_id, last_msg_id)

        pipeline = yield self.redis_connection.multi()
        for topic, __ in topics:
            pipeline.zrangebyscore(self.source_object.messages.get_for(topic).key, first, last,
                                   withscores=True)
        pipeline_result = yield pipeline.commit()

        messages = []
        for index, topic_rule in enumerate(topics):
            topic_messages = pipeline_result[index]
            topic_messages = zip(topic_messages[::2], topic_messages[1::2])
            messages += [
                (int(msg_id) , json.loads(message), topic_rule[0], topic_rule[1])
                for message, msg_id in topic_messages
            ]

        returnValue(sorted(messages))

    @inlineCallbacks
    def get_all_message_ids(self):

        all_topics = yield self.all_topics()
        first, last = prepare_zrangebyscore_bounds(None, None)

        pipeline = yield self.redis_connection.multi()
        for topic in all_topics:
            pipeline.zrangebyscore(self.source_object.messages.get_for(topic).key, first, last,
                                   withscores=True)
        pipeline_result = yield pipeline.commit()

        ids = []
        for index, topic_rule in enumerate(all_topics):
            ids += map(int, pipeline_result[index][1::2])

        returnValue(ids)

    @inlineCallbacks
    def delete(self):
        # If we were in sync mode it would be simple: ``self.source_object.delete()``
        # In async mode, we don't have limpyd so we have to do it all ourselves

        repository = self.source_object
        topics = yield self.all_topics()

        # We remove all the keys related to the repository
        self.redis_connection.delete([
            repository.last_msg_id.key,
            repository.last_msg_id_sent.key,
            repository.messages.key,
        ] + [
            repository.messages.get_for(topic).key for topic in topics
        ])

        # And we remove the repository from the repositories collection
        yield self.redis_connection.srem(repository.pk.collection_key, [int(repository._pk)])


class RepositoryHistory(HistoryMixin, ModelWithDynamicFieldMixin, lmodel.RedisModel):
    pass


class AsyncRepositoryHistory(AsyncHistoryMixin):
    source_model = RepositoryHistory


class Publisher(HistoryMixin, lmodel.RedisModel):

    # To know the repository (value) for each msg_id (score)
    repositories = lfields.SortedSetField()

    PK = 1
    auto_inc_msg_id = True

    @classmethod
    def get_for(cls, source_pk=None, async=False):
        return super(Publisher, cls).get_for(cls.PK, async)

    @classmethod
    def singleton(cls):
        if not hasattr(cls, '_singleton'):
            cls._singleton = cls.get_for(async=True)
        return cls._singleton

    def save_message(self, topic, repository_id=None, *args, **kwargs):
        """Add the message as the last one in the list of messages."""
        msg_id = self.get_new_msg_id()

        if repository_id:
            obj = RepositoryHistory.get_for(repository_id)
        else:
            obj = super(Publisher, self)

        with self.database.pipeline() as pipeline:
            obj.save_message(msg_id, topic, *args, **kwargs)
            # Save for empty repository if no pk
            self.repositories.zadd(msg_id, '%s:%s' % (msg_id, repository_id or ''))

            pipeline.execute()

        return msg_id

    @cached_property
    def http_client(self):
        return Client("%(host)s:%(port)s/ws-publish" % {
            'host': settings.CROSSBAR_REST_HOST,
            'port': settings.CROSSBAR_REST_PORT,
        }, key=settings.CROSSBAR_REST_KEY, secret=settings.CROSSBAR_REST_SECRET)

    def send_message(self, msg_id, topic, repository_id=None, *args, **kwargs):
        try:
            publish_result = self.http_client.publish(topic, *args, **kwargs)
        except Exception:
            raise
        else:
            with self.database.pipeline() as pipeline:
                self.save_last_sent_message(msg_id)
                if repository_id:
                    RepositoryHistory.get_for(repository_id).save_last_sent_message(msg_id)
                pipeline.execute()
            return publish_result

    def send_messages(self, messages):
        for msg_id, topic, repository, args, kwargs in messages:
            add_ws_extra_details(kwargs, topic, msg_id)
            try:
                self.send_message(msg_id, topic, repository, *args, **kwargs)
            except Exception:
                logger.exception('Message %d could not be sent on %s (repo %s)', msg_id, topic,
                                 repository)
            else:
                logger.info('Message %d sent on %s (repo %s)', msg_id, topic, repository)

    @property
    def lock_key(self):
        return self.make_key(
            self._name,
            self.PK,
            "lock",
        )

    def lock_publishing(self, **kwargs):
        if 'sleep' not in kwargs:
            kwargs['sleep'] = 0.001
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 10
        return Lock(self.database.connection, self.lock_key, **kwargs)

    def publish(self, topic, repository_id=None, *args, **kwargs):

        topic = normalize_topic(topic)

        # Tell other publish to wait until we're done here
        with self.lock_publishing():

            # Sent unsent messages if any
            self.send_unsent_messages()

            # Prepare message to send
            msg_id = self.save_message(topic, repository_id, *args, **kwargs)

            # We can now send our message
            self.send_messages([
                (msg_id, topic, repository_id, args, kwargs)
            ])

        return msg_id

    def get_unsent_bounds(self):
        last_msg_id = self.get_last_msg_id()
        last_msg_id_sent = self.get_last_msg_id_sent()
        return last_msg_id_sent+1, last_msg_id

    def send_unsent_messages(self):

        first_msg_id, last_msg_id = self.get_unsent_bounds()

        if first_msg_id > last_msg_id:
            return

        # We have old messages to send
        logger.warning('Send unsent message from %d to %d', first_msg_id, last_msg_id)

        messages = self.get_messages(first_msg_id, last_msg_id)

        self.send_messages([
            (msg_id, topic, repository, message['args'], message['kwargs'])
            for msg_id, message, topic, topic_rules, repository
            in messages
        ])

    def get_messages(self, first_msg_id=None, last_msg_id=None, topics_rules=None):
        if first_msg_id is not None and last_msg_id is not None and first_msg_id > last_msg_id:
            return []

        topics_rules = prepare_rules(topics_rules)

        first, last = prepare_zrangebyscore_bounds(first_msg_id, last_msg_id)
        touched = self.repositories.zrangebyscore(first, last)
        repositories = set(val.split(':')[1] for val in touched) - {''}

        publisher_messages = super(Publisher, self).get_messages(first_msg_id, last_msg_id,
                                                                 topics_rules)

        messages = [
            (msg_id, message, topic, topic_rules, None)
            for msg_id, message, topic, topic_rules
            in publisher_messages
        ]

        if repositories:
            messages += [
                (msg_id, message, topic, topic_rules, repository)
                for repository in repositories
                for msg_id, message, topic, topic_rules
                in RepositoryHistory.get_for(repository).get_messages(first_msg_id, last_msg_id,
                                                                      topics_rules)
            ]

        return sorted(messages)

    def remove_repository(self, repository_id):
        repository = RepositoryHistory.get_for(repository_id)

        # We'll need all the msg ids used for this repository, to replace them in the main
        # ``repositories`` hash of the publisher
        ids = repository.get_all_message_ids()

        # No we can do the replacement
        with self.database.pipeline() as pipeline:
            # Remove the old entries
            self.repositories.zrem(*['%s:%s' % (id, repository_id) for id in ids])
            # Add then them without the repository part
            self.repositories.zadd(**{('%s:' % id): id for id in ids})

            pipeline.execute()

        # And then we can delete all stored messages for this repository
        repository.delete()

    def clean(self, min_msg_id_to_keep):
        super(Publisher, self).clean(min_msg_id_to_keep)

        touched = self.repositories.zrangebyscore(0, '(%s' % min_msg_id_to_keep)
        repositories = set(val.split(':')[1] for val in touched) - {''}

        for repository_id in repositories:
            RepositoryHistory.get_for(repository_id).clean(min_msg_id_to_keep)

        return self.repositories.zremrangebyscore(0, '(%s' % min_msg_id_to_keep)


class AsyncPublisher(AsyncHistoryMixin):

    source_model = Publisher

    def __init__(self, app):
        super(AsyncPublisher, self).__init__()
        self.app = app

    @classmethod
    @inlineCallbacks
    def get_for(cls, source_pk=None, pipeline=None, **kwargs):
        obj = yield super(AsyncPublisher, cls).get_for(cls.source_model.PK, pipeline=pipeline,
                                                       **kwargs)
        returnValue(obj)


    @inlineCallbacks
    def save_message(self, topic, repository_id=None, *args, **kwargs):
        """Add the message as the last one in the list of messages."""
        msg_id = yield self.get_new_msg_id()

        pipeline = yield self.redis_connection.multi()

        if repository_id:
            obj = yield AsyncRepositoryHistory.get_for(repository_id, pipeline=pipeline)
        else:
            obj = super(AsyncPublisher, self)

        obj.save_message(msg_id, topic, pipeline=pipeline, *args, **kwargs)
        # Save for empty repository if no pk
        pipeline.zadd(self.source_object.repositories.key, msg_id,
                      '%s:%s' % (msg_id, repository_id or ''))

        yield pipeline.commit()

        returnValue(msg_id)

    @inlineCallbacks
    def send_message(self, msg_id, topic, repository_id=None, *args, **kwargs):
        try:
            publish_result = yield self.app.publish(topic, *args, **kwargs)
        except Exception:
            raise
        else:
            pipeline = yield self.redis_connection.multi()
            self.save_last_sent_message(msg_id, pipeline=pipeline)
            if repository_id:
                obj = yield AsyncRepositoryHistory.get_for(repository_id, pipeline=pipeline)
                yield obj.save_last_sent_message(msg_id, pipeline=pipeline)
            yield pipeline.commit()
            returnValue(publish_result)

    @inlineCallbacks
    def send_messages(self, messages):
        for msg_id, topic, repository, args, kwargs in messages:
            add_ws_extra_details(kwargs, topic, msg_id)
            try:
                yield self.send_message(msg_id, topic, repository, *args, **kwargs)
            except Exception:
                logger.exception('Message %d could not be sent on %s (repo %s)', msg_id, topic,
                                 repository)
            else:
                logger.info('Message %d sent on %s (repo %s)', msg_id, topic, repository)

    @property
    def lock_key(self):
        return self.source_object.lock_key

    def lock_publishing(self, **kwargs):
        if 'sleep' not in kwargs:
            kwargs['sleep'] = 0.001
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 10
        return txLock(self.redis_connection, self.lock_key, **kwargs)

    @inlineCallbacks
    def publish(self, topic, repository_id=None, *args, **kwargs):

        topic = normalize_topic(topic)

        # Tell other publish to wait until we're done here
        lock = self.lock_publishing()

        yield lock.acquire()
        try:
            # Sent unsent messages if any
            yield self.send_unsent_messages()

            # Prepare message to send
            msg_id = yield self.save_message(topic, repository_id, *args, **kwargs)
            add_ws_extra_details(kwargs, topic, msg_id)

            # We can now send our message
            yield self.send_messages([
                (msg_id, topic, repository_id, args, kwargs)
            ])
        finally:
            yield lock.release()

        returnValue(msg_id)

    @inlineCallbacks
    def get_unsent_bounds(self):
        last_msg_id = yield self.get_last_msg_id()
        last_msg_id_sent = yield self.get_last_msg_id_sent()
        returnValue((last_msg_id_sent+1, last_msg_id))

    @inlineCallbacks
    def send_unsent_messages(self):

        first_msg_id, last_msg_id = yield self.get_unsent_bounds()

        if first_msg_id > last_msg_id:
            return

        # We have old messages to send
        logger.warning('Send unsent message from %d to %d', first_msg_id, last_msg_id)

        messages = yield self.get_messages(first_msg_id, last_msg_id)

        yield self.send_messages([
            (msg_id, topic, repository, message['args'], message['kwargs'])
            for msg_id, message, topic, topic_rules, repository
            in messages
        ])

    @inlineCallbacks
    def get_messages(self, first_msg_id=None, last_msg_id=None, topics_rules=None):
        if first_msg_id is not None and last_msg_id is not None and first_msg_id > last_msg_id:
            returnValue([])

        topics_rules = prepare_rules(topics_rules)

        first, last = prepare_zrangebyscore_bounds(first_msg_id, last_msg_id)
        touched = yield self.redis_connection.zrangebyscore(self.source_object.repositories.key,
                                                            first, last)
        repositories = set(val.split(':')[1] for val in touched) - {''}

        publisher_messages = yield super(AsyncPublisher, self).get_messages(first_msg_id,
                                                                            last_msg_id,
                                                                            topics_rules)
        messages = [
            (msg_id, message, topic, topic_rules, None)
            for msg_id, message, topic, topic_rules
            in publisher_messages
        ]

        if repositories:
            for repository in repositories:
                obj = yield AsyncRepositoryHistory.get_for(repository)
                repository_messages = yield obj.get_messages(first_msg_id, last_msg_id,
                                                             topics_rules)
                messages += [
                    (msg_id, message, topic, topic_rules, repository)
                    for msg_id, message, topic, topic_rules
                    in repository_messages
                ]

        returnValue(sorted(messages))

    @inlineCallbacks
    def remove_repository(self, repository_id):
        repository = yield AsyncRepositoryHistory.get_for(repository_id)

        # We'll need all the msg ids used for this repository, to replace them in the main
        # ``repositories`` hash of the publisher
        ids = yield repository.get_all_message_ids()

        # No we can do the replacement
        pipeline = yield self.redis_connection.multi()
        # Remove the old entries
        pipeline.zrem(self.source_object.repositories.key,
                      *['%s:%s' % (id, repository_id) for id in ids])
        # Add then them without the repository part
        pipeline.zadd(self.source_object.repositories.key,
                      *chain.from_iterable((id, '%s:' % id) for id in ids))

        pipeline.commit()

        # And then we can delete all stored messages for this repository
        yield repository.delete()


class txLock(object):
    """
    A shared, distributed Lock. Using Redis for locking allows the Lock
    to be shared across processes and/or machines.

    It's left to the user to resolve deadlock issues and make sure
    multiple clients play nicely together.
    """
    def __init__(self, redis, name, timeout=None, sleep=0.1,
                 blocking=True, blocking_timeout=None):
        """
        Adaptation of redis-py Lock class to use with txredisapi.
        Notes:
            - does not provide the threading local token management
            - does not provide the extend api
            - release simply remove the key

        It's not available as a context manager. You should use it this way:

        >>> lock = txLock(redis, 'test-lock')
        >>> yield lock.acquire()
        >>> try:
        >>>     yield do_stuff()
        >>> finally:
            >>> yield lock.release()

        Original documentation:

        Create a new Lock instance named ``name`` using the Redis client
        supplied by ``redis``.

        ``timeout`` indicates a maximum life for the lock.
        By default, it will remain locked until release() is called.
        ``timeout`` can be specified as a float or integer, both representing
        the number of seconds to wait.

        ``sleep`` indicates the amount of time to sleep per loop iteration
        when the lock is in blocking mode and another client is currently
        holding the lock.

        ``blocking`` indicates whether calling ``acquire`` should block until
        the lock has been acquired or to fail immediately, causing ``acquire``
        to return False and the lock not being acquired. Defaults to True.
        Note this value can be overridden by passing a ``blocking``
        argument to ``acquire``.

        ``blocking_timeout`` indicates the maximum amount of time in seconds to
        spend trying to acquire the lock. A value of ``None`` indicates
        continue trying forever. ``blocking_timeout`` can be specified as a
        float or integer, both representing the number of seconds to wait.
        """
        self.redis = redis
        self.name = name
        self.timeout = timeout
        self.sleep = sleep
        self.blocking = blocking
        self.blocking_timeout = blocking_timeout
        if self.timeout and self.sleep > self.timeout:
            raise LockError("'sleep' must be less than 'timeout'")

    @inlineCallbacks
    def acquire(self, blocking=None, blocking_timeout=None):
        """
        Use Redis to hold a shared, distributed lock named ``name``.
        Returns True once the lock is acquired.

        If ``blocking`` is False, always return immediately. If the lock
        was acquired, return True, otherwise return False.

        ``blocking_timeout`` specifies the maximum number of seconds to
        wait trying to acquire the lock.
        """
        sleep = self.sleep
        token = str(uuid.uuid1().hex)
        if blocking is None:
            blocking = self.blocking
        if blocking_timeout is None:
            blocking_timeout = self.blocking_timeout
        stop_trying_at = None
        if blocking_timeout is not None:
            stop_trying_at = time.time() + blocking_timeout
        returned = False
        while not returned:
            returned = True
            acquired = yield self.do_acquire(token)
            if acquired:
                returnValue(True)
            if not blocking:
                returnValue(False)
            if stop_trying_at is not None and time.time() > stop_trying_at:
                returnValue(False)
            returned = False
            yield txsleep(sleep)

    @inlineCallbacks
    def do_acquire(self, token):
        value_set = yield self.redis.setnx(self.name, token)
        if value_set:
            if self.timeout:
                # convert to milliseconds
                timeout = int(self.timeout * 1000)
                # "pexpire" not supported by txredisapi
                # yield self.redis.pexpire(self.name, timeout)
                yield self.redis.execute_command('PEXPIRE', self.name, timeout)
            returnValue(True)
        returnValue(False)

    @inlineCallbacks
    def release(self):
        """Releases the already acquired lock"""
        name = self.name
        yield self.redis.delete(name)


class Reconciler(object):
    def __init__(self, publisher):
        self.publisher = publisher

    def limit_rules(self, topics_rules):
        return set([
            (topic, match_type)
            for topic, match_type
            in topics_rules
            if topic.startswith('gim.front.') and not topic.startswith('gim.front..') and (
                match_type in (TOPIC_TYPE_EXACT, TOPIC_TYPE_PREFIX) or
                match_type == TOPIC_TYPE_WILDCARD and '..' in topic
            )
        ])

    @inlineCallbacks
    def validate_ids(self, last_received_id, next_received_id=None):
        valid_ids = True
        try:
            last_received_id = int(last_received_id)
        except ValueError:
            valid_ids = False
        else:
            try:
                if next_received_id is not None:
                    next_received_id = int(next_received_id)
            except ValueError:
                valid_ids = False
            else:
                if next_received_id is not None and next_received_id <= last_received_id:
                    valid_ids = False

        if not valid_ids:
            logger.warning('Invalid IDs to reconcile: %s, %s', last_received_id, next_received_id)
            returnValue((False, {
                'error': {'message': 'Impossible to retrieve data.', 'code': 'REC0001'}
            }))

        # Check if `last_received_id` is still in hosted data
        data = yield self.publisher.redis_connection.zrangebyscore(
            self.publisher.source_object.repositories.key, last_received_id, last_received_id)
        if not data:
            logger.warning('Not enough message in history to reconcile (from=%s)', last_received_id)
            returnValue((False, {
                'error': {'message': 'You were offline too long.', 'code': 'REC0002'}
            }))

        # Check if `next_received_id` was really sent
        if next_received_id is not None:
            data = yield self.publisher.redis_connection.zrangebyscore(
                self.publisher.source_object.repositories.key, next_received_id, next_received_id)
            if not data:
                logger.warning('Limit up to reconcile is incoherent (next=%s)', next_received_id)
                returnValue((False, {
                    'error': {'message': 'Impossible to retrieve data.', 'code': 'REC0003'}
                }))

        returnValue((True, None))

    def prepare_messages(self, messages):
        missed_messages = []
        for msg_id, message, topic, topics_rules, repository in messages:
            add_ws_extra_details(message['kwargs'], topic, msg_id)
            message['kwargs']['ws_extra']['subscribed'] = topics_rules
            missed_messages.append({
                'args': message['args'],
                'kwargs': message['kwargs'],
            })
        return missed_messages

    @inlineCallbacks
    def get_data(self, last_received_id, next_received_id, topics_rules, iteration):
        topics_rules = self.limit_rules(topics_rules)

        logger.info('Reconciler called with last_received_id=%s, next_received_id=%s, '
                    'topics_rules=%s, iteration=%s',
                    last_received_id, next_received_id, topics_rules, iteration)

        valid, error = yield self.validate_ids(last_received_id, next_received_id)
        if not valid:
            returnValue(error)

        try:
            iteration = int(iteration)
        except ValueError:
            iteration = 1

        if iteration >= 5:
            # At the 5th iterations, we can ask ourselves if we really want to continue forever...
            # So we lock publishing for this iteration, that should be the last one!
            lock = self.publisher.lock_publishing()
            yield lock.acquire()
        else:
            lock = None

        try:

            last_msg_id = yield self.publisher.get_last_msg_id()

            messages = yield self.publisher.get_messages(
                first_msg_id=int(last_received_id)+1,
                last_msg_id=int(next_received_id)-1 if next_received_id else None,
                topics_rules=topics_rules,
            )

            missed_messages = self.prepare_messages(messages)

            if next_received_id:
                # Tell the client that he doesn't need to try to reconcile more: we know he has
                # the data needed after the current reconcile
                max_msg_id = int(next_received_id)
                if last_msg_id > max_msg_id:
                    max_msg_id = last_msg_id
            else:
                # We don't know what is the status of the client, so we can only tell him the last
                # message we could have send him, and he'll have to check if he needs to reconcile more
                if messages:
                    max_msg_id = messages[-1][0]
                    if last_msg_id > max_msg_id:
                        max_msg_id = last_msg_id
                else:
                    max_msg_id = last_msg_id

            # Maybe more messages were posted in the meantime
            # We need to tell the client that maybe more messages were posted, so he'll try a new
            # reconcile. But if a lot of messages are sent, but none to him, it could last forever
            # In case of lock, this should be the same as `last_msg_id`
            final_last_msg_id = yield self.publisher.get_last_msg_id()

        finally:
            if lock:
                yield lock.release()

        returnValue({
            'missed_messages': missed_messages,
            'max_msg_id': max_msg_id,
            'last_msg_id': final_last_msg_id,
            'iteration': iteration,
        })


publisher = Publisher.singleton()
