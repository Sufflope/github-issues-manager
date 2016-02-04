import logging

from autobahn import wamp
from autobahn.twisted.wamp import ApplicationSession
from twisted.internet.defer import inlineCallbacks, returnValue

from gim import ws

logger = logging.getLogger('gim.ws.reconcilier')


class GimReconciler(ApplicationSession):

    @inlineCallbacks
    def onJoin(self, details):
        try:
            self.publisher = yield ws.AsyncPublisher.get_for(app=self)
            self.reconciler = ws.Reconciler(self.publisher)
            yield self.register(self)
        except Exception:
            logger.exception('Failed to register reconciler')
        else:
            logger.info('Reconciler registered')

        lock = self.publisher.lock_publishing()
        yield lock.acquire()
        try:
            yield self.publisher.send_unsent_messages()
        finally:
            yield lock.release()

    @wamp.register(u'gim.reconcile')
    @inlineCallbacks
    def reconcile(self, last_received_id, topics_rules, iteration, next_received_id=None):
        try:
            data = yield self.reconciler.get_data(last_received_id, next_received_id,
                                                  topics_rules, iteration)
            returnValue(data)

        except Exception:
            logger.exception('Failed to reconcile')
            returnValue({
                'error': {
                    'message': 'There was a problem synchronizing data sent when you were offline.',
                    'code': 'REC0000',
                }
            })
