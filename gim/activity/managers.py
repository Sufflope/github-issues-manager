__all__ = [
    'ActivityManager'
]

from django.db.models import Q

from limpyd_jobs.utils import import_class

from gim.core.models import Issue, IssueCommits

from gim.events.models import EventPart
from gim.events.renderers import IssueRendererCollapsableTitleAndBody


class ActivityManager(object):
    """
    The base class defining attributes and methods to get/load/save data from
    and to an activity stream, with one subclasse needed for each type of
    activity.
    All subclasses will be saved in the MAPPING attribute, using the
    code as key, and the subclass as value.
    The goal is to avoid specifying codes in the *Acivity classes, to have
    nothing to do if we add a code (except adding the field in the BaseActivity
    class)
    """
    limpyd_field = None  # field on the limpyd activity object
    related_name = None  # name of the related queryset from the issue point of vue
    model_uri = None  # path of the model storing data (event, comment, commit...)
    model = None  # the model described by model_uri
    date_field = 'created_at'  # the field on the object serving as a date for the score
    pr_only = False  # is this code limited to pull requests

    MAPPING = {}

    @classmethod
    def get_model(cls):
        """
        Compute and save the model based on the model_uri attribute, and return
        it.
        """
        if not cls.model:
            cls.model = import_class(cls.model_uri)
        return cls.model

    @classmethod
    def get_load_queryset(cls):
        """
        Return the default queryset to load objects of the current code. It may
        be overriden in subclasses to add [select|prefetch]_related
        """
        return cls.get_model().objects.exclude(issue__number__isnull=True)

    @classmethod
    def load_object(cls, pk):
        """
        Return an object with the given pk, using the queryset from
        get_load_queryset
        """
        return cls.get_load_queryset().get(pk=pk)

    @classmethod
    def load_objects(cls, pks):
        """
        Load a list of objects using the given list of pk and the queryset from
        get_load_queryset
        """
        return cls.get_load_queryset().filter(pk__in=pks)

    @classmethod
    def get_for_model(cls, model):
        """
        Return the correct ActivityManager class for the given model (a class, not an uri)
        """
        return [c for c in ActivityManager.MAPPING.values() if c.get_model() == model][0]

    @classmethod
    def get_for_model_instance(cls, instance):
        """
        Return the correct ActivityManager class for the given instance
        """
        return cls.get_for_model(instance.__class__)

    @classmethod
    def get_data_queryset(cls, issue):
        """
        Return the default queryset to use to get objects that need to be saved
        in the activity stream. It may be overriden in subclasses to exclude
        unwanted data.
        """
        return getattr(issue, cls.related_name).exclude(issue__number__isnull=True)

    @classmethod
    def is_obj_valid(cls, issue, obj=None, obj_pk=None):
        """
        Return True if the given object can be added in the acitivity stream of
        the given issue
        """
        if obj_pk is None:
            obj_pk = obj.pk
        return cls.get_data_queryset(issue).filter(pk=obj_pk).exists()

    @classmethod
    def get_data(cls, issue):
        """
        Return the data for the given model that need to be saved in the
        activity stream, using the queryset from get_data_queryset.
        The returned data is a list of tuple (pk, date), using the date field
        defined in the "date_field" attribute.
        """
        return cls.get_data_queryset(issue).values_list('pk', cls.date_field)

    @classmethod
    def prepare_data(cls, values):
        """
        Expect a list of tuples, each tuple beging:
        - the pk of an object
        - a date to use as a base for the score
        Return a dict to use with zadds:
        - as key, the data to store (code:pk)
        - as value, the date to use as a score
        """
        return dict(
                (
                    '%s:%s' % (cls.code, pk),
                    float(str(dat).replace('-', '').replace(' ', '').replace(':', ''))
                )
            for pk, dat in values
        )

    @classmethod
    def get_object_date(cls, obj):
        """
        Return the date we want to use for the given object. May be overriden
        for more complex stuff than just getting the "date_field" field
        """
        return getattr(obj, cls.date_field)


