from django.utils.functional import cached_property

__all__ = [
    'FetchUser',
    'FetchAvailableRepositoriesJob',
    'ManageDualUser',
    'FinalizeGithubNotification',
    'GithubNotificationEditJob',
    'FetchNotifications',
]

import sys

try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO

from async_messages import messages
from limpyd import fields

from gim.core.managers import MODE_UPDATE
from gim.core.models import GithubNotification, GithubUser
from gim.github import ApiNotFoundError

from .base import DjangoModelJob, Job
from .utils import update_user_related_stuff


class UserJob(DjangoModelJob):
    """
    Abstract job model for jobs based on the GithubUser model
    """
    abstract = True
    model = GithubUser

    @cached_property
    def user(self):
        return self.object


class FetchUser(UserJob):
    """We need to fetch the full user to have its name"""

    queue_name = 'fetch-user'
    clonable_fields = ('force_fetch', )

    force_fetch = fields.InstanceHashField()

    permission = 'read'

    def run(self, queue):
        super(FetchUser, self).run(queue)

        user = self.user

        gh = self.gh
        if not gh:
            return  # it's delayed !

        force_fetch = self.force_fetch.hget() == '1' or user.must_be_fetched()

        return user.fetch(gh, force_fetch=force_fetch)



class FetchAvailableRepositoriesJob(UserJob):
    """
    Job that fetches available repositories of a user
    """
    queue_name = 'fetch-available-repos'

    inform_user = fields.InstanceHashField()

    clonable_fields = ('gh', )
    permission = 'self'

    def run(self, queue):
        """
        Get the user and its available repositories from github, and save the
        counts in the job
        """
        super(FetchAvailableRepositoriesJob, self).run(queue)

        user = self.user

        # force gh if not set
        if not self.gh_args.hgetall():
            gh = user.get_connection()
            if gh and 'access_token' in gh._connection_args:
                self.gh = gh

        # check availability
        gh = self.gh
        if not gh:
            return  # it's delayed !

        nb_repos, nb_orgs, nb_watched, nb_starred, nb_teams, nb_notifs = user.fetch_all()

        if self.inform_user.hget() == '1':
            if nb_repos + nb_teams:
                message = u'The list of repositories you can subscribe to (ones you own, collaborate to, or in your organizations) was just updated'
            else:
                message = u'There is no new repositories you own, collaborate to, or in your organizations'
            messages.success(user, message)

        upgraded, downgraded = user.check_subscriptions()

        return nb_repos, nb_orgs, nb_watched, nb_starred, nb_teams, nb_notifs, len(upgraded), len(downgraded)

    def success_message_addon(self, queue, result):
        """
        Display infos got from the fetch_available_repositories call
        """
        nb_repos, nb_orgs, nb_watched, nb_starred, nb_teams, nb_notifs, nb_upgraded, nb_downgraded = result
        return ' [nb_repos=%d, nb_orgs=%d, nb_watched=%d, nb_starred=%d, nb_teams=%d, nb_notifs=%d, nb_upgraded=%d, nb_downgraded=%d]' % (
                nb_repos, nb_orgs, nb_watched, nb_starred, nb_teams, nb_notifs, nb_upgraded, nb_downgraded)

    def on_success(self, queue, result):
        """
        Make a new fetch later
        """
        self.clone(delayed_for=60*60*3)  # once per 3h


class ManageDualUser(Job):
    """
    Job that tries to resolve a new github user that cannot be inserted because one with the same
    username but a different github_id already exist.
    """

    queue_name = 'manage-dual-user'

    new_github_id = fields.InstanceHashField()
    resolution = fields.InstanceHashField()
    update_related_output = fields.InstanceHashField()

    clonable_fields = ('gh', 'new_github_id')

    def run(self, queue):
        """
        Will return `False` if nothing had to be done, `True`.
        Will raise if we cannot be sure at the end that the problem was solved.
        """

        super(ManageDualUser, self).run(queue)

        username, new_github_id = self.hmget('identifier', 'new_github_id')
        new_github_id = int(new_github_id)

        try:
            user = GithubUser.objects.exclude(github_id=new_github_id).get(username=username)
        except GithubUser.DoesNotExist:
            # Something already corrected the problem
            self.resolution.hset('Problem already managed')
            return False

        # Toekn to fetch the user and get the related data
        gh = self.gh
        if not gh:
            return  # it's delayed !

        # Start by fetching the existing user, maybe he just changed its name
        try:

            GithubUser.objects.get_from_github(
                gh=gh,
                identifiers=('user', user.github_id),  # Check by id, not username
                modes=MODE_UPDATE,
                force_update=True,
            )

        except ApiNotFoundError:
            # Ok the user was deleted, we have to update all related objects

            # But you start by changing it's username
            user.username = ('to-delete--%s--%s' % (user.github_id, user.username))[:255]
            user.save(update_fields=['username'])

            old_stdout = sys.stdout
            try:
                new_stdout = StringIO()
                sys.stdout = new_stdout
                rest = update_user_related_stuff(username, gh, user=user)
            finally:
                sys.stdout = old_stdout

            self.update_related_output.hset(new_stdout.getvalue())

            if rest:
                # Some data are still tied to the user: we have a problem
                raise Exception('There is still some data tied to the user')

            # Ok we're good, we can delete the user
            user.delete()
            self.resolution.hset('User deleted')
            return True

        else:
            # Check that the username has changed
            user = GithubUser.objects.get(pk=user.pk)

            # If the username is the same, it will raise and the job will be postponed
            assert user.username != username, 'Username is still the same'

            # We're ok
            self.resolution.hset('User has a new username: %s' % user.username)
            return True


