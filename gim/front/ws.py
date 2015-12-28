import json
import logging
import re
import time as mod_time
import uuid

import txredisapi as redis


from autobahn.twisted.util import sleep as txsleep
from crossbarhttp import Client
from limpyd import model as lmodel, fields as lfields
from redis.exceptions import LockError
from redis.lock import Lock
from twisted.internet.defer import inlineCallbacks, returnValue, maybeDeferred

from django.conf import settings
from django.utils.functional import cached_property

from gim.core import get_main_limpyd_database


logger = logging.getLogger('gim.ws')


class NotEnoughHistory(Exception):
    pass


class BaseHistory(object):

    TOPIC_TYPE_EXACT = 'exact'
    TOPIC_TYPE_PREFIX = 'prefix'
    TOPIC_TYPE_WILDCARD = 'wildcard'

    PK = 1

    def prepare_history_entries(self, all_entries, from_msg_id, topics=None, ensure_first=True):
        # If set, ``topics`` is a list of tuples (topic, match)

        if ensure_first and len(all_entries) and all_entries.pop(0)[1] != from_msg_id:
            raise NotEnoughHistory()

        topics_tuples = {}
        if topics and all_entries:

            topics_tuples = {
                self.TOPIC_TYPE_EXACT: [],
                self.TOPIC_TYPE_PREFIX: [],
                self.TOPIC_TYPE_WILDCARD: [],
            }

            for topic, match in topics:
                if match == self.TOPIC_TYPE_WILDCARD:
                    # replace the topic by a tuple with the topic and a regex to check a topic
                    topic = topic, re.compile(
                        '^' + topic.replace('.', r'\.').replace(r'\.\.', r'\.[^\.]+\.') + '$'
                    )
                topics_tuples[match].append(topic)

        entries = []
        for entry, msg_id in all_entries:
            decoded = json.loads(entry)
            decoded_topic = decoded['topic']

            if not topics:
                entries.append((topics, None, decoded, msg_id))
                continue

            for topic in topics_tuples[self.TOPIC_TYPE_EXACT]:
                if topic == decoded_topic:
                    entries.append((topic, self.TOPIC_TYPE_EXACT, decoded, msg_id))
                    # Break as we can only have one exact topic
                    break

            for topic in topics_tuples[self.TOPIC_TYPE_PREFIX]:
                if decoded_topic.startswith(topic):
                    entries.append((topic, self.TOPIC_TYPE_PREFIX, decoded, msg_id))

            for topic, topic_regex in topics_tuples[self.TOPIC_TYPE_WILDCARD]:
                if topic_regex.search(decoded_topic):
                    entries.append((topic, self.TOPIC_TYPE_WILDCARD, decoded, msg_id))

        return entries, (all_entries[-1][1] if all_entries else None)

    @property
    def lock_key(self):
        return self.make_key(
            self._name,
            self.PK,
            "lock",
        )

    @staticmethod
    def add_extra_details(kwargs, topic, msg_id):
        kwargs['ws_extra'] = {
            'topic': topic,
            'msg_id': msg_id,
        }

    @staticmethod
    def serialize(msg_id, topic, *args, **kwargs):
        return json.dumps({
            'msg_id': msg_id,
            'topic': topic,
            'args': args,
            'kwargs': kwargs,
        })

