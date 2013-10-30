from operator import attrgetter
import re

from django.core.urlresolvers import reverse, reverse_lazy
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template import loader, Context

from limpyd import model as lmodel, fields as lfields

from core import models as core_models, main_limpyd_database
from core.utils import contribute_to_model

from subscriptions import models as subscriptions_models


class _GithubUser(models.Model):
    AVATAR_START = re.compile('^https?://\d+\.')

    class Meta:
        abstract = True

    @property
    def hash(self):
        """
        Hash for this object representing its state at the current time, used to
        know if we have to reset an issue's cache
        """
        # we remove the subdomain of the gravatar url that may change between
        # requests to the github api for the same user with the save avatar
        # (https://0.gravatar...,  https://1.gravatar...)
        avatar_url = ''
        if self.avatar_url:
            avatar_url = self.AVATAR_START.sub('', self.avatar_url, count=1)
        return hash((self.username, avatar_url, ))

    def get_related_issues(self):
        """
        Return a list of all issues related to this user (it may be the creator,
        the assignee, or the closer)
        """
        return core_models.Issue.objects.filter(
                                                   models.Q(user=self)
                                                 | models.Q(assignee=self)
                                                 | models.Q(closed_by=self)
                                               )

contribute_to_model(_GithubUser, core_models.GithubUser)


class _Repository(models.Model):
    class Meta:
        abstract = True

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.owner.username,
            'repository_name': self.name,
        }

    def get_absolute_url(self):
        return reverse_lazy('front:repository:home', kwargs=self.get_reverse_kwargs())

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name,
                                  kwargs=self.get_reverse_kwargs())

    def get_issues_filter_url(self):
        kwargs = self.get_reverse_kwargs()
        return reverse('front:repository:issues', kwargs=kwargs)

    def get_issues_user_filter_url_for_username(self, filter_type, username):
        """
        Return the url to filter issues of this repositories by filter_type, for
        the given username
        Calls are cached for faster access
        """
        cache_key = (self.id, filter_type, username)
        if cache_key not in self.get_issues_user_filter_url_for_username._cache:
            kwargs = self.get_reverse_kwargs()
            kwargs.update({
                'username': username,
                'user_filter_type': filter_type
            })
            self.get_issues_user_filter_url_for_username._cache[cache_key] = \
                        reverse('front:repository:user_issues', kwargs=kwargs)
        return self.get_issues_user_filter_url_for_username._cache[cache_key]
    get_issues_user_filter_url_for_username._cache = {}

contribute_to_model(_Repository, core_models.Repository)


class _LabelType(models.Model):
    class Meta:
        abstract = True

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'label_type_id': self.id
        }

    def get_edit_url(self):
        from front.repository.dashboard.views import LabelTypeEdit
        return reverse_lazy('front:repository:%s' % LabelTypeEdit.url_name, kwargs=self.get_reverse_kwargs())

    def get_delete_url(self):
        from front.repository.dashboard.views import LabelTypeDelete
        return reverse_lazy('front:repository:%s' % LabelTypeDelete.url_name, kwargs=self.get_reverse_kwargs())

    @property
    def hash(self):
        """
        Hash for this object representing its state at the current time, used to
        know if we have to reset an issue's cache
        """
        return hash((self.id, self.name, ))

    def get_related_issues(self):
        """
        Return a list of all issues related to this label type
        """
        return core_models.Issue.objects.filter(labels__label_type=self)

contribute_to_model(_LabelType, core_models.LabelType)


class _Label(models.Model):
    class Meta:
        abstract = True

    @property
    def hash(self):
        """
        Hash for this object representing its state at the current time, used to
        know if we have to reset an issue's cache
        """
        return hash((self.id, self.name, self.color,
                     self.label_type.hash if self.label_type_id else None, ))

    def get_related_issues(self):
        """
        Return a list of all issues related to this label
        """
        return core_models.Issue.objects.filter(labels=self)

contribute_to_model(_Label, core_models.Label)


class _Milestone(models.Model):
    class Meta:
        abstract = True

    @property
    def hash(self):
        """
        Hash for this object representing its state at the current time, used to
        know if we have to reset an issue's cache
        """
        return hash((self.id, self.title, self.state, ))

    def get_related_issues(self):
        """
        Return a list of all issues related to this milestone
        """
        return core_models.Issue.objects.filter(milestone=self)

contribute_to_model(_Milestone, core_models.Milestone)


