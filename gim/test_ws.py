# Run these tests with `DJANGO_SETTINGS_MODULE=gim.settings.tests trial gim.test_ws`

import json
import logging
import unittest

import txredisapi as txredis

from django.conf import settings
from mock import call, patch
from redis.lock import Lock
from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest as txunittest

from gim import ws

patch.object = patch.object
logging.disable(logging.CRITICAL)

if not getattr(settings, 'TEST_SETTINGS', False):
    raise RuntimeError('Tests must be run with DJANGO_SETTINGS_MODULE=gim.settings.tests')


class UtilsTestCase(unittest.TestCase):

    def test_serialize(self):

        result = ws.serialize(123, 'foo', 1, b=2)

        self.assertEqual(
            json.loads(result),
            {
                'msg_id': 123,
                'topic': 'foo',
                'args': [1],
                'kwargs': {'b': 2}
            }
        )

    def test_normalize_topic(self):

        result = ws.normalize_topic('gim.foo')
        self.assertEqual(result, 'gim.foo')

        result = ws.normalize_topic('foo')
        self.assertEqual(result, 'gim.foo')

    def test_add_ws_extra_details(self):

        d = {'x': 'y'}
        result = ws.add_ws_extra_details(d, 'foo', 1)

        self.assertIsNone(result)
        self.assertEqual(d, {'x': 'y', 'ws_extra': {'topic': 'foo', 'msg_id': 1}})

    def test_prepare_rules(self):
        result = ws.prepare_rules(None)
        self.assertIsNone(result)

        result = ws.prepare_rules([])
        self.assertEqual(result, [])

        result = ws.prepare_rules([
            ('foo', ws.TOPIC_TYPE_EXACT),
            ('foo.bar', ws.TOPIC_TYPE_EXACT),
            ('bar', ws.TOPIC_TYPE_PREFIX),
            ('bar.baz.', ws.TOPIC_TYPE_PREFIX),
            ('foo..baz', ws.TOPIC_TYPE_WILDCARD),
            ('..baz', ws.TOPIC_TYPE_WILDCARD),
            ('foo..', ws.TOPIC_TYPE_WILDCARD),
            ('.bar.', ws.TOPIC_TYPE_WILDCARD),
            ('..', ws.TOPIC_TYPE_WILDCARD),
        ])
        self.assertEqual(len(result), 3)
        self.assertEqual(result[ws.TOPIC_TYPE_EXACT], [
            ('foo', 'foo'),
            ('foo.bar', 'foo.bar'),
        ])
        self.assertEqual(result[ws.TOPIC_TYPE_PREFIX], [
            ('bar', 'bar'),
            ('bar.baz.', 'bar.baz.'),
        ])
        self.assertEqual([(o, r.pattern) for o, r in result[ws.TOPIC_TYPE_WILDCARD]], [
            ('foo..baz', r'^foo\.[^\.]+\.baz$'),
            ('..baz', r'^[^\.]+\.[^\.]+\.baz$'),
            ('foo..', r'^foo\.[^\.]+\.[^\.]+$'),
            ('.bar.', r'^[^\.]+\.bar\.[^\.]+$'),
            ('..', r'^[^\.]+\.[^\.]+\.[^\.]+$'),
        ])

    def test_restrict_topics(self):
        result = ws.restrict_topics(['foo', 'bar'], None)
        self.assertEqual(result, {
            'foo': [],
            'bar': [],
        })

        result = ws.restrict_topics(['foo', 'bar'], [])
        self.assertEqual(result, {})

        result = ws.restrict_topics([
            'foo',
            'bar',
            'bar2',
            'baz',
            'foo.bar.baz',
            'foo.bar2.baz',
            'foo.bar2.baz2',
            'foo.bar.qux.baz',
            'foo.bar.qux.quz.baz',
        ], [
            ('foo', ws.TOPIC_TYPE_EXACT),
            ('bar', ws.TOPIC_TYPE_PREFIX),
            ('bar2', ws.TOPIC_TYPE_EXACT),
            ('foo..baz', ws.TOPIC_TYPE_WILDCARD),
        ])

        self.assertEqual(result, {
            'foo': [('foo', ws.TOPIC_TYPE_EXACT), ],
            'bar': [('bar', ws.TOPIC_TYPE_PREFIX), ],
            'bar2': [('bar2', ws.TOPIC_TYPE_EXACT), ('bar', ws.TOPIC_TYPE_PREFIX), ],
            'foo.bar.baz': [('foo..baz', ws.TOPIC_TYPE_WILDCARD), ],
            'foo.bar2.baz': [('foo..baz', ws.TOPIC_TYPE_WILDCARD), ],
        })

        # test values from
        # https://github.com/crossbario/crossbar/blob/master/crossbar/router/test/test_wildcard.py
        WILDCARDS = ['.', 'a..c', 'a.b.', 'a..', '.b.', '..', 'x..', '.x.', '..x', 'x..x', 'x.x.',
                     '.x.x', 'x.x.x']

        MATCHES = {
            'abc': [],
            'a.b': ['.'],
            'a.b.c': ['a..c', 'a.b.', 'a..', '.b.', '..'],
            'a.x.c': ['a..c', 'a..', '..', '.x.'],
            'a.b.x': ['a.b.', 'a..', '.b.', '..', '..x'],
            'a.x.x': ['a..', '..', '.x.', '..x', '.x.x'],
            'x.y.z': ['..', 'x..'],
            'a.b.c.d': []
        }

        for topic in MATCHES:
            for pattern in WILDCARDS:
                result = ws.restrict_topics([topic], [(pattern, ws.TOPIC_TYPE_WILDCARD)])
                if pattern in MATCHES[topic]:
                    self.assertEqual(result, {topic: [(pattern, ws.TOPIC_TYPE_WILDCARD)]},
                        'Pattern `%s` should match topic `%s`, but it doesn\'t match' % (
                                         pattern, topic))
                else:
                    self.assertEqual(result, {},
                        'Pattern `%s` should not match topic `%s`, but it matches' % (
                                         pattern, topic))


class UsingSyncRedis(unittest.TestCase):

    @classmethod
    def flushdb(cls):
        database = ws.get_main_limpyd_database()
        database.connection.flushdb()

    def setUp(self):
        super(UsingSyncRedis, self).setUp()
        self.flushdb()

    def tearDown(self):
        self.flushdb()
        super(UsingSyncRedis, self).tearDown()


class UsingAsyncRedis(txunittest.TestCase):

    @inlineCallbacks
    def flushdb(self):
        yield self.db.flushdb()

    @inlineCallbacks
    def setUp(self):
        super(UsingAsyncRedis, self).setUp()
        self.db = yield txredis.Connection(
            host=settings.LIMPYD_DB_CONFIG['host'],
            port=settings.LIMPYD_DB_CONFIG['port'],
            dbid=settings.LIMPYD_DB_CONFIG['db'],
            reconnect=False
        )
        ws.AsyncHistoryMixin.redis_connection = self.db

        yield self.flushdb()

    @inlineCallbacks
    def tearDown(self):
        yield self.flushdb()
        yield self.db.disconnect()
        super(UsingAsyncRedis, self).tearDown()


