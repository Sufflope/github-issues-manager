# -*- coding: utf-8 -*-

import json
import re
from collections import Counter, OrderedDict
from operator import attrgetter

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.urlresolvers import reverse_lazy
from django.db import models
from django.db.models import FieldDoesNotExist
from django.template import loader, Context
from django.template.defaultfilters import date as convert_date, escape
from django.utils.functional import cached_property
from limpyd import model as lmodel, fields as lfields
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from pymdownx.github import GithubExtension

from gim.core import models as core_models, get_main_limpyd_database
from gim.core.models.base import GithubObject
from gim.core.utils import cached_method
from gim.events.models import EventPart
from gim.subscriptions import models as subscriptions_models
from gim.ws import publisher

from .publish import thread_data


def html_content(self, body_field='body', force=False):
    html = None
    if not force:
        html = getattr(self, '%s_html' % body_field, None)
    if html is None:
        html = markdown(getattr(self, body_field),
                        extensions=[
                            GithubExtension(),
                            CodeHiliteExtension(guess_lang=False),
                        ]
                    )
    return html


class FrontEditable(models.Model):

    front_uuid = models.CharField(max_length=36, blank=True, null=True)

    class Meta:
        abstract = True

    def defaults_create_values(self, mode):
        values = self.old_defaults_create_values(mode)
        values.setdefault('simple', {})['front_uuid'] = self.front_uuid
        if hasattr(self, 'is_new'):
            values['simple']['is_new'] = self.is_new
        return values

    def clear_front_uuid(self):
        # We don't call save as we are already in a save call and don't want things to be called twice
        self.__class__.objects.filter(pk=self.pk).update(front_uuid=None)

    @staticmethod
    def isinstance(obj):
        try:
            obj._meta.get_field('front_uuid')
        except FieldDoesNotExist:
            return False
        else:
            return True


class Hashable(object):

    @property
    def hash(self):
        raise NotImplementedError()

    def hash_changed(self, force_update=False):
        """
        Tells if the current hash is different of the saved one
        """
        hash_obj, hash_obj_created = Hash.get_or_connect(
                        type=self.model_name, obj_id=self.pk)

        hash = self.hash

        if not force_update and not hash_obj_created and str(hash) == hash_obj.hash.hget():
            return False

        # save the new hash
        hash_obj.hash.hset(hash)

        return hash