class GithubNotificationJob(DjangoModelJob):
    """
    Abstract job model for jobs based on the IssueComment model
    """
    abstract = True
    model = GithubNotification

    permission = 'self'
    clonable_fields = ('gh', )

    @cached_property
    def github_notification(self):
        return self.object


class FinalizeGithubNotification(GithubNotificationJob):

    queue_name = 'finalize-notification'
    publish = fields.InstanceHashField()

    clonable_fields = ('gh', 'publish')

    def run(self, queue):
        """
        Get the user and its available repositories from github, and save the
        counts in the job
        """
        super(FinalizeGithubNotification, self).run(queue)

        notification = self.github_notification

        # force gh if not set
        if not self.gh_args.hgetall():
            gh = notification.user.get_connection()
            if gh and 'access_token' in gh._connection_args:
                self.gh = gh

        # check availability
        gh = self.gh
        if not gh:
            return  # it's delayed !

        ready = True
        issue = None

        # Fetch the subscription
        try:
            notification.fetch_subscription(gh)
        except ApiNotFoundError:
            # it may be the case when the notification happened because the user belongs to an org
            # and in this case there is no subscription
            pass

        # Fetch the repository
        try:
            notification.repository.fetch_minimal(gh)
        except ApiNotFoundError:
            ready = False
        else:
            # Fetch the issue
            from gim.core.models import Issue
            try:
                issue = notification.repository.issues.get(number=notification.issue_number)
            except Issue.DoesNotExist:
                issue = Issue(repository=notification.repository, number=notification.issue_number)

            try:
                issue.fetch(gh)
            except ApiNotFoundError:
                if issue.pk:
                    issue.delete()
                ready = False
            else:
                from gim.core.tasks.issue import FetchIssueByNumber
                FetchIssueByNumber.add_job('%s#%s' % (notification.repository.pk, notification.issue_number), gh=gh)

        notification.issue = issue if issue and issue.pk else None
        notification.ready = ready
        notification.save(publish=ready and self.publish.hget() == '1')

        return True


class GithubNotificationEditJob(GithubNotificationJob):

    queue_name = 'edit-notification'

    def run(self, queue):

        notification = self.github_notification

        # force gh if not set
        if not self.gh_args.hgetall():
            gh = notification.user.get_connection()
            if gh and 'access_token' in gh._connection_args:
                self.gh = gh

        # check availability
        gh = self.gh
        if not gh:
            return  # it's delayed !

        # mark as read
        if not notification.unread:
            notification.dist_edit(gh, 'update')

        # update subscription
        notification.dist_edit(gh, 'update', meta_base_name='subscription')


class FetchNotifications(UserJob):

    queue_name = 'fetch-notifications'

    def run(self, queue):

        user = self.user

        # force gh if not set
        if not self.gh_args.hgetall():
            gh = user.get_connection()
            if gh and 'access_token' in gh._connection_args:
                self.gh = gh

        # check availability
        gh = self.gh
        if not gh:
            return  # it's delayed !

        response_headers = {}
        count = user.fetch_github_notifications(None, parameters={'response_headers': response_headers})

        try:
            delay = int(response_headers['x-poll-interval'])
        except Exception:
            delay = 60

        return count, delay

    def success_message_addon(self, queue, result):
        """
        Display infos got from the fetch_available_repositories call
        """
        count, delay = result

        return ' [notifs=%d, delay=%d]' % (count, delay)

    def on_success(self, queue, result):
        """
        Make a new fetch later
        """
        count, delay = result

        self.clone(delayed_for=delay)

        self.user.ping_github_notifications()
