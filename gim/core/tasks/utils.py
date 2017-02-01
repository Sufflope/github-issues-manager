from collections import defaultdict, OrderedDict
from datetime import datetime
import logging
from operator import attrgetter, itemgetter

from limpyd_jobs import STATUSES

from django.utils.termcolors import colorize

from gim.hooks.tasks import CheckRepositoryHook, CheckRepositoryEvents

from ..models import GithubUser, Repository

from . import JobRegistry
from .base import Queue, Error
from .repository import FetchForUpdate

maintenance_logger = logging.getLogger('gim.maintenance')


def get_job_models():
    """
    Return the list of all Job models, sorted by queue_name
    """
    return sorted(JobRegistry, key=attrgetter('queue_name'))


def get_job_model_for_name(name):
    """
    Given a queue name, return the matching Job model
    """
    return [J for J in JobRegistry if J.queue_name == name][0]


def print_queues():
    """
    Print each queue with waiting or delayed jobs, by priority
    """
    queues = OrderedDict()
    for q in Queue.collection().sort(by='name', alpha=True).instances():
        waiting = q.waiting.llen()
        delayed = q.delayed.zcard()
        if waiting + delayed == 0:
            continue
        name, priority = q.hmget('name', 'priority')
        queues.setdefault(name, []).append({
            'priority': int(priority),
            'waiting': waiting,
            'delayed': delayed,
        })

    for name in queues:
        sub_queues = sorted(queues[name], key=itemgetter('priority'), reverse=True)

        total_waiting = sum([q['waiting'] for q in sub_queues])
        total_delayed = sum([q['delayed'] for q in sub_queues])

        if len(sub_queues) == 1:
            priority_part = sub_queues[0]['priority']
        else:
            priority_part = '----'

        print('%30s  %4s  %4d  %4d' % (name, priority_part, total_waiting, total_delayed))

        if len(sub_queues) > 1:
            for i, q in enumerate(sub_queues):
                print('%30s  %4d  %4d  %4d' % (' ', q['priority'], q['waiting'], q['delayed']))


def diff_queues(old_data=None, sort_by='name'):
    assert sort_by in ('name', 'priority')

    new_queues = {}

    # Get existing queues
    for order, q in enumerate(Queue.collection().sort(by=sort_by, alpha=(sort_by == 'name')).instances()):
        waiting = q.waiting.llen()
        delayed = q.delayed.zcard()
        if waiting + delayed == 0:
            continue
        name, priority = q.hmget('name', 'priority')
        priority = - int(priority or 0)  # `-` to sort easily
        new_queues[(name, priority)] = {
            'name': name,
            'priority': priority,
            'order': order,
            'waiting': waiting,
            'no_waiting': waiting == 0,
            'old_waiting': 0,
            'delayed': delayed,
            'old_delayed': 0,
        }

    # Add old data
    queues = new_queues.copy()
    for key, value in old_data.items() or []:
        if key in queues:
            queues[key].update({
                'old_waiting': value['waiting'],
                'old_delayed': value['delayed'],
            })
            continue

        queues[key] = {
            'name': key[0],
            'priority': key[1],
            'order': 9999,
            'waiting': 0,
            'no_waiting': True,
            'old_waiting': value['waiting'],
            'delayed': 0,
            'old_delayed': value['delayed'],
        }

    # Final sort ( https://wiki.python.org/moin/HowTo/Sorting#Sort_Stability_and_Complex_Sorts )
    sorted_queues = queues.values()
    sort_keys = ('name', 'priority') if sort_by == 'name' else ('no_waiting', 'priority', 'order')
    for sort_key in sort_keys[::-1]:
        sorted_queues = sorted(sorted_queues, key=itemgetter(sort_key))

    # Display
    for queue in sorted_queues:
        changed = False
        waiting_output = '%5s' % queue['waiting']
        if queue['waiting'] != queue['old_waiting']:
            changed = True
            waiting_color = 'green' if queue['waiting'] < queue['old_waiting'] else 'red'
            waiting_output = colorize(waiting_output, fg=waiting_color, opts=['bold'])
        delayed_output = '%5s' % queue['delayed']
        if queue['delayed'] != queue['old_delayed']:
            changed = True
            delayed_color = 'green' if queue['delayed'] < queue['old_delayed'] else 'red'
            delayed_output = colorize(delayed_output, fg=delayed_color, opts=['bold'])

        name_output = '%30s' % queue['name']
        if changed:
            name_output = colorize(name_output, opts=['bold'])

        print('%s  %4d  %s  %s' % (name_output, -queue['priority'], waiting_output, delayed_output))

    # Return only new queues, not old ones without items
    return new_queues