class _GithubUser(Hashable, models.Model):
    AVATAR_STARTS = [
        # 0.gravatar.com => gravatar.com
        (re.compile('^(https?://)\d+\.'), r'\1'),
        # avatars0.githubusercontent.com => avatars.githubusercontent.com
        (re.compile('^(https?://[^\.]+)\d+\.'), r'\1.'),
    ]

    class Meta:
        abstract = True

    @classmethod
    def get_default_avatar(cls):
        if not hasattr(core_models.GithubUser, '_default_avatar'):
            core_models.GithubUser._default_avatar = staticfiles_storage.url('front/img/default-avatar.png')
        return core_models.GithubUser._default_avatar

    @cached_property
    def full_avatar_url(self):
        if self.avatar_url:
            return '%s%s' % (settings.AVATARS_PREFIX, self.avatar_url)
        return core_models.GithubUser.get_default_avatar()

    @property
    def hash(self):
        """
        Hash for this object representing its state at the current time, used to
        know if we have to reset an issue's cache
        """

        avatar_url = ''

        if self.avatar_url:
            avatar_url = self.avatar_url

            # if we have a number at the end of the subdomain, we remove it because it may
            # change between requests to the github api for the same user with the save avatar
            for regex, repl in self.AVATAR_STARTS:
                if regex.match(avatar_url):
                    avatar_url = regex.sub(repl, avatar_url, count=1)
                    break

        return hash((self.username, avatar_url, ))

    def get_related_issues(self):
        """
        Return a list of all issues related to this user (it may be the creator,
        an assignee, or the closer)
        """
        return core_models.Issue.objects.filter(
                                                   models.Q(user=self)
                                                 | models.Q(assignees=self)
                                                 | models.Q(closed_by=self)
                                               )

    @cached_property
    def readable_subscribed_repositories(self):
        """
        Return a dict with, for each available repository for the user, the
        repository fullname as key and the "Subscription" object as value
        """
        from gim.subscriptions.models import SUBSCRIPTION_STATES

        ids = self.subscriptions.filter(
            state__in=SUBSCRIPTION_STATES.READ_RIGHTS).values_list('repository_id', flat=True)

        return core_models.Repository.objects.filter(id__in=ids).extra(select={
                    'lower_name': 'lower(name)',
                }
            ).select_related('owner').order_by('owner__username_lower', 'lower_name')

    @cached_property
    def unread_notifications_count(self):
        return self.github_notifications.filter(unread=True, issue__isnull=False).count()

    @cached_property
    def last_unread_notification_date(self):
        return self.github_notifications.filter(
            unread=True, issue__isnull=False).order_by('-updated_at').values_list('updated_at', flat=True).first()


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
        return self.get_view_url('home')

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_create_issue_url(self):
        return self.get_view_url('issue.create')

    def get_create_project_url(self):
        from gim.front.repository.board.views import ProjectCreateView
        return self.get_view_url(ProjectCreateView.url_name)

    def delete(self, using=None):
        pk = self.pk

        # When deleting a repository we don't publish when things (comments...) are deleted
        thread_data.skip_publish = True
        try:
            self.old_delete(using)
        finally:
            thread_data.skip_publish = False

        publisher.remove_repository(pk)

    def get_milestones_for_select(self, key='id', with_graph_url=False, include_grouped=True,
                                  milestones=None):

        if milestones is None:
            milestones = self.milestones.all()

        data = {getattr(m, key): {
                'id': m.id,
                'number': m.number,
                'due_on': convert_date(m.due_on, settings.DATE_FORMAT) if m.due_on else None,
                'title': escape(m.title),
                'state': m.state,
                'graph_url': str(m.get_graph_url()) if with_graph_url else None,
              }
            for m in milestones
        }

        result = {
            'milestones_json': json.dumps(data),
        }

        if include_grouped:

            grouped_milestones = {}
            for milestone in milestones:
                grouped_milestones.setdefault(milestone.state, []).append(milestone)

            result['grouped_milestones'] = grouped_milestones

        return result

    def all_metrics(self):
        return self.label_types.filter(is_metric=True)


class _LabelType(Hashable, models.Model):
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

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_edit_url(self):
        from gim.front.repository.dashboard.views import LabelTypeEdit
        return self.get_view_url(LabelTypeEdit.url_name)

    def get_delete_url(self):
        from gim.front.repository.dashboard.views import LabelTypeDelete
        return self.get_view_url(LabelTypeDelete.url_name)

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


class _Label(Hashable, FrontEditable):
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


class _Milestone(Hashable, FrontEditable):
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

    @property
    def html_content(self):
        return html_content(self, 'description')

    @property
    def short_title(self):
        if len(self.title) > 25:
            result = self.title[:20] + u'…'
        else:
            result = self.title
        return escape(result)

    def get_reverse_kwargs(self, key="id"):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'milestone_%s' % key: getattr(self, key),
        }

    def get_view_url(self, url_name, key="id"):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs(key=key))

    def get_edit_url(self):
        from gim.front.repository.dashboard.views import MilestoneEdit
        return self.get_view_url(MilestoneEdit.url_name)

    def get_delete_url(self):
        from gim.front.repository.dashboard.views import MilestoneDelete
        return self.get_view_url(MilestoneDelete.url_name)

    def get_graph_url(self):
        from gim.front.repository.dashboard.views import MilestoneGraph
        return self.get_view_url(MilestoneGraph.url_name, key='number')


class WithFiles(object):

    def files_enhanced_for_user(self, user):
        counts = self.comments_count_by_path

        files = list(self.files.all())

        for file in files:
            file.repository = self.repository
            file.nb_comments = counts.get(file.path, 0)
            file.reviewed_hunks_locally = file.get_hunks_locally_reviewed_by_user(user)
            file.reviewed_locally = all(file.reviewed_hunks_locally.values())

        return files


