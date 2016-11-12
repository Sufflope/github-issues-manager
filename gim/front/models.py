# -*- coding: utf-8 -*-

from collections import defaultdict, Counter, OrderedDict
from operator import attrgetter, itemgetter
from threading import local
import json
import re

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.urlresolvers import reverse, reverse_lazy
from django.db import models
from django.db.models import ForeignKey, FieldDoesNotExist
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.template import loader, Context
from django.template.defaultfilters import date as convert_date, escape
from django.utils.dateformat import format
from django.utils.functional import cached_property

from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from pymdownx.github import GithubExtension

from limpyd import model as lmodel, fields as lfields

from gim.core import models as core_models, get_main_limpyd_database
from gim.core.models.base import GithubObject
from gim.core.utils import contribute_to_model, cached_method

from gim.events.models import EventPart

from gim.subscriptions import models as subscriptions_models

from gim.ws import publisher


thread_data = local()


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
        return self.get_view_url('home')

    def get_view_url(self, url_name):
        return reverse_lazy('front:repository:%s' % url_name, kwargs=self.get_reverse_kwargs())

    def get_create_issue_url(self):
        return self.get_view_url('issue.create')

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

contribute_to_model(_Repository, core_models.Repository, {'delete'}, {'delete'})


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

contribute_to_model(_LabelType, core_models.LabelType)


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

contribute_to_model(_Label, core_models.Label, {'defaults_create_values'})


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

contribute_to_model(_Milestone, core_models.Milestone, {'defaults_create_values'})


class _Issue(Hashable, FrontEditable):
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
            hashable_fields += ('base_sha', 'head_sha', 'merged')
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
            hash_values += (commits_part, )

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
    def all_commits(self, include_deleted):
        qs = self.related_commits.select_related('commit__author',
                                                 'commit__committer',
                                                 'commit__repository__owner'
                                ).order_by('commit__authored_at', 'commit__committed_at')
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
            self._all_entry_points = list(self.pr_comments_entry_points
                                .annotate(nb_comments=models.Count('comments'))
                                .filter(nb_comments__gt=0)
                                .select_related('user', 'repository__owner')
                                .prefetch_related('comments__user'))
        return self._all_entry_points

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

        activity.sort(key=attrgetter('created_at'))

        if self.is_pull_request:
            activity = GroupedCommits.group_in_activity(activity)
            activity = GroupedPullRequestComments.group_in_activity(activity)

        return activity

    def get_sorted_entry_points(self):
        for entry_point in self.all_entry_points:
            entry_point.last_created = list(entry_point.comments.all())[-1].created_at
        return sorted(self.all_entry_points, key=attrgetter('last_created'))

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
    def _comments_count_by_path(self):
        return Counter(
            self.pr_comments.select_related('entry_point')
                            .values_list('entry_point__path', flat=True)
        )

    @cached_property
    def files_with_comments_count(self):
        counts = self._comments_count_by_path
        files = []
        for file in self.files.all():
            file.nb_comments = counts.get(file.path, 0)
            files.append(file)
        return files

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

contribute_to_model(_Issue, core_models.Issue, {'defaults_create_values'})


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


class _Commit(models.Model):
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
            self._all_entry_points = list(self.commit_comments_entry_points
                                .annotate(nb_comments=models.Count('comments'))  # cannot exclude wating_deleted for now
                                .filter(nb_comments__gt=0)
                                .select_related('user', 'repository__owner')
                                .prefetch_related('comments__user'))
        return self._all_entry_points

    @cached_property
    def _comments_count_by_path(self):
        return Counter(
            self.commit_comments.select_related('entry_point')
                                .values_list('entry_point__path', flat=True)
        )

    @cached_property
    def files_with_comments_count(self):
        counts = self._comments_count_by_path
        files = []
        for file in self.files.all():
            file.nb_comments = counts.get(file.path, 0)
            files.append(file)
        return files

    @cached_property
    def count_global_comments(self):
        return self._comments_count_by_path.get(None, 0)

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

contribute_to_model(_Commit, core_models.Commit)


class _WaitingSubscription(models.Model):
    class Meta:
        abstract = True

    def can_add_again(self):
        """
        Return True if the user can add the repository again (it is allowed if
        the state is FAILED)
        """
        return self.state == subscriptions_models.WAITING_SUBSCRIPTION_STATES.FAILED