class RepositoryHistoryTestCase(UsingSyncRedis):

    def test_get_for(self):

        # Existing entry
        ws.RepositoryHistory(pk=666)

        result = ws.RepositoryHistory.get_for(666, async=False)
        self.assertEqual(result._pk, '666')
        self.assertTrue(result.connected)

        result = ws.RepositoryHistory.get_for(666, async=True)
        self.assertEqual(result._pk, '666')
        self.assertFalse(result.connected)

        # New entry

        result = ws.RepositoryHistory.get_for(667, async=False)
        self.assertEqual(result._pk, '667')
        self.assertTrue(result.connected)

        result = ws.RepositoryHistory.get_for(668, async=True)
        self.assertEqual(result._pk, '668')
        self.assertFalse(result.connected)

    def test_all_topics(self):
        obj = ws.RepositoryHistory.get_for(1)

        # Add two members
        obj.messages.get_for('foo').zadd(123, 'do-not-care')
        obj.messages.get_for('bar').zadd(456, 'still-do-not-care')

        topics = obj.all_topics()
        self.assertEqual(topics, {'foo', 'bar'})

    def test_save_message_without_pipeline(self):

        # Save a first message
        obj = ws.RepositoryHistory.get_for(1)
        obj.save_message(123, 'foo', 1, b=2)

        topics = obj.all_topics()
        self.assertEqual(topics, {'foo'})
        messages_foo = obj.messages.get_for('foo').zrange(0, -1, withscores=True)
        self.assertEqual(messages_foo, [
            (ws.serialize(123, 'foo', 1, b=2), 123),
        ])
        messages_bar = obj.messages.get_for('bar').zrange(0, -1, withscores=True)
        self.assertEqual(messages_bar, [])
        last_msg_id = obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 123)

        # Save another message for the same repository, same topic
        obj = ws.RepositoryHistory.get_for(1)
        obj.save_message(124, 'foo', 11, b=22)

        topics = obj.all_topics()
        self.assertEqual(topics, {'foo'})
        messages_foo = obj.messages.get_for('foo').zrange(0, -1, withscores=True)
        self.assertEqual(messages_foo, [
            (ws.serialize(123, 'foo', 1, b=2), 123),
            (ws.serialize(124, 'foo', 11, b=22), 124),
        ])
        messages_bar = obj.messages.get_for('bar').zrange(0, -1, withscores=True)
        self.assertEqual(messages_bar, [])
        last_msg_id = obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 124)

        # Save another message for the same repository, other topic
        obj = ws.RepositoryHistory.get_for(1)
        obj.save_message(125, 'bar', 111, b=222)

        topics = obj.all_topics()
        self.assertEqual(topics, {'foo', 'bar'})
        messages_foo = obj.messages.get_for('foo').zrange(0, -1, withscores=True)
        self.assertEqual(messages_foo, [
            (ws.serialize(123, 'foo', 1, b=2), 123),
            (ws.serialize(124, 'foo', 11, b=22), 124),
        ])
        messages_bar = obj.messages.get_for('bar').zrange(0, -1, withscores=True)
        self.assertEqual(messages_bar, [
            (ws.serialize(125, 'bar', 111, b=222), 125),
        ])
        last_msg_id = obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 125)

        # Save another message for another repository, other topic
        obj = ws.RepositoryHistory.get_for(2)
        obj.save_message(126, 'bar', 1111, b=2222)

        topics = obj.all_topics()
        self.assertEqual(topics, {'bar'})
        messages_foo = obj.messages.get_for('foo').zrange(0, -1, withscores=True)
        self.assertEqual(messages_foo, [])
        messages_bar = obj.messages.get_for('bar').zrange(0, -1, withscores=True)
        self.assertEqual(messages_bar, [
            (ws.serialize(126, 'bar', 1111, b=2222), 126),
        ])
        last_msg_id = obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 126)

    def test_save_message_with_pipeline(self):

        obj = ws.RepositoryHistory.get_for(1)
        with ws.RepositoryHistory.database.pipeline() as pipeline:
            obj.save_message(123, 'foo', 1, b=2)
            pipeline.execute()

        topics = obj.all_topics()
        self.assertEqual(topics, {'foo'})
        messages_foo = obj.messages.get_for('foo').zrange(0, -1, withscores=True)
        self.assertEqual(messages_foo, [
            (ws.serialize(123, 'foo', 1, b=2), 123),
        ])
        messages_bar = obj.messages.get_for('bar').zrange(0, -1, withscores=True)
        self.assertEqual(messages_bar, [])
        last_msg_id = obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 123)

    def test_get_last_msg_id(self):

        entry = ws.RepositoryHistory(pk=666)
        result = entry.get_last_msg_id()
        self.assertEqual(result, 0)

        entry = ws.RepositoryHistory(pk=667, last_msg_id=123)
        result = entry.get_last_msg_id()
        self.assertEqual(result, 123)

    def test_get_new_msg_id(self):
        entry = ws.RepositoryHistory(pk=666)

        result = entry.get_new_msg_id()
        self.assertEqual(result, 1)
        result = entry.get_last_msg_id()
        self.assertEqual(result, 1)

        result = entry.get_new_msg_id()
        self.assertEqual(result, 2)
        result = entry.get_last_msg_id()
        self.assertEqual(result, 2)

    def test_get_last_msg_id_sent(self):

        entry = ws.RepositoryHistory(pk=666)
        result = entry.get_last_msg_id_sent()
        self.assertEqual(result, 0)

        entry = ws.RepositoryHistory(pk=667, last_msg_id_sent=123)
        result = entry.get_last_msg_id_sent()
        self.assertEqual(result, 123)

    def test_save_last_sent_message_without_pipeline(self):

        entry = ws.RepositoryHistory(pk=666)

        result = entry.get_last_msg_id_sent()
        self.assertEqual(result, 0)

        entry.save_last_sent_message(123)

        result = entry.get_last_msg_id_sent()
        self.assertEqual(result, 123)

    def test_save_last_sent_message_with_pipeline(self):

        entry = ws.RepositoryHistory(pk=666)

        result = entry.get_last_msg_id_sent()
        self.assertEqual(result, 0)

        with entry.database.pipeline() as pipeline:
            entry.save_last_sent_message(123)
            pipeline.execute()

        result = entry.get_last_msg_id_sent()
        self.assertEqual(result, 123)

    def test_get_messages(self):

        entry = ws.RepositoryHistory(pk=666)

        messages_foo = entry.messages.get_for('foo')
        messages_bar = entry.messages.get_for('bar.xxx')
        messages_baz = entry.messages.get_for('baz.yyy.baz')

        messages_foo.zadd(2, json.dumps({'foo': 'msg-2'}))
        messages_bar.zadd(3, json.dumps({'bar': 'msg-3'}))
        messages_foo.zadd(4, json.dumps({'foo': 'msg-4'}))
        messages_foo.zadd(5, json.dumps({'foo': 'msg-5'}))
        messages_baz.zadd(6, json.dumps({'baz': 'msg-6'}))

        result = entry.get_messages()
        self.assertEqual(result, [
            (2, {'foo': 'msg-2'}, 'foo', []),
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
            (4, {'foo': 'msg-4'}, 'foo', []),
            (5, {'foo': 'msg-5'}, 'foo', []),
            (6, {'baz': 'msg-6'}, 'baz.yyy.baz', []),
        ])

        result = entry.get_messages(topics_rules=[])
        self.assertEqual(result, [])

        result = entry.get_messages(topics_rules=[
            ('foo', ws.TOPIC_TYPE_EXACT),
            ('baz', ws.TOPIC_TYPE_PREFIX),
        ])
        self.assertEqual(result, [
            (2, {'foo': 'msg-2'}, 'foo', [('foo', ws.TOPIC_TYPE_EXACT), ]),
            (4, {'foo': 'msg-4'}, 'foo', [('foo', ws.TOPIC_TYPE_EXACT), ]),
            (5, {'foo': 'msg-5'}, 'foo', [('foo', ws.TOPIC_TYPE_EXACT), ]),
            (6, {'baz': 'msg-6'}, 'baz.yyy.baz', [('baz', ws.TOPIC_TYPE_PREFIX), ]),
        ])

        result = entry.get_messages(topics_rules=[
            ('qux', ws.TOPIC_TYPE_EXACT),
            ('bar.', ws.TOPIC_TYPE_PREFIX),
            ('baz..baz', ws.TOPIC_TYPE_WILDCARD),
        ])
        self.assertEqual(result, [
            (3, {'bar': 'msg-3'}, 'bar.xxx', [('bar.', ws.TOPIC_TYPE_PREFIX), ]),
            (6, {'baz': 'msg-6'}, 'baz.yyy.baz', [('baz..baz', ws.TOPIC_TYPE_WILDCARD), ]),
        ])

        result = entry.get_messages(3)
        self.assertEqual(result, [
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
            (4, {'foo': 'msg-4'}, 'foo', []),
            (5, {'foo': 'msg-5'}, 'foo', []),
            (6, {'baz': 'msg-6'}, 'baz.yyy.baz', []),
        ])

        result = entry.get_messages(last_msg_id=4)
        self.assertEqual(result, [
            (2, {'foo': 'msg-2'}, 'foo', []),
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
            (4, {'foo': 'msg-4'}, 'foo', []),
        ])

        result = entry.get_messages(3, 4)
        self.assertEqual(result, [
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
            (4, {'foo': 'msg-4'}, 'foo', []),
        ])

        result = entry.get_messages(3, 3)
        self.assertEqual(result, [
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
        ])

        result = entry.get_messages(4, 3)
        self.assertEqual(result, [])

        result = entry.get_messages(7, 9)
        self.assertEqual(result, [])

        result = entry.get_messages(7)
        self.assertEqual(result, [])

        result = entry.get_messages(last_msg_id=1)
        self.assertEqual(result, [])

        result = entry.get_messages(0.5, 1)
        self.assertEqual(result, [])