class _Issue(WithFiles, Hashable, FrontEditable):
    class Meta:
        abstract = True

    RENDERER_IGNORE_FIELDS = {'state', 'merged'}

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'issue_number': self.number
        }

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_absolute_url(self):
        return self.get_view_url('issue')

    def get_websocket_data_url(self):
        return self.get_view_url('issue.summary')

    def get_created_url(self):
        kwargs = self.get_reverse_kwargs()
        del kwargs['issue_number']
        kwargs['issue_pk'] = self.pk
        return reverse_lazy('front:repository:issue.created', kwargs=kwargs)

    def edit_field_url(self, field):
        return self.get_view_url('issue.edit.%s' % field)

    def issue_comment_create_url(self):
        from gim.front.repository.issues.views import IssueCommentCreateView
        return self.get_view_url(IssueCommentCreateView.url_name)

    def pr_comment_create_url(self):
        if not hasattr(self, '_pr_comment_create_url'):
            from gim.front.repository.issues.views import PullRequestCommentCreateView
            self._pr_comment_create_url = self.get_view_url(PullRequestCommentCreateView.url_name)
        return self._pr_comment_create_url

    def pr_review_create_url(self):
        if not hasattr(self, '_pr_review_create_url'):
            from gim.front.repository.issues.views import PullRequestReviewCreateView
            self._pr_review_create_url = self.get_view_url(PullRequestReviewCreateView.url_name)
        return self._pr_review_create_url

    def ajax_files_url(self):
        return self.get_view_url('issue.files')

    def ajax_commits_url(self):
        return self.get_view_url('issue.commits')

    def ajax_review_url(self):
        return self.get_view_url('issue.review')

    def ajax_commit_base_url(self):
        kwargs = self.get_reverse_kwargs()
        kwargs['commit_sha'] = '0' * 40
        from gim.front.repository.issues.views import CommitAjaxIssueView
        return reverse_lazy('front:repository:%s' % CommitAjaxIssueView.url_name, kwargs=kwargs)

    def commit_comment_create_url(self):
        if not hasattr(self, '_commit_comment_create_url'):
            kwargs = self.get_reverse_kwargs()
            kwargs['commit_sha'] = '0' * 40
            from gim.front.repository.issues.views import CommitCommentCreateView
            self._commit_comment_create_url = reverse_lazy('front:repository:%s' % CommitCommentCreateView.url_name,
                                                           kwargs=kwargs)
        return self._commit_comment_create_url

    @property
    def type(self):
        return 'pull request' if self.is_pull_request else 'issue'

    @property
    def nb_authors(self):
        if not self.is_pull_request or not self.nb_commits:
            return 0
        if self.nb_commits == 1:
            return 1
        return len(set(self.commits.filter(related_commits__deleted=False)
                                   .values_list('author_name', flat=True)))

    @property
    def hash_values(self):
        """
        Hash for this issue representing its state at the current time, used to
        know if we have to reset its cache
        """

        hashable_fields = ('number', 'title', 'body', 'state', 'is_pull_request', 'updated_at')
        if self.is_pull_request:
            hashable_fields += (
                'base_sha', 'head_sha', 'merged', 'last_head_status', 'pr_review_state', 'pr_review_required'
            )
            if self.state == 'open' and not self.merged:
                hashable_fields += ('mergeable', 'mergeable_state')

        hash_values = tuple(getattr(self, field) for field in hashable_fields) + (
            self.user_id,
            self.closed_by_id,
            ','.join(map(str, sorted(self.assignees.values_list('pk', flat=True)))),
            self.milestone_id,
            self.total_comments_count or 0,
            ','.join(map(str, sorted(self.labels.values_list('pk', flat=True)))),
            ','.join(sorted(['%s:%s' % c for c in self.cards.values_list('column_id', 'position')]))
        )

        if self.is_pull_request:
            commits_part = ','.join(sorted(self.related_commits.filter(deleted=False).values_list('commit__sha', flat=True)))
            hash_values += (commits_part, self.repository.pr_reviews_activated, self.displayable_pr_reviews_count)

        return hash_values

    @property
    def hash(self):
        return hash(self.hash_values)

    def update_saved_hash(self):
        """
        Update in redis the saved hash
        """
        hash_obj, _ = Hash.get_or_connect(
                                type=self.model_name, obj_id=self.pk)
        hash_obj.hash.hset(self.hash)

    @property
    def saved_hash(self):
        """
        Return the saved hash, create it if not exist
        """
        hash_obj, created = Hash.get_or_connect(
                                type=self.model_name, obj_id=self.pk)
        if created:
            self.update_saved_hash()
        return hash_obj.hash.hget()

    def update_cached_template(self, force_regenerate=False):
        """
        Update, if needed, the cached template for the current issue.
        """
        template = 'front/repository/issues/include_issue_item_for_cache.html'

        # minimize queries
        issue = self.__class__.objects.filter(
            id=self.id
        ).select_related(
            'repository__owner', 'user', 'created_by', 'closed_by', 'milestone'
        ).prefetch_related(
            'assignees', 'labels__label_type', 'cards__column__project'
        )[0]

        context = Context({
            'issue': issue,
            '__regenerate__': force_regenerate,
        })

        loader.get_template(template).render(context)

    @cached_method
    def all_commits(self, include_deleted, sort=True):
        qs = self.related_commits.select_related(
            'commit__author', 'commit__committer', 'commit__repository__owner'
        )

        if sort:
            qs = qs.order_by(
               'commit__authored_at', 'commit__committed_at'
            )

        if not include_deleted:
            qs = qs.filter(deleted=False)

        result = []
        for c in qs:
            c.commit.relation_deleted = c.deleted
            result.append(c.commit)

        return result

    @property
    def all_entry_points(self):
        if not hasattr(self, '_all_entry_points'):
            self._all_entry_points = list(
                self.pr_comments_entry_points.annotate(
                    nb_comments=models.Count('comments')
                ).filter(
                    nb_comments__gt=0
                ).select_related(
                    'user', 'repository__owner'
                ).prefetch_related(
                    'comments__user'
                )
            )
        return self._all_entry_points

    @property
    def all_commit_entry_points(self):
        if not hasattr(self, '_all_commit_entry_points'):

            commits = self.all_commits(True, False)  # only args for cache_method
            commits_by_pk = {commit.pk: commit for commit in commits}

            self._all_commit_entry_points = list(
                core_models.CommitCommentEntryPoint.objects.filter(
                    commit__id__in=commits_by_pk.keys()
                ).annotate(
                    nb_comments=models.Count('comments')
                ).filter(
                    nb_comments__gt=0
                ).select_related(
                    'user', 'repository__owner',
                ).prefetch_related(
                    'comments__user'
                )
            )

            # cache commit for each entry point, using the ones got from
            # `all_commits`, that include the `relation_deleted` attribute
            for entry_point in self._all_commit_entry_points:
                entry_point._commit_cache = commits_by_pk[entry_point.commit_id]

        return self._all_commit_entry_points

    def get_activity(self):
        """
        Return the activity of the issue, including comments, events and
        pr_comments if it's a pull request
        """
        change_events = list(self.event_set.filter(id__in=set(
                            EventPart.objects.filter(
                                            event__is_update=True,
                                            event__issue_id=self.id,
                                        )
                                        .exclude(
                                            field__in=self.RENDERER_IGNORE_FIELDS
                                        )
                                        .values_list('event_id', flat=True)
                            )).prefetch_related('parts'))

        for event in change_events:
            event.renderer_ignore_fields = self.RENDERER_IGNORE_FIELDS

        comments = list(self.comments.select_related('user', 'repository__owner'))

        events = list(self.events.exclude(event='referenced', commit_sha__isnull=True)
                                        .select_related('user', 'repository__owner'))

        activity = change_events + comments + events

        if self.is_pull_request:
            pr_comments = list(self.pr_comments.select_related('user'))

            activity += pr_comments + self.all_commits(False)

            # group commit comments by day + commit
            cc_by_commit = {}
            commit_comments = list(core_models.CommitComment.objects
                                    .filter(commit__related_commits__issue=self)
                                    .select_related('commit', 'user'))

            if len(commit_comments):
                all_commits_by_sha = {c.sha: c for c in self.all_commits(True)}
                for c in commit_comments:

                    if c.commit.sha in all_commits_by_sha:
                        c.commit.relation_deleted = all_commits_by_sha[c.commit.sha].relation_deleted

                    cc_by_commit.setdefault(c.commit, []).append(c)

                for comments in cc_by_commit.values():
                    activity += GroupedCommitComments.group_by_day(comments)

            # add pull request reviews
            if self.repository.pr_reviews_activated:
                activity += self.get_pr_reviews_activity()

        activity.sort(key=attrgetter('created_at'))

        if self.is_pull_request:
            activity = GroupedCommits.group_in_activity(activity)
            activity = GroupedPullRequestComments.group_in_activity(activity)

        return activity

    def get_pr_reviews_activity(self):
        if not self.repository.pr_reviews_activated:
            return []

        if not hasattr(self, '_pr_reviews_activity'):

            self._pr_reviews_activity = list(self.reviews.filter(displayable=True).select_related('author'))

        return self._pr_reviews_activity

    @property
    def displayable_pr_reviews_count(self):
        return len(self.get_pr_reviews_activity())

    def get_sorted_entry_points(self):
        for entry_point in self.all_entry_points:
            entry_point.last_created = list(entry_point.comments.all())[-1].created_at
        return sorted(self.all_entry_points, key=attrgetter('last_created'))

    def get_sorted_entry_points_including_commits(self):
        for entry_points in [self.all_entry_points, self.all_commit_entry_points]:
            for entry_point in entry_points:
                entry_point.last_created = list(entry_point.comments.all())[-1].created_at
        return sorted(self.all_entry_points + self.all_commit_entry_points, key=attrgetter('last_created'))

    def get_commits_per_day(self, include_deleted=False):
        if not self.is_pull_request:
            return []
        return GroupedCommits.group_by_day(
            self.all_commits(include_deleted)
        )

    def get_all_commits_per_day(self):
        return self.get_commits_per_day(True)

    @cached_property
    def nb_deleted_commits(self):
        return self.related_commits.filter(deleted=True).count()

    @cached_property
    def nb_comments_in_deleted_commits_comments(self):
        return core_models.CommitComment.objects.filter(
            commit__issues=self,
            commit__related_commits__deleted=True
        ).count()

    @property
    def html_content(self):
        return html_content(self)

    @cached_property
    def comments_count_by_path(self):
        return Counter(
            self.pr_comments.filter(
                entry_point__position__isnull=False
            ).select_related(
                'entry_point'
            ).values_list(
                'entry_point__path', flat=True
            )
        )

    def publish_notifications(self):
        for notification in self.github_notifications.select_related('user').all():
            if hasattr(self, '_repository_cache'):
                notification._repository_cache = self._repository_cache
            notification.publish()

    def ordered_cards(self):
        """Order card by project/column, using prefetched info if present"""

        need_fetch = True

        if hasattr(self, '_prefetched_objects_cache') and 'cards' in self._prefetched_objects_cache:
            # cards are already prefetched
            need_fetch = False
            for card in self._prefetched_objects_cache['cards']:
                try:
                    card._column_cache._project_cache
                except AttributeError:
                    # column or project not in cache
                    need_fetch = True
                    break

            if not need_fetch:
                return sorted(
                    self._prefetched_objects_cache['cards'],
                    key=lambda card: (card.column.project.number, card.column.position)
                )

        if not hasattr(self, '_prefetched_objects_cache'):
            self._prefetched_objects_cache = {}
        self._prefetched_objects_cache['cards'] =  list(self.cards.select_related(
            'column__project'
        ).order_by(
            'column__project__number'
        ))
        return self._prefetched_objects_cache['cards']

    def user_can_add_pr_review(self, user):
        if not self.is_pull_request:
            return False
        if not user or user.is_anonymous():
            return False
        if not self.repository.pr_reviews_activated:
            return False
        return self.user != user


