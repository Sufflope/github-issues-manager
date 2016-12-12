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
    def for_graphql(self):
        return self.identifier.hget().endswith(':graphql')

    @cached_property
    def token_obj(self):
        identifier = self.identifier.hget()
        if self.for_graphql:
            identifier = identifier.split(':graphql')[0]
        try:
            return Token.get(token=identifier)
        except Token.DoesNotExist:
            self.hmset(status=STATUSES.CANCELED, cancel_on_error=1)
            raise

    def run(self, queue):
        super(ResetTokenFlags, self).run(queue)
        return self.token_obj.reset_flags(self.for_graphql)

    def on_success(self, queue, result):
        if result is False:
            token = self.token_obj
            field = token.graphql_rate_limit_remaining if self.for_graphql else token.rate_limit_remaining
            ttl = token.connection.ttl(field.key)
            self.clone(delayed_for=ttl+2)