def delete_empty_queues(dry_run=False, max_priority=0):
    """
    Delete all queues without any waiting or delayed job
    """
    for JobModel in get_job_models():
        QueueModel = JobModel.queue_model
        name = JobModel.queue_name

        for q in QueueModel.get_all_by_priority(name):
            priority = int(q.priority.hget())
            if priority >= max_priority:
                continue

            # two checks to be sure
            if q.waiting.llen() + q.delayed.zcard() > 0:
                continue
            if q.waiting.llen() + q.delayed.zcard() > 0:
                continue

            if dry_run:
                maintenance_logger.info('Empty: %s (%d)', name, priority)
            else:
                q.delete()
                maintenance_logger.info('Deleted: %s (%d)', name, priority)


def requeue_halted_jobs(dry_run=False):
    """
    Requeue all jobs that were halted but still in running state
    """

    for JobModel in get_job_models():

        running_job_ids = list(JobModel.collection(queued=1, status=STATUSES.RUNNING))
        for job_id in running_job_ids:

            try:
                job = JobModel.get(job_id)
            except JobModel.DoesNotExist:
                continue

            if job.ident in (job.queue.waiting.lmembers() + job.queue.delayed.zmembers()):
                # ignore job if already waiting or delayed
                continue

            priority = int(job.priority.hget() or 0)

            if dry_run:
                maintenance_logger.info('Halted: %s (%s)', job.ident, priority)
            else:
                job.status.hset(STATUSES.WAITING)
                job.queue.enqueue_job(job)
                maintenance_logger.info('Requeued: %s (%s)', job.ident, priority)


def requeue_unqueued_waiting_jobs(dry_run=False):
    """
    Requeue all jobs that are marked as waiting but not in a waiting queue
    """

    for JobModel in get_job_models():
        waiting_job_ids = list(JobModel.collection(queued=1, status=STATUSES.WAITING))
        queues = Queue.collection(name=JobModel.queue_name).instances()

        for job_id in waiting_job_ids:

            try:
                job = JobModel.get(job_id)
            except JobModel.DoesNotExist:
                continue

            if job.ident in job.queue.waiting.lmembers():
                continue

            found = False
            for queue in queues:
                if job.ident in queue.waiting.lmembers():
                    found = True
                    break

            if not found:
                # one more check
                if job.status.hget() == STATUSES.WAITING and job.ident not in job.queue.waiting.lmembers():

                    priority = int(job.priority.hget() or 0)

                    if dry_run:
                        maintenance_logger.info('Not queued: %s (%s)', job.ident, priority)
                    else:
                        job.queue.enqueue_job(job)
                        maintenance_logger.info('Requeued: %s (%s)', job.ident, priority)


def requeue_unqueued_delayed_jobs(dry_run=False):
    """
    Requeue all jobs that are marked as delayed but not in a delayed queue
    """

    for JobModel in get_job_models():
        delayed_job_ids = list(JobModel.collection(queued=1, status=STATUSES.DELAYED))
        queues = Queue.collection(name=JobModel.queue_name).instances()

        for job_id in delayed_job_ids:

            try:
                job = JobModel.get(job_id)
            except JobModel.DoesNotExist:
                continue

            if job.ident in job.queue.delayed.zmembers():
                continue

            found = False
            for queue in queues:
                if job.ident in queue.delayed.zmembers():
                    found = True
                    break

            if not found:
                # one more check
                if job.status.hget() == STATUSES.DELAYED and job.ident not in job.queue.delayed.zmembers():

                    priority = int(job.priority.hget() or 0)

                    if dry_run:
                        maintenance_logger.info('Not queued: %s (%s)', job.ident, priority)
                    else:
                        job.queue.delay_job(job, job.delayed_until.hget())
                        maintenance_logger.info('Requeued: %s (%s)', job.ident, priority)