class GroupedItems(list):
    """
    An object to regroup a list of entries of the same type:
    - in a list of activities: all entries between two entries of the activity
      list are grouped together per day ("group_in_activity")
    - per day ("group_by_day")
    Also provides an 'author' method which returns a a dict with each author and
    its number of entries
    """
    model = None
    date_field = 'created_at'
    author_field = 'user'

    @classmethod
    def group_in_activity(cls, activity):
        final_activity = []
        current_group = None

        for entry in activity:

            if isinstance(entry, cls.model):
                # we have a THING

                # create a new group if first THING in a row
                if not current_group:
                    current_group = cls()

                # add the THING to the current group
                current_group.append(entry)

            else:
                # not a THING

                # we close the current group, group its THINGs by day, and insert
                # the resulting sub groups in the activity
                if current_group:
                    final_activity.extend(cls.group_by_day(current_group))
                    # we'll want to start a fresh group
                    current_group = None

                # we add the non-THING entry in the activity
                final_activity.append(entry)

        # still some THINGs with nothing after, add a group with them
        if current_group:
            final_activity.extend(cls.group_by_day(current_group))

        return final_activity

    @classmethod
    def group_by_day(cls, entries):
        if not len(entries):
            return []

        groups = []

        for entry in entries:
            entry_datetime = getattr(entry, cls.date_field)
            entry_date = entry_datetime.date()
            if not groups or entry_date != groups[-1].start_date:
                groups.append(cls())
                groups[-1].start_date = entry_date
                groups[-1].created_at = entry_datetime
            groups[-1].append(entry)

        return groups

    @classmethod
    def get_author(cls, entry):
        author = getattr(entry, cls.author_field)
        return {
            'username': author.username,
            'full_avatar_url': author.full_avatar_url,
        }

    def authors(self):
        result = OrderedDict()

        for entry in self:
            author = self.get_author(entry)
            name = author['username']
            if name not in result:
                result[name] = author
                result[name]['count'] = 0
            result[name]['count'] += 1

        return result