class History(BaseHistory, lmodel.RedisModel):
    database = get_main_limpyd_database()
    namespace = 'ws'

    pk = lfields.PKField()
    last_msg_id = lfields.StringField()
    last_msg_id_sent = lfields.StringField()
    messages = lfields.SortedSetField()

    def __init__(self, *args, **kwargs):
        self.async = kwargs.pop('async', False)

        super(History, self).__init__(*args, **kwargs)

    @classmethod
    def singleton(cls, async=False):
        if async:
            obj = cls(async=True)
            obj._pk = cls.PK
        else:
            obj = cls.get_or_connect(pk=cls.PK)[0]

        return obj

    def get_last_msg_id(self):
        """Return the last used message id."""
        return int(self.last_msg_id.get() or 0)

    def get_new_msg_id(self):
        """Increment in redis and get the new ``last_msg_id`` value."""
        return int(self.last_msg_id.incr())

    def get_last_msg_sent_id(self):
        """Return the last used message id."""
        return int(self.last_msg_id_sent.get() or 0)

    def save_message(self, topic, *args, **kwargs):
        """Add the message as the last one in the list of messages."""
        msg_id = self.get_new_msg_id()
        message = self.serialize(msg_id, topic, *args, **kwargs)
        self.messages.zadd(msg_id, message)
        return msg_id

    def save_last_sent_message(self, msg_id):
        self.last_msg_id_sent.set(msg_id)

    def get_history(self, from_msg_id, topics=None, to_msg_id=None, ensure_first=True):

        all_entries = self.messages.zrangebyscore(
            min=from_msg_id,
            max='+inf' if not to_msg_id else '(%s' % to_msg_id,
            withscores=True,
        )

        return self.prepare_history_entries(all_entries, from_msg_id, topics, ensure_first)

    def send_unsent_messages(self):
        last_msg_id = self.get_last_msg_id()
        last_msg_id_sent = self.get_last_msg_sent_id()

        if last_msg_id > last_msg_id_sent:
            logger.warning('Send unsent message from %d to %d', last_msg_id_sent+1, last_msg_id)

            # We have old messages to send
            old_messages, max_msg_id = self.get_history(
                from_msg_id=last_msg_id_sent,
                ensure_first=False
            )

            failed = False
            for __, __, old_decoded, old_msg_id in old_messages[1:]:
                old_topic = old_decoded['topic']
                try:
                    self.add_extra_details(old_decoded['kwargs'], old_topic, old_msg_id)
                    self.send_message(
                        old_msg_id, old_topic, *old_decoded['args'], **old_decoded['kwargs']
                    )
                except Exception:
                    logger.exception('Old message %d could not be sent on %s',
                                     old_msg_id, old_topic)
                    # We can't send the message, something is really wrong, we stop here
                    failed = True
                    break
                else:
                    logger.warning('Old message %d sent on %s', old_msg_id, old_topic)

            return not failed

    @cached_property
    def http_client(self):
        return Client("http://127.0.0.1:8888/ws-publish", key='foo', secret='bar')

    def send_message(self, msg_id, topic, *args, **kwargs):
        try:
            publish_result = self.http_client.publish(topic, *args, **kwargs)
        except Exception:
            raise
        else:
            self.save_last_sent_message(msg_id)
            return publish_result


