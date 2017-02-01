from datetime import datetime, timedelta
from random import randint
import logging

from .base import Error, Job, Queue
from . import JobRegistry


__all__ = [
    'CleanupJob',
]


logger = logging.getLogger('gim.maintenance')


def _get_past_date(days):
    return (datetime.utcnow()-timedelta(days=days)).strftime('%Y-%m-%d')


def clean_errors(log_step=1000, keep_days=7, batch_size=100, max_delete=None):
    """
    Remove from the Errors model all entries older than the given number of days
    """
    count = len(Error.collection())
    max_date = _get_past_date(keep_days)
    done = 0
    errors = 0
    logger.info('Deleting Error (limit: %s, max-date: %s, total: %d)', max_delete, max_date, count)
    stop = False
    iterate = 0
    while not stop:
        instances = list(Error.collection().sort(by='date', alpha=True).instances(skip_exist_test=True)[:batch_size])
        if not instances:
            break
        for instance in instances:
            iterate += 1
            if iterate and not iterate % log_step:
                logger.info('Deleted %d on %d (limit %s)', done, count, max_delete)
            try:
                if keep_days and instance.date.hget() >= max_date:
                    stop = True
                    break
                instance.delete()
            except Exception, e:
                logger.info('Cannot delete Error %s: %s', instance.pk.get(), e)
                errors += 1
            else:
                done += 1
            if max_delete and iterate >= max_delete:
                stop = True
                break

    logger.info('Total Error deleted (limit %s): %d on %d, keep %d (including %d errors)', max_delete, done, count, count - done, errors)


def clean_job_model(job_model, log_step=1000, keep_days=7, batch_size=100, max_delete=None):
    """
    Remove from the given job model all entries older than the given number of days
    Also clear the success and errors list of all the queues (different priorities)
    linked to the model
    """
    model_repr = job_model.get_model_repr()
    count = len(job_model.collection())
    max_date = _get_past_date(keep_days)
    done = 0
    errors = 0
    planned = set(sum([q.waiting.lmembers() + q.delayed.zmembers() for q in Queue.get_all_by_priority(job_model.queue_name)], []))
    logger.info('Deleting %s (limit: %s, max-date: %s, total: %d (planned: %d))', model_repr, max_delete, max_date, count, len(planned))
    kept = 0
    iterate = 0
    while (not max_delete) or (iterate < max_delete):
        instances = list(job_model.collection().instances(skip_exist_test=True)[kept:kept+batch_size])
        if not instances:
            break
        for instance in instances:
            iterate += 1
            if iterate and not iterate % log_step:
                logger.info('Deleted %d on %d (limit %s, kept %d)', done, count, max_delete, kept)
            try:
                if instance.ident in planned or keep_days and instance.added.hget()[:10] >= max_date:
                    # skip it, so stay in the list, so skip in the next batch
                    kept += 1
                    continue
                instance.delete()
            except Exception, e:
                logger.info('Cannot delete %s %s: %s', model_repr, instance.pk.get(), e)
                errors += 1
                # skip it, so stay in the list, so skip in the next batch
                kept += 1
            else:
                done += 1
            if max_delete and iterate >= max_delete:
                break

    for q in Queue.get_all_by_priority(job_model.queue_name):
        q.success.delete()
        q.errors.delete()

    logger.info('Total %s deleted (limit %s): %d on %d, keep %d (including %d errors and %d planned)', model_repr, max_delete, done, count, kept, errors, len(planned))


def clean_all(log_step=1000, keep_days=7, batch_size=100, max_delete=None):
    """
    Remove from the Error and all Job models entries older than the given number of days
    """
    clean_errors(log_step=log_step, keep_days=keep_days, batch_size=batch_size, max_delete=max_delete)
    for J in JobRegistry:
        clean_job_model(J, log_step=log_step, keep_days=keep_days, batch_size=batch_size, max_delete=max_delete)


class CleanupJob(Job):
    queue_name = 'cleanup'

    def run(self, queue):
        super(CleanupJob, self).run(queue)

        # between 1000 and 3000
        clean_all(keep_days=3, max_delete=1000 + randint(0, 2000))

    def on_success(self, queue, result):
        """ Clean again in 300s +- 60 """

        self.clone(delayed_for=240 + randint(0, 120))