class GroupedPullRequestComments(GroupedItems):
    model = core_models.PullRequestComment
    date_field = 'created_at'
    author_field = 'user'
    is_pr_comments_group = True  # for template


class GroupedCommitComments(GroupedItems):
    model = core_models.CommitComment
    date_field = 'created_at'
    author_field = 'user'
    is_commit_comments_group = True  # for template


class GroupedCommits(GroupedItems):
    model = core_models.Commit
    date_field = 'authored_at'
    author_field = 'author'
    is_commits_group = True  # for template

    @classmethod
    def get_author(cls, entry):
        if entry.author_id:
            return super(GroupedCommits, cls).get_author(entry)
        else:
            return {
                'username': entry.author_name,
                'full_avatar_url': None,
            }


class _Commit(WithFiles, models.Model):
    class Meta:
        abstract = True

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

    @property
    def all_entry_points(self):
        if not hasattr(self, '_all_entry_points'):
            self._all_entry_points = list(
                self.commit_comments_entry_points.annotate(
                    nb_comments=models.Count('comments')  # cannot exclude waiting_deleted for now
                ).filter(
                    nb_comments__gt=0
                ).select_related(
                    'user', 'repository__owner'
                ).prefetch_related(
                    'comments__user'
                )
            )
        return self._all_entry_points

    @cached_property
    def comments_count_by_path(self):
        return Counter(
            self.commit_comments.filter(
                models.Q(entry_point__position__isnull=False)
                |
                models.Q(entry_point__path__isnull=True)
            ).select_related(
                'entry_point'
            ).values_list(
                'entry_point__path', flat=True
            )
        )

    @cached_property
    def count_global_comments(self):
        return self.comments_count_by_path.get(None, 0)

    @cached_property
    def real_author_name(self):
        return self.author.username if self.author_id else self.author_name

    @cached_property
    def real_committer_name(self):
        return self.committer.username if self.committer_id else self.committer_name

    @cached_property
    def committer_is_author(self):
        if self.author_id and self.committer_id:
            return self.author_id == self.committer_id
        if self.author_id:
            return (self.author.email or self.author_email) == self.committer_email
        if self.committer_id:
            return (self.committer.email or self.committer_email) == self.author_email
        return self.author_email == self.committer_email

    def get_reverse_kwargs_for_issue(self, issue):
        return dict(
            issue.get_reverse_kwargs(),
            commit_sha=self.commit.sha,
        )

    def get_absolute_url_for_issue(self, issue):
        from gim.front.repository.issues.views import CommitAjaxIssueView
        return reverse_lazy('front:repository:%s' % CommitAjaxIssueView.url_name,
                            kwargs=self.get_reverse_kwargs_for_issue(issue))


