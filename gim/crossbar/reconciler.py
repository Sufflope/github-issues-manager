import logging

from twisted.internet.defer import inlineCallbacks, returnValue

from autobahn import wamp
from autobahn.twisted.util import sleep as txsleep
from autobahn.twisted.wamp import ApplicationSession

from gim.front.ws import AsyncHistory, NotEnoughHistory, txLock


logger = logging.getLogger('gim.ws.reconcilier')


class GimReconciler(ApplicationSession):

    @inlineCallbacks
    def onJoin(self, details):
        try:
            self.history = AsyncHistory(self)
            yield self.register(self)
        except Exception:
            logger.exception('Failed to register reconciler')
        else:
            logger.info('Reconciler registered')

        lock = txLock(self.history.connection, self.history.lock_key)

        yield lock.acquire()
        try:
            yield self.history.send_unsent_messages()
        finally:
            yield lock.release()


    @wamp.register(u'gim.reconcile')
    @inlineCallbacks
    def reconcile(self, from_msg_id, topics, to_msg_id=None):

        topics = set([
            (topic, match)
            for topic, match
            in topics
            if topic.startswith('gim.front.') and not topic.startswith('gim.front..') and (
                match in (AsyncHistory.TOPIC_TYPE_EXACT, AsyncHistory.TOPIC_TYPE_PREFIX) or
                match == AsyncHistory.TOPIC_TYPE_WILDCARD and '..' in topic
            )
        ])

        logger.info('Reconciler called with from_msg_id=%s, to_msg_id=%s, topics=%s',
                    from_msg_id, to_msg_id, topics)

        try:

            try:
                history_entries, max_msg_id = yield self.history.get_history(
                    from_msg_id=from_msg_id,
                    to_msg_id=to_msg_id,
                    topics=topics,
                    ensure_first=True
                )
            except NotEnoughHistory:
                logger.warning('Not enough message in history to reconcile')
                returnValue({
                    'error': {'message': 'You were offline too long.'}
                })
            else:
                missed_entries = [
                    {
                        'args': entry['args'],
                        'kwargs': entry['kwargs'],
                        'details': {
                            'extra': {
                                'msg_id': msg_id,
                                'subscribed_topic': topic,
                                'subscribed_match': match,
                            },
                            'topic': entry['topic'],
                        }
                    }
                    for topic, match, entry, msg_id in history_entries
                ]

                last_msg_id = yield self.history.get_last_msg_id()

                result = {
                    'missed_entries': missed_entries,
                    'max_msg_id': max_msg_id,
                    'last_msg_id': last_msg_id,
                }

                returnValue(result)

        except Exception:
            logger.exception('Failed to reconcile')
            returnValue({
                'error': {
                    'message': 'There was a problem synchronizing data sent when you were offline.'
                }
            })
