
__all__ = [
    'FetchClosedIssuesWithNoClosedBy',
    'FetchUpdatedPullRequests',
    'FetchPullRequestsCommitsParents',
    'FetchUpdatedReviews',
    'FetchUnmergedPullRequests',
    'FetchCollaborators',
    'FirstFetch',
    'FirstFetchStep2',
    'FetchForUpdate',
    'ManageDualRepository',
]

from datetime import timedelta
from dateutil.parser import parse
from random import randint
from threading import local

from limpyd import fields
from limpyd_jobs import STATUSES
from async_messages import messages

from gim.core.managers import MODE_UPDATE
from gim.core.models import Repository, GithubUser
from gim.github import ApiNotFoundError
from gim.core.limpyd_models import Token
from gim.subscriptions.models import WaitingSubscription, WAITING_SUBSCRIPTION_STATES

from .base import DjangoModelJob, Job

thread_data = local()


class RepositoryJob(DjangoModelJob):
    """
    Abstract job model for jobs based on the Repository model
    """
    abstract = True
    model = Repository

    @property
    def repository(self):
        if not hasattr(self, '_repository'):
            try:
                self._repository = self.object
            except Repository.DoesNotExist:
                # We can cancel the job if the repository does not exist anymore
                self.hmset(status=STATUSES.CANCELED, cancel_on_error=1)
                raise
        return self._repository