class ActivityManagerICE(ActivityManager):
    code = 'ice'
    limpyd_field = 'change_events'
    related_name = 'event_set'
    model_uri = 'gim.events.models.Event'

    NAMES = {
        'mergeable_state': 'mergeable status',
        'mergeable': 'mergeable status',
        'label_type': 'labels',
        'body': 'description',
    }

    @classmethod
    def _get_event_parts_queryset(cls, issue):
        """
        Method used to return the event_parts allowed to be shown in the
        actitivy stream of the issue, used by get_data_queryset and is_obj_valid
        """
        return EventPart.objects.filter(
                event__issue_id=issue.id,
            ).exclude(
                field__in=issue.RENDERER_IGNORE_FIELDS
            )

    @classmethod
    def get_data_queryset(cls, issue):
        """
        Filter to return only events with parts we want to be shown
        """
        event_ids = set(cls._get_event_parts_queryset(issue).values_list('event_id', flat=True))
        qs = super(ActivityManagerICE, cls).get_data_queryset(issue)
        return qs.filter(Q(id__in=event_ids) | Q(is_update=False))

    @classmethod
    def is_obj_valid(cls, issue, obj=None, obj_pk=None):
        """
        Bypass full queryset to test if the event must be shown in the activity
        stream
        """
        if obj_pk is None:
            obj_pk = obj.pk
        else:
            obj = cls.get_model().objects.get(pk=obj_pk)
        # creations are valid
        if not obj.is_update:
            return True
        # for updates, check parts
        return cls._get_event_parts_queryset(issue).filter(event_id=obj_pk).exists()

    @classmethod
    def get_load_queryset(cls):
        """
        Prefetch issue, repository, and parts of events
        """
        qs = super(ActivityManagerICE, cls).get_load_queryset()
        return qs.select_related('issue__user', 'issue__repository__owner'
                                                    ).prefetch_related('parts')

    @classmethod
    def load_objects(cls, pks):
        """
        Prepare display of updated parts
        """
        objs = list(super(ActivityManagerICE, cls).load_objects(pks))
        for obj in objs:
            obj.renderer_ignore_fields = Issue.RENDERER_IGNORE_FIELDS
            obj.updated_parts = set([cls.NAMES.get(p.field, p.field)
                                    for p in obj.parts.all()
                                    if p.field not in obj.renderer_ignore_fields])
            obj._renderer = IssueRendererCollapsableTitleAndBody(obj)
        return objs


class ActivityManagerICO(ActivityManager):
    code = 'ico'
    limpyd_field = 'issue_comments'
    related_name = 'comments'
    model_uri = 'gim.core.models.IssueComment'

    @classmethod
    def get_load_queryset(cls):
        """
        Prefetch issue, repository, and author of the comment
        """
        qs = super(ActivityManagerICO, cls).get_load_queryset()
        return qs.select_related('issue__user', 'issue__repository__owner', 'user')


class ActivityManagerIEV(ActivityManager):
    code = 'iev'
    limpyd_field = 'issue_events'
    related_name = 'events'
    model_uri = 'gim.core.models.IssueEvent'

    @classmethod
    def get_data_queryset(cls, issue):
        """
        Exclude the event about referenced commits without sha, and ones about
        mentioning/subscribing
        """
        qs = super(ActivityManagerIEV, cls).get_data_queryset(issue)
        return qs.exclude(Q(issue__number__isnull=True)
                          |
                          Q(event='referenced', commit_sha__isnull=True)
                          |
                          Q(event__in=('mentioned', 'subscribed', 'labeled',
                                       'unlabeled', 'assigned', 'unassigned',
                                       'milestoned', 'demilestoned', 'renamed'))
                        )

    @classmethod
    def get_load_queryset(cls):
        """
        Prefetch issue, repository, and author of the event
        """
        qs = super(ActivityManagerIEV, cls).get_load_queryset()
        return qs.select_related('issue__user', 'issue__repository__owner', 'user')