def requeue_unqueued_errored_jobs(dry_run=False):
    """
    Requeue all jobs that are marked as errored but not in a queue
    """

    for JobModel in get_job_models():
        errored_job_ids = list(JobModel.collection(queued=1, status=STATUSES.ERROR))
        queues = Queue.collection(name=JobModel.queue_name).instances()

        for job_id in errored_job_ids:

            try:
                job = JobModel.get(job_id)
            except JobModel.DoesNotExist:
                continue

            if job.ident in job.queue.delayed.zmembers():
                continue
            if job.ident in job.queue.waiting.lmembers():
                continue

            found = False
            for queue in queues:
                if job.ident in queue.delayed.zmembers():
                    found = True
                    break
                if job.ident in queue.waiting.lmembers():
                    found = True
                    break

            if not found:
                # one more check
                if job.ident not in job.queue.delayed.zmembers() and job.ident not in job.queue.waiting.lmembers():

                    priority = int(job.priority.hget() or 0)

                    if dry_run:
                        maintenance_logger.info('Not queued: %s (%s)', job.ident, priority)
                    else:
                        job.status.hset('w')
                        job.queue.enqueue_job(job)
                        maintenance_logger.info('Requeued: %s (%s)', job.ident, priority)


def get_last_error_for_job(job, index=0, date=None):
    """
    Return the last (or last-index if index is given) error for the given job,
    for the given date (use today if not given)
    """
    if not date:
        date = datetime.utcnow().strftime('%Y-%m-%d')
    return Error.collection_for_job(job).filter(date=date).sort(by='-time', alpha=True).instances()[index]


def get_last_error_for_job_model(job_model, index=0, date=None):
    """
    Return the last (or last-index if index is given) error for the given job model,
    for the given date (use today if not given)
    """
    if not date:
        date = datetime.utcnow().strftime('%Y-%m-%d')
    job_model_repr = '%s.%s' % (job_model.__module__, job_model.__name__)
    return Error.collection(job_model_repr=job_model_repr).filter(date=date).sort(by='-time', alpha=True).instances()[index]


def get_last_errors_for_job_model(job_model, count=10, date=None):
    """
    Return some of the last (or last-index if index is given) errors for the given job model,
    for the given date (use today if not given)
    """
    if not date:
        date = datetime.utcnow().strftime('%Y-%m-%d')
    job_model_repr = '%s.%s' % (job_model.__module__, job_model.__name__)
    return Error.collection(job_model_repr=job_model_repr).filter(date=date).sort(by='-time', alpha=True).instances()[:count]


def requeue_job(job, priority=0):
    """
    Reset the priority (default to 0) and status (WAITING) of a job and requeue it
    """
    job.priority.hset(priority)
    job.status.hset(STATUSES.WAITING)
    job.queue.enqueue_job(job)


