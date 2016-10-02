__all__ = [
    'ResetTokenFlags',
]

from django.utils.functional import cached_property

from limpyd_jobs import STATUSES

from gim.core.limpyd_models import Token

from .base import Job


class ResetTokenFlags(Job):
    queue_name = 'reset-token-flags'

    @cached_property
    def token_obj(self):
        try:
            return Token.get(token=self.identifier.hget())
        except Token.DoesNotExist:
            self.hmset(status=STATUSES.CANCELED, cancel_on_error=1)
            raise

    def run(self, queue):
        super(ResetTokenFlags, self).run(queue)

        return self.token_obj.reset_flags()

    def on_success(self, queue, result):
        if result is False:
            ttl = self.token_obj.connection.ttl(self.token_obj.rate_limit_remaining.key)
            self.clone(delayed_for=ttl+2)
