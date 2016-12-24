__all__ = [
    'ResetTokenFlags',
]


from gim.core.limpyd_models import Token

from .base import Job


class ResetTokenFlags(Job):
    queue_name = 'reset-token-flags'

    def run(self, queue):
        super(ResetTokenFlags, self).run(queue)
        Token.reset_all_flags()

    def on_success(self, queue, result):
        if self.identifier.hget() == '42':  # to avoid cloning previous individual jobs
            self.clone(delayed_for=60)