class AsyncRepositoryHistoryTestCase(UsingAsyncRedis):

    @inlineCallbacks
    def test_get_for_without_pipeline(self):
        result = yield ws.AsyncRepositoryHistory.get_for(666)
        self.assertIsInstance(result.source_object, ws.RepositoryHistory)
        self.assertEqual(result.source_object._pk, '666')

    @inlineCallbacks
    def test_get_for_with_pipeline(self):
        pipeline = yield self.db.multi()
        result = yield ws.AsyncRepositoryHistory.get_for(666, pipeline=pipeline)
        yield pipeline.commit()
        self.assertIsInstance(result.source_object, ws.RepositoryHistory)
        self.assertEqual(result.source_object._pk, '666')

    @inlineCallbacks
    def test_all_topics(self):
        obj = yield ws.AsyncRepositoryHistory.get_for(1)

        # Add two members
        yield self.db.sadd(obj.source_object.messages._inventory.key, ['foo'])
        yield self.db.sadd(obj.source_object.messages._inventory.key, ['bar'])

        topics = yield obj.all_topics()
        self.assertEqual(topics, {'foo', 'bar'})

    @inlineCallbacks
    def test_save_message_without_pipeline(self):

        # Save a first message
        obj = yield ws.AsyncRepositoryHistory.get_for(1)
        yield obj.save_message(123, 'foo', 1, b=2)

        topics = yield obj.all_topics()
        self.assertEqual(topics, {'foo'})
        messages_foo = yield self.db.zrange(obj.source_object.messages.get_for('foo').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_foo, [
            (ws.serialize(123, 'foo', 1, b=2), 123),
        ])
        messages_bar = yield self.db.zrange(obj.source_object.messages.get_for('bar').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_bar, [])
        last_msg_id = yield obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 123)

        # Save another message for the same repository, same topic
        obj = yield ws.AsyncRepositoryHistory.get_for(1)
        yield obj.save_message(124, 'foo', 11, b=22)

        topics = yield obj.all_topics()
        self.assertEqual(topics, {'foo'})
        messages_foo = yield self.db.zrange(obj.source_object.messages.get_for('foo').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_foo, [
            (ws.serialize(123, 'foo', 1, b=2), 123),
            (ws.serialize(124, 'foo', 11, b=22), 124),
        ])
        messages_bar = yield self.db.zrange(obj.source_object.messages.get_for('bar').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_bar, [])
        last_msg_id = yield obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 124)

        # Save another message for the same repository, other topic
        obj = yield ws.AsyncRepositoryHistory.get_for(1)
        yield obj.save_message(125, 'bar', 111, b=222)

        topics = yield obj.all_topics()
        self.assertEqual(topics, {'foo', 'bar'})
        messages_foo = yield self.db.zrange(obj.source_object.messages.get_for('foo').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_foo, [
            (ws.serialize(123, 'foo', 1, b=2), 123),
            (ws.serialize(124, 'foo', 11, b=22), 124),
        ])
        messages_bar = yield self.db.zrange(obj.source_object.messages.get_for('bar').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_bar, [
            (ws.serialize(125, 'bar', 111, b=222), 125),
        ])
        last_msg_id = yield obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 125)

        # Save another message for another repository, other topic
        obj = yield ws.AsyncRepositoryHistory.get_for(2)
        yield obj.save_message(126, 'bar', 1111, b=2222)

        topics = yield obj.all_topics()
        self.assertEqual(topics, {'bar'})
        messages_foo = yield self.db.zrange(obj.source_object.messages.get_for('foo').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_foo, [])
        messages_bar = yield self.db.zrange(obj.source_object.messages.get_for('bar').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_bar, [
            (ws.serialize(126, 'bar', 1111, b=2222), 126),
        ])
        last_msg_id = yield obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 126)

    @inlineCallbacks
    def test_save_message_with_pipeline(self):

        obj = yield ws.AsyncRepositoryHistory.get_for(1)

        pipeline = yield self.db.multi()
        obj.save_message(123, 'foo', 1, b=2, pipeline=pipeline)
        yield pipeline.commit()

        topics = yield obj.all_topics()
        self.assertEqual(topics, {'foo'})
        messages_foo = yield self.db.zrange(obj.source_object.messages.get_for('foo').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_foo, [
            (ws.serialize(123, 'foo', 1, b=2), 123),
        ])
        messages_bar = yield self.db.zrange(obj.source_object.messages.get_for('bar').key, 0, -1,
                                            withscores=True)
        self.assertEqual(messages_bar, [])
        last_msg_id = yield obj.get_last_msg_id()
        self.assertEqual(last_msg_id, 123)

    @inlineCallbacks
    def test_get_last_msg_id(self):

        entry = yield ws.AsyncRepositoryHistory.get_for(666)
        result = yield entry.get_last_msg_id()
        self.assertEqual(result, 0)

        entry = yield ws.AsyncRepositoryHistory.get_for(667)
        yield self.db.set(entry.source_object.last_msg_id.key, 123)
        result = yield entry.get_last_msg_id()
        self.assertEqual(result, 123)

    @inlineCallbacks
    def test_get_new_msg_id(self):
        entry = yield ws.AsyncRepositoryHistory.get_for(666)

        result = yield entry.get_new_msg_id()
        self.assertEqual(result, 1)
        result = yield entry.get_last_msg_id()
        self.assertEqual(result, 1)

        result = yield entry.get_new_msg_id()
        self.assertEqual(result, 2)
        result = yield entry.get_last_msg_id()
        self.assertEqual(result, 2)

    @inlineCallbacks
    def test_get_last_msg_id_sent(self):

        entry = yield ws.AsyncRepositoryHistory.get_for(666)
        result = yield entry.get_last_msg_id_sent()
        self.assertEqual(result, 0)

        entry = yield ws.AsyncRepositoryHistory.get_for(667)
        yield self.db.set(entry.source_object.last_msg_id_sent.key, 123)
        result = yield entry.get_last_msg_id_sent()
        self.assertEqual(result, 123)

    @inlineCallbacks
    def test_save_last_sent_message_without_pipeline(self):

        entry = yield ws.AsyncRepositoryHistory.get_for(666)

        result = yield entry.get_last_msg_id_sent()
        self.assertEqual(result, 0)

        yield entry.save_last_sent_message(123)

        result = yield entry.get_last_msg_id_sent()
        self.assertEqual(result, 123)

    @inlineCallbacks
    def test_save_last_sent_message_with_pipeline(self):

        entry = yield ws.AsyncRepositoryHistory.get_for(666)

        result = yield entry.get_last_msg_id_sent()
        self.assertEqual(result, 0)

        pipeline = yield self.db.multi()
        yield entry.save_last_sent_message(123, pipeline=pipeline)
        yield pipeline.commit()

        result = yield entry.get_last_msg_id_sent()
        self.assertEqual(result, 123)

    @inlineCallbacks
    def test_get_messages(self):

        entry = yield ws.AsyncRepositoryHistory.get_for(666)

        messages_foo = entry.source_object.messages.get_for('foo')
        messages_bar = entry.source_object.messages.get_for('bar.xxx')
        messages_baz = entry.source_object.messages.get_for('baz.yyy.baz')

        yield self.db.zadd(messages_foo.key, 2, json.dumps({'foo': 'msg-2'}))
        yield self.db.zadd(messages_bar.key, 3, json.dumps({'bar': 'msg-3'}))
        yield self.db.zadd(messages_foo.key, 4, json.dumps({'foo': 'msg-4'}))
        yield self.db.zadd(messages_foo.key, 5, json.dumps({'foo': 'msg-5'}))
        yield self.db.zadd(messages_baz.key, 6, json.dumps({'baz': 'msg-6'}))
        yield self.db.sadd(entry.source_object.messages._inventory.key,
                           ['foo', 'bar.xxx', 'baz.yyy.baz'])

        result = yield entry.get_messages()
        self.assertEqual(result, [
            (2, {'foo': 'msg-2'}, 'foo', []),
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
            (4, {'foo': 'msg-4'}, 'foo', []),
            (5, {'foo': 'msg-5'}, 'foo', []),
            (6, {'baz': 'msg-6'}, 'baz.yyy.baz', []),
        ])

        result = yield entry.get_messages(topics_rules=[])
        self.assertEqual(result, [])

        result = yield entry.get_messages(topics_rules=[
            ('foo', ws.TOPIC_TYPE_EXACT),
            ('baz', ws.TOPIC_TYPE_PREFIX),
        ])
        self.assertEqual(result, [
            (2, {'foo': 'msg-2'}, 'foo', [('foo', ws.TOPIC_TYPE_EXACT), ]),
            (4, {'foo': 'msg-4'}, 'foo', [('foo', ws.TOPIC_TYPE_EXACT), ]),
            (5, {'foo': 'msg-5'}, 'foo', [('foo', ws.TOPIC_TYPE_EXACT), ]),
            (6, {'baz': 'msg-6'}, 'baz.yyy.baz', [('baz', ws.TOPIC_TYPE_PREFIX), ]),
        ])

        result = yield entry.get_messages(topics_rules=[
            ('qux', ws.TOPIC_TYPE_EXACT),
            ('bar.', ws.TOPIC_TYPE_PREFIX),
            ('baz..baz', ws.TOPIC_TYPE_WILDCARD),
        ])
        self.assertEqual(result, [
            (3, {'bar': 'msg-3'}, 'bar.xxx', [('bar.', ws.TOPIC_TYPE_PREFIX), ]),
            (6, {'baz': 'msg-6'}, 'baz.yyy.baz', [('baz..baz', ws.TOPIC_TYPE_WILDCARD), ]),
        ])

        result = yield entry.get_messages(3)
        self.assertEqual(result, [
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
            (4, {'foo': 'msg-4'}, 'foo', []),
            (5, {'foo': 'msg-5'}, 'foo', []),
            (6, {'baz': 'msg-6'}, 'baz.yyy.baz', []),
        ])

        result = yield entry.get_messages(last_msg_id=4)
        self.assertEqual(result, [
            (2, {'foo': 'msg-2'}, 'foo', []),
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
            (4, {'foo': 'msg-4'}, 'foo', []),
        ])

        result = yield entry.get_messages(3, 4)
        self.assertEqual(result, [
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
            (4, {'foo': 'msg-4'}, 'foo', []),
        ])

        result = yield entry.get_messages(3, 3)
        self.assertEqual(result, [
            (3, {'bar': 'msg-3'}, 'bar.xxx', []),
        ])

        result = yield entry.get_messages(4, 3)
        self.assertEqual(result, [])

        result = yield entry.get_messages(7, 9)
        self.assertEqual(result, [])

        result = yield entry.get_messages(7)
        self.assertEqual(result, [])

        result = yield entry.get_messages(last_msg_id=1)
        self.assertEqual(result, [])

        result = yield entry.get_messages(0.5, 1)
        self.assertEqual(result, [])


