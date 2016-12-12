__all__ = [
    'Repository',
    'ProtectedBranch',
]

from datetime import datetime, timedelta

from django.db import models
from django.utils.functional import cached_property


from gim.core.graphql_utils import (
    compose_query,
    encode_graphql_id_for_object,
    fetch_graphql,
    reindent,
    GraphQLComplexityError,
    GraphQLGithubInternalError,
)

from .. import GITHUB_HOST

from ..ghpool import (
    ApiError,
    ApiNotFoundError,
)

from ..limpyd_models import Token

from ..managers import (
    MODE_ALL,
    MODE_UPDATE,
    RepositoryManager,
    ProtectedBranchManager,
)

from .base import (
    GithubObject,
    GithubObjectWithId,
)


class Repository(GithubObjectWithId):
    owner = models.ForeignKey('GithubUser', related_name='owned_repositories')
    name = models.TextField(db_index=True)
    description = models.TextField(blank=True, null=True)
    collaborators = models.ManyToManyField('GithubUser', related_name='repositories')
    private = models.BooleanField(default=False)
    is_fork = models.BooleanField(default=False)
    has_issues = models.BooleanField(default=False)
    default_branch = models.TextField(blank=True, null=True)

    first_fetch_done = models.BooleanField(default=False)
    fetch_minimal_done = models.BooleanField(default=False)
    collaborators_fetched_at = models.DateTimeField(blank=True, null=True)
    collaborators_etag = models.CharField(max_length=64, blank=True, null=True)
    milestones_fetched_at = models.DateTimeField(blank=True, null=True)
    milestones_state_open_etag = models.CharField(max_length=64, blank=True, null=True)
    milestones_state_closed_etag = models.CharField(max_length=64, blank=True, null=True)
    labels_fetched_at = models.DateTimeField(blank=True, null=True)
    labels_etag = models.CharField(max_length=64, blank=True, null=True)
    issues_fetched_at = models.DateTimeField(blank=True, null=True)
    issues_state_open_etag = models.CharField(max_length=64, blank=True, null=True)
    issues_state_closed_etag = models.CharField(max_length=64, blank=True, null=True)
    issues_state_all_etag = models.CharField(max_length=64, blank=True, null=True)
    prs_fetched_at = models.DateTimeField(blank=True, null=True)
    prs_state_open_etag = models.CharField(max_length=64, blank=True, null=True)
    prs_state_closed_etag = models.CharField(max_length=64, blank=True, null=True)
    prs_state_all_etag = models.CharField(max_length=64, blank=True, null=True)
    comments_fetched_at = models.DateTimeField(blank=True, null=True)
    comments_etag = models.CharField(max_length=64, blank=True, null=True)
    pr_comments_fetched_at = models.DateTimeField(blank=True, null=True)
    pr_comments_etag = models.CharField(max_length=64, blank=True, null=True)
    issues_events_fetched_at = models.DateTimeField(blank=True, null=True)
    issues_events_etag = models.CharField(max_length=64, blank=True, null=True)
    commit_comments_fetched_at = models.DateTimeField(blank=True, null=True)
    commit_comments_etag = models.CharField(max_length=64, blank=True, null=True)
    # this list is not ordered, we must memorize the last page
    commit_comments_last_page = models.PositiveIntegerField(blank=True, null=True)
    has_commit_statuses = models.BooleanField(default=False)
    main_metric = models.OneToOneField('LabelType', blank=True, null=True, related_name='+',
                                        on_delete=models.SET_NULL)
    projects_fetched_at = models.DateTimeField(blank=True, null=True)
    projects_etag = models.CharField(max_length=64, blank=True, null=True)
    protected_branches_fetched_at = models.DateTimeField(blank=True, null=True)
    protected_branches_etag = models.CharField(max_length=64, blank=True, null=True)
    pr_reviews_activated = models.BooleanField(default=False)

    objects = RepositoryManager()

    github_matching = dict(GithubObjectWithId.github_matching)
    github_matching.update({
        'fork': 'is_fork',
    })
    github_ignore = GithubObjectWithId.github_ignore + ('is_fork', ) + ('issues_url', 'has_wiki',
        'forks_url', 'mirror_url', 'subscription_url', 'notifications_url', 'subscribers_count',
        'updated_at', 'svn_url', 'pulls_url', 'full_name', 'issue_comment_url', 'contents_url',
        'keys_url', 'size', 'tags_url', 'contributors_url', 'network_count', 'downloads_url',
        'assignees_url', 'statuses_url', 'git_refs_url', 'git_commits_url', 'clone_url',
        'watchers_count', 'git_tags_url', 'milestones_url', 'stargazers_count', 'hooks_url',
        'homepage', 'commits_url', 'releases_url', 'issue_events_url', 'has_downloads', 'labels_url',
        'events_url', 'comments_url', 'html_url', 'compare_url', 'open_issues', 'watchers',
        'git_url', 'forks_count', 'merges_url', 'ssh_url', 'blobs_url', 'master_branch', 'forks',
        'permissions', 'open_issues_count', 'languages_url', 'language', 'collaborators_url', 'url',
        'created_at', 'archive_url', 'pushed_at', 'teams_url', 'trees_url',
        'branches_url', 'subscribers_url', 'stargazers_url', 'main_metric')

    class Meta:
        app_label = 'core'
        unique_together = (
            ('owner', 'name'),
        )
        ordering = ('owner', 'name', )

    def __unicode__(self):
        return self.full_name

    @property
    def full_name(self):
        return u'%s/%s' % (self.owner.username if self.owner else '?', self.name)

    @property
    def github_url(self):
        return GITHUB_HOST + self.full_name

    @property
    def untyped_labels(self):
        """
        Shortcut to return a queryset for untyped labels of the repository
        """
        return self.labels.ready().filter(label_type_id__isnull=True)

    def _distinct_users(self, relation):
        from .users import GithubUser
        return GithubUser.objects.filter(**{
                '%s__repository' % relation: self.id
            }).distinct()  # distinct can take the 'username' arg in postgresql

    @property
    def issues_creators(self):
        """
        Shortcut to return a queryset for creator of issues on this repository
        """
        return self._distinct_users('created_issues')

    @property
    def issues_assigned(self):
        """
        Shortcut to return a queryset for users assigned to issues on this repository
        """
        return self._distinct_users('assigned_issues')

    @property
    def issues_closers(self):
        """
        Shortcut to return a queryset for users who closed issues on this repository
        """
        return self._distinct_users('closed_issues')

    @property
    def issues_mentioned(self):
        """
        Shortcut to return a queryset for users who are mentioned in issues on this repository
        """
        return self._distinct_users('mentions__issue')

    @property
    def github_callable_identifiers(self):
        return [
            'repos',
            self.owner.username,
            self.name,
        ]

    @property
    def github_callable_identifiers_for_collaborators(self):
        return self.github_callable_identifiers + [
            'collaborators',
        ]

    def fetch_collaborators(self, gh, force_fetch=False, parameters=None):
        count = self._fetch_many('collaborators', gh,
                                 force_fetch=force_fetch,
                                 parameters=parameters)

        from gim.core.tasks.githubuser import FetchUser
        for user in self.collaborators.all():
            if user.must_be_fetched():
                FetchUser.add_job(user.pk, force_fetch=1)

        return count

    @property
    def github_callable_identifiers_for_labels(self):
        return self.github_callable_identifiers + [
            'labels',
        ]

    def fetch_labels(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('labels', gh,
                                defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                force_fetch=force_fetch,
                                parameters=parameters)

    @property
    def github_callable_identifiers_for_milestones(self):
        return self.github_callable_identifiers + [
            'milestones',
        ]

    def fetch_milestones(self, gh, force_fetch=False, parameters=None):
        if not self.has_issues:
            return 0
        return self._fetch_many('milestones', gh,
                                vary={'state': ('open', 'closed')},
                                defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                force_fetch=force_fetch,
                                parameters=parameters)

    @property
    def github_callable_identifiers_for_issues(self):
        return self.github_callable_identifiers + [
            'issues',
        ]

    @property
    def github_callable_identifiers_for_prs(self):
        return self.github_callable_identifiers + [
            'pulls',
        ]

    def fetch_issues(self, gh, force_fetch=False, state=None, parameters=None,
                                        parameters_prs=None, max_pages=None):
        from .issues import Issue

        if state:
            vary = {'state': (state, )}
            remove_missing = False
        else:
            vary = {'state': ('all', )}
            remove_missing = True

        count = 0
        if self.has_issues:

            final_issues_parameters = {
                'sort': Issue.github_date_field[1],
                'direction': Issue.github_date_field[2],
            }
            if parameters:
                final_issues_parameters.update(parameters)

            count = self._fetch_many('issues', gh,
                                    vary=vary,
                                    defaults={
                                        'fk': {'repository': self},
                                        'related': {'*': {'fk': {'repository': self}}},
                                    },
                                    parameters=final_issues_parameters,
                                    remove_missing=remove_missing,
                                    force_fetch=force_fetch,
                                    max_pages=max_pages)

        # now fetch pull requests to have more informations for them (only
        # ones that already exist as an issue, not the new ones)

        final_prs_parameters = {
            'sort': Issue.github_date_field[1],
            'direction': Issue.github_date_field[2],
        }
        if parameters_prs:
            final_prs_parameters.update(parameters_prs)

        pr_count = self._fetch_many('issues', gh,
                        vary=vary,
                        defaults={
                            'fk': {'repository': self},
                            'related': {'*': {'fk': {'repository': self}}},
                            'simple': {'is_pull_request': True},
                            'mergeable_state': 'checking',
                        },
                        parameters=final_prs_parameters,
                        remove_missing=False,
                        force_fetch=force_fetch,
                        meta_base_name='prs',
                        modes=MODE_UPDATE if self.has_issues else MODE_ALL,
                        max_pages=max_pages)

        count += pr_count

        if self.has_issues and (not state or state == 'closed'):
            from gim.core.tasks.repository import FetchClosedIssuesWithNoClosedBy
            FetchClosedIssuesWithNoClosedBy.add_job(self.id, limit=20, gh=gh)

        from gim.core.tasks.repository import FetchUpdatedPullRequests
        FetchUpdatedPullRequests.add_job(self.id, limit=20, gh=gh)

        return count

    def fetch_closed_issues_without_closed_by(self, gh, limit=20):
        # the "closed_by" attribute of an issue is not filled in list call, so
        # we fetch all closed issue that has no closed_by, one by one (but only
        # if we never did it because some times there is noone who closed an
        # issue on the github api :( ))
        if not self.has_issues:
            return 0, 0, 0, 0

        qs = self.issues.filter(state='closed',
                                closed_by_id__isnull=True,
                                closed_by_fetched=False
                               )

        issues = list(qs.order_by('-closed_at')[:limit])

        count = errors = deleted = todo = 0

        if len(issues):

            for issue in issues:
                try:
                    issue.fetch(gh, force_fetch=True,
                                defaults={'simple': {'closed_by_fetched': True}})
                except ApiNotFoundError:
                    # the issue doen't exist anymore !
                    issue.delete()
                    deleted += 1
                except ApiError:
                    errors += 1
                else:
                    count += 1

            todo = qs.count()

        return count, deleted, errors, todo

    def fetch_updated_prs(self, gh, limit=20):
        """
        Fetch pull requests individually when it was never done or when the
        updated_at retrieved from the issues list is newer than the previous
        'pr_fetched_at'.
        """
        from .issues import Issue

        filter = self.issues.filter(
            # only pull requests
            models.Q(is_pull_request=True)
            &
            (
                # that where never fetched
                models.Q(pr_fetched_at__isnull=True)
                |
                # or last fetched long time ago
                models.Q(pr_fetched_at__lt=models.F('updated_at'))
                |
                (
                    # or open ones...
                    models.Q(state='open')
                    &
                    (
                        # that are not merged or with unknown merged status
                        models.Q(merged=False)
                        |
                        models.Q(merged__isnull=True)
                    )
                    &
                    (
                        # with unknown mergeable status
                        models.Q(mergeable_state__in=Issue.MERGEABLE_STATES['unknown'])
                        |
                        models.Q(mergeable_state__isnull=True)
                        |
                        models.Q(mergeable__isnull=True)
                    )
                )
                |
                # or closed ones without merged status
                models.Q(merged__isnull=True, state='closed')
            )
        )

        def action(gh, pr):
            pr.fetch_pr(gh, force_fetch=True)
            pr.fetch_commits(gh)
            pr.fetch_files(gh)

        return self._fetch_some_prs(filter, action, gh=gh, limit=limit)

    def fetch_unmerged_prs(self, gh, limit=20, start_date=None):
        """
        Fetch pull requests individually to updated their "mergeable" status.
        If a PR was not updated, it may not cause a real Github call (but a 304)
        """

        def get_filter(start_date):
            filter = self.issues.filter(
                # only open pull requests
                models.Q(is_pull_request=True, state='open')
                &
                (
                    # that are not merged or with unknown merged status
                    models.Q(merged=False)
                    |
                    models.Q(merged__isnull=True)
                )
            )
            if start_date:
                filter = filter.filter(updated_at__lt=start_date)
            return filter

        def action(gh, pr):
            mergeable = pr.mergeable
            mergeable_state = pr.mergeable_state
            pr.fetch_pr(gh, force_fetch=False)
            if pr.mergeable != mergeable or pr.mergeable_state != mergeable_state:
                action.updated += 1
            if not action.last_date or pr.updated_at < action.last_date:
                action.last_date = pr.updated_at
        action.updated = 0
        action.last_date = None

        count, deleted, errors, todo = self._fetch_some_prs(get_filter(start_date),
                                                        action, gh=gh, limit=limit)

        todo = get_filter((action.last_date-timedelta(seconds=1)) if action.last_date else None).count()

        return count, action.updated, deleted, errors, todo, action.last_date

    def _fetch_some_prs(self, filter, action, gh, limit=20):
        """
        Update some PRs, with filter and things to merge depending on the mode.
        """
        prs = list(filter.order_by('-updated_at')[:limit])

        count = errors = deleted = todo = 0

        if len(prs):

            for pr in prs:
                try:
                    action(gh, pr)
                except ApiNotFoundError:
                    # the PR doen't exist anymore !
                    pr.delete()
                    deleted += 1
                except ApiError:
                    errors += 1
                else:
                    count += 1

            todo = filter.count()

        return count, deleted, errors, todo

    def fetch_unfetched_commits(self, gh, limit=20):
        """
        Fetch commits that were never fetched, for example just created with a
        sha from an IssueEvent
        """
        qs = self.commits.filter(fetched_at__isnull=True)

        commits = list(qs.order_by('-authored_at')[:limit])

        count = errors = deleted = todo = 0

        if len(commits):

            for commit in commits:
                try:
                    commit.fetch(gh, force_fetch=True)
                except ApiNotFoundError:
                    # the commit doesn't exist anymore !
                    commit.fetched_at = datetime.utcnow()
                    commit.deleted = True
                    commit.save(update_fields=['fetched_at', 'deleted'])
                    deleted += 1
                except ApiError:
                    errors += 1
                else:
                    count += 1

            todo = qs.count()

        return count, deleted, errors, todo

    @property
    def github_callable_identifiers_for_issues_events(self):
        return self.github_callable_identifiers_for_issues + [
            'events',
        ]

    def fetch_issues_events(self, gh, force_fetch=False, parameters=None,
                                                            max_pages=None):
        count = self._fetch_many('issues_events', gh,
                                 defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                 parameters=parameters,
                                 force_fetch=force_fetch,
                                 max_pages=max_pages)

        return count

    @property
    def github_callable_identifiers_for_comments(self):
        return self.github_callable_identifiers_for_issues + [
            'comments',
        ]

    @property
    def github_callable_identifiers_for_pr_comments(self):
        return self.github_callable_identifiers_for_prs + [
            'comments'
        ]

    def fetch_comments(self, gh, force_fetch=False, parameters=None,
                                                                max_pages=None):
        from .comments import IssueComment

        final_parameters = {
            'sort': IssueComment.github_date_field[1],
            'direction': IssueComment.github_date_field[2],
        }
        if parameters:
            final_parameters.update(parameters)

        return self._fetch_many('comments', gh,
                                defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                parameters=final_parameters,
                                force_fetch=force_fetch,
                                max_pages=max_pages)

    def fetch_pr_comments(self, gh, force_fetch=False, parameters=None,
                                                                max_pages=None):
        from .comments import PullRequestComment

        final_parameters = {
            'sort': PullRequestComment.github_date_field[1],
            'direction': PullRequestComment.github_date_field[2],
        }
        if parameters:
            final_parameters.update(parameters)

        return self._fetch_many('pr_comments', gh,
                                defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                parameters=final_parameters,
                                force_fetch=force_fetch,
                                max_pages=max_pages)

    @property
    def github_callable_identifiers_for_commits(self):
        return self.github_callable_identifiers + [
            'commits',
        ]

    @property
    def github_callable_identifiers_for_commit_comments(self):
        return self.github_callable_identifiers + [
            'comments',
        ]

    def fetch_commit_comments(self, gh, force_fetch=False, parameters=None,
                                                                max_pages=None):
        from .comments import CommitComment

        final_parameters = {
            'sort': CommitComment.github_date_field[1],
            'direction': CommitComment.github_date_field[2],
        }

        if not force_fetch:
            final_parameters['page'] = self.commit_comments_last_page or 1

        if CommitComment.github_reverse_order:
            force_fetch = True

        if parameters:
            final_parameters.update(parameters)

        return self._fetch_many('commit_comments', gh,
                                defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                parameters=final_parameters,
                                force_fetch=force_fetch,
                                max_pages=max_pages)

    @property
    def github_callable_identifiers_for_projects(self):
        return self.github_callable_identifiers + [
            'projects',
        ]

    def fetch_projects(self, gh, force_fetch=False, parameters=None, max_pages=None):
        return self._fetch_many('projects', gh,
                                defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                force_fetch=force_fetch,
                                parameters=parameters,
                                max_pages=None)  # we need them all to get all the positions

    def fetch_all_projects(self, gh, force_fetch=False):
        if not force_fetch:
            if not self.projects_fetched_at:
                force_fetch = True
        now = datetime.utcnow()
        try:
            self.fetch_projects(gh, force_fetch=force_fetch)
            # we must always fetch each projects to get the order if changed
            for project in self.projects.exclude(github_status__in=self.GITHUB_STATUS_CHOICES.NOT_READY):
                if not project.fetch_columns(gh, force_fetch=force_fetch):
                    # we have no new/updated columns
                    continue
                for column in project.columns.exclude(github_status__in=self.GITHUB_STATUS_CHOICES.NOT_READY):
                    if force_fetch or column.fetched_at > now:
                        try:
                            column.fetch_cards(gh, force_fetch=force_fetch)
                        except ApiError:
                            # Currently Github raise a 500 when asking for the second page of cards
                            # We want to continue to fetch cards of other columns
                            pass
        except Exception:
            # Next time we'll refetch all. Else we won't be able to get new data if
            # the error occured for example while fetching cards: the fetch of the
            # project would have returned 304, so no more fetch
            self.projects_fetched_at = None
            self.save(update_fields=['projects_fetched_at'])
            raise

    @property
    def github_callable_identifiers_for_protected_branches(self):
        return self.github_callable_identifiers + [
            'branches',
        ]

    def fetch_protected_branches(self, gh, force_fetch=False, parameters=None, max_pages=None):
        if parameters is None:
            parameters = {}
        parameters['protected'] = 1
        return self._fetch_many('protected_branches', gh,
                                defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                force_fetch=force_fetch,
                                parameters=parameters,
                                max_pages=None)  # we need them all to get all the positions

    def fetch_all_protected_branches(self, gh, force_fetch=False):
        # only admins can fetch protected branches :(
        token = Token.get_for_gh(gh)
        if not token.repos_admin.sismember(self.pk):
            token = Token.get_one_for_repository(self.pk, 'admin')
            if token:
                gh = token.gh
            else:
                return

        if not force_fetch:
            if not self.protected_branches_fetched_at:
                force_fetch = True
        try:
            self.fetch_protected_branches(gh, force_fetch=force_fetch)
            for branch in self.protected_branches.all():
                branch.fetch_all(gh, force_fetch=force_fetch)
        except Exception:
            # Next time we'll refetch all. Else we won't be able to get new data
            self.protected_branches_fetched_at = None
            self.save(update_fields=['protected_branches_fetched_at'])
            raise

    def fetch_minimal(self, gh, force_fetch=False, **kwargs):
        if not self.fetch_minimal_done:
            force_fetch = True
        self.fetch(gh, force_fetch=force_fetch)
        self.fetch_labels(gh, force_fetch=force_fetch)
        self.fetch_milestones(gh, force_fetch=force_fetch)
        if not self.fetch_minimal_done:
            self.fetch_minimal_done = True
            self.save(update_fields=['fetch_minimal_done'])

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        """
        Pass "two_steps=True" to felay fetch of closed issues and comments (by
        adding a FirstFetchStep2 job that will call fetch_all_step2)
        """
        two_steps = bool(kwargs.get('two_steps', False))

        self.fetch_minimal(gh, force_fetch=force_fetch)
        self.fetch_all_protected_branches(gh, force_fetch=force_fetch)

        if two_steps:
            self.fetch_issues(gh, force_fetch=force_fetch, state='open')
            from gim.core.tasks.repository import FirstFetchStep2
            FirstFetchStep2.add_job(self.id, gh=gh)
        else:
            self.fetch_all_step2(gh, force_fetch)
            from gim.core.tasks.project import FetchProjects
            FetchProjects.add_job(self.id)
            from gim.core.tasks.repository import FetchUnmergedPullRequests
            FetchUnmergedPullRequests.add_job(self.id, priority=-15, gh=gh, delayed_for=60*60*3)  # 3 hours

        if not self.first_fetch_done:
            self.first_fetch_done = True
            self.save(update_fields=['first_fetch_done'])

    def fetch_all_step2(self, gh, force_fetch=False, start_page=None,
                        max_pages=None, to_ignore=None, issues_state=None):

        # projects are fetched separately

        if not to_ignore:
            to_ignore = set()

        parameters = {}
        if start_page and start_page > 1:
            parameters['page'] = start_page

        kwargs = {
            'gh': gh,
            'force_fetch': force_fetch,
            'max_pages': max_pages,
            'parameters': parameters,
        }

        counts = {}

        if 'issues' not in to_ignore:
            counts['issues'] = self.fetch_issues(parameters_prs=parameters,
                                                 state=issues_state, **kwargs)
        if 'issues_events' not in to_ignore:
            counts['issues_events'] = self.fetch_issues_events(**kwargs)
        if 'comments' not in to_ignore:
            counts['comments'] = self.fetch_comments(**kwargs)
        if 'pr_comments' not in to_ignore:
            counts['pr_comments'] = self.fetch_pr_comments(**kwargs)
        if 'commit_comments' not in to_ignore:
            counts['commit_comments'] = self.fetch_commit_comments(**kwargs)

        return counts

    @cached_property
    def has_projects(self):
        return self.projects.exists()

    @property
    def has_projects_with_issues(self):
        from .projects import CARDTYPE
        return self.projects.filter(columns__cards__type=CARDTYPE.ISSUE).exists()

    GRAPHQL_FETCH_REVIEWS = compose_query("""
        query RepositoryPullRequestsReviews($nbReviewsToRetrieve: Int = 30, $nextReviewsPageCursor: String) {
            %s
        }
    """, 'pullRequestReviewsFull')

    GRAPHQL_FETCH_REVIEWS_PR_SUBQUERY = """
        node%(pr_index)02d: node(id: "%(pr_id)s") {
            ...pullRequestReviewsFull
        }
    """

    GRAPHQL_FETCH_ALL_REVIEWS = compose_query("""
        query RepositoryAllPullRequestsReviews($repositoryOwnerLogin: String!, $repositoryName: String!, $nbPullRequestsToRetrieve: Int = 30, $nbReviewsToRetrieve: Int = 30, $nextPullRequestsPageCursor: String, $nextReviewsPageCursor: String) {
            repository(owner:$repositoryOwnerLogin, name:$repositoryName) {
                pullRequests(first: $nbPullRequestsToRetrieve, after: $nextPullRequestsPageCursor) {
                    pageInfo {
                        ...pageInfoNext
                    }
                    edges {
                        node {
                            ...pullRequestNumber
                            ...pullRequestReviewsFull
                        }
                    }
                }
            }
        }
    """, 'pageInfoNext', 'pullRequestNumber', 'pullRequestReviewsFull')

    GRAPHQL_FETCH_ALL_REVIEWS_LITE = compose_query("""
        query RepositoryAllPullRequestsReviewsLite($repositoryOwnerLogin: String!, $repositoryName: String!, $nbPullRequestsToRetrieve: Int = 30, $nextPullRequestsPageCursor: String) {
            repository(owner:$repositoryOwnerLogin, name:$repositoryName) {
                pullRequests(first: $nbPullRequestsToRetrieve, after: $nextPullRequestsPageCursor) {
                    pageInfo {
                        ...pageInfoNext
                    }
                    edges {
                        node {
                            ...pullRequestNumber
                        }
                    }
                }
            }
        }
    """, 'pageInfoNext', 'pullRequestNumber')

    def _manage_pr_reviews_from_fetch(self, gh, pr, reviews_node):
        from gim.core.models import PullRequestReview

        if reviews_node and reviews_node.get('edges'):

            objs = PullRequestReview.objects.create_or_update_from_list(
                [edge.node for edge in reviews_node.edges],
                defaults={'fk': {'issue': pr}},
            )

            # continue fetching the reviews for this issue if more than one page
            has_next_page = reviews_node.pageInfo.hasNextPage
            if has_next_page:
                objs += pr.fetch_pr_reviews(gh, reviews_node.pageInfo.endCursor, False)

        # we're done
        pr.pr_reviews_fetched_at = datetime.utcnow()
        pr.save(update_fields=['pr_reviews_fetched_at'])

    def fetch_all_pr_reviews(self, gh, next_page_cursor=''):

        if not self.pr_reviews_activated:
            return

        from gim.core.models import Issue

        has_next_page = True

        per_page = normal_per_page = 30

        done = 0
        failed = 0
        total = self.issues.filter(is_pull_request=True).count()

        variables = {
            'repositoryOwnerLogin': self.owner.username,
            'repositoryName': self.name,
        }
        debug_context = {
            'total': total,
        }

        while has_next_page:
            variables['nbPullRequestsToRetrieve'] =  per_page
            if next_page_cursor:
                variables['nextPullRequestsPageCursor'] =  next_page_cursor
            debug_context.update({
                'failed': failed,
                'done': done,
            })

            manage_reviews = True

            try:
                data = fetch_graphql(gh, self.GRAPHQL_FETCH_ALL_REVIEWS, variables, 'RepositoryAllPullRequestsReviews', debug_context)
            except GraphQLGithubInternalError:
                # We don't know which one fails, so we retry only with the half.
                # When only one PR, and a failure, we have our failing PR, and
                # will fetch it in a very light way to get the number

                if per_page > 1:
                    per_page /= 2
                    continue

                failed += 1
                manage_reviews = False
                debug_context['failed'] = failed
                data = fetch_graphql(gh, self.GRAPHQL_FETCH_ALL_REVIEWS_LITE, variables, 'RepositoryAllPullRequestsReviewsLite', debug_context)

                # now we can get the pr and retrieve its reviews
                pr_number = data.repository.pullRequests.edges[0].node.number
                try:
                    pr = self.issues.get(number=pr_number)
                    pr.fetch_pr_reviews(gh)
                except Issue.DoesNotExist:
                    pass
                else:
                    done += 1

                # we can restore the qtt per page
                per_page = normal_per_page
                # and let the process continue using pagination info

            pulls_node = data.repository.pullRequests

            has_next_page = pulls_node.pageInfo.hasNextPage
            if has_next_page:
                next_page_cursor = pulls_node.pageInfo.endCursor

            if not manage_reviews:
                continue

            # now work on each retrieved pr
            for edge in pulls_node.get('edges', []):
                try:
                    self._manage_pr_reviews_from_fetch(
                        gh,
                        self.issues.get(number=edge.node.number),
                        edge.get('node', {}).get('reviews', {})
                    )
                except Issue.DoesNotExist:
                    pass
                else:
                    done += 1

    def fetch_updated_pr_reviews(self, gh, prs=None, nb_prs_by_query=10): # more is too much complexity for github

        if not self.pr_reviews_activated:
            return 0

        # get the list of PRs to fetch: the ones where it was never fetched, or the one where it
        # was fetched before the last updated at
        if prs is None:
            prs = list(self.issues.filter(is_pull_request=True).filter(
                models.Q(pr_reviews_fetched_at__isnull=True)
                |
                models.Q(pr_reviews_fetched_at__lt=models.F('updated_at'))
            ).select_related('repository__owner'))

        if not prs:
            return 0

        count = 0

        failing_prs = []
        while len(prs):
            current_prs, prs = prs[:nb_prs_by_query], prs[nb_prs_by_query:]

            subqueries = [
                self.GRAPHQL_FETCH_REVIEWS_PR_SUBQUERY % {
                    'pr_index': index,
                    'pr_id': encode_graphql_id_for_object(pr),
                }
                for index, pr
                in enumerate(current_prs)
            ]

            query = reindent(self.GRAPHQL_FETCH_REVIEWS % '\n'.join(subqueries))

            try:
                data = fetch_graphql(gh, query, {}, 'RepositoryPullRequestsReviews', {
                    'repository': self.full_name,
                    'prs_left': len(prs) + len(current_prs),
                    'failed': len(failing_prs),
                })
            except GraphQLGithubInternalError:
                # we'll try them later
                failing_prs += current_prs
                continue
            except GraphQLComplexityError as e:
                # reset list to restart with a lower nb of prs by query
                nb_prs_by_query = e.complexity[1] / (e.complexity[0] / nb_prs_by_query)
                prs = current_prs + prs
                continue

            for index, node_key in enumerate(sorted(data.keys())):
                self._manage_pr_reviews_from_fetch(
                    gh,
                    current_prs[index],
                    data[node_key].get('reviews', {})
                )
                count += 1

        if failing_prs:
            if nb_prs_by_query / 2 > 1:
                count += self.fetch_updated_pr_reviews(gh, failing_prs, nb_prs_by_query / 2)
            else:
                # fetch the reviews one by one
                for pr in failing_prs:
                    pr.fetch_pr_reviews(gh)
                    count += 1

        return count


class ProtectedBranch(GithubObject):
    repository = models.ForeignKey('Repository', related_name='protected_branches')
    name = models.TextField(db_index=True)
    require_status_check = models.BooleanField(default=False)
    require_status_check_include_admins = models.BooleanField(default=False)
    require_up_to_date = models.BooleanField(default=False)
    require_approved_review = models.BooleanField(default=False)
    require_approved_review_include_admins = models.BooleanField(default=False)
    etag = models.CharField(max_length=64, blank=True, null=True)

    github_api_version = 'loki-preview'
    github_identifiers = {'repository__github_id': ('repository', 'github_id'), 'name': 'name'}

    objects = ProtectedBranchManager()

    class Meta:
        app_label = 'core'

    def __unicode__(self):
        return u'%s' % self.name

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_protected_branches + [
            self.name,
            'protection',
        ]

    def fetch(self, gh, defaults=None, force_fetch=False, parameters=None, meta_base_name=None, github_api_version=None):
        if defaults is None:
            defaults = {}
        if not defaults.get('fk', {}):
            defaults['fk'] = {}
        if not defaults.get('repository'):
            defaults['fk']['repository'] = self.repository
        if not defaults.get('simple', {}):
            defaults['simple'] = {}
        if not defaults['simple'].get('name'):
            defaults['simple']['name'] = self.name

        try:
            return super(ProtectedBranch, self).fetch(gh, defaults, force_fetch, parameters, meta_base_name, github_api_version)
        except ApiNotFoundError:
            # the branch is not protected anymore
            self.delete()
        return None