contribute_to_model(_WaitingSubscription, subscriptions_models.WaitingSubscription)


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

contribute_to_model(_IssueComment, core_models.IssueComment, {'defaults_create_values'})


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

contribute_to_model(_PullRequestComment, core_models.PullRequestComment, {'defaults_create_values'})


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

contribute_to_model(_CommitComment, core_models.CommitComment, {'defaults_create_values'})


class _GithubNotification(models.Model):
    class Meta:
        abstract = True

    def get_edit_url(self):
        return reverse_lazy('front:github-notifications:edit', kwargs={'notif_id': self.pk})

contribute_to_model(_GithubNotification, core_models.GithubNotification)


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
        from gim.front.repository.board.views import ProjectSummaryView
        return self.get_view_url(ProjectSummaryView.url_name)

    def get_edit_url(self):
        from gim.front.repository.board.views import ProjectEditView
        return self.get_view_url(ProjectEditView.url_name)

    def get_delete_url(self):
        from gim.front.repository.board.views import ProjectDeleteView
        return self.get_view_url(ProjectDeleteView.url_name)

    def get_create_column_url(self):
        from gim.front.repository.board.views import ColumnCreateView
        return self.get_view_url(ColumnCreateView.url_name)

contribute_to_model(_Project, core_models.Project, {'save', 'defaults_create_values'}, {'save'})


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

contribute_to_model(_Column, core_models.Column, {'defaults_create_values'})


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


contribute_to_model(_Card, core_models.Card, {'save', 'defaults_create_values'}, {'save'})


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


def unify_messages(store, topic, *args, **kwargs):
    """Keep only the last message for a topic/instance each time we receive one in the store"""

    store['__order__'] = store.get('__order__', 0) + 1

    message = {
        'message': {
            'topic': topic,
            'args': args,
            'kwargs': kwargs,
        },
        'order': store['__order__']
    }

    if 'model' in kwargs and 'id' in kwargs:
        model, pk = kwargs['model'], kwargs['id']
        store.setdefault('__instances__', {}).setdefault(model, {})

        # If it's the first time, we register the 'previous hash'
        if pk not in store.setdefault('__hashes__', {}).setdefault(model, {}):
            # Store the previous hash, or None
            store['__hashes__'][model][pk] = kwargs.get('previous_hash', None)

        # Else, we check if we have the same hash as the original one
        elif store['__hashes__'][model][pk] is not None and kwargs.get('hash') == store['__hashes__'][model][pk]:
            # In this case we skip the message, because we're back to the original
            message = None
            # And we don't send the stored message either
            if pk in store['__instances__'][model]:
                del store['__instances__'][model][pk]

        # We are allowed to store the message (because no hash or the hash is not the original one)
        if message:
            store['__instances__'][model].setdefault(pk, {})[topic] = message

    else:
        # Not an instance, we store the message (but avoid duplication)
        store.setdefault('__others__', {})[hash(frozenset(message['message']))] = message


def send_unified_messages(store):
    if not store:
        return

    messages = []
    for model in store.get('__instances__', {}):
        for pk in store['__instances__'][model]:
            messages.extend(store['__instances__'][model][pk].values())
    messages.extend(store.get('__others__', {}).values())

    for container in sorted(messages, key=itemgetter('order')):
        message = container['message']
        publisher.publish(
            topic=message['topic'],
            repository_id=message['kwargs'].pop('repository_id', None),
            *message['args'],
            **message['kwargs']
        )