class PublisherTestCase(UsingSyncRedis):

    PK = ws.Publisher.PK
    sPK = str(PK)

    def setUp(self):
        super(PublisherTestCase, self).setUp()
        self.publisher = ws.Publisher.get_for(self.PK)

    def test_get_for(self):
        # Existing entry

        result = ws.Publisher.get_for(666, async=False)
        self.assertEqual(result._pk, self.sPK)
        self.assertTrue(result.connected)

        result = ws.Publisher.get_for(666, async=True)
        self.assertEqual(result._pk, self.sPK)
        self.assertFalse(result.connected)

        # Without pk
        result = ws.Publisher.get_for()
        self.assertEqual(result._pk, self.sPK)
        self.assertTrue(result.connected)

        # Non existing entry

        self.flushdb()
        result = ws.Publisher.get_for(667, async=False)
        self.assertEqual(result._pk, self.sPK)
        self.assertTrue(result.connected)

        self.flushdb()
        result = ws.Publisher.get_for(668, async=True)
        self.assertEqual(result._pk, self.sPK)
        self.assertFalse(result.connected)

    def test_singleton(self):
        result1 = ws.Publisher.singleton()
        self.assertIsInstance(result1, ws.Publisher)
        self.assertEqual(result1._pk, self.sPK)
        self.assertTrue(result1.connected)

        result2 = ws.Publisher.singleton()
        self.assertIs(result2, result1)

    def test_lock_key(self):
        self.assertEqual(self.publisher.lock_key, 'ws:publisher:%s:lock' % self.sPK)

    def test_lock_publishing(self):
        lock = self.publisher.lock_publishing()
        self.assertIsInstance(lock, Lock)
        self.assertEqual(lock.name, self.publisher.lock_key)

    def test_save_message_for_repository(self):

        with patch.object(ws.RepositoryHistory, 'save_message') as repository_save_message:
            msg_id = self.publisher.save_message('foo', 666, 11, b=22)

        self.assertEqual(msg_id, 1)

        result = self.publisher.get_last_msg_id()
        self.assertEqual(result, 1)

        # Check the message id is tied to the repository
        repositories = self.publisher.repositories.zrange(0, -1, withscores=True)
        self.assertEqual(repositories, [
            ('1:666', 1)
        ])

        # We should have called `save_message` for the repository
        repository_save_message.assert_called_once_with(1, 'foo', 11, b=22)

        # And the message should not be stored in the global store
        messages = self.publisher.messages.get_for('foo').zrange(0, -1, withscores=True)
        self.assertEqual(messages, [])

    def test_save_message_not_for_repository(self):

        with patch.object(ws.RepositoryHistory, 'save_message') as repository_save_message:
            msg_id = self.publisher.save_message('foo', None, 11, b=22)

        self.assertEqual(msg_id, 1)

        result = self.publisher.get_last_msg_id()
        self.assertEqual(result, 1)

        # Check the message id is NOT tied to the repository
        repositories = self.publisher.repositories.zrange(0, -1, withscores=True)
        self.assertEqual(repositories, [
            ('1:', 1)
        ])

        # We should have NOT called `save_message` for the repository
        self.assertEqual(repository_save_message.call_count, 0)

        # But the message should be stored in the global store
        messages = self.publisher.messages.get_for('foo').zrange(0, -1, withscores=True)
        self.assertEqual(messages, [
            (ws.serialize(1, 'foo', 11, b=22), 1),
        ])

    def test_send_message_for_repository(self):

        with patch.object(self.publisher.http_client, 'publish') as publish:
            self.publisher.send_message(123, 'foo', 666, 11, b=22)

        # We published to crossbar
        publish.assert_called_once_with('foo', 11, b=22)

        # We saved the last message for the repository
        obj = ws.RepositoryHistory.get_for(666)
        last_msg_id_sent = obj.get_last_msg_id_sent()
        self.assertEqual(last_msg_id_sent, 123)

        # And globally
        last_msg_id_sent = self.publisher.get_last_msg_id_sent()
        self.assertEqual(last_msg_id_sent, 123)

    def test_send_message_not_for_repository(self):

        with patch.object(self.publisher.http_client, 'publish') as publish:
            with patch.object(ws.RepositoryHistory, 'save_last_sent_message') as \
                    repository_save_last_sent_message:
                self.publisher.send_message(123, 'foo', None, 11, b=22)

        # We published to crossbar
        publish.assert_called_once_with('foo', 11, b=22)

        # We DIDN'T save the last message for any repository
        self.assertEqual(repository_save_last_sent_message.call_count, 0)

        # But globally
        last_msg_id_sent = self.publisher.get_last_msg_id_sent()
        self.assertEqual(last_msg_id_sent, 123)

    def test_send_messages(self):
        messages = [
            (5, 'gim.bar', '667', [1], {'b': 2}),
            (6, 'gim.foo', '666', [11], {'b': 22}),
            (7, 'gim.baz', None, [111], {'b': 222}),
        ]

        with patch.object(self.publisher, 'send_message') as send_message:
            self.publisher.send_messages(messages)

        self.assertEqual(send_message.call_args_list, [
            call(5, 'gim.bar', '667', 1, b=2, ws_extra={'topic': 'gim.bar', 'msg_id': 5}),
            call(6, 'gim.foo', '666', 11, b=22, ws_extra={'topic': 'gim.foo', 'msg_id': 6}),
            call(7, 'gim.baz', None, 111, b=222, ws_extra={'topic': 'gim.baz', 'msg_id': 7}),
        ])

    def test_publish_for_repository(self):

        with patch.object(self.publisher, 'save_message', return_value=123) as save_message:
            with patch.object(self.publisher, 'send_message') as send_message:
                with patch.object(self.publisher, 'send_unsent_messages') as send_unsent_messages:
                    msg_id = self.publisher.publish('foo', 666, 11, b=22)

        self.assertEqual(msg_id, 123)
        send_unsent_messages.assert_called_once_with()
        save_message.assert_called_once_with('gim.foo', 666, 11, b=22)
        send_message.assert_called_once_with(123, 'gim.foo', 666, 11, b=22,
                                             ws_extra={'msg_id': 123, 'topic': 'gim.foo'})

    def test_publish_not_for_repository(self):

        with patch.object(self.publisher, 'save_message', return_value=123) as save_message:
            with patch.object(self.publisher, 'send_message') as send_message:
                with patch.object(self.publisher, 'send_unsent_messages') as send_unsent_messages:
                    msg_id = self.publisher.publish('foo', None, 11, b=22)

        self.assertEqual(msg_id, 123)
        send_unsent_messages.assert_called_once_with()
        save_message.assert_called_once_with('gim.foo', None, 11, b=22)
        send_message.assert_called_once_with(123, 'gim.foo', None, 11, b=22,
                                             ws_extra={'msg_id': 123, 'topic': 'gim.foo'})

    def test_get_unsent_bounds(self):
        with patch.object(self.publisher, 'get_last_msg_id', return_value=10):
            with patch.object(self.publisher, 'get_last_msg_id_sent', return_value=5):
                result = self.publisher.get_unsent_bounds()

        self.assertEqual(result, (6, 10))

        with patch.object(self.publisher, 'get_last_msg_id', return_value=10):
            with patch.object(self.publisher, 'get_last_msg_id_sent', return_value=10):
                result = self.publisher.get_unsent_bounds()

        self.assertEqual(result, (11, 10))

    def test_send_unsent_messages(self):
        # Send some messages
        with patch.object(self.publisher.http_client, 'publish'):
            self.publisher.publish('foo', 666, 1, b=2)  # id 1
            self.publisher.publish('foo', 666, 11, b=22)  # id 2
            self.publisher.publish('foo', 666, 111, b=222)  # id 3
            self.publisher.publish('foo2', 666, 1111, b=2222)  # id 4

        # Send unsent ones: there is no unsent message
        with patch.object(self.publisher, 'send_messages') as send_messages:
            self.publisher.send_unsent_messages()

        self.assertEqual(send_messages.call_count, 0)

        # Fake send more messages
        with patch.object(self.publisher, 'send_message'):
            # And don't try to send unsent messages for now
            with patch.object(self.publisher, 'send_unsent_messages'):
                self.publisher.publish('bar', 667, 11111, b=22222)  # id 5
                self.publisher.publish('foo', 666, 111111, b=222222)  # id 6
                self.publisher.publish('baz', None, 1111111, b=2222222)  # id 7

        # Send unsent ones: there is 3 unsent messages
        with patch.object(self.publisher, 'send_message') as send_message:
            self.publisher.send_unsent_messages()

        self.assertEqual(send_message.call_args_list, [
            call(5, 'gim.bar', '667', 11111, b=22222, ws_extra={'topic': 'gim.bar', 'msg_id': 5}),
            call(6, 'gim.foo', '666', 111111, b=222222, ws_extra={'topic': 'gim.foo', 'msg_id': 6}),
            call(7, 'gim.baz', None, 1111111, b=2222222, ws_extra={'topic': 'gim.baz', 'msg_id': 7}),
        ])

    def test_publish_send_unsent_messages(self):
        # Send some messages
        with patch.object(self.publisher.http_client, 'publish'):
            self.publisher.publish('foo', 666, 1, b=2)  # id 1
            self.publisher.publish('foo', 666, 11, b=22)  # id 2
            self.publisher.publish('foo', 666, 111, b=222)  # id 3
            self.publisher.publish('foo2', 666, 1111, b=2222)  # id 4

        # Fake send more messages
        with patch.object(self.publisher, 'send_message'):
            self.publisher.publish('bar', 667, 11111, b=22222)  # id 5
            self.publisher.publish('foo', 666, 111111, b=222222)  # id 6
            self.publisher.publish('baz', None, 1111111, b=2222222)  # id 7

        # Send one with sending reactivated,
        with patch.object(self.publisher.http_client, 'publish') as publish:
            self.publisher.publish('baz2', None, 11111111, b=22222222)  # id 8

        self.assertEqual(publish.call_args_list, [
            call('gim.bar', 11111, b=22222, ws_extra={'msg_id': 5, 'topic': 'gim.bar'}),
            call('gim.foo', 111111, b=222222, ws_extra={'msg_id': 6, 'topic': 'gim.foo'}),
            call('gim.baz', 1111111, b=2222222, ws_extra={'msg_id': 7, 'topic': 'gim.baz'}),
            call('gim.baz2', 11111111, b=22222222, ws_extra={'msg_id': 8, 'topic': 'gim.baz2'}),
        ])

    def test_get_messages(self):
        # Send two messages
        with patch.object(self.publisher.http_client, 'publish'):
            self.publisher.publish('foo', 666, 1, b=2)  # id 1
            self.publisher.publish('foo', 666, 11, b=22)  # id 2

        # Fake send more messages
        with patch.object(self.publisher, 'send_message'):
            # And don't try to send unsent messages for now
            with patch.object(self.publisher, 'send_unsent_messages'):
                self.publisher.publish('foo', 666, 111, b=222)  # id 3
                self.publisher.publish('foo2', 666, 1111, b=2222)  # id 4
                self.publisher.publish('bar', 667, 11111, b=22222)  # id 5
                self.publisher.publish('foo', 666, 111111, b=222222)  # id 6
                self.publisher.publish('baz', None, 1111111, b=2222222)  # id 7
                self.publisher.publish('baz2', None, 11111111, b=22222222)  # id 8

        result = self.publisher.get_messages(3, 7)

        self.assertEqual(result, [
            (3, {'topic': 'gim.foo', 'msg_id': 3, 'args': [111], 'kwargs': {'b': 222}},
             'gim.foo', [], '666'),
            (4, {'topic': 'gim.foo2', 'msg_id': 4, 'args': [1111], 'kwargs': {'b': 2222}},
             'gim.foo2', [], '666'),
            (5, {'topic': 'gim.bar', 'msg_id': 5, 'args': [11111], 'kwargs': {'b': 22222}},
             'gim.bar', [], '667'),
            (6, {'topic': 'gim.foo', 'msg_id': 6, 'args': [111111], 'kwargs': {'b': 222222}},
             'gim.foo', [], '666'),
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [], None),
        ])

        result = self.publisher.get_messages(3, 7, [
            ('gim.foo', ws.TOPIC_TYPE_EXACT),
            ('gim.ba', ws.TOPIC_TYPE_PREFIX),
        ])

        self.assertEqual(result, [
            (3, {'topic': 'gim.foo', 'msg_id': 3, 'args': [111], 'kwargs': {'b': 222}},
             'gim.foo', [('gim.foo', ws.TOPIC_TYPE_EXACT), ], '666'),
            (5, {'topic': 'gim.bar', 'msg_id': 5, 'args': [11111], 'kwargs': {'b': 22222}},
             'gim.bar', [('gim.ba', ws.TOPIC_TYPE_PREFIX), ], '667'),
            (6, {'topic': 'gim.foo', 'msg_id': 6, 'args': [111111], 'kwargs': {'b': 222222}},
             'gim.foo', [('gim.foo', ws.TOPIC_TYPE_EXACT), ], '666'),
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [('gim.ba', ws.TOPIC_TYPE_PREFIX), ], None),
        ])

        result = self.publisher.get_messages()
        self.assertEqual(result, [
            (1, {'topic': 'gim.foo', 'msg_id': 1, 'args': [1], 'kwargs': {'b': 2}},
             'gim.foo', [], '666'),
            (2, {'topic': 'gim.foo', 'msg_id': 2, 'args': [11], 'kwargs': {'b': 22}},
             'gim.foo', [], '666'),
            (3, {'topic': 'gim.foo', 'msg_id': 3, 'args': [111], 'kwargs': {'b': 222}},
             'gim.foo', [], '666'),
            (4, {'topic': 'gim.foo2', 'msg_id': 4, 'args': [1111], 'kwargs': {'b': 2222}},
             'gim.foo2', [], '666'),
            (5, {'topic': 'gim.bar', 'msg_id': 5, 'args': [11111], 'kwargs': {'b': 22222}},
             'gim.bar', [], '667'),
            (6, {'topic': 'gim.foo', 'msg_id': 6, 'args': [111111], 'kwargs': {'b': 222222}},
             'gim.foo', [], '666'),
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [], None),
            (8, {'topic': 'gim.baz2', 'msg_id': 8, 'args': [11111111], 'kwargs': {'b': 22222222}},
             'gim.baz2', [], None),
        ])

        result = self.publisher.get_messages(first_msg_id=7)
        self.assertEqual(result, [
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [], None),
            (8, {'topic': 'gim.baz2', 'msg_id': 8, 'args': [11111111], 'kwargs': {'b': 22222222}},
             'gim.baz2', [], None),
        ])

        result = self.publisher.get_messages(last_msg_id=2)
        self.assertEqual(result, [
            (1, {'topic': 'gim.foo', 'msg_id': 1, 'args': [1], 'kwargs': {'b': 2}},
             'gim.foo', [], '666'),
            (2, {'topic': 'gim.foo', 'msg_id': 2, 'args': [11], 'kwargs': {'b': 22}},
             'gim.foo', [], '666'),
        ])