class AsyncHistory(BaseHistory):
    def __init__(self, app):
        self.app = app
        self.object = History.singleton(async=True)
        self._name = self.object._name
        self.connect()

    @classmethod
    def connect(cls):
        cls.connection = redis.lazyConnection(
            host=settings.LIMPYD_DB_CONFIG['host'],
            port=settings.LIMPYD_DB_CONFIG['port'],
            dbid=settings.LIMPYD_DB_CONFIG['db'],
        )

    def make_key(self, *args):
        return self.object.make_key(*args)

    @inlineCallbacks
    def get_last_msg_id(self):
        key = self.object.last_msg_id.key
        msg_id = yield self.connection.get(key)
        returnValue(int(msg_id or 0))

    @inlineCallbacks
    def get_new_msg_id(self):
        """Increment in redis and get the new ``last_msg_id`` value."""
        key = self.object.last_msg_id.key
        msg_id = yield self.connection.incr(key)
        returnValue(int(msg_id))

    @inlineCallbacks
    def get_last_msg_sent_id(self):
        """Return the last used message id."""
        key = self.object.last_msg_id_sent.key
        msg_id = yield self.connection.get(key)
        returnValue(int(msg_id or 0))

    @inlineCallbacks
    def save_message(self, topic, *args, **kwargs):
        """Add the message as the last one in the list of messages."""
        msg_id = yield self.get_new_msg_id()
        message = self.serialize(msg_id, topic, *args, **kwargs)
        key = self.object.messages.key
        yield self.connection.zadd(key, msg_id, message)
        returnValue(msg_id)

    @inlineCallbacks
    def save_last_sent_message(self, msg_id):
        key = self.object.last_msg_id_sent.key
        yield self.connection.set(key, msg_id)

    @inlineCallbacks
    def get_history(self, from_msg_id, topics=None, to_msg_id=None, ensure_first=True):
        key = self.object.messages.key
        all_entries = yield self.connection.zrangebyscore(
            key,
            min=from_msg_id,
            max='+inf' if not to_msg_id else '(%s' % to_msg_id,
            withscores=True,
        )

        returnValue(self.prepare_history_entries(all_entries, from_msg_id, topics, ensure_first))

    @inlineCallbacks
    def send_unsent_messages(self):
        last_msg_id = yield self.get_last_msg_id()
        last_msg_id_sent = yield self.get_last_msg_sent_id()

        if last_msg_id > last_msg_id_sent:
            logger.warning('Send unsent message from %d to %d', last_msg_id_sent+1, last_msg_id)

            # We have old messages to send
            old_messages, max_msg_id = yield self.get_history(
                from_msg_id=last_msg_id_sent,
                ensure_first=False
            )

            failed = False
            for __, __, old_decoded, old_msg_id in old_messages[1:]:
                old_topic = old_decoded['topic']
                try:
                    self.add_extra_details(old_decoded['kwargs'], old_topic, old_msg_id)
                    yield self.send_message(
                        old_msg_id, old_topic, *old_decoded['args'], **old_decoded['kwargs']
                    )
                except Exception:
                    logger.exception('Old message %d could not be sent on %s',
                                     old_msg_id, old_topic)
                    # We can't send the message, something is really wrong, we stop here
                    failed = True
                    break
                else:
                    logger.warning('Old message %d sent on %s', old_msg_id, old_topic)

            returnValue(not failed)

    @inlineCallbacks
    def send_message(self, msg_id, topic, *args, **kwargs):
        try:
            publish_result = yield self.app.publish(topic, *args, **kwargs)
        except Exception:
            raise
        else:
            yield self.save_last_sent_message(msg_id)
            returnValue(publish_result)


class WS(object):

    def __init__(self, async=False):
        self.async = async

    @cached_property
    def history(self):
        return History.singleton()

    def publish(self, topic, *args, **kwargs):

        if not topic.startswith('gim.'):
            topic = 'gim.' + topic

        # Tell other publish to wait until we're done here
        with Lock(self.history.database.connection, self.history.lock_key):

            # Sent unsent messages if any
            self.history.send_unsent_messages()

            # Prepare message to send
            msg_id = self.history.save_message(topic, *args, **kwargs)
            self.history.add_extra_details(kwargs, topic, msg_id)

            # We can now send our message
            try:
                self.history.send_message(msg_id, topic, *args, **kwargs)
            except Exception:
                logger.exception('Message %d could not be sent on %s', msg_id, topic)
            else:
                logger.info('Message %d sent on %s', msg_id, topic)


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
            stop_trying_at = mod_time.time() + blocking_timeout
        returned = False
        while not returned:
            returned = True
            acquired = yield self.do_acquire(token)
            if acquired:
                returnValue(True)
            if not blocking:
                returnValue(False)
            if stop_trying_at is not None and mod_time.time() > stop_trying_at:
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
                yield self.redis.pexpire(self.name, timeout)
            returnValue(True)
        returnValue(False)

    @inlineCallbacks
    def release(self):
        "Releases the already acquired lock"
        name = self.name
        yield self.redis.delete(name)


Ws = WS()