class ActivityManagerPCO(ActivityManager):
    code = 'pco'
    limpyd_field = 'pr_comments'
    related_name = 'pr_comments'
    model_uri = 'gim.core.models.PullRequestComment'
    pr_only = True

    @classmethod
    def get_load_queryset(cls):
        """
        Prefetch issue, repository, and author of the comment
        """
        qs = super(ActivityManagerPCO, cls).get_load_queryset()
        return qs.select_related('issue__user', 'issue__repository__owner', 'user')


class ActivityManagerPCI(ActivityManager):
    """
    Specific case: we want to store the relation between issue and commit
    """
    code = 'pci'
    limpyd_field = 'pr_commits'
    pr_only = True
    # automatic through table
    related_name = None
    model_uri = None
    model = IssueCommits
    date_field = 'commit__committed_at'

    @classmethod
    def is_obj_valid(cls, *args, **kwargs):
        """
        Assum its always valid, as it's a through and we don't have constraints
        """
        return True

    @classmethod
    def get_data_queryset(cls, issue):
        """
        Use our through table, we don't have related_name here
        """
        return cls.get_model().objects.exclude(issue__number__isnull=True).filter(issue=issue)

    @classmethod
    def get_load_queryset(cls):
        """
        Prefetch issue, commit, repository, and author+committer of the commit
        """
        qs = super(ActivityManagerPCI, cls).get_load_queryset()
        return qs.select_related('issue__user', 'issue__repository__owner',
                                        'commit__author', 'commit__committer')

    @classmethod
    def get_object_date(cls, obj):
        """
        Return the date stored on the commit object, not the "through" one
        """
        return obj.commit.committed_at


class ActivityManagerPCC(ActivityManager):
    code = 'pcc'
    limpyd_field = 'commit_comments'
    related_name = None  # no direct link betwwem commit comment and issue
    model_uri = 'gim.core.models.CommitComment'
    pr_only = True

    @classmethod
    def get_data_queryset(cls, issue):
        """
        There is no direct link between a commit comment and an issue, but we
        can use CommitComment => Commit => IssueCommits => Issue
        """
        return cls.get_model().objects.filter(commit__related_commits__issue=issue)

    @classmethod
    def get_load_queryset(cls):
        """
        Prefetch author of the comment, commit and its author, linked issue, and
        its repository, with their owners
        """
        # don't use super as super excludes the issue and we don't have issue here
        return cls.get_model().objects.filter(
            commit__related_commits__issue__isnull=False
            ).select_related(
                'user',
                'repository__user',
                'commit__author',
                'commit__committer',
            ).prefetch_related(
                'commit__related_commits__issue__user',
            )

    @classmethod
    def _link_relations(cls, obj):
        """
        Add issue from the commit relation to the object, and the repository from
        the object, to the issue, to avoid useless sql queries
        """
        # ensure to use "all" to benefit from the prefetch_related in get_load_queryset
        obj.issue = list(obj.commit.related_commits.all())[0].issue
        obj.issue_id = obj.issue.id
        obj.issue._repository_cache = obj.repository

    @classmethod
    def load_object(cls, pk):
        """
        Try to get an issue on which we have the commit linked to this comment
        and add it to the object.
        """
        try:
            obj = cls.get_load_queryset().get(pk=pk)
        except cls.model.DoesNotExist:
            return None
        cls._link_relations(obj)
        return obj

    @classmethod
    def load_objects(cls, pks):
        """
        Load a list of objects using the given list of pk and the queryset from
        get_load_queryset
        """
        objs = cls.get_load_queryset().filter(pk__in=pks)
        for obj in objs:
            cls._link_relations(obj)
        return objs


# automatically register all ActivityManager classes
for manager in ActivityManager.__subclasses__():
    ActivityManager.MAPPING[manager.code] = manager
ActivityManager.all_codes = sorted(ActivityManager.MAPPING.keys())