class FakeCrossbar:
    @inlineCallbacks
    def publish(self, topic, *args, **kwargs):
        pass


class AsyncPublisherTestCase(UsingAsyncRedis):

    PK = ws.Publisher.PK
    sPK = str(PK)

    @inlineCallbacks
    def setUp(self):
        yield super(AsyncPublisherTestCase, self).setUp()
        self.app = FakeCrossbar()
        self.publisher = yield ws.AsyncPublisher.get_for(self.PK, app=self.app)

    @inlineCallbacks
    def test_get_for_without_pipeline(self):
        # Existing entry

        result = yield ws.AsyncPublisher.get_for(666, app=self.app)
        self.assertIsInstance(result.source_object, ws.Publisher)
        self.assertEqual(result.source_object._pk, self.sPK)

        # Without pk
        result = yield ws.AsyncPublisher.get_for(app=self.app)
        self.assertIsInstance(result.source_object, ws.Publisher)
        self.assertEqual(result.source_object._pk, self.sPK)

        # Non existing entry

        self.flushdb()
        result = yield ws.AsyncPublisher.get_for(667, app=self.app)
        self.assertIsInstance(result.source_object, ws.Publisher)
        self.assertEqual(result.source_object._pk, self.sPK)

    @inlineCallbacks
    def test_get_for_with_pipeline(self):

        pipeline = yield self.db.multi()
        result = yield ws.AsyncPublisher.get_for(666, pipeline=pipeline, app=self.app)
        yield pipeline.commit()
        self.assertIsInstance(result.source_object, ws.Publisher)
        self.assertEqual(result.source_object._pk, self.sPK)

    def assert_called_once_with_pipeline(self, patched, *args, **kwargs):
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(patched.call_args[0], args)
        call_kwargs = patched.call_args[1].copy()
        self.assertIsInstance(call_kwargs.pop('pipeline'), txredis.BaseRedisProtocol)
        self.assertEqual(call_kwargs, kwargs)

    def test_lock_key(self):
        self.assertEqual(self.publisher.lock_key, 'ws:publisher:%s:lock' % self.sPK)

    def test_lock_publishing(self):
        lock = self.publisher.lock_publishing()
        self.assertIsInstance(lock, ws.txLock)
        self.assertEqual(lock.name, self.publisher.lock_key)

    @inlineCallbacks
    def test_save_message_for_repository(self):

        with patch.object(ws.AsyncRepositoryHistory, 'save_message') as repository_save_message:
            msg_id = yield self.publisher.save_message('foo', 666, 11, b=22)

        self.assertEqual(msg_id, 1)

        result = yield self.publisher.get_last_msg_id()
        self.assertEqual(result, 1)

        # Check the message id is tied to the repository
        repositories = yield self.db.zrange(self.publisher.source_object.repositories.key, 0, -1,
                                            withscores=True)
        self.assertEqual(repositories, [
            ('1:666', 1)
        ])

        # We should have called `save_message` for the repository
        self.assert_called_once_with_pipeline(repository_save_message, 1, 'foo', 11, b=22)

        # And the message should not be stored in the global store
        messages = yield self.db.zrange(self.publisher.source_object.messages.get_for('foo').key,
                                        0, -1, withscores=True)
        self.assertEqual(messages, [])

    @inlineCallbacks
    def test_save_message_not_for_repository(self):

        with patch.object(ws.RepositoryHistory, 'save_message') as repository_save_message:
            msg_id = yield self.publisher.save_message('foo', None, 11, b=22)

        self.assertEqual(msg_id, 1)

        result = yield self.publisher.get_last_msg_id()
        self.assertEqual(result, 1)

        # Check the message id is NOT tied to the repository
        repositories = yield self.db.zrange(self.publisher.source_object.repositories.key, 0, -1,
                                            withscores=True)
        self.assertEqual(repositories, [
            ('1:', 1)
        ])

        # We should have NOT called `save_message` for the repository
        self.assertEqual(repository_save_message.call_count, 0)

        # But the message should be stored in the global store
        messages = yield self.db.zrange(self.publisher.source_object.messages.get_for('foo').key,
                                        0, -1, withscores=True)
        self.assertEqual(messages, [
            (ws.serialize(1, 'foo', 11, b=22), 1),
        ])

    @inlineCallbacks
    def test_send_message_for_repository(self):

        with patch.object(FakeCrossbar, 'publish') as publish:
            yield self.publisher.send_message(123, 'foo', 666, 11, b=22)

        # We published to crossbar
        publish.assert_called_once_with('foo', 11, b=22)

        # We saved the last message for the repository
        obj = yield ws.AsyncRepositoryHistory.get_for(666)
        last_msg_id_sent = yield obj.get_last_msg_id_sent()
        self.assertEqual(last_msg_id_sent, 123)

        # And globally
        last_msg_id_sent = yield self.publisher.get_last_msg_id_sent()
        self.assertEqual(last_msg_id_sent, 123)

    @inlineCallbacks
    def test_send_message_not_for_repository(self):

        with patch.object(FakeCrossbar, 'publish') as publish:
            with patch.object(ws.RepositoryHistory, 'save_last_sent_message') as \
                    repository_save_last_sent_message:
                yield self.publisher.send_message(123, 'foo', None, 11, b=22)

        # We published to crossbar
        publish.assert_called_once_with('foo', 11, b=22)

        # We DIDN'T save the last message for any repository
        self.assertEqual(repository_save_last_sent_message.call_count, 0)

        # But globally
        last_msg_id_sent = yield self.publisher.get_last_msg_id_sent()
        self.assertEqual(last_msg_id_sent, 123)

    @inlineCallbacks
    def test_send_messages(self):
        messages = [
            (5, 'gim.bar', '667', [1], {'b': 2}),
            (6, 'gim.foo', '666', [11], {'b': 22}),
            (7, 'gim.baz', None, [111], {'b': 222}),
        ]

        with patch.object(self.publisher, 'send_message') as send_message:
            yield self.publisher.send_messages(messages)

        self.assertEqual(send_message.call_args_list, [
            call(5, 'gim.bar', '667', 1, b=2, ws_extra={'topic': 'gim.bar', 'msg_id': 5}),
            call(6, 'gim.foo', '666', 11, b=22, ws_extra={'topic': 'gim.foo', 'msg_id': 6}),
            call(7, 'gim.baz', None, 111, b=222, ws_extra={'topic': 'gim.baz', 'msg_id': 7}),
        ])

    @inlineCallbacks
    def test_publish_for_repository(self):

        with patch.object(self.publisher, 'save_message', return_value=123) as save_message:
            with patch.object(self.publisher, 'send_message') as send_message:
                with patch.object(self.publisher, 'send_unsent_messages') as send_unsent_messages:
                    msg_id = yield self.publisher.publish('foo', 666, 11, b=22)

        self.assertEqual(msg_id, 123)
        send_unsent_messages.assert_called_once_with()
        save_message.assert_called_once_with('gim.foo', 666, 11, b=22)
        send_message.assert_called_once_with(123, 'gim.foo', 666, 11, b=22,
                                             ws_extra={'msg_id': 123, 'topic': 'gim.foo'})

    @inlineCallbacks
    def test_publish_not_for_repository(self):

        with patch.object(self.publisher, 'save_message', return_value=123) as save_message:
            with patch.object(self.publisher, 'send_message') as send_message:
                with patch.object(self.publisher, 'send_unsent_messages') as send_unsent_messages:
                    msg_id = yield self.publisher.publish('foo', None, 11, b=22)

        self.assertEqual(msg_id, 123)
        send_unsent_messages.assert_called_once_with()
        save_message.assert_called_once_with('gim.foo', None, 11, b=22)
        send_message.assert_called_once_with(123, 'gim.foo', None, 11, b=22,
                                             ws_extra={'msg_id': 123, 'topic': 'gim.foo'})

    @inlineCallbacks
    def test_get_unsent_bounds(self):
        with patch.object(self.publisher, 'get_last_msg_id', return_value=10):
            with patch.object(self.publisher, 'get_last_msg_id_sent', return_value=5):
                result = yield self.publisher.get_unsent_bounds()

        self.assertEqual(result, (6, 10))

        with patch.object(self.publisher, 'get_last_msg_id', return_value=10):
            with patch.object(self.publisher, 'get_last_msg_id_sent', return_value=10):
                result = yield self.publisher.get_unsent_bounds()

        self.assertEqual(result, (11, 10))

    @inlineCallbacks
    def test_send_unsent_messages(self):
        # Send some messages
        with patch.object(FakeCrossbar, 'publish'):
            yield self.publisher.publish('foo', 666, 1, b=2)  # id 1
            yield self.publisher.publish('foo', 666, 11, b=22)  # id 2
            yield self.publisher.publish('foo', 666, 111, b=222)  # id 3
            yield self.publisher.publish('foo2', 666, 1111, b=2222)  # id 4

        # Send unsent ones: there is no unsent message
        with patch.object(self.publisher, 'send_messages') as send_messages:
            yield self.publisher.send_unsent_messages()

        self.assertEqual(send_messages.call_count, 0)

        # Fake send more messages
        with patch.object(self.publisher, 'send_message'):
            # And don't try to send unsent messages for now
            with patch.object(self.publisher, 'send_unsent_messages'):
                yield self.publisher.publish('bar', 667, 11111, b=22222)  # id 5
                yield self.publisher.publish('foo', 666, 111111, b=222222)  # id 6
                yield self.publisher.publish('baz', None, 1111111, b=2222222)  # id 7

        # Send unsent ones: there is 3 unsent messages
        with patch.object(self.publisher, 'send_message') as send_message:
            yield self.publisher.send_unsent_messages()

        self.assertEqual(send_message.call_args_list, [
            call(5, 'gim.bar', '667', 11111, b=22222, ws_extra={'topic': 'gim.bar', 'msg_id': 5}),
            call(6, 'gim.foo', '666', 111111, b=222222, ws_extra={'topic': 'gim.foo', 'msg_id': 6}),
            call(7, 'gim.baz', None, 1111111, b=2222222, ws_extra={'topic': 'gim.baz', 'msg_id': 7}),
        ])

    @inlineCallbacks
    def test_publish_send_unsent_messages(self):
        # Send some messages
        with patch.object(FakeCrossbar, 'publish'):
            yield self.publisher.publish('foo', 666, 1, b=2)  # id 1
            yield self.publisher.publish('foo', 666, 11, b=22)  # id 2
            yield self.publisher.publish('foo', 666, 111, b=222)  # id 3
            yield self.publisher.publish('foo2', 666, 1111, b=2222)  # id 4

        # Fake send more messages
        with patch.object(self.publisher, 'send_message'):
            yield self.publisher.publish('bar', 667, 11111, b=22222)  # id 5
            yield self.publisher.publish('foo', 666, 111111, b=222222)  # id 6
            yield self.publisher.publish('baz', None, 1111111, b=2222222)  # id 7

        # Send one with sending reactivated,
        with patch.object(FakeCrossbar, 'publish') as publish:
            yield self.publisher.publish('baz2', None, 11111111, b=22222222)  # id 8

        self.assertEqual(publish.call_args_list, [
            call('gim.bar', 11111, b=22222, ws_extra={'msg_id': 5, 'topic': 'gim.bar'}),
            call('gim.foo', 111111, b=222222, ws_extra={'msg_id': 6, 'topic': 'gim.foo'}),
            call('gim.baz', 1111111, b=2222222, ws_extra={'msg_id': 7, 'topic': 'gim.baz'}),
            call('gim.baz2', 11111111, b=22222222, ws_extra={'msg_id': 8, 'topic': 'gim.baz2'}),
        ])

    @inlineCallbacks
    def test_get_messages(self):
        # Send two messages
        with patch.object(FakeCrossbar, 'publish'):
            yield self.publisher.publish('foo', 666, 1, b=2)  # id 1
            yield self.publisher.publish('foo', 666, 11, b=22)  # id 2

        # Fake send more messages
        with patch.object(self.publisher, 'send_message'):
            # And don't try to send unsent messages for now
            with patch.object(self.publisher, 'send_unsent_messages'):
                yield self.publisher.publish('foo', 666, 111, b=222)  # id 3
                yield self.publisher.publish('foo2', 666, 1111, b=2222)  # id 4
                yield self.publisher.publish('bar', 667, 11111, b=22222)  # id 5
                yield self.publisher.publish('foo', 666, 111111, b=222222)  # id 6
                yield self.publisher.publish('baz', None, 1111111, b=2222222)  # id 7
                yield self.publisher.publish('baz2', None, 11111111, b=22222222)  # id 8

        result = yield self.publisher.get_messages(3, 7)

        self.assertEqual(result, [
            (3, {'topic': 'gim.foo', 'msg_id': 3, 'args': [111], 'kwargs': {'b': 222}},
             'gim.foo', [], '666'),
            (4, {'topic': 'gim.foo2', 'msg_id': 4, 'args': [1111], 'kwargs': {'b': 2222}},
             'gim.foo2', [], '666'),
            (5, {'topic': 'gim.bar', 'msg_id': 5, 'args': [11111], 'kwargs': {'b': 22222}},
             'gim.bar', [], '667'),
            (6, {'topic': 'gim.foo', 'msg_id': 6, 'args': [111111], 'kwargs': {'b': 222222}},
             'gim.foo', [], '666'),
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [], None),
        ])

        result = yield self.publisher.get_messages(3, 7, [
            ('gim.foo', ws.TOPIC_TYPE_EXACT),
            ('gim.ba', ws.TOPIC_TYPE_PREFIX),
        ])

        self.assertEqual(result, [
            (3, {'topic': 'gim.foo', 'msg_id': 3, 'args': [111], 'kwargs': {'b': 222}},
             'gim.foo', [('gim.foo', ws.TOPIC_TYPE_EXACT), ], '666'),
            (5, {'topic': 'gim.bar', 'msg_id': 5, 'args': [11111], 'kwargs': {'b': 22222}},
             'gim.bar', [('gim.ba', ws.TOPIC_TYPE_PREFIX), ], '667'),
            (6, {'topic': 'gim.foo', 'msg_id': 6, 'args': [111111], 'kwargs': {'b': 222222}},
             'gim.foo', [('gim.foo', ws.TOPIC_TYPE_EXACT), ], '666'),
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [('gim.ba', ws.TOPIC_TYPE_PREFIX), ], None),
        ])

        result = yield self.publisher.get_messages()
        self.assertEqual(result, [
            (1, {'topic': 'gim.foo', 'msg_id': 1, 'args': [1], 'kwargs': {'b': 2}},
             'gim.foo', [], '666'),
            (2, {'topic': 'gim.foo', 'msg_id': 2, 'args': [11], 'kwargs': {'b': 22}},
             'gim.foo', [], '666'),
            (3, {'topic': 'gim.foo', 'msg_id': 3, 'args': [111], 'kwargs': {'b': 222}},
             'gim.foo', [], '666'),
            (4, {'topic': 'gim.foo2', 'msg_id': 4, 'args': [1111], 'kwargs': {'b': 2222}},
             'gim.foo2', [], '666'),
            (5, {'topic': 'gim.bar', 'msg_id': 5, 'args': [11111], 'kwargs': {'b': 22222}},
             'gim.bar', [], '667'),
            (6, {'topic': 'gim.foo', 'msg_id': 6, 'args': [111111], 'kwargs': {'b': 222222}},
             'gim.foo', [], '666'),
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [], None),
            (8, {'topic': 'gim.baz2', 'msg_id': 8, 'args': [11111111], 'kwargs': {'b': 22222222}},
             'gim.baz2', [], None),
        ])

        result = yield self.publisher.get_messages(first_msg_id=7)
        self.assertEqual(result, [
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [], None),
            (8, {'topic': 'gim.baz2', 'msg_id': 8, 'args': [11111111], 'kwargs': {'b': 22222222}},
             'gim.baz2', [], None),
        ])

        result = yield self.publisher.get_messages(last_msg_id=2)
        self.assertEqual(result, [
            (1, {'topic': 'gim.foo', 'msg_id': 1, 'args': [1], 'kwargs': {'b': 2}},
             'gim.foo', [], '666'),
            (2, {'topic': 'gim.foo', 'msg_id': 2, 'args': [11], 'kwargs': {'b': 22}},
             'gim.foo', [], '666'),
        ])


