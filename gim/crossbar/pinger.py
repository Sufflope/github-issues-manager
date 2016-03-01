from datetime import datetime
import logging

from twisted.internet.defer import inlineCallbacks

from autobahn.twisted.util import sleep as txsleep
from autobahn.twisted.wamp import ApplicationSession

from django.utils.dateformat import format

from gim import ws


logger = logging.getLogger('gim.ws.pinger')


class Pinger(ApplicationSession):

    @inlineCallbacks
    def onJoin(self, details):

        publisher = yield ws.AsyncPublisher.get_for(app=self)

        while True:

            last_msg_id = yield publisher.get_last_msg_id()

            yield self.publish('gim.ping',
                               last_msg_id=last_msg_id,
                               # Use the same format as `utcnow|date:"r"` in template
                               utcnow=format(datetime.utcnow(), 'r'),
                               )

            logger.info('Ping with last_msg_id=%s', last_msg_id)

            yield txsleep(15)