def update_user_related_stuff(username, gh=None, dry_run=False, user=None):
    """
    Fetch for update all stuff related to the user.
    Needed before deleting a user which was deleted on the Github side.
    """
    if not dry_run and not gh:
        raise Exception('If dry_run set to False, you must pass gh')

    user = user or GithubUser.objects.get(username=username)

    issues_fetched = set()
    rest = defaultdict(int)

    repositories = user.owned_repositories.all()
    if len(repositories):
        maintenance_logger.info('Owned repositories: %s', ', '.join(['[%s] %s' % (r.id, r.full_name) for r in repositories]))
        if not dry_run:
            for r in repositories:
                try:
                    r.fetch(gh=gh, force_fetch=True)
                except Exception as e:
                    maintenance_logger.info('Failure while updating repository %s: %s', r.id, e)
            repositories = user.owned_repositories.all()
            if len(repositories):
                rest['Repository'] += len(repositories)
                maintenance_logger.info('STILL Owned repositories: %s', ', '.join(['[%s] %s' % (r.id, r.full_name) for r in repositories]))

    milestones = user.milestones.all()
    if len(milestones):
        maintenance_logger.info('Created milestones: %s', ', '.join(['[%s] %s:%s' % (m.id, m.repository.full_name, m.title) for m in milestones]))
        if not dry_run:
            for m in milestones:
                try:
                    m.fetch(gh=gh, force_fetch=True)
                except Exception as e:
                    maintenance_logger.info('Failure while updating milestone %s: %s', m.id, e)
            milestones = user.milestones.all()
            if len(milestones):
                rest['Milestone'] += len(milestones)
                maintenance_logger.info('STILL Created milestones: %s', ', '.join(['[%s] %s:%s' % (m.id, m.repository.full_name, m.title) for m in milestones]))

    for field, name in [('commits_authored', 'Authored'), ('commits_commited', 'Commited')]:
        commits = getattr(user, field).all()
        if len(commits):
            maintenance_logger.info('%s commits: %s', name, ', '.join(['[%s] %s:%s' % (c.id, c.repository.full_name, c.sha) for c in commits]))
            if not dry_run:
                for c in commits:
                    try:
                        c.fetch(gh=gh, force_fetch=True)
                    except Exception as e:
                        maintenance_logger.info('Failure while updating commit %s: %s', c.id, e)
                commits = getattr(user, field).all()
                if len(commits):
                    rest['Commit'] += len(commits)
                    maintenance_logger.info('STILL %s commits: %s', name, ', '.join(['[%s] %s:%s' % (c.id, c.repository.full_name, c.sha) for c in commits]))

    for field, name in [('created_issues', 'Created'), ('assigned_issues', 'Assigned'), ('closed_issues', 'Closed'), ('merged_prs', 'Merged')]:
        issues = getattr(user, field).all()
        if len(issues):
            maintenance_logger.info('%s issues: %s', name, ', '.join(['[%s] %s:%s' % (i.id, i.repository.full_name, i.number) for i in issues]))
            if not dry_run:
                for i in issues:
                    if i.id in issues_fetched:
                        continue
                    try:
                        i.fetch_all(gh=gh, force_fetch=True)
                    except Exception as e:
                        maintenance_logger.info('Failure while updating issue %s: %s' % (i.id, e))
                    issues_fetched.add(i.id)
                issues = getattr(user, field).all()
                if len(issues):
                    rest['Issue'] += len(issues)
                    maintenance_logger.info('STILL %s issues: %s', name, ', '.join(['[%s] %s:%s' % (i.id, i.repository.full_name, i.number) for i in issues]))

    for field, name in [('issue_comments', 'Simple'), ('pr_comments', 'Code')]:
        comments = getattr(user, field).all()
        if len(comments):
            maintenance_logger.info('%s comments: %s', name, ', '.join(['[%s] %s:%s' % (c.id, c.repository.full_name, c.issue.number) for c in comments]))
            if not dry_run:
                for c in comments:
                    if c.issue_id in issues_fetched:
                        continue
                    try:
                        c.issue.fetch_all(gh=gh, force_fetch=True)
                    except Exception as e:
                        maintenance_logger.info('Failure while updating issue %s for comment %s: %s', c.issue.id, c.id, e)
                    issues_fetched.add(c.issue_id)
                comments = getattr(user, field).all()
                if len(comments):
                    rest[comments[0].model_name] += len(comments)
                    maintenance_logger.info('STILL %s comments: %s', name, ', '.join(['[%s] %s:%s' % (c.id, c.repository.full_name, c.issue.number) for c in comments]))

    entry_points = user.pr_comments_entry_points.all()
    if len(entry_points):
        maintenance_logger.info('Started entry points: %s', ', '.join(['[%s] %s:%s' % (e.id, e.repository.full_name, e.issue.number) for e in entry_points]))
        if not dry_run:
            for ep in entry_points:
                try:
                    ep.update_starting_point()
                except Exception as e:
                    maintenance_logger.info('Failure while updating entry-point %s: %s', ep.id, e)
            entry_points = user.pr_comments_entry_points.all()
            if len(entry_points):
                rest['PullRequestCommentEntryPoint'] += len(entry_points)
                maintenance_logger.info('STILL Started entry points: %s', ', '.join(['[%s] %s:%s' % (e.id, e.repository.full_name, e.issue.number) for e in entry_points]))

    events = user.issues_events.all()
    if len(events):
        maintenance_logger.info('Issue events: %s', ', '.join(['[%s] %s:%s' % (e.id, e.repository.full_name, e.issue.number) for e in events]))
        if not dry_run:
            for ev in events:
                if ev.issue_id in issues_fetched:
                    continue
                try:
                    ev.issue.fetch_all(gh=gh, force_fetch=True)
                except Exception as e:
                    maintenance_logger.info('Failure while updating issue %s for event %s: %s', ev.issue.id, ev.id, e)
                issues_fetched.add(ev.issue_id)
            events = user.issues_events.all()
            if len(events):
                rest['Event'] += len(events)
                maintenance_logger.info('STILL Issue events: %s', ', '.join(['[%s] %s:%s' % (e.id, e.repository.full_name, e.issue.number) for e in events]))

    return rest