class _Issue(models.Model):
    class Meta:
        abstract = True

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'issue_number': self.number
        }

    def get_absolute_url(self):
        return reverse_lazy('front:repository:issue', kwargs=self.get_reverse_kwargs())

    @property
    def hash(self):
        """
        Hash for this issue representing its state at the current time, used to
        know if we have to reset an its cache
        """
        return hash((self.updated_at,
                     self.user.hash if self.user_id else None,
                     self.closed_by.hash if self.closed_by_id else None,
                     self.assignee.hash if self.assignee_id else None,
                     self.milestone.hash if self.milestone_id else None,
                     self.total_comments_count or 0,
                     ','.join(['%d' % l.hash for l in self.labels.all()]),
                ))

    def update_saved_hash(self):
        """
        Update in redis the saved hash
        """
        hash_obj, _ = Hash.get_or_connect(
                                type=self.__class__.__name__, obj_id=self.pk)
        hash_obj.hash.hset(self.hash)

    @property
    def saved_hash(self):
        """
        Return the saved hash, create it if not exist
        """
        hash_obj, created = Hash.get_or_connect(
                                type=self.__class__.__name__, obj_id=self.pk)
        if created:
            self.update_saved_hash()
        return hash_obj.hash.hget()

    def update_cached_template(self, force_regenerate=False):
        """
        Update, if needed, the cached template for the current issue.
        """
        template = 'front/repository/issues/include_issue_item_for_cache.html'

        # mnimize queries
        issue = self.__class__.objects.filter(id=self.id)\
                .select_related('user', 'assignee', 'created_by', 'milestone')\
                .prefetch_related('labels__label_type')[0]

        context = Context({
            'issue': issue,
            '__regenerate__': force_regenerate,
        })

        loader.get_template(template).render(context)

    def get_activity(self):
        """
        Return the activity of the issue, including comments, events and
        pr_comments if it's a pull request
        """
        types = [
            list(self.comments.ready().select_related('user')),
            list(self.events.ready().select_related('user')),
        ]
        if self.is_pull_request:
            types.append(list(self.pr_comments_entry_points.all()
                                     .select_related('user', 'pr_comments')))

        activity = sorted(sum(types, []), key=attrgetter('created_at'))

        if self.is_pull_request:
            activity = GroupedPullRequestCommits.add_commits_in_activity(self, activity)

        return activity

contribute_to_model(_Issue, core_models.Issue)


class GroupedPullRequestCommits(list):
    is_commits_group = True  # for template

    @classmethod
    def add_commits_in_activity(cls, issue, activity):
        commits = list(issue.commits.all().select_related('author', 'committer'))
        if not len(commits):
            return activity

        final_activity = []
        current_group = None

        for entry in activity:

            # add in a group all commits before the entry
            while len(commits) and commits[0].committed_at < entry.created_at:
                if current_group is None:
                    current_group = cls()
                current_group.append(commits.pop(0))

            if current_group:
                final_activity.append(current_group)
                current_group = None

            # then add the entry
            final_activity.append(entry)

        # still some commits, add a group with them
        if len(commits):
            final_activity.append(cls(commits))

        return final_activity

    def authors(self):
        authors = []
        for commit in self:
            name = commit.author.username if commit.author_id else commit.author_name
            if name not in authors:
                authors.append(name)
        return authors


class _PullRequestCommit(models.Model):
    class Meta:
        abstract = True

    @property
    def short_sha(self):
        return self.sha[:8]

    @property
    def splitted_message(self):
        LEN = 72
        ln_pos = self.message.find('\n')
        if 0 <= ln_pos < LEN:
            result = [self.message[:ln_pos], self.message[ln_pos+1:]]
            while result[1] and result[1][0] == '\n':
                result[1] = result[1][1:]
            return result
        return [self.message[:LEN], self.message[LEN:]]

contribute_to_model(_PullRequestCommit, core_models.PullRequestCommit)


class _WaitingSubscription(models.Model):
    class Meta:
        abstract = True

    def can_add_again(self):
        """
        Return True if the user can add the reposiory again (it is allowed if
        the state is FAILED)
        """
        return self.state == subscriptions_models.WAITING_SUBSCRIPTION_STATES.FAILED

contribute_to_model(_WaitingSubscription, subscriptions_models.WaitingSubscription)


class Hash(lmodel.RedisModel):

    database = main_limpyd_database

    type = lfields.InstanceHashField(indexable=True)
    obj_id = lfields.InstanceHashField(indexable=True)
    hash = lfields.InstanceHashField()


@receiver(post_save, dispatch_uid="hash_check")
def hash_check(sender, instance, created, **kwargs):
    """
    Check if the hash of the object has changed since its last save and if True,
    update the Issue if its an issue, or related issues if it's a:
    - user
    - milestone
    - label_type
    - label
    """

    if not isinstance(instance, (
                        core_models.GithubUser,
                        core_models.Milestone,
                        core_models.LabelType,
                        core_models.Label,
                        core_models.Issue
                      )):
        return

    # get the limpyd instance storing the hash, create it if not exists
    hash_obj, hash_obj_created = Hash.get_or_connect(
                        type=instance.__class__.__name__, obj_id=instance.pk)

    if created:
        hash_changed = True
    else:
        hash_changed = hash_obj_created or str(instance.hash) != hash_obj.hash.hget()

    if not hash_changed:
        return

    # save the new hash
    hash_obj.hash.hset(instance.hash)

    from core.tasks.issue import UpdateIssueCacheTemplate

    if isinstance(instance, core_models.Issue):
        # if an issue, add a job to update its template
        UpdateIssueCacheTemplate.add_job(instance.id)

    else:
        # if not an issue, add a job to update the templates of all related issues
        for issue in instance.get_related_issues():
            UpdateIssueCacheTemplate.add_job(issue.id)