class _WaitingSubscription(models.Model):
    class Meta:
        abstract = True

    def can_add_again(self):
        """
        Return True if the user can add the repository again (it is allowed if
        the state is FAILED)
        """
        return self.state == subscriptions_models.WAITING_SUBSCRIPTION_STATES.FAILED


class _IssueComment(FrontEditable):
    class Meta:
        abstract = True

    @property
    def html_content(self):
        return html_content(self)

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'issue_number': self.issue.number,
            'comment_pk': self.pk,
        }

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_absolute_url(self):
        from gim.front.repository.issues.views import IssueCommentView
        return self.get_view_url(IssueCommentView.url_name)

    def get_edit_url(self):
        from gim.front.repository.issues.views import IssueCommentEditView
        return self.get_view_url(IssueCommentEditView.url_name)

    def get_delete_url(self):
        from gim.front.repository.issues.views import IssueCommentDeleteView
        return self.get_view_url(IssueCommentDeleteView.url_name)


class _PullRequestComment(FrontEditable):
    class Meta:
        abstract = True

    @property
    def html_content(self):
        return html_content(self)

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'issue_number': self.issue.number,
            'comment_pk': self.pk,
        }

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_absolute_url(self):
        from gim.front.repository.issues.views import PullRequestCommentView
        return self.get_view_url(PullRequestCommentView.url_name)

    def get_edit_url(self):
        from gim.front.repository.issues.views import PullRequestCommentEditView
        return self.get_view_url(PullRequestCommentEditView.url_name)

    def get_delete_url(self):
        from gim.front.repository.issues.views import PullRequestCommentDeleteView
        return self.get_view_url(PullRequestCommentDeleteView.url_name)