class ReconcilerTestCase(UsingAsyncRedis):

    @inlineCallbacks
    def setUp(self):
        yield super(ReconcilerTestCase, self).setUp()
        self.app = FakeCrossbar()
        self.publisher = yield ws.AsyncPublisher.get_for(app=self.app)
        self.reconciler = ws.Reconciler(self.publisher)

    def test_limit_rules(self):
        result = self.reconciler.limit_rules([
            ('gim.front.foo', ws.TOPIC_TYPE_EXACT),
            ('gim.foo', ws.TOPIC_TYPE_EXACT),
            ('gim.front.bar', ws.TOPIC_TYPE_WILDCARD),
            ('gim.', ws.TOPIC_TYPE_PREFIX),
            ('gim.front.foo..bar', ws.TOPIC_TYPE_WILDCARD),
            ('gim.front.foo', ws.TOPIC_TYPE_PREFIX),
        ])
        self.assertEqual(result, {
            ('gim.front.foo', ws.TOPIC_TYPE_EXACT),
            ('gim.front.foo..bar', ws.TOPIC_TYPE_WILDCARD),
            ('gim.front.foo', ws.TOPIC_TYPE_PREFIX),
        })

    @inlineCallbacks
    def test_validate_ids(self):
        valid, error = yield self.reconciler.validate_ids('a')
        self.assertFalse(valid)
        self.assertIsInstance(error, dict)
        self.assertEqual(error.keys(), ['error'])
        self.assertEqual(error['error']['code'], 'REC0001')

        valid, error = yield self.reconciler.validate_ids(1, 'b')
        self.assertFalse(valid)
        self.assertEqual(error['error']['code'], 'REC0001')

        valid, error = yield self.reconciler.validate_ids(3, 3)
        self.assertFalse(valid)
        self.assertEqual(error['error']['code'], 'REC0001')

        valid, error = yield self.reconciler.validate_ids(4, 3)
        self.assertFalse(valid)
        self.assertEqual(error['error']['code'], 'REC0001')

        # Simulate 2 sent messages, with id 2 and 3
        yield self.db.zadd(self.publisher.source_object.repositories.key, 2, '2:')
        yield self.db.zadd(self.publisher.source_object.repositories.key, 3, '3:')

        valid, error = yield self.reconciler.validate_ids(1)
        self.assertFalse(valid)
        self.assertEqual(error['error']['code'], 'REC0002')

        valid, error = yield self.reconciler.validate_ids(1, 4)
        self.assertFalse(valid)
        self.assertEqual(error['error']['code'], 'REC0002')

        valid, error = yield self.reconciler.validate_ids(2)
        self.assertTrue(valid)
        self.assertIsNone(error)

        valid, error = yield self.reconciler.validate_ids(2, 3)
        self.assertTrue(valid)
        self.assertIsNone(error)

        valid, error = yield self.reconciler.validate_ids(2, 4)
        self.assertFalse(valid)
        self.assertEqual(error['error']['code'], 'REC0003')


    def test_prepare_messages(self):
        messages = [
            (6, {'topic': 'gim.foo', 'msg_id': 6, 'args': [111111], 'kwargs': {'b': 222222}},
             'gim.foo', [('gim.foo', ws.TOPIC_TYPE_EXACT), ], '666'),
            (7, {'topic': 'gim.baz', 'msg_id': 7, 'args': [1111111], 'kwargs': {'b': 2222222}},
             'gim.baz', [('gim.ba', ws.TOPIC_TYPE_PREFIX), ], None),
        ]

        result = self.reconciler.prepare_messages(messages)
        self.assertEqual(result, [
            {'args': [111111], 'kwargs': {'b': 222222,
                'ws_extra': {'topic': 'gim.foo', 'msg_id': 6,
                    'subscribed': [('gim.foo', ws.TOPIC_TYPE_EXACT), ]}}},
            {'args': [1111111], 'kwargs': {'b': 2222222,
                'ws_extra': {'topic': 'gim.baz', 'msg_id': 7,
                    'subscribed': [('gim.ba', ws.TOPIC_TYPE_PREFIX), ]}}},
        ])

    @inlineCallbacks
    def test_get_data(self):
        # Start at id 2 to test reconciliation with previous id
        self.db.set(self.publisher.source_object.last_msg_id.key, 2)

        # Send some messages
        with patch.object(FakeCrossbar, 'publish'):
            yield self.publisher.publish('front.foo', 666, 111, b=222)  # id 3
            yield self.publisher.publish('front.foo2', 666, 1111, b=2222)  # id 4
            yield self.publisher.publish('front.bar', 667, 11111, b=22222)  # id 5
            yield self.publisher.publish('front.foo', 666, 111111, b=222222)  # id 6
            yield self.publisher.publish('front.baz', None, 1111111, b=2222222)  # id 7
            yield self.publisher.publish('front.baz2', None, 11111111, b=22222222)  # id 8

        # from_msg_id too low
        result = yield self.reconciler.get_data(last_received_id=1, next_received_id=None,
                                                topics_rules=[
            ('gim.front.foo', ws.TOPIC_TYPE_EXACT),
            ('gim.front.ba', ws.TOPIC_TYPE_PREFIX),
        ], iteration=1)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.keys(), ['error'])

        # The client already received all the messages
        result = yield self.reconciler.get_data(last_received_id=8, next_received_id=None,
                                                topics_rules=[
            ('gim.front.foo', ws.TOPIC_TYPE_EXACT),
            ('gim.front.ba', ws.TOPIC_TYPE_PREFIX),
        ], iteration=1)
        self.assertEqual(result, {
            'missed_messages': [],
            'max_msg_id': 8,
            'last_msg_id': 8,
            'iteration': 1.
        })

        # The client needed some messages

        result = yield self.reconciler.get_data(last_received_id=4, next_received_id=None,
                                                topics_rules=[
            ('gim.front.foo', ws.TOPIC_TYPE_EXACT),
            ('gim.front.baz', ws.TOPIC_TYPE_PREFIX),
        ], iteration=2)
        self.assertEqual(result, {
            'missed_messages': [
                {'args': [111111], 'kwargs': {'b': 222222,
                    'ws_extra': {'topic': 'gim.front.foo', 'msg_id': 6,
                        'subscribed': [('gim.front.foo', ws.TOPIC_TYPE_EXACT), ]}}},
                {'args': [1111111], 'kwargs': {'b': 2222222,
                    'ws_extra': {'topic': 'gim.front.baz', 'msg_id': 7,
                        'subscribed': [('gim.front.baz', ws.TOPIC_TYPE_PREFIX), ]}}},
                {'args': [11111111], 'kwargs': {'b': 22222222,
                    'ws_extra': {'topic': 'gim.front.baz2', 'msg_id': 8,
                        'subscribed': [('gim.front.baz', ws.TOPIC_TYPE_PREFIX), ]}}},
            ],
            'max_msg_id': 8,  # max in `missed_messages`, also the last at fetch time
            'last_msg_id': 8,
            'iteration': 2.
        })

        result = yield self.reconciler.get_data(last_received_id=4, next_received_id=None,
                                                topics_rules=[
            ('gim.front.foo', ws.TOPIC_TYPE_EXACT),
        ], iteration=1)
        self.assertEqual(result, {
            'missed_messages': [
                {'args': [111111], 'kwargs': {'b': 222222,
                    'ws_extra': {'topic': 'gim.front.foo', 'msg_id': 6,
                        'subscribed': [('gim.front.foo', ws.TOPIC_TYPE_EXACT), ]}}},

            ],
            'max_msg_id': 8,  # the last at fetch time
            'last_msg_id': 8,
            'iteration': 1.
        })

        # We shouldn't have a lock on iteration < 5
        with patch.object(self.publisher, 'lock_publishing', autospec=True) as locked:
            result = yield self.reconciler.get_data(last_received_id=4, next_received_id=8,
                                                    topics_rules=[
                ('gim.front.foo', ws.TOPIC_TYPE_EXACT),
                ('gim.front.baz', ws.TOPIC_TYPE_PREFIX),
            ], iteration=1)
        self.assertEqual(locked.call_count, 0)
        self.assertEqual(result, {
            'missed_messages': [
                {'args': [111111], 'kwargs': {'b': 222222,
                    'ws_extra': {'topic': 'gim.front.foo', 'msg_id': 6,
                        'subscribed': [('gim.front.foo', ws.TOPIC_TYPE_EXACT), ]}}},
                {'args': [1111111], 'kwargs': {'b': 2222222,
                    'ws_extra': {'topic': 'gim.front.baz', 'msg_id': 7,
                        'subscribed': [('gim.front.baz', ws.TOPIC_TYPE_PREFIX), ]}}},
            ],
            'max_msg_id': 8,  # `next_received_id`, also the last at fetch time
            'last_msg_id': 8,
            'iteration': 1.
        })

        # We should have a lock on iteration 5
        with patch.object(self.publisher, 'lock_publishing', autospec=True) as locked:
            result = yield self.reconciler.get_data(last_received_id=4, next_received_id=7,
                                                    topics_rules=[
                ('gim.front.foo', ws.TOPIC_TYPE_EXACT),
                ('gim.front.baz', ws.TOPIC_TYPE_PREFIX),
            ], iteration=5)
        locked.assert_called_once_with()
        self.assertEqual(result, {
            'missed_messages': [
                {'args': [111111], 'kwargs': {'b': 222222,
                    'ws_extra': {'topic': 'gim.front.foo', 'msg_id': 6,
                        'subscribed': [('gim.front.foo', ws.TOPIC_TYPE_EXACT), ]}}},
            ],
            'max_msg_id': 8,  # the last at fetch time
            'last_msg_id': 8,
            'iteration': 5.
        })