def requeue_all_repositories():
    """
    Add (ignore if already present) Hook and Event check jobs for all activated
    repositories
    """
    for repository in Repository.objects.filter(first_fetch_done=True):
        CheckRepositoryEvents.add_job(repository.id)
        CheckRepositoryHook.add_job(repository.id, delayed_for=30)
        FetchForUpdate.add_job(repository.id)


def requeue_all_users():
    from gim.core.tasks.githubuser import FetchAvailableRepositoriesJob, FetchNotifications

    for user in GithubUser.objects.filter(token__isnull=False):
        FetchNotifications.add_job(user.id)
        FetchAvailableRepositoriesJob.add_job(user.id)


def requeue_standalone_jobs():
    from gim.core.tasks.cleanup import CleanupJob
    from gim.core.tasks.general import ManageDeletedInstancesJob
    from gim.core.tasks.githubuser import CheckGraphQLAccesses
    from gim.core.tasks.tokens import ResetTokenFlags

    CleanupJob.add_job(42)
    ManageDeletedInstancesJob.add_job(42)
    CheckGraphQLAccesses.add_job(42)
    ResetTokenFlags.add_job(42)


def maintenance(include_users_and_repositories=True):
    maintenance_logger.info('Maintenance tasks...')
    maintenance_logger.info('    clear_requeue_delayed_lock_key...')
    for q in Queue.collection().instances():
        if q.requeue_delayed_lock_key_exists():
            maintenance_logger.info('     clear lock key for %s:%s', *q.hmget('name', 'priority'))
            q.clear_requeue_delayed_lock_key()
    maintenance_logger.info('    requeue_halted_jobs...')
    requeue_halted_jobs()
    maintenance_logger.info('    requeue_unqueued_waiting_jobs...')
    requeue_unqueued_waiting_jobs()
    maintenance_logger.info('    requeue_unqueued_delayed_jobs...')
    requeue_unqueued_delayed_jobs()
    maintenance_logger.info('    requeue_unqueued_errored_jobs...')
    requeue_unqueued_errored_jobs()
    maintenance_logger.info('    delete_empty_queues...')
    maintenance_logger.info('    requeue standalone jobs...')
    requeue_standalone_jobs()
    delete_empty_queues()
    if include_users_and_repositories:
        maintenance_logger.info('    requeue_all_users...')
        requeue_all_users()
        maintenance_logger.info('    requeue_all_repositories...')
        requeue_all_repositories()
    maintenance_logger.info('[done]')