class _CommitComment(FrontEditable):
    class Meta:
        abstract = True

    @property
    def html_content(self):
        return html_content(self)

    def get_reverse_kwargs_for_issue(self, issue):
        return dict(
            issue.get_reverse_kwargs(),
            commit_sha=self.commit.sha,
            comment_pk=self.pk,
        )

    def get_absolute_url_for_issue(self, issue):
        from gim.front.repository.issues.views import CommitCommentView
        return reverse_lazy('front:repository:%s' % CommitCommentView.url_name,
                            kwargs=self.get_reverse_kwargs_for_issue(issue))


class _GithubNotification(models.Model):
    class Meta:
        abstract = True

    def get_edit_url(self):
        return reverse_lazy('front:github-notifications:edit', kwargs={'notif_id': self.pk})


class _PullRequestReview(Hashable, FrontEditable):

    class Meta:
        abstract = True

    is_pull_request_review = True

    @property
    def hash(self):
        return hash((self.author_id, self.submitted_at, self.state))

    def get_related_issues(self):
        """
        Return a list of all issues related to this review(ie only one!)
        """
        return core_models.Issue.objects.filter(pk=self.issue_id)

    @property
    def created_at(self):
        return self.submitted_at

    @property
    def user_id(self):
        return self.author_id

    @property
    def user(self):
        return self.author

    @property
    def repository_id(self):
        return self.issue.repository_id

    @property
    def repository(self):
        return self.issue.repository

    @property
    def html_content(self):
        return html_content(self)

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'issue_number': self.issue.number,
            'review_pk': self.pk,
        }

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_absolute_url(self):
        from gim.front.repository.issues.views import PullRequestReviewView
        return self.get_view_url(PullRequestReviewView.url_name)

    def get_edit_url(self):
        from gim.front.repository.issues.views import PullRequestReviewEditView
        return self.get_view_url(PullRequestReviewEditView.url_name)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):

        is_new = not bool(self.pk)

        if not update_fields or 'body' in update_fields:
            self.body_html = html_content(self) if self.body else ''
            if update_fields:
                update_fields.append('body_html')

        if is_new and self.front_uuid:
            self.issue.front_uuid = self.front_uuid

        self.old_save(force_insert, force_update, using, update_fields)


class _Project(Hashable, FrontEditable):
    body_html = models.TextField(blank=True, null=True)

    class Meta:
        abstract = True

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):

        if not update_fields or 'body' in update_fields:
            self.body_html = html_content(self) if self.body else ''
            if update_fields:
                update_fields.append('body_html')

        self.old_save(force_insert, force_update, using, update_fields)

    @property
    def hash(self):
        """
        Hash for this object representing its state at the current time, used to
        know if we have to reset an issue's cache
        """
        return hash((self.name, ))

    def get_related_issues(self):
        """
        Return a list of all issues related to this project
        """
        return core_models.Issue.objects.filter(cards__column__project=self)

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'project_number': self.number,
        }

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_absolute_url(self):
        from gim.front.repository.board.views import BoardView
        return reverse_lazy('front:repository:%s' % BoardView.url_name, kwargs={
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'board_mode': 'project',
            'board_key': self.number,
        }) + '?sort=position&direction=asc'

    def get_summary_url(self):
        if self.number:
            from gim.front.repository.board.views import ProjectSummaryView
            return self.get_view_url(ProjectSummaryView.url_name)
        else:
            from gim.front.repository.board.views import NewProjectSummaryView
            kwargs = self.get_reverse_kwargs()
            del kwargs['project_number']
            kwargs['project_id'] = self.pk
        return reverse_lazy('front:repository:%s' % NewProjectSummaryView.url_name, kwargs=kwargs)

    def get_edit_url(self):
        from gim.front.repository.board.views import ProjectEditView
        return self.get_view_url(ProjectEditView.url_name)

    def get_delete_url(self):
        from gim.front.repository.board.views import ProjectDeleteView
        return self.get_view_url(ProjectDeleteView.url_name)

    def get_create_column_url(self):
        from gim.front.repository.board.views import ColumnCreateView
        return self.get_view_url(ColumnCreateView.url_name)