PUBLISHABLE = {
    core_models.IssueComment: {
        'self': False,
        'parents': [
            ('Issue', 'issue', lambda self: [self.issue_id], None),
        ],
    },
    core_models.PullRequestComment: {
        'self': False,
        'parents': [
            ('Issue', 'issue', lambda self: [self.issue_id], None),
        ],
    },
    core_models.CommitComment: {
        'self': False,
        'parents': [
            ('Issue', 'issues',
             lambda self: self.commit.issues.all().select_related('commit', 'repository__owner'),
             lambda self, issue: {'url': str(self.get_absolute_url_for_issue(issue))}
             ),
        ],
    },
    # core_models.Commit: {
    #     'self': False,
    #     'parents': [
    #         ('Issue', 'issues',
    #          lambda self: self.issues.all().select_related('repository__owner'),
    #          lambda self, issue: {'url': self.get_absolute_url_for_issue(issue)}
    #          ),
    #     ],
    # },
    core_models.Issue: {
        'self': True,
        'pre_publish_action': lambda self: setattr(self, 'signal_hash_changed', self.hash_changed()),
        'more_data': lambda self: {'is_pr': self.is_pull_request, 'number': self.number}
    },
    core_models.Card: {
        'self': True,
        'pre_publish_action': lambda self: setattr(self.issue, 'signal_hash_changed', self.issue.hash_changed()) if self.issue_id else None,
        'more_data': lambda self: {
            'project_number': self.column.project.number,
            'column_id': self.column_id,
            'position': self.position,
            'url': self.get_absolute_url(),
            'issue': {  # used by the front if the issue needs to be fetched when the card changed, for example a change of column
                        # model and front_uuid will be set by the front
                'id': self.issue.id,
                'url': str(self.issue.get_websocket_data_url()),
                'hash': self.issue.saved_hash,
                'is_new': getattr(self.issue, 'is_new', False),
                'is_pr': self.issue.is_pull_request,
                'number': self.issue.number,
            } if self.issue_id else None,
        }
    },
    core_models.Column: {
        'self': True,
        'more_data': lambda self: {
            'project_number': self.project.number,
            'position': self.position,
            'name': self.name,
            'url': str(self.get_absolute_url()),
        }
    },
    core_models.Project: {
        'self': True,
        'more_data': lambda self: {
            'name': self.name,
            'number': self.number,
            'url': str(self.get_absolute_url()),
            'nb_columns': self.columns.count(),
        }
    },
    # core_models.Repository: {
    #     'self': True,
    # },
}
PUBLISHABLE_MODELS = tuple(PUBLISHABLE.keys())


def publish_update(instance, message_type, extra_data=None):
    """Publish a message when something happen to an instance."""

    conf = PUBLISHABLE[instance.__class__]

    try:
        previous_saved_hash = instance.saved_hash
    except Exception:
        previous_saved_hash = None

    if conf.get('pre_publish_action'):
        conf['pre_publish_action'](instance)

    # try:
    #     from pprint import pformat
    #     extra_data['hashable_values'] = pformat(instance.hash_values)
    # except Exception:
    #     pass
    # try:
    #     extra_data["github_status"] = instance.get_github_status_display()
    # except Exception:
    #     pass

    base_data = {
        'model': str(instance.model_name),
        'id': str(instance.pk),
    }
    if 'more_data' in conf:
        base_data.update(conf['more_data'](instance))
    if extra_data:
        base_data.update(extra_data)

    try:
        base_data['hash'] = instance.saved_hash
        if previous_saved_hash != base_data['hash']:
            base_data['previous_hash'] = previous_saved_hash
    except Exception:
        pass

    if isinstance(instance, core_models.Repository):
        repository_id = instance.pk
    else:
        repository_id = getattr(instance, 'repository_id', None)

    if getattr(instance, 'front_uuid', None):
        base_data['front_uuid'] = str(instance.front_uuid)

    try:
        if hasattr(instance, 'get_websocket_data_url'):
            base_data['url'] = str(instance.get_websocket_data_url())
        else:
            base_data['url'] = str(instance.get_absolute_url())
    except Exception:
        pass

    parents = [
        (
            model_name,
            str(getattr(obj, 'pk', obj)),
            field_name,
            dict(base_data, **more_data(instance, obj)) if more_data else base_data
        )
        for model_name, field_name, get_objects, more_data
        in conf.get('parents', [])
        for obj in get_objects(instance)
    ]

    to_publish = [
        (
            'front.Repository.%(repository_id)s.model.%(message_type)s.isRelatedTo.%(parent_model)s.%(parent_id)s',
            'front.model.%(message_type)s.isRelatedTo.%(parent_model)s.%(parent_id)s',
            dict(
                parent_model=parent_model,
                parent_id=parent_id,
                parent_field=parent_field,
                **parent_data
            )
        )
        for (parent_model, parent_id, parent_field, parent_data)
        in parents
    ]

    if conf.get('self'):
        to_publish += [
            (
                'front.Repository.%(repository_id)s.model.%(message_type)s.is.%(model)s.%(id)s',
                'front.model.%(message_type)s.is.%(model)s.%(id)s',
                base_data
            )
        ]

    for topic_with_repo, topic_without_repo, data in to_publish:
        message_repository_id = repository_id
        if data.get('parent_model', 'None') == 'Repository' and data['parent_field'] == 'repository':
            message_repository_id = data['parent_id']

        topic = topic_with_repo if message_repository_id else topic_without_repo

        publisher.publish(
            topic=topic % dict(
                message_type=message_type, repository_id=message_repository_id, **data),
            repository_id=message_repository_id,
            **data
        )

    # If we published about an issue that have some notifications, publish the notifications
    issue_to_notif = None
    if isinstance(instance, core_models.Issue):
        issue_to_notif = instance
    else:
        for topic_with_repo, topic_without_repo, data in to_publish:
            if data.get('parent_model') == 'Issue':
                try:
                    issue_to_notif = core_models.Issue.objects.get(id=data['parent_id'])
                except core_models.Issue.DoesNotExist:
                    pass
    if issue_to_notif:
        issue_to_notif.publish_notifications()

    # No we can remove the front_uuid field and the is_new flag
    if hasattr(instance, 'is_new'):
        del instance.is_new
    if getattr(instance, 'front_uuid') and not getattr(instance, 'skip_reset_front_uuid', False):
        instance.front_uuid = None
        if instance.pk and FrontEditable.isinstance(instance):
            instance.clear_front_uuid()