class FetchClosedIssuesWithNoClosedBy(RepositoryJob):
    """
    Job that fetches issues from a repository, that are closed but without a
    closed_by (to get the closer_by, we need to fetch each closed issue
    individually)
    """
    queue_name = 'fetch-closed-issues'

    limit = fields.InstanceHashField()
    count = fields.InstanceHashField()
    errors = fields.InstanceHashField()

    permission = 'read'
    clonable_fields = ('limit', )

    def run(self, queue):
        """
        Get the repository and update some closed issues, and save the count
        of fetched issues in the job
        """
        super(FetchClosedIssuesWithNoClosedBy, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        count, deleted, errors, todo = self.repository.fetch_closed_issues_without_closed_by(
                                                    limit=int(self.limit.hget() or 20), gh=gh)

        self.hmset(count=count, errors=errors)

        return count, deleted, errors, todo

    def on_success(self, queue, result):
        """
        If there is still issues to fetch, add a new job
        """
        todo = result[3]
        if todo:
            self.clone(delayed_for=60)

    def success_message_addon(self, queue, result):
        """
        Display the count of closed issues fetched
        """
        return ' [fetched=%d, deleted=%s, errors=%s, todo=%s]' % result


class FetchUpdatedPullRequests(RepositoryJob):
    """
    Job that fetches updated pull requests from a repository, to have infos we
    can only have by fetching them one by one
    """
    queue_name = 'update-pull-requests'

    limit = fields.InstanceHashField()
    count = fields.InstanceHashField()
    errors = fields.InstanceHashField()

    permission = 'read'
    clonable_fields = ('limit', )

    def run(self, queue):
        """
        Get the repository and update some pull requests, and save the count
        of updated pull requests in the job
        """
        super(FetchUpdatedPullRequests, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        count, deleted, errors, todo = self.repository.fetch_updated_prs(
                                    limit=int(self.limit.hget() or 20), gh=gh)

        self.hmset(count=count, errors=errors)

        return count, deleted, errors, todo

    def on_success(self, queue, result):
        """
        If there is still PRs to fetch, add a new job
        """
        todo = result[3]
        if todo:
            self.clone(delayed_for=60)

    def success_message_addon(self, queue, result):
        """
        Display the count of updated pull requests
        """
        return ' [fetched=%d, deleted=%s, errors=%s, todo=%s]' % result


class FetchPullRequestsCommitsParents(RepositoryJob):
    queue_name = 'fetch-commits-parents'

    limit = fields.InstanceHashField()
    count = fields.InstanceHashField()
    errors = fields.InstanceHashField()
    nb_commits = fields.InstanceHashField()

    permission = 'read'
    clonable_fields = ('limit', )

    def run(self, queue):
        super(FetchPullRequestsCommitsParents, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        count, deleted, errors, todo, nb_commits = \
            self.repository.fetch_prs_commits_parents(limit=int(self.limit.hget() or 20), gh=gh)

        self.hmset(count=count, errors=errors, nb_commits=nb_commits)

        return count, deleted, errors, todo, nb_commits

    def on_success(self, queue, result):
        todo = result[3]
        if todo:
            self.clone(priority=-20, delayed_for=300)

    def success_message_addon(self, queue, result):
        return ' [fetched=%d, deleted=%s, errors=%s, todo=%s, nb_commits=%s]' % result


class FetchUpdatedReviews(RepositoryJob):
    queue_name = 'update-pr-reviews'

    limit = fields.InstanceHashField()
    count = fields.InstanceHashField()

    permission = 'read'
    use_graphql = True

    def run(self, queue):

        super(FetchUpdatedReviews, self).run(queue)

        gh = self.gh
        if not gh:
            return   # it's delayed !

        count, total = self.repository.fetch_updated_pr_reviews(gh, max_prs=int(self.limit.hget() or 10))

        self.count.hset(count)

        return count, total

    def on_success(self, queue, result):
        # replay this often
        if self.repository.pr_reviews_activated:
            self.clone(delayed_for=60)

    def success_message_addon(self, queue, result):
        return ' [fetched=%s, total=%s]' % result


class FetchUnmergedPullRequests(RepositoryJob):
    """
    Job that fetches open pull requests from a repository, to update their
    mergeable status
    """
    queue_name = 'update-mergable-status'

    start_date = fields.InstanceHashField()
    limit = fields.InstanceHashField()
    count = fields.InstanceHashField()
    errors = fields.InstanceHashField()

    permission = 'read'
    clonable_fields = ('limit', )

    def run(self, queue):
        """
        Get the repository and update some pull requests, and save the count
        of updated pull requests in the job
        """
        super(FetchUnmergedPullRequests, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        start_date = self.start_date.hget()
        if start_date:
            start_date = parse(start_date)
        else:
            start_date = None

        count, updated, deleted, errors, todo, last_date = self.repository.fetch_unmerged_prs(
                                limit=int(self.limit.hget() or 20), gh=gh, start_date=start_date)

        self.hmset(count=updated, errors=errors)

        return count, updated, deleted, errors, todo, last_date

    def on_success(self, queue, result):
        """
        If there is still PRs to fetch, add a new job
        """
        todo = result[4]
        if todo:
            last_date = result[5]
            self.clone(priority=-15, delayed_for=60, start_date=str(last_date-timedelta(seconds=1)))

    def success_message_addon(self, queue, result):
        """
        Display the count of updated pull requests
        """
        return ' [fetched=%d, updated=%s, deleted=%s, errors=%s, todo=%s]' % result[:-1]


class FetchCollaborators(RepositoryJob):
    """
    A job to fetch collaborators, as it has to be done by user with at least
    push access
    """
    queue_name = 'fetch-collaborators'
    clonable_fields = ('force_fetch', )

    force_fetch = fields.InstanceHashField()

    permission = 'push'

    def run(self, queue):
        super(FetchCollaborators, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        force_fetch = self.force_fetch.hget() == '1'

        count = self.repository.fetch_collaborators(gh, force_fetch=force_fetch)

        return count


class FirstFetch(Job):
    """
    A job to do the first fetch of a repository.
    It's a specific job because when the job will be fetched, the waiting
    subscriptions associated with it will be converted to real ones.
    """
    queue_name = 'first-repository-fetch'

    converted_subscriptions = fields.InstanceHashField()

    permission = 'self'

    def run(self, queue):
        """
        Fetch the repository and once done, convert waiting subscriptions into
        real ones, and save the cout of converted subscriptions in the job.
        """
        super(FirstFetch, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        # the identifier of this job is not the repository's id, but its full name
        repository_name = self.identifier.hget()

        # mark waiting subscriptions as in fetching status
        WaitingSubscription.objects.filter(repository_name=repository_name)\
            .update(state=WAITING_SUBSCRIPTION_STATES.FETCHING)

        # get the user who asked to add this repo, and check its rights
        user = GithubUser.objects.get(username=self.gh_args.hget('username'))
        rights = user.can_use_repository(repository_name)

        # TODO: in these two case, we must not retry the job without getting
        #       an other user with fetch rights
        if rights is None:
            raise Exception('An error occured while fetching rights for the user')
        elif rights is False:
            raise Exception('The user has not rights to fetch this repository')

        # try to get a GithubUser which is the owner of the repository
        user_part, repo_name_part = repository_name.split('/')

        if user_part == user.username:
            owner = user
        else:
            try:
                owner = GithubUser.objects.get(username=user_part)
            except GithubUser.DoesNotExist:
                # no user, we will create it during the fetch
                owner = GithubUser(username=user_part)

        # Check if the repository already exists in the DB
        repository = None
        if owner.id:
            try:
                repository = owner.owned_repositories.get(name=repo_name_part)
            except Repository.DoesNotExist:
                pass

        if not repository:
            # create a temporary repository to fetch if none exists
            repository = Repository(name=repo_name_part, owner=owner)

        # fetch the repository if never fetched
        if not repository.first_fetch_done:
            # We don't publish things (comments...) when we first create a repository
            thread_data.skip_publish = True
            try:
                repository.fetch_all(gh=self.gh, force_fetch=True, two_steps=True)
            finally:
                thread_data.skip_publish = False
            FetchCollaborators.add_job(repository.id)

        # and convert waiting subscriptions to real ones
        count = 0
        for subscription in WaitingSubscription.objects.filter(repository_name=repository_name):
            try:
                rights = subscription.user.can_use_repository(repository)
            except Exception:
                continue
            if rights:
                count += 1
                subscription.convert(rights)
                message = u'Your subscription to <strong>%s</strong> is now ready' % repository.full_name
                messages.success(subscription.user, message)
            else:
                subscription.state = WAITING_SUBSCRIPTION_STATES.FAILED
                subscription.save(update_fields=['state'])

        # save count in the job
        self.converted_subscriptions.hset(count)

        # add check-hook/events jobs
        # TODO: should not be in core but for now...
        from gim.hooks.tasks import CheckRepositoryHook, CheckRepositoryEvents
        CheckRepositoryEvents.add_job(repository.id)
        CheckRepositoryHook.add_job(repository.id, delayed_for=30)

        # return the number of converted subscriptions
        return count

    def success_message_addon(self, queue, result):
        """
        Display the count of converted subscriptions
        """
        return ' [converted=%d]' % result


class FirstFetchStep2(RepositoryJob):
    """
    A job to fetch the less important data of a repository (closed issues and
    comments)
    """
    queue_name = 'repository-fetch-step2'
    clonable_fields = ('max_pages', )

    start_page = fields.InstanceHashField()
    max_pages = fields.InstanceHashField()
    to_ignore = fields.SetField()

    counts = fields.HashField()
    last_one = fields.InstanceHashField()

    pr_reviews_next_page_cursor = fields.InstanceHashField()

    permission = 'read'

    def run(self, queue):
        """
        Call the fetch_all_step2 method of the linked repository, using the
        value of the start_page and max_pages job's attributes
        """
        super(FirstFetchStep2, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        self._start_page, self._max_pages = self.hmget('start_page', 'max_pages')

        try:
            self._start_page = int(self._start_page)
        except Exception:
            self._start_page = 1
            self.start_page.hset(self._start_page)

        try:
            self._max_pages = int(self._max_pages)
        except Exception:
            self._max_pages = 5
            self.max_pages.hset(self._max_pages)

        try:
            self._to_ignore = set(self.to_ignore.smembers())
        except:
            self._to_ignore = None

        self._pr_reviews_next_page_cursor = self.pr_reviews_next_page_cursor.hget() or None

        # We don't publish things (comments...) when we first create a repository
        thread_data.skip_publish = True
        try:
            counts = self.repository.fetch_all_step2(gh=gh, force_fetch=True,
                            start_page=self._start_page, max_pages=self._max_pages,
                            to_ignore=self._to_ignore, issues_state='closed')

            if self.repository.pr_reviews_activated and 'pr_reviews' not in self._to_ignore:
                counts['pr_reviews'] = -1  # to indicate failure

                # always get the token with the most remaining
                graphql_token = Token.get_one_for_repository(
                    self.repository.pk,
                    permission='pull' if self.repository.private else None,
                    for_graphql=True
                )

                if graphql_token:

                    total, done, failed, next_page_cursor = self.repository.fetch_all_pr_reviews(
                        graphql_token.gh,
                        next_page_cursor=self._pr_reviews_next_page_cursor,
                        max_prs=30,
                    )
                    counts['pr_reviews'] = done
                    if next_page_cursor:
                        self._pr_reviews_next_page_cursor = next_page_cursor
                    else:
                        self._pr_reviews_next_page_cursor = None
                        self._to_ignore.add('pr_reviews')

        finally:
            thread_data.skip_publish = False

        return counts

    def on_success(self, queue, result):
        """
        When done, if something was fetched, add a new job to continue the fetch
        of following pages one minute later.
        If nothing was fetched, we are done and add a job to do a new full
        fetch to check updates.
        """

        if result:
            self.counts.hmset(**result)
            total_count = sum(result.values())
            total_count_excluding_reviews = total_count - result.get('pr_reviews', 0)
            only_reviews = set(result.keys()) == {'pr_reviews'}
            force_continue = any(v for v in result.values() if v and v < 0)
        else:
            only_reviews = False
            total_count = 0
            total_count_excluding_reviews = 0

        if total_count or force_continue:
            # we got data, continue at least one time

            self._to_ignore.update([k for k, v in result.iteritems() if not v])

            kwargs = {'start_page': self._start_page + self._max_pages}
            if self._to_ignore:
                kwargs['to_ignore'] = self._to_ignore  # cannot sadd an empty set
            if self._pr_reviews_next_page_cursor:
                kwargs['pr_reviews_next_page_cursor'] = self._pr_reviews_next_page_cursor

            self.clone(delayed_for=60, **kwargs)

        if total_count_excluding_reviews == 0 and not only_reviews:
            # got nothing else than reviews to do, we can let the reviews continue
            # to be fetched and add a job to do future fetches of other data
            repository = self.object
            self.last_one.hset(1)
            FetchForUpdate.add_job(repository.id)
            # and also to fetch projects independently
            from .project import FetchProjects
            FetchProjects.add_job(repository.id)

    def success_message_addon(self, queue, result):
        msg = ' [%s]' % (', '.join(['%s=%s' % (k, v) for k, v in result.iteritems()]))

        if result and sum(result.values()):

            msg += ' - Continue (start page %s for %s pages)' % (
                            self._start_page + self._max_pages, self._max_pages)

        else:
            msg += ' - The end.'

        return msg


class FetchForUpdate(RepositoryJob):
    """
    Job that will do an unforced full fetch of the repository to update all that
    needs to.
    When done:
    - spawn a job to fetch collaborators
    - clone the job to be done again 15 min laters (+-2mn)
    """
    queue_name = 'update-repo'

    permission = 'read'

    def run(self, queue):
        """
        Fetch the whole repository stuff if it has a subscription
        """
        super(FetchForUpdate, self).run(queue)

        gh = self.gh
        if not gh:
            return  # it's delayed !

        self.repository.fetch_all(gh)

    def on_success(self, queue, result):
        """
        Fetch collaborators and go fetch again in 15 +- 2mn
        """
        FetchCollaborators.add_job(self.object.id)
        self.clone(delayed_for=60 * 13 + randint(0, 60 * 4))


class ManageDualRepository(Job):
    """
    Job that tries to resolve a new github repository that cannot be inserted because one with the
    same username+name but a different github_id already exist.
    """

    queue_name = 'manage-dual-repo'
    permission = 'read'

    new_github_id = fields.InstanceHashField()
    resolution = fields.InstanceHashField()
    update_related_output = fields.InstanceHashField()

    clonable_fields = ('new_github_id', )

    def run(self, queue):
        """
        Will return `False` if nothing had to be done, `True`.
        Will raise if we cannot be sure at the end that the problem was solved.
        """

        super(ManageDualRepository, self).run(queue)

        repository_name, new_github_id = self.hmget('identifier', 'new_github_id')
        new_github_id = int(new_github_id)

        # Get the different parts of the identifier
        owner_id, repo_name = repository_name.split('/')
        owner_id = int(owner_id)

        try:
            self.repository = Repository.objects.exclude(github_id=new_github_id).get(
                owner_id=owner_id, name=repo_name)
        except Repository.DoesNotExist:
            # Something already corrected the problem
            self.resolution.hset('Problem already managed')
            return False

        # Token to fetch the repository
        gh = self.gh
        if not gh:
            return  # it's delayed !

        # Start by fetching the existing repository, maybe someone just changed its owner/name
        try:

            Repository.objects.get_from_github(
                gh=gh,
                identifiers=('repositories', self.repository.github_id),  # Check by id, not owner+name
                modes=MODE_UPDATE,
                force_update=True,
            )

        except ApiNotFoundError:
            # Ok the repository was deleted, we can delete it
            self.repository.delete()
            self.resolution.hset('Repository deleted')
            return True

        else:
            # Check that the owner/name has changed
            self.repository = Repository.objects.get(pk=self.repository.pk)

            # If the username is the same, it will raise and the job will be postponed
            assert (self.repository.owner_id, self.repository.name) != (owner_id, repo_name),\
                'Owner+name is still the same'

            # We're ok
            self.resolution.hset('Repository has a new owner+name: %s/%s' % (
                self.repository.owner_id, self.repository.name))
            return True