class _Column(Hashable, FrontEditable):
    class Meta:
        abstract = True

    @property
    def hash(self):
        """
        Hash for this object representing its state at the current time, used to
        know if we have to reset an issue's cache
        """
        return hash((self.name, self.position, ))

    def get_related_issues(self):
        """
        Return a list of all issues related to this column
        """
        return core_models.Issue.objects.filter(cards__column=self)

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.project.repository.owner.username,
            'repository_name': self.project.repository.name,
            'project_number': self.project.number,
            'column_id': self.pk,
        }

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_absolute_url(self):
        from gim.front.repository.board.views import BoardProjectColumnView
        return reverse_lazy('front:repository:%s' % BoardProjectColumnView.url_name, kwargs={
            'owner_username': self.project.repository.owner.username,
            'repository_name': self.project.repository.name,
            'board_mode': 'project',
            'board_key': self.project.number,
            'column_key': self.pk,
        }) + '?sort=position&direction=asc'

    def get_edit_url(self):
        from gim.front.repository.board.views import ColumnEditView
        return self.get_view_url(ColumnEditView.url_name)

    def get_info_url(self):
        from gim.front.repository.board.views import ColumnInfoView
        return self.get_view_url(ColumnInfoView.url_name)

    def get_delete_url(self):
        from gim.front.repository.board.views import ColumnDeleteView
        return self.get_view_url(ColumnDeleteView.url_name)

    def get_can_move_url(self):
        from gim.front.repository.board.views import ColumnCanMoveView
        return self.get_view_url(ColumnCanMoveView.url_name)

    def get_move_url(self):
        from gim.front.repository.board.views import ColumnMoveView
        return self.get_view_url(ColumnMoveView.url_name)

    def get_create_note_url(self):
        from gim.front.repository.board.views import CardNoteCreateView
        return self.get_view_url(CardNoteCreateView.url_name)


class _Card(Hashable, FrontEditable):
    note_html = models.TextField(blank=True, null=True)

    class Meta:
        abstract = True

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):

        if self.type == self.CARDTYPE.NOTE:
            if not update_fields or 'note' in update_fields:
                self.note_html = html_content(self, 'note', force=True) if self.note else ''
                if update_fields:
                    update_fields.append('note_html')

        self.old_save(force_insert, force_update, using, update_fields)

    @property
    def hash(self):
        """
        Hash for this object representing its state at the current time, used to
        know if we have to reset an issue's cache
        """
        return hash((self.column_id, self.position, ))

    def get_related_issues(self):
        """
        Return a list of all issues related to this card (ie only one!)
        """
        return core_models.Issue.objects.filter(cards=self)

    def get_reverse_kwargs(self):
        """
        Return the kwargs to use for "reverse"
        """
        return {
            'owner_username': self.repository.owner.username,
            'repository_name': self.repository.name,
            'project_number': self.column.project.number,
            'card_pk': self.pk,
        }

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_absolute_url(self):
        from gim.front.repository.board.views import CardNoteView
        return self.get_view_url(CardNoteView.url_name)

    def get_edit_url(self):
        from gim.front.repository.board.views import CardNoteEditView
        return self.get_view_url(CardNoteEditView.url_name)

    def get_delete_url(self):
        from gim.front.repository.board.views import CardNoteDeleteView
        return self.get_view_url(CardNoteDeleteView.url_name)


class Hash(lmodel.RedisModel):

    database = get_main_limpyd_database()

    type = lfields.InstanceHashField(indexable=True)
    obj_id = lfields.InstanceHashField(indexable=True)
    hash = lfields.InstanceHashField()

    @classmethod
    def get_or_connect(cls, **kwargs):
        """Manage the case where we have more than one entry...We should not, but still """
        try:
            return super(Hash, cls).get_or_connect(**kwargs)
        except ValueError:

            hashes = Hash.collection(**kwargs).instances()[1:]
            for hash in hashes:
                hash.delete()

            # It should be ok. If not, we have another problem, so we let it raises
            return super(Hash, cls).get_or_connect(**kwargs)