@receiver(post_save, dispatch_uid="publish_github_updated")
def publish_github_updated(sender, instance, created, **kwargs):
    """Publish a message each time a github object is created/updated."""

    # Only for objects we care about
    if not isinstance(instance, PUBLISHABLE_MODELS):
        return

    # That we got from github
    if not getattr(instance, 'skip_status_check_to_publish', False) and \
            getattr(instance, 'github_status', instance.GITHUB_STATUS_CHOICES.FETCHED) != instance.GITHUB_STATUS_CHOICES.FETCHED:
        return

    # Only if we didn't specifically say to not publish
    if getattr(thread_data, 'skip_publish', False):
        return
    if getattr(instance, 'skip_publish', False):
        return

    # Ignore some cases
    update_fields = kwargs.get('update_fields', [])
    if update_fields:

        # Remove fields that are not real updates
        update_fields = set([
            f for f in update_fields
            if f not in ('front_uuid', ) and
                not f.endswith('fetched_at') and
                not f.endswith('etag')
        ])

        # If no field left, we're good
        if not update_fields:
            return

        # If only status and updated date, we're good
        if update_fields == {'github_status', 'updated_at'}:
            return

    extra_data = {}
    if created or getattr(instance, 'is_new', False):
        extra_data['is_new'] = True

    # extra_data['updated_fields'] = list(update_fields or [])

    publish_update(instance, 'updated', extra_data)


@receiver(post_delete, dispatch_uid="publish_github_deleted")
def publish_github_deleted(sender, instance, **kwargs):
    """Publish a message each time a github object is deleted."""

    # Only for objects we care about
    if not isinstance(instance, PUBLISHABLE_MODELS):
        return

    # Only if we didn't specifically say to not publish
    if getattr(thread_data, 'skip_publish', False):
        return

    # That we are not currently deleting before creating from github
    if getattr(instance, 'github_status', None) == instance.GITHUB_STATUS_CHOICES.WAITING_CREATE:
        return

    publish_update(instance, 'deleted')


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
                        core_models.Project,
                        core_models.Column,
                        core_models.Card,
                        core_models.Issue
                      )):
        return

    # Only if the data is fresh from github
    if hasattr(instance, 'github_status') and instance.github_status != instance.GITHUB_STATUS_CHOICES.FETCHED:
        return

    if not hasattr(instance, 'signal_hash_changed'):
        instance.signal_hash_changed = instance.hash_changed(force_update=created)

    if not instance.signal_hash_changed:
        return

    from gim.core.tasks.issue import UpdateIssueCacheTemplate

    if isinstance(instance, core_models.Issue):
        # if an issue, add a job to update its template
        UpdateIssueCacheTemplate.add_job(instance.id)

    else:
        # if not an issue, add a job to update the templates of all related issues
        for issue_id in instance.get_related_issues().values_list('id', flat=True):
            UpdateIssueCacheTemplate.add_job(issue_id, force_regenerate=1)
