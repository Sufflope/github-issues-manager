
from urlparse import urlsplit, parse_qs
from itertools import product
from datetime import datetime, timedelta
from math import ceil
import re

from django.db import models, DatabaseError
from django.db.models import F, Q
from django.contrib.auth.models import AbstractUser
from django.core import validators
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from jsonfield import JSONField

from extended_choices import Choices

from . import GITHUB_HOST
from .ghpool import (parse_header_links, ApiError, ApiNotFoundError, Connection,
                     prepare_fetch_headers)
from .managers import (MODE_ALL, MODE_UPDATE,
                       GithubObjectManager, WithRepositoryManager,
                       IssueCommentManager, GithubUserManager, IssueManager,
                       RepositoryManager, LabelTypeManager,
                       PullRequestCommentManager, IssueEventManager,
                       PullRequestCommentEntryPointManager, CommitManager,
                       PullRequestFileManager, AvailableRepositoryManager)

import username_hack  # force the username length to be 255 chars


class MinDateRaised(Exception):
    pass


GITHUB_STATUS_CHOICES = Choices(
    ('WAITING_CREATE', 1, u'Awaiting creation'),
    ('WAITING_UPDATE', 2, u'Awaiting update'),
    ('WAITING_DELETE', 3, u'Awaiting delete'),
    ('FETCHED', 10, u'Fetched'),
    ('ERROR_CREATE', 21, u'Error while creating'),
    ('ERROR_UPDATE', 22, u'Error while updating'),
    ('ERROR_DELETE', 23, u'Error while deleting'),
    ('ERROR_FETCHED', 30, u'Error while fetching'),
)
GITHUB_STATUS_CHOICES.ALL_WAITING = (GITHUB_STATUS_CHOICES.WAITING_CREATE,
                                     GITHUB_STATUS_CHOICES.WAITING_UPDATE,
                                     GITHUB_STATUS_CHOICES.WAITING_DELETE)
GITHUB_STATUS_CHOICES.ALL_ERRORS = (GITHUB_STATUS_CHOICES.ERROR_CREATE,
                                    GITHUB_STATUS_CHOICES.ERROR_UPDATE,
                                    GITHUB_STATUS_CHOICES.ERROR_DELETE,
                                    GITHUB_STATUS_CHOICES.ERROR_FETCHED)


class GithubObject(models.Model):
    fetched_at = models.DateTimeField(null=True, blank=True)
    github_status = models.PositiveSmallIntegerField(
                                choices=GITHUB_STATUS_CHOICES.CHOICES,
                                default=GITHUB_STATUS_CHOICES.WAITING_CREATE,
                                db_index=True)

    objects = GithubObjectManager()

    GITHUB_STATUS_CHOICES = GITHUB_STATUS_CHOICES

    github_matching = {}
    github_ignore = ()
    github_format = '+json'
    github_edit_fields = {'create': (), 'update': ()}
    github_per_page = {'min': 10, 'max': 100}
    github_date_field = None  # ex ('updated_at', 'updated',   'desc')
                              #      obj field     sort param  direction param

    class Meta:
        abstract = True

    def __str__(self):
        return unicode(self).encode('utf-8')

    def fetch(self, gh, defaults=None, force_fetch=False, parameters=None,
                                                        meta_base_name=None):
        """
        Fetch data from github for the current object and update itself.
        If defined, "defaults" is a dict with values that will be used if not
        found in fetched data.
        The meta_base_name argument is used to get the identifiers to use for
        calling the github api, and the 'fetched_at' field to use for the
        'If-Modified-Since' header and field to updated.
        """
        if meta_base_name:
            identifiers = getattr(self, 'github_callable_identifiers_for_%s' % meta_base_name)
            fetched_at_field = '%s_fetched_at' % meta_base_name
        else:
            identifiers = self.github_callable_identifiers
            fetched_at_field = 'fetched_at'

        request_headers = prepare_fetch_headers(
                    if_modified_since=None if force_fetch else getattr(self, fetched_at_field),
                    github_format=self.github_format)
        response_headers = {}

        try:
            obj = self.__class__.objects.get_from_github(
                gh=gh,
                identifiers=identifiers,
                modes=MODE_ALL,
                defaults=defaults,
                parameters=parameters,
                request_headers=request_headers,
                response_headers=response_headers,
                fetched_at_field=fetched_at_field,
                force_update=force_fetch,
            )

        except ApiError, e:
            if e.response and e.response['code'] == 304:
                # github tell us nothing is new, so we stop all the work here
                return True
            else:
                raise

        if obj is None:
            return False

        self.__dict__.update(obj.__dict__)

        return True

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        """
        By default fetch only the current object. Override to add some _fetch_many
        """
        return self.fetch(gh, force_fetch=force_fetch)

    def _fetch_many(self, field_name, gh, vary=None, defaults=None,
                    parameters=None, remove_missing=True, force_fetch=False,
                    meta_base_name=None, modes=MODE_ALL, max_pages=None,
                    filter_queryset=None):
        """
        Fetch data from github for the given m2m or related field.
        If defined, "vary" is a dict of list of parameters to fetch. For each
        key of this dict, all values of the list will be used as a parameter,
        one after the other. If many keys are in "vary", all combinations will
        be fetched.
        If defined, "defaults" is a dict with values that will be used if not
        found in fetched data.
        By default, the field_name is not only used to know which list to update,
        but also as a base used to know which "metadata" fields to use/update
        (fetched_at, etag, github_callable_identifiers_for_). To use another
        base, simply pass it to the `meta_base_name` argument.
        Mode must be a tuple containing none, one or both of "create" and
        "update". If None is passed, the default is both values.
        """
        field, _, direct, m2m = self._meta.get_field_by_name(field_name)
        if direct:
            # we are on a field of the current model, the objects to create or
            # update are on the model on the other side of the relation
            model = field.related.parent_model
        else:
            # the field is originally defined on the other side of the relation,
            # we have a RelatedObject with the model on the other side of the
            # relation to use to create or update are on the current model
            model = field.model

        if not meta_base_name:
            meta_base_name = field_name

        if modes is None:
            modes = MODE_ALL

        if parameters is None:
            parameters = {}

        identifiers = getattr(self, 'github_callable_identifiers_for_%s' % meta_base_name)

        per_page_parameter = {
            'per_page': parameters.get('per_page', model.github_per_page['max'])
        }

        # prepare headers to add in the request
        min_date = None
        if_modified_since = None
        fetched_at_field = '%s_fetched_at' % meta_base_name

        if not force_fetch:
            if hasattr(self, fetched_at_field):
                # if we have a fetch date, use it
                fetched_at = getattr(self, fetched_at_field)
                if fetched_at:
                    # tell github we have all data since this date
                    if_modified_since = fetched_at
                    # limit to a few items per list when updating a repository
                    # only if per_page not forced
                    if not parameters.get('per_page'):
                        per_page_parameter['per_page'] = model.github_per_page['min']

                    # do we have to check for a min date ?
                    if model.github_date_field:
                        date_field_name, sort, direction = model.github_date_field
                        # sort_param = (parameters or {}).get('sort')
                        # direction_param = (parameters or {}).get('direction')
                        # if (not sort and not sort_param or sort and sort_param == sort)\
                        #     and (not direction and not direction_param or direction and direction_param == direction):
                        if parameters.get('sort') == sort and\
                           parameters.get('direction') == direction:
                            min_date = fetched_at

        request_headers = prepare_fetch_headers(
                    if_modified_since=if_modified_since,
                    github_format=model.github_format)

        def fetch_page_and_next(objs, parameters, min_date):
            """
            Fetch a page of objects with the given parameters, and if github
            tell us there is a "next" page, tell caller to continue fetching by
            returning the parameters for the next page as first return argument
            (or None if no next page).
            Return the etag header of the page as second argument

            """
            response_headers = {}
            etag = None

            page_objs = []

            try:
                page_objs = model.objects.get_from_github(
                    gh=gh,
                    identifiers=identifiers,
                    modes=modes,
                    defaults=defaults,
                    parameters=parameters,
                    request_headers=request_headers,
                    response_headers=response_headers,
                    min_date=min_date,
                    force_update=force_fetch,
                )

            except ApiNotFoundError:
                # no data for this list (issues may be no activated, for example)
                pass
            except ApiError, e:
                if e.response and e.response['code'] in (410, ):
                    # no data for this list (issues may be no activated, for example)
                    pass
                else:
                    raise
            except Exception:
                raise

            etag = response_headers.get('etag') or None

            if not page_objs:
                # no fetched objects, we're done
                return None, etag

            objs += page_objs

            # if we reached the min_date, stop
            if min_date:
                obj_min_date = getattr(page_objs[-1], model.github_date_field[0])
                if obj_min_date and obj_min_date < min_date:
                    raise MinDateRaised(etag)

            # if we have a next page, got fetch it
            if 'link' in response_headers:
                links = parse_header_links(response_headers['link'])
                if 'next' in links and 'url' in links['next']:
                    next_page_parameters = parameters.copy()
                    next_page_parameters.update(
                        dict(
                            (k, v[0]) for k, v in parse_qs(
                                    urlsplit(links['next']['url']).query
                                ).items() if len(v)
                            )
                    )
                    # params for next page
                    return next_page_parameters, etag

            # no more page, stop
            return None, etag

        if not vary:
            # no varying parameter, fetch with an empty set of parameters, with
            # a simple etag field
            parameters_combinations = [({}, '%s_etag' % meta_base_name)]
        else:
            # create all combinations of varying parameters
            vary_keys = sorted(vary)
            parameters_combinations_dicts = [
                dict(zip(vary_keys, prod))
                for prod in product(
                    *(vary[key] for key in vary_keys)
                )
            ]

            # get the etag field for each combination
            parameters_combinations = []
            for dikt in parameters_combinations_dicts:
                etag_varation = '_'.join([
                    '%s_%s' % (k, dikt[k])
                    for k in sorted(dikt)
                ])
                etag_field = '%s_%s_etag' % (meta_base_name, etag_varation)
                parameters_combinations.append((dikt, etag_field))

        # add per_page option
        for parameters_combination, _ in parameters_combinations:
            parameters_combination.update(per_page_parameter)
            if parameters:
                parameters_combination.update(parameters)

        # fetch data for each combination of varying parameters
        etags = {}
        objs = []
        cache_hit = False
        max_pages_raised = False
        something_fetched = False
        for parameters_combination, etag_field in parameters_combinations:

            # use the etag if we have one and we don't have any 200 pages yet
            request_etag = None
            if not force_fetch and hasattr(self, etag_field):
                request_etag = getattr(self, etag_field) or None

                request_headers = prepare_fetch_headers(
                        if_modified_since=if_modified_since,
                        if_none_match=request_etag,
                        github_format=model.github_format)

            try:
                # fetch all available pages
                page = parameters.get('page', 0)
                pages_total = 0
                page_parameters = parameters_combination.copy()
                while True:
                    page += 1
                    page_parameters, page_etag = fetch_page_and_next(objs,
                                                    page_parameters, min_date)
                    pages_total += 1
                    if page == 1:
                        etags[etag_field] = page_etag
                        if request_etag:
                            # clear if-none-match header for pages > 1
                            request_headers = prepare_fetch_headers(
                                if_modified_since=if_modified_since,
                                if_none_match=None,
                                github_format=model.github_format)

                    if page_parameters is None:
                        break

                    if max_pages and pages_total >= max_pages:
                        max_pages_raised = True
                        break

            except MinDateRaised, e:
                etags[etag_field] = e.args[0]
                cache_hit = True

            except ApiError, e:
                if e.response and e.response['code'] == 304:
                    # github tell us nothing is new for this combination
                    cache_hit = True
                    continue
                else:
                    raise

            # at least we fetched something
            something_fetched = True

        # now update the list with created/updated objects
        if something_fetched:
            # but only if we had all fresh data !
            started_at_first_page = parameters.get('page', 1) in (0, 1, None)
            do_remove = (remove_missing
                     and not cache_hit
                     and modes == MODE_ALL
                     and not max_pages_raised
                     and started_at_first_page
                )
            save_etags_and_fetched_at = started_at_first_page
            self.update_related_field(field_name,
                                      [obj.id for obj in objs],
                                      do_remove=do_remove,
                                      save_etags_and_fetched_at=save_etags_and_fetched_at,
                                      etags=etags,
                                      fetched_at_field=fetched_at_field,
                                      filter_queryset=filter_queryset)

        # we return the number of fetched objects
        if not objs:
            return 0
        else:
            return len(objs)

    def update_related_field(self, field_name, ids, do_remove=True,
                                save_etags_and_fetched_at=True, etags=None,
                                fetched_at_field=None, filter_queryset=None):
        """
        For the given field name, with must be a m2m or the reverse side of
        a m2m or a fk, use the given list of ids as the lists of ids of all the
        objects that must be linked.
        Objects that were linked but not in the given list will be removed from
        the relation, or deleted if the relation has a non-nullable link.
        New objects will be simple added to the relation.
        """
        instance_field = getattr(self, field_name)

        count = {'removed': 0, 'added': 0}

        # guess whitch relations to add and whicth to delete
        existing_queryset = instance_field
        if filter_queryset:
            existing_queryset = instance_field.filter(filter_queryset)
        existing_ids = set(existing_queryset.values_list('id', flat=True))
        fetched_ids = set(ids or [])

        # if some relations are not here, remove them
        to_remove = existing_ids - fetched_ids
        if do_remove and to_remove:
            count['removed'] = len(to_remove)
            # if FK, only objects with nullable FK have a clear method, so we
            # only clear if the model allows us to
            if hasattr(instance_field, 'remove'):
                # The relation itself can be removed, we remove it but we keep
                # the original object
                # Example: a user is not anymore a collaborator, we keep the
                # the user but remove the relation user <-> repository
                try:
                    instance_field.remove(*to_remove)
                except DatabaseError, e:
                    # sqlite limits the vars passed in a request to 999
                    # In this case, we loop on the data by slice of 950 obj to remove
                    if u'%s' % e != 'too many SQL variables':
                        raise
                    per_iteration = 950  # do not use 999 has we may have other vars for internal django filter
                    to_remove = list(to_remove)
                    iterations = int(ceil(len(to_remove) / float(per_iteration)))
                    for iteration in range(0, iterations):
                        instance_field.remove(*to_remove[iteration * per_iteration:(iteration + 1) * per_iteration])
            else:
                # The relation cannot be removed, because the current object is
                # a non-nullable fk of the other objects. In this case we are
                # sure the object is fully deleted on the github side, or
                # attached to another object, but we don't care here, so we
                # delete the objects.
                # Example: a milestone of a repository is not fetched via
                # fetch_milestones? => we know it's deleted
                to_delete_queryset = instance_field.model.objects.filter(id__in=to_remove)
                if filter_queryset:
                    to_delete_queryset = to_delete_queryset.filter(filter_queryset)
                to_delete_queryset.delete()

        # if we have new relations, add them
        to_add = fetched_ids - existing_ids
        if to_add:
            count['added'] = len(to_add)
            try:
                instance_field.add(*to_add)
            except DatabaseError, e:
                # sqlite limits the vars passed in a request to 999
                # In this case, we loop on the data by slice of 950 obj to add
                if u'%s' % e != 'too many SQL variables':
                    raise
                per_iteration = 950  # do not use 999 has we may have other vars for internal django filter
                to_add = list(to_add)
                iterations = int(ceil(count['added'] / float(per_iteration)))
                for iteration in range(0, iterations):
                    instance_field.add(*to_add[iteration * per_iteration:(iteration + 1) * per_iteration])

        # check if we have something to save on the main object
        update_fields = []

        if save_etags_and_fetched_at:
            all_field_names = self._meta.get_all_field_names()
            # can we save a fetch date ?
            if not fetched_at_field:
                fetched_at_field = '%s_fetched_at' % field_name
            setattr(self, fetched_at_field, datetime.utcnow())
            if fetched_at_field in all_field_names:
                update_fields.append(fetched_at_field)

            # do we have etags to save ?
            if etags:
                for etag_field, etag in etags.items():
                    setattr(self, etag_field, etag)
                    if etag_field in all_field_names:
                        update_fields.append(etag_field)

        # save main object if needed
        if update_fields:
            self.save(update_fields=update_fields, force_update=True)

        # return count of added and removed data
        return count

    def dist_delete(self, gh):
        """
        Delete the object on the github side, then delete it on our side.
        """
        identifiers = self.github_callable_identifiers
        gh_callable = self.__class__.objects.get_github_callable(gh, identifiers)
        gh_callable.delete()
        self.delete()

    def dist_edit(self, gh, mode, fields=None, values=None):
        """
        Edit the object on the github side. Mode can be 'create' or 'update' to
        do the matching action on Github.
        Field sends are defined in github_edit_fields, and the url is defined
        by github_callable_identifiers or github_callable_create_identifiers
        The new/updated object is returned
        """
        # check mode
        if mode not in ('create', 'update'):
            raise Exception('Invalid mode for dist_edit')

        # get fields to send
        if not fields:
            fields = self.github_edit_fields[mode]

        # get data to send
        data = {}

        for field_name in fields:
            if isinstance(field_name, tuple):
                key, field_name = field_name
            else:
                key = field_name

            if values and key in values:
                data[key] = values[key]
            else:
                if '__' in field_name:
                    field_name, subfield_name = field_name.split('__')
                    field, _, direct, is_m2m = self._meta.get_field_by_name(field_name)
                    relation = getattr(self, field_name)
                    if is_m2m or not direct:
                        # we have a many to many relationship
                        data[key] = list(relation.values_list(subfield_name, flat=True))
                    else:
                        # we have a foreignkey
                        data[key] = None if not relation else getattr(relation, subfield_name)
                else:
                    # it's a direct field
                    data[key] = getattr(self, field_name)
                    if isinstance(data[field_name], datetime):
                        data[key] = data[field_name].isoformat()

        # prepare the request
        identifiers = self.github_callable_identifiers if mode == 'update' else self.github_callable_create_identifiers
        gh_callable = self.__class__.objects.get_github_callable(gh, identifiers)
        method = getattr(gh_callable, 'patch' if mode == 'update' else 'post')
        request_headers = prepare_fetch_headers(github_format=self.github_format)

        # make the request and get fresh data for the object
        result = method(request_headers=request_headers, **data)

        # get defaults to update the data with fresh data we just got
        defaults = self.defaults_create_values()

        # if we are in create mode, we delete the object to recreate it with
        # the data we just got
        if mode == 'create':
            self.delete()

        # update the object on our side
        return self.__class__.objects.create_or_update_from_dict(
                                                            data=result,
                                                            defaults=defaults)


class GithubObjectWithId(GithubObject):
    github_id = models.PositiveIntegerField(unique=True, null=True, blank=True)

    github_matching = dict(GithubObject.github_matching)
    github_matching.update({
        'id': 'github_id'
    })
    github_ignore = GithubObject.github_ignore + ('github_id', )
    github_identifiers = {'github_id': 'github_id'}

    class Meta:
        abstract = True


class Team(GithubObjectWithId):
    organization = models.ForeignKey('GithubUser', related_name='org_teams')
    name = models.TextField()
    slug = models.TextField()
    permission = models.CharField(max_length=5)
    repositories = models.ManyToManyField('Repository', related_name='teams')
    repositories_fetched_at = models.DateTimeField(blank=True, null=True)
    repositories_etag = models.CharField(max_length=64, blank=True, null=True)

    objects = GithubObjectManager()

    github_ignore = GithubObjectWithId.github_ignore + ('members_url',
                    'repositories_url', 'url', 'repos_count', 'members_count')

    github_per_page = {'min': 100, 'max': 100}

    class Meta:
        ordering = ('name', )

    def __unicode__(self):
        return u'%s - %s' % (self.organization.username, self.name)

    @property
    def github_url(self):
        return self.organization.github_organization_url + '/teams/' + self.name

    @property
    def github_callable_identifiers(self):
        return [
            'teams',
            self.github_id,
        ]

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        super(Team, self).fetch_all(gh, force_fetch, **kwargs)
        try:
            self.fetch_repositories(gh, force_fetch=force_fetch)
        except ApiNotFoundError:
            # we may have no rights
            pass

    @property
    def github_callable_identifiers_for_repositories(self):
        return self.github_callable_identifiers + [
            'repos',
        ]

    def fetch_repositories(self, gh, force_fetch=False, parameters=None):

        # force fetching 100 orgs by default, as we cannot set "github_per_page"
        # for the whole Repository class
        if not parameters:
            parameters = {}
        if 'per_page' not in parameters:
            parameters['per_page'] = 100

        return self._fetch_many('repositories', gh,
                                force_fetch=force_fetch,
                                parameters=parameters)


AVAILABLE_PERMISSIONS = Choices(
    ('pull', 'pull', 'Simple user'),  # can read, create issues
    ('push', 'push', 'Collaborator'),  # can push, manage issues
    ('admin', 'admin', 'Admin'),  # can admin, push, manage issues
)


class AvailableRepository(GithubObject):
    """
    Will host repositories a user can access ("through" table for user.available_repositories)
    """
    user = models.ForeignKey('GithubUser', related_name='available_repositories_set')
    repository = models.ForeignKey('Repository')
    permission = models.CharField(max_length=5, choices=AVAILABLE_PERMISSIONS.CHOICES)
    # cannot use another FK to GithubUser as its a through table :(
    organization_id = models.PositiveIntegerField(blank=True, null=True)
    organization_username = models.CharField(max_length=255, blank=True, null=True)

    objects = AvailableRepositoryManager()

    github_identifiers = {
        'repository__github_id': ('repository', 'github_id'),
        'user__username': ('user', 'username'),
    }

    class Meta:
        unique_together = (
            ('user', 'repository'),
        )
        ordering = ('organization_username', 'repository',)

    def __unicode__(self):
        return '%s can "%s" %s (org: %s)' % (self.user, self.permission, self.repository, self.organization_username)


class GithubUser(GithubObjectWithId, AbstractUser):
    # username will hold the github "login"
    token = models.TextField(blank=True, null=True)
    avatar_url = models.TextField(blank=True, null=True)
    is_organization = models.BooleanField(default=False)
    organizations = models.ManyToManyField('self', related_name='members')
    organizations_fetched_at = models.DateTimeField(blank=True, null=True)
    organizations_etag = models.CharField(max_length=64, blank=True, null=True)
    teams = models.ManyToManyField(Team, related_name='members')
    teams_fetched_at = models.DateTimeField(blank=True, null=True)
    teams_etag = models.CharField(max_length=64, blank=True, null=True)
    available_repositories = models.ManyToManyField('Repository', through=AvailableRepository)
    watched_repositories = models.ManyToManyField('Repository', related_name='watched')
    starred_repositories = models.ManyToManyField('Repository', related_name='starred')

    objects = GithubUserManager()

    github_matching = dict(GithubObjectWithId.github_matching)
    github_matching.update({
        'login': 'username',
    })
    github_ignore = GithubObjectWithId.github_ignore + ('token', 'is_organization', 'password',
        'is_staff', 'is_active', 'date_joined', 'username', ) + ('following_url', 'events_url',
        'organizations_url', 'url', 'gists_url', 'html_url', 'subscriptions_url', 'repos_url',
        'received_events_url', 'gravatar_id', 'starred_url', 'site_admin', 'type', 'followers_url', )

    class Meta:
        ordering = ('username', )

    @property
    def github_url(self):
        return GITHUB_HOST + self.username

    @property
    def github_organization_url(self):
        return GITHUB_HOST + 'orgs/' + self.username

    @property
    def github_callable_identifiers(self):
        return [
            'users',
            self.username,
        ]

    @property
    def github_callable_identifiers_for_self(self):
        # api.github.com/user
        return [
            'user',
        ]

    @property
    def github_callable_identifiers_for_organization(self):
        return [
            'orgs',
            self.username,
        ]

    @property
    def github_callable_identifiers_for_organizations(self):
        return self.github_callable_identifiers + [
            'orgs',
        ]

    @property
    def github_callable_identifiers_for_teams(self):
        if self.is_organization:
            return self.github_callable_identifiers_for_organization + [
                'teams',
            ]
        else:
            return self.github_callable_identifiers_for_self + [
                'teams',
            ]

    @property
    def github_callable_identifiers_for_available_repositories_set(self):
        # won't work for organizations, but not called in this case
        return self.github_callable_identifiers_for_self + [
            'repos',
        ]

    @property
    def github_callable_identifiers_for_starred_repositories(self):
        # won't work for organizations, but not called in this case
        return self.github_callable_identifiers_for_self + [
            'starred',
        ]

    @property
    def github_callable_identifiers_for_watched_repositories(self):
        # won't work for organizations, but not called in this case
        return self.github_callable_identifiers_for_self + [
            'subscriptions',
        ]

    def __getattr__(self, name):
        """
        We create "github_identifiers_for" to fetch repositories of an
        organization by calling it from the user, so we must create it on the
        fly.
        """
        if name.startswith('github_callable_identifiers_for_org_repositories_'):
            org_name = name[49:]
            return [
                'orgs',
                org_name,
                'repos'
            ]

        raise AttributeError("%r object has no attribute %r" % (self.__class__, name))

    def fetch_organizations(self, gh, force_fetch=False, parameters=None):
        if self.is_organization:
            # an organization cannot belong to an other organization
            return 0

        # force fetching 100 orgs by default, as we cannot set "github_per_page"
        # for the whole GithubUser class
        if not parameters:
            parameters = {}
        if 'per_page' not in parameters:
            parameters['per_page'] = 100

        return self._fetch_many('organizations', gh,
                                defaults={'simple': {'is_organization': True}},
                                force_fetch=force_fetch,
                                parameters=parameters)

    def fetch_teams(self, gh, force_fetch=False, parameters=None):
        defaults = None
        if self.is_organization:
            defaults = {'fk': {'organization': self}}
        return self._fetch_many('teams', gh,
                                defaults=defaults,
                                force_fetch=force_fetch,
                                parameters=parameters)

    def fetch_starred_repositories(self, gh=None, force_fetch=False, parameters=None):
        # FORCE GH
        if not gh or gh._connection_args.get('username') != self.username:
            gh = self.get_connection()

        # force fetching 100 orgs by default, as we cannot set "github_per_page"
        # for the whole Repository class
        if not parameters:
            parameters = {}
        if 'per_page' not in parameters:
            parameters['per_page'] = 100

        return self._fetch_many('starred_repositories', gh,
                                force_fetch=force_fetch,
                                parameters=parameters)

    def fetch_watched_repositories(self, gh=None, force_fetch=False, parameters=None):
        # FORCE GH
        if not gh or gh._connection_args.get('username') != self.username:
            gh = self.get_connection()

        # force fetching 100 orgs by default, as we cannot set "github_per_page"
        # for the whole Repository class
        if not parameters:
            parameters = {}
        if 'per_page' not in parameters:
            parameters['per_page'] = 100

        return self._fetch_many('watched_repositories', gh,
                                force_fetch=force_fetch,
                                parameters=parameters)

    def fetch_available_repositories(self, gh=None, force_fetch=False, org=None, parameters=None):
        """
        Fetch available repositories for the current user (the "gh" will be
        forced").
        It will fetch the repositories available within an organization if "org"
        is filled, and if not, it will fecth the other repositories available to
        the user: ones he owns, or ones where he is a collaborator.
        """
        if self.is_organization:
            # no available repositories for an organization as they can't login
            return 0

        # force fetching 100 orgs by default, as we cannot set "github_per_page"
        # for the whole Repository class
        if not parameters:
            parameters = {}
        if 'per_page' not in parameters:
            parameters['per_page'] = 100

        # FORCE GH
        if not gh or gh._connection_args.get('username') != self.username:
            gh = self.get_connection()

        # force to work on current user
        if gh._connection_args['username'] == self.username:
            user = self
        else:
            user = GithubUser.objects.get(username=gh._connection_args['username'])

        defaults = {'fk': {'user': user}}

        if org:
            filter_queryset = Q(organization_id=org.id)
            meta_base_name = 'org_repositories_' + org.username
            defaults['simple'] = {
                'organization_id': org.id,
                'organization_username': org.username,
            }
        else:
            filter_queryset = Q(organization_id__isnull=True)
            meta_base_name = None
            defaults['simple'] = {
                'organization_id': None,
                'organization_username': None,
            }

        return self._fetch_many('available_repositories_set', gh,
                                meta_base_name=meta_base_name,
                                defaults=defaults,
                                force_fetch=force_fetch,
                                parameters=parameters,
                                filter_queryset=filter_queryset)

    def fetch_all(self, gh=None, force_fetch=False, **kwargs):
        # FORCE GH
        if not gh or gh._connection_args.get('username') != self.username:
            gh = self.get_connection()

        super(GithubUser, self).fetch_all(gh, force_fetch=force_fetch)

        if self.is_organization:
            return 0, 0, 0, 0, 0

        if not self.token:
            return 0, 0, 0, 0, 0

        # repositories a user own or collaborate to, but not in organizations
        nb_repositories_fetched = self.fetch_available_repositories(gh, force_fetch=force_fetch)

        # repositories in the user's organizations
        nb_orgs_fetched = self.fetch_organizations(gh, force_fetch=force_fetch)
        for org in self.organizations.all():
            try:
                nb_repositories_fetched += self.fetch_available_repositories(gh, org=org, force_fetch=force_fetch)
            except ApiNotFoundError:
                # we may have no rights
                pass

        if not kwargs.get('available_only'):
            nb_watched = self.fetch_watched_repositories(gh, force_fetch=force_fetch)
            nb_starred = self.fetch_starred_repositories(gh, force_fetch=force_fetch)
        else:
            nb_watched = 0
            nb_starred = 0

        # # repositories on organizations teams the user are a collaborator
        # try:
        #     nb_teams_fetched = self.fetch_teams(gh, force_fetch=force_fetch)
        # except ApiNotFoundError:
        #     # we may have no rights
        #     pass
        # else:
        #     for team in self.teams.all():
        #         try:
        #             team.fetch_repositories(gh, force_fetch=force_fetch)
        #         except ApiNotFoundError:
        #             # we may have no rights
        #             pass

        # update permissions in token object
        t = self.token_object
        if t:
            t.update_repos()

        return nb_repositories_fetched, nb_orgs_fetched, nb_watched, nb_starred, 0  # nb_teams_fetched

    def get_connection(self):
        return Connection.get(username=self.username, access_token=self.token)

    @property
    def token_object(self):
        """
        Return the "Token" object for the current user, creating it if needed
        """
        if not hasattr(self, '_token_object'):
            if not self.token:
                return None
            from .limpyd_models import Token
            self._token_object, created = Token.get_or_connect(token=self.token)
            if created:
                self._token_object.username.hset(self.username)
        return self._token_object

    def can_use_repository(self, repository):
        """
        Return 'admin', 'push' or 'read' if the user can use this repository
        ('admin' if he has admin rights, 'push' if push rights, else 'read')
        The repository can be a real repository object, a tuple with two entries
        (the owner's username and the repository name), or a string on the
        github format: "username/reponame"
        The user can use this repository if it has admin/push/read rights.
        It's done by fetching the repository via the github api, and if the
        users can push/admin it, the repository is updated (if it's a real
        repository object).
        The result will be None if a problem occured during the check.
        """
        gh = self.get_connection()

        is_real_repository = isinstance(repository, Repository)

        if is_real_repository:
            identifiers = repository.github_callable_identifiers
        else:
            if isinstance(repository, basestring):
                parts = repository.split('/')
            else:
                parts = list(repository)
            identifiers = ['repos'] + parts

        gh_callable = Repository.objects.get_github_callable(gh, identifiers)
        try:
            repo_infos = gh_callable.get()
        except ApiNotFoundError:
            return False
        except ApiError, e:
            if e.response and e.response.code and e.response.code in (401, 403):
                return False
            return None
        except:
            return None

        if not repo_infos:
            return False

        permissions = repo_infos.get('permissions', {'admin': False, 'pull': True, 'push': False})

        if permissions.get('pull', False):
            can_admin = permissions.get('admin', False)
            can_push = permissions.get('push', False)

            if is_real_repository and (can_admin or can_push):
                Repository.objects.create_or_update_from_dict(repo_infos)

            return 'admin' if can_admin else 'push' if can_push else 'read'

        return False

    def save(self, *args, **kwargs):
        """
        Save the user but override to set the mail not set to '' (None not
        allowed from AbstractUser)
        """
        if self.email is None:
            self.email = ''
        super(GithubUser, self).save(*args, **kwargs)


class Repository(GithubObjectWithId):
    owner = models.ForeignKey(GithubUser, related_name='owned_repositories')
    name = models.TextField(db_index=True)
    description = models.TextField(blank=True, null=True)
    collaborators = models.ManyToManyField(GithubUser, related_name='repositories')
    private = models.BooleanField(default=False)
    is_fork = models.BooleanField(default=False)
    has_issues = models.BooleanField(default=False)

    first_fetch_done = models.BooleanField(default=False)
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
        'created_at', 'archive_url', 'pushed_at', 'default_branch', 'teams_url', 'trees_url',
        'branches_url', 'subscribers_url', 'stargazers_url', )

    class Meta:
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
        return self.labels.ready().filter(label_type__isnull=True)

    def _distinct_users(self, relation):
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
        return self._fetch_many('collaborators', gh,
                                force_fetch=force_fetch,
                                parameters=parameters)

    @property
    def github_callable_identifiers_for_labels(self):
        return self.github_callable_identifiers + [
            'labels',
        ]

    def fetch_labels(self, gh, force_fetch=False, parameters=None):
        if not self.has_issues:
            return 0
        return self._fetch_many('labels', gh,
                                defaults={'fk': {'repository': self}},
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
                                defaults={'fk': {'repository': self}},
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
            from .tasks.repository import FetchClosedIssuesWithNoClosedBy
            FetchClosedIssuesWithNoClosedBy.add_job(self.id, limit=20, gh=gh)

        from .tasks.repository import FetchUpdatedPullRequests
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
                                closed_by__isnull=True,
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
        filter = self.issues.filter(
            # only pull requests
            Q(is_pull_request=True)
            &
            (
                # that where never fetched
                Q(pr_fetched_at__isnull=True)
                |
                # or last fetched long time ago
                Q(pr_fetched_at__lt=F('updated_at'))
                |
                (
                    # or open ones...
                    Q(state='open')
                    &
                    (
                        # that are not merged or with unknown merged status
                        Q(merged=False)
                        |
                        Q(merged__isnull=True)
                    )
                    &
                    (
                        # with unknown mergeable status
                        Q(mergeable_state__in=Issue.MERGEABLE_STATES['unknown'])
                        |
                        Q(mergeable_state__isnull=True)
                        |
                        Q(mergeable__isnull=True)
                    )
                )
                |
                # or closed ones without merged status
                Q(merged__isnull=True, state='closed')
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
                Q(is_pull_request=True, state='open')
                &
                (
                    # that are not merged or with unknown merged status
                    Q(merged=False)
                    |
                    Q(merged__isnull=True)
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
        if not self.has_issues:
            # bug in the github api, not able to retrieve issue events if only PRs
            return 0
        count = self._fetch_many('issues_events', gh,
                                 defaults={
                                    'fk': {'repository': self},
                                    'related': {'*': {'fk': {'repository': self}}},
                                },
                                 parameters=parameters,
                                 force_fetch=force_fetch,
                                 max_pages=max_pages)

        from .tasks.repository import FetchUnfetchedCommits
        FetchUnfetchedCommits.add_job(self.id, limit=20, gh=gh)

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

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        """
        Pass "two_steps=True" to felay fetch of closed issues and comments (by
        adding a FirstFetchStep2 job that will call fetch_all_step2)
        """
        two_steps = bool(kwargs.get('two_steps', False))

        super(Repository, self).fetch_all(gh, force_fetch=force_fetch)
        self.fetch_collaborators(gh, force_fetch=force_fetch)
        if self.has_issues:
            self.fetch_labels(gh, force_fetch=force_fetch)
            self.fetch_milestones(gh, force_fetch=force_fetch)

        if two_steps:
            self.fetch_issues(gh, force_fetch=force_fetch, state='open')
            from .tasks.repository import FirstFetchStep2
            FirstFetchStep2.add_job(self.id, gh=gh)
        else:
            self.fetch_all_step2(gh, force_fetch)
            from .tasks.repository import FetchUnmergedPullRequests
            FetchUnmergedPullRequests.add_job(self.id, priority=-15, gh=gh, delayed_for=60*60*3)  # 3 hours

        if not self.first_fetch_done:
            self.first_fetch_done = True
            self.save(update_fields=['first_fetch_done'])

    def fetch_all_step2(self, gh, force_fetch=False, start_page=None,
                        max_pages=None, to_ignore=None, issues_state=None):
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

        return counts


class WithRepositoryMixin(object):
    """
    A base class for all models containing data owned by a repository.
    """

    def fetch(self, gh, defaults=None, force_fetch=False, parameters=None,
                                                        meta_base_name=None):
        """
        Enhance the default fetch by setting the current repository as
        default value.
        """
        if self.repository_id:
            if not defaults:
                defaults = {}
            defaults.setdefault('fk', {})['repository'] = self.repository
            defaults.setdefault('related', {}).setdefault('*', {}).setdefault('fk', {})['repository'] = self.repository

        return super(WithRepositoryMixin, self).fetch(gh, defaults,
                                               force_fetch=force_fetch,
                                               parameters=parameters,
                                               meta_base_name=meta_base_name)

    def defaults_create_values(self):
        return {'fk': {'repository': self.repository}}


LABELTYPE_EDITMODE = Choices(
    ('LIST', 3, u'List of labels'),
    ('FORMAT', 2, u'Simple format'),
    ('REGEX', 1, u'Regular expression'),
)


class LabelType(models.Model):
    LABELTYPE_EDITMODE = LABELTYPE_EDITMODE

    repository = models.ForeignKey(Repository, related_name='label_types')
    regex = models.TextField(
        help_text='Must contain at least this part: (?P<label>visible-part-of-the-label)", and can include "(?P<order>\d+)" for ordering',
        validators=[
            validators.RegexValidator(re.compile('\(\?\P<label>.+\)'), 'Must contain a "label" part: "(?P<label>visible-part-of-the-label)"', 'no-label'),
            validators.RegexValidator(re.compile('^(?!.*\(\?P<order>(?!\\\d\+\))).*$'), 'If an order is present, it must math a number: the exact part must be: "(?P<order>\d+)"', 'invalid-order'),
        ]
    )
    name = models.CharField(max_length=250, db_index=True)
    edit_mode = models.PositiveSmallIntegerField(choices=LABELTYPE_EDITMODE.CHOICES, default=LABELTYPE_EDITMODE.REGEX)
    edit_details = JSONField(blank=True, null=True)

    objects = LabelTypeManager()

    class Meta:
        verbose_name = u'Group'
        unique_together = (
            ('repository', 'name'),
        )
        ordering = ('name', )

    def __unicode__(self):
        return u'%s' % self.name

    def __str__(self):
        return unicode(self).encode('utf-8')

    @property
    def r(self):
        if not hasattr(self, '_regex'):
            self._regex = re.compile(self.regex)
        return self._regex

    def match(self, name):
        return self.r.search(name)

    def get_name_and_order(self, name):
        d = self.match(name).groupdict()
        return d['label'], d.get('order', None)

    def save(self, *args, **kwargs):
        """
        Check validity, save the label-type, and apply label-type search for
        all labels of the repository
        """

        # validate that the regex is ok
        self.clean_fields()

        # clear the cached compiled regex
        if hasattr(self, '_regex'):
            del self._regex

        super(LabelType, self).save(*args, **kwargs)

        # reset the cache for this label, for all names
        LabelType.objects._reset_cache(self.repository)

        # update all labels for the repository
        for label in self.repository.labels.all():
            label.save()

    def delete(self, *args, **kwargs):
        LabelType.objects._reset_cache(self.repository)
        super(LabelType, self).delete(*args, **kwargs)

    @staticmethod
    def regex_from_format(format_string):
        return '^%s$' % re.escape(format_string)\
                          .replace('\\{label\\}', '(?P<label>.+)', 1) \
                          .replace('\\{order\\}', '(?P<order>\d+)', 1)

    @staticmethod
    def regex_from_list(labels_list):
        return '^(?P<label>%s)$' % u'|'.join(map(re.escape, labels_list.split(u',')))


class Label(WithRepositoryMixin, GithubObject):
    repository = models.ForeignKey(Repository, related_name='labels')
    name = models.TextField()
    color = models.CharField(max_length=6)
    api_url = models.TextField(blank=True, null=True)
    label_type = models.ForeignKey(LabelType, related_name='labels', blank=True, null=True, on_delete=models.SET_NULL)
    typed_name = models.TextField(db_index=True)
    order = models.IntegerField(blank=True, null=True)

    objects = WithRepositoryManager()

    github_matching = dict(GithubObject.github_matching)
    github_matching.update({
        'url': 'api_url'
    })
    github_ignore = GithubObject.github_ignore + ('api_url', 'label_type', 'typed_name', 'order', )
    github_identifiers = {'repository__github_id': ('repository', 'github_id'), 'name': 'name'}
    github_edit_fields = {
        'create': ('color', 'name', ),
        'update': ('color', 'name', )
    }
    github_per_page = {'min': 100, 'max': 100}

    class Meta:
        unique_together = (
            ('repository', 'name'),
        )
        index_together = (
            ('repository', 'label_type', 'order'),
        )
        ordering = ('label_type', 'order', 'typed_name', )

    @property
    def github_url(self):
        return self.repository.github_url + '/issues?labels=%s' % self.name

    def __unicode__(self):
        if self.label_type_id:
            if self.order is not None:
                return u'%s: #%d %s' % (self.label_type.name, self.order, self.typed_name)
            else:
                return u'%s: %s' % (self.label_type.name, self.typed_name)
        else:
            return u'%s' % self.name

    @property
    def github_callable_identifiers(self):
        """
        If we have the api url of the label, use it as the normal way to get
        identifiers will fail since it's based on the name which may have been
        changed by the user
        """
        if self.api_url:
            return [self.api_url.replace('https://api.github.com/', '')]

        return self.repository.github_callable_identifiers_for_labels + [
            self.name,
        ]

    @property
    def github_callable_create_identifiers(self):
        return self.repository.github_callable_identifiers_for_labels

    def save(self, *args, **kwargs):
        label_type_infos = LabelType.objects.get_for_name(self.repository, self.name)
        if label_type_infos:
            self.label_type, self.typed_name, self.order = label_type_infos
        else:
            self.label_type, self.typed_name, self.order = None, self.name, None

        if kwargs.get('update_fields', None) is not None:
            kwargs['update_fields'] += ['label_type', 'typed_name', 'order']

        super(Label, self).save(*args, **kwargs)


class Milestone(WithRepositoryMixin, GithubObjectWithId):
    repository = models.ForeignKey(Repository, related_name='milestones')
    number = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    title = models.TextField(db_index=True)
    description = models.TextField(blank=True, null=True)
    state = models.CharField(max_length=10, db_index=True)
    created_at = models.DateTimeField(db_index=True, blank=True, null=True)
    due_on = models.DateTimeField(db_index=True, blank=True, null=True)
    creator = models.ForeignKey(GithubUser, related_name='milestones')

    objects = WithRepositoryManager()

    github_ignore = GithubObjectWithId.github_ignore + ('url', 'labels_url',
                                'updated_at', 'closed_issues', 'open_issues', )
    github_edit_fields = {
        'create': ('title', 'state', 'description', 'due_on', ),
        'update': ('title', 'state', 'description', 'due_on', )
    }
    github_per_page = {'min': 100, 'max': 100}

    class Meta:
        ordering = ('-number', )

    @property
    def github_url(self):
        return self.repository.github_url + '/issues?milestone=%s' % self.number

    def __unicode__(self):
        return u'%s' % self.title

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_milestones + [
            self.number,
        ]

    @property
    def github_callable_create_identifiers(self):
        return self.repository.github_callable_identifiers_for_milestones

    def save(self, *args, **kwargs):
        """
        If the creator, which is mandatory, is not defined, use (and create if
        needed) a special user named 'user.deleted'
        """
        if self.creator_id is None:
            self.creator = GithubUser.objects.get_deleted_user()
            if kwargs.get('update_fields'):
                kwargs['update_fields'].append('creator')
        super(Milestone, self).save(*args, **kwargs)

        if not kwargs.get('updated_field')\
                or 'description' in kwargs['updated_field']\
                or 'title' in kwargs['updated_field']:
            IssueEvent.objects.check_references(self, ['description', 'title'], 'creator')


class Commit(WithRepositoryMixin, GithubObject):
    repository = models.ForeignKey(Repository, related_name='commits')
    author = models.ForeignKey(GithubUser, related_name='commits_authored', blank=True, null=True)
    committer = models.ForeignKey(GithubUser, related_name='commits__commited', blank=True, null=True)
    sha = models.CharField(max_length=40, db_index=True)
    message = models.TextField(blank=True, null=True)
    author_name = models.TextField(blank=True, null=True)
    author_email = models.CharField(max_length=256, blank=True, null=True)
    committer_name = models.TextField(blank=True, null=True)
    committer_email = models.CharField(max_length=256, blank=True, null=True)
    authored_at = models.DateTimeField(db_index=True, blank=True, null=True)
    committed_at = models.DateTimeField(db_index=True, blank=True, null=True)
    comments_count = models.PositiveIntegerField(blank=True, null=True)
    tree = models.CharField(max_length=40, blank=True, null=True)
    deleted = models.BooleanField(default=False)

    objects = CommitManager()

    class Meta:
        ordering = ('committed_at', )
        unique_together = (
            ('repository', 'sha'),
        )

    github_identifiers = {'repository__github_id': ('repository', 'github_id'), 'sha': 'sha'}

    github_matching = dict(GithubObjectWithId.github_matching)
    github_matching.update({
        'comment_count': 'comments_count',
    })
    github_ignore = GithubObject.github_ignore + ('deleted', 'comments_count',
        ) + ('url', 'parents', 'comments_url', 'html_url', 'commit', )

    @property
    def github_url(self):
        return self.repository.github_url + '/commit/%s' % self.sha

    def __unicode__(self):
        return u'%s' % self.sha

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_commits + [
            self.sha,
        ]


class Issue(WithRepositoryMixin, GithubObjectWithId):
    repository = models.ForeignKey(Repository, related_name='issues')
    number = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    title = models.TextField(db_index=True)
    body = models.TextField(blank=True, null=True)
    body_html = models.TextField(blank=True, null=True)
    labels = models.ManyToManyField(Label, related_name='issues')
    user = models.ForeignKey(GithubUser, related_name='created_issues')
    assignee = models.ForeignKey(GithubUser, related_name='assigned_issues', blank=True, null=True)
    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)
    closed_at = models.DateTimeField(blank=True, null=True, db_index=True)
    milestone = models.ForeignKey(Milestone, related_name='issues', blank=True, null=True)
    state = models.CharField(max_length=10, db_index=True)
    comments_count = models.PositiveIntegerField(blank=True, null=True)
    closed_by = models.ForeignKey(GithubUser, related_name='closed_issues', blank=True, null=True, db_index=True)
    closed_by_fetched = models.BooleanField(default=False, db_index=True)
    comments_fetched_at = models.DateTimeField(blank=True, null=True)
    comments_etag = models.CharField(max_length=64, blank=True, null=True)
    events_fetched_at = models.DateTimeField(blank=True, null=True)
    events_etag = models.CharField(max_length=64, blank=True, null=True)
    # pr stuff
    is_pull_request = models.BooleanField(default=False, db_index=True)
    pr_fetched_at = models.DateTimeField(blank=True, null=True, db_index=True)
    pr_comments_count = models.PositiveIntegerField(blank=True, null=True)
    pr_comments_fetched_at = models.DateTimeField(blank=True, null=True)
    pr_comments_etag = models.CharField(max_length=64, blank=True, null=True)
    base_label = models.TextField(blank=True, null=True)
    base_sha = models.CharField(max_length=256, blank=True, null=True)
    head_label = models.TextField(blank=True, null=True)
    head_sha = models.CharField(max_length=256, blank=True, null=True)
    merged_at = models.DateTimeField(blank=True, null=True)
    merged_by = models.ForeignKey(GithubUser, related_name='merged_prs', blank=True, null=True)
    github_pr_id = models.PositiveIntegerField(unique=True, null=True, blank=True)
    mergeable = models.NullBooleanField()
    mergeable_state = models.CharField(max_length=20, null=True, blank=True)
    merged = models.NullBooleanField()
    nb_commits = models.PositiveIntegerField(blank=True, null=True)
    nb_additions = models.PositiveIntegerField(blank=True, null=True)
    nb_deletions = models.PositiveIntegerField(blank=True, null=True)
    nb_changed_files = models.PositiveIntegerField(blank=True, null=True)
    commits_fetched_at = models.DateTimeField(blank=True, null=True)
    commits_etag = models.CharField(max_length=64, blank=True, null=True)
    commits = models.ManyToManyField(Commit, related_name='issues')
    files_fetched_at = models.DateTimeField(blank=True, null=True)
    files_etag = models.CharField(max_length=64, blank=True, null=True)

    objects = IssueManager()

    github_matching = dict(GithubObjectWithId.github_matching)
    github_matching.update({
        'comments': 'comments_count',
        # "review_comments" is only filled if fetching a pull_request directly (we don't do it, but just in case...)
        'review_comments': 'pr_comments_count',
        'commits': 'nb_commits',
        'additions': 'nb_additions',
        'deletions': 'nb_deletions',
        'changed_files': 'nb_changed_files'
    })
    github_ignore = GithubObjectWithId.github_ignore + ('is_pull_request', 'closed_by_fetched',
        'github_pr_id', 'pr_comments_count', 'nb_commits', 'nb_additions', 'nb_deletions',
        'nb_changed_files', ) + ('head', 'commits_url', 'body_text', 'url', 'labels_url',
        'events_url', 'comments_url', 'html_url', 'merge_commit_sha', 'review_comments_url',
        'review_comment_url', 'base', 'patch_url', 'pull_request', 'diff_url',
        'statuses_url', 'issue_url', )

    github_format = '.full+json'
    github_edit_fields = {
        'create': (
            'title',
            'body',
            ('assignee', 'assignee__username'),
            ('milestone', 'milestone__number'),
            ('labels', 'labels__name', )
        ),
        'create': (
            'title',
            'body',
            'state',
            ('assignee', 'assignee__username'),
            ('milestone', 'milestone__number'),
            ('labels', 'labels__name', )
        ),
    }

    # fetch from repo + number because we can have PRs but no issues from github
    github_identifiers = {'repository__github_id': ('repository', 'github_id'), 'number': 'number'}

    github_date_field = ('updated_at', 'updated', 'desc')

    MERGEABLE_STATES = {
        'mergeable': ('clean', 'stable'),
        'unmergeable': ('unknown', 'checking', 'dirty', 'unstable'),
        'unknown': ('unknown', 'checking'),
    }

    class Meta:
        unique_together = (
            ('repository', 'number'),
        )

    @property
    def github_url(self):
        return self.repository.github_url + '/issues/%s' % self.number

    def __unicode__(self):
        return u'#%s %s' % (self.number or '??', self.title)

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_issues + [
            self.number,
        ]

    @property
    def github_callable_identifiers_for_pr(self):
        return self.repository.github_callable_identifiers_for_prs + [
            self.number,
        ]

    @property
    def github_callable_create_identifiers(self):
        return self.repository.github_callable_identifiers_for_issues

    @property
    def github_callable_identifiers_for_events(self):
        return self.github_callable_identifiers + [
            'events',
        ]

    @property
    def github_callable_identifiers_for_comments(self):
        return self.github_callable_identifiers + [
            'comments',
        ]

    @property
    def github_callable_identifiers_for_pr_comments(self):
        return self.github_callable_identifiers_for_pr + [
            'comments'
        ]

    def fetch(self, gh, defaults=None, force_fetch=False, parameters=None,
                                                        meta_base_name=None):
        if not self.repository.has_issues:
            # do not use the issues api endpoint if repos with PRs only
            meta_base_name = 'pr'
        return super(Issue, self).fetch(gh, defaults, force_fetch, parameters, meta_base_name)

    def fetch_pr(self, gh, defaults=None, force_fetch=False, parameters=None):
        if defaults is None:
            defaults = {}
        if 'simple' not in defaults:
            defaults['simple'] = {}
        defaults['simple'].update({
            'is_pull_request': True,
            'mergeable_state': 'checking',
        })
        return self.fetch(gh=gh, defaults=defaults, force_fetch=force_fetch,
                                    parameters=parameters, meta_base_name='pr')

    def fetch_events(self, gh, force_fetch=True, parameters=None):
        """
        force_fetch is forced to True because for an issue events are in the
        reverse order (first created first, last created last, maybe on an other
        page)
        """
        if not self.repository.has_issues:
            # bug in the github api, not able to retrieve issue events if only PRs
            return

        return self._fetch_many('events', gh,
                                defaults={
                                    'fk': {
                                        'issue': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'issue': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=parameters,
                                force_fetch=True)

    def fetch_comments(self, gh, force_fetch=False, parameters=None):
        """
        Don't fetch comments if the previous fetch of the issue told us there
        is not comments for it
        """
        if not force_fetch and self.comments_count == 0:
            return 0
        final_parameters = {
            'sort': IssueComment.github_date_field[1],
            'direction': IssueComment.github_date_field[2],
        }
        if parameters:
            final_parameters.update(parameters)
        count = self._fetch_many('comments', gh,
                                defaults={
                                    'fk': {
                                        'issue': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'issue': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=final_parameters,
                                force_fetch=force_fetch)
        if count and (not self.comments_count or count > self.comments_count):
            self.comments_count = count
            self.save(update_fields=('comments_count',))

        return count

    def fetch_pr_comments(self, gh, force_fetch=False, parameters=None):
        final_parameters = {
            'sort': PullRequestComment.github_date_field[1],
            'direction': PullRequestComment.github_date_field[2],
        }
        if parameters:
            final_parameters.update(parameters)
        return self._fetch_many('pr_comments', gh,
                                defaults={
                                    'fk': {
                                        'issue': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'issue': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=final_parameters,
                                force_fetch=force_fetch)

    @property
    def github_callable_identifiers_for_labels(self):
        return self.github_callable_identifiers + [
            'labels',
        ]

    def fetch_labels(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('labels', gh,
                                defaults={
                                    'fk': {'repository': self.repository},
                                    'related': {'*': {'fk': {'repository': self.repository}}},
                                },
                                force_fetch=force_fetch,
                                parameters=parameters)

    @property
    def github_callable_identifiers_for_commits(self):
        return self.github_callable_identifiers_for_pr + [
            'commits'
        ]

    @property
    def github_callable_identifiers_for_files(self):
        return self.github_callable_identifiers_for_pr + [
            'files'
        ]

    def fetch_commits(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('commits', gh,
                                defaults={'fk': {'repository': self.repository}},
                                parameters=parameters,
                                force_fetch=force_fetch)

    def fetch_files(self, gh, force_fetch=False, parameters=None):
        return self._fetch_many('files', gh,
                                defaults={
                                    'fk': {
                                        'issue': self,
                                        'repository': self.repository
                                    },
                                    'related': {'*': {
                                        'fk': {
                                            'issue': self,
                                            'repository': self.repository
                                        }
                                    }}
                                },
                                parameters=parameters,
                                force_fetch=force_fetch)

    def fetch_all(self, gh, force_fetch=False, **kwargs):
        super(Issue, self).fetch_all(gh, force_fetch=force_fetch)
        #self.fetch_labels(gh, force_fetch=force_fetch)  # already retrieved via self.fetch
        self.fetch_events(gh, force_fetch=True)
        self.fetch_comments(gh, force_fetch=force_fetch)
        if self.is_pull_request:
            self.fetch_pr(gh, force_fetch=force_fetch)
            self.fetch_pr_comments(gh, force_fetch=force_fetch)
            self.fetch_commits(gh, force_fetch=force_fetch)
            self.fetch_files(gh, force_fetch=force_fetch)

    @property
    def total_comments_count(self):
        return (self.comments_count or 0) + (self.pr_comments_count or 0)

    def update_pr_comments_count(self):
        if self.is_pull_request:
            count = self.pr_comments.count()
            if count and (not self.pr_comments_count or count > self.pr_comments_count):
                self.pr_comments_count = self.pr_comments.count()
                self.save(update_fields=['pr_comments_count'])

    def save(self, *args, **kwargs):
        """
        If the user, which is mandatory, is not defined, use (and create if
        needed) a special user named 'user.deleted'
        Also check that if the issue is reopened, we'll be able to fetch the
        future closed_by
        """
        fields_to_update = []

        if self.user_id is None:
            self.user = GithubUser.objects.get_deleted_user()
            fields_to_update.append('user')

        if self.state != 'closed' and self.closed_by_fetched:
            self.closed_by_fetched = False
            fields_to_update.append('closed_by_fetched')

        if fields_to_update and kwargs.get('update_fields'):
            kwargs['update_fields'].extend(fields_to_update)

        super(Issue, self).save(*args, **kwargs)

        if not kwargs.get('updated_field')\
                or 'body_html' in kwargs['updated_field']\
                or 'title' in kwargs['updated_field']:
            IssueEvent.objects.check_references(self, ['body_html', 'title'])

    @property
    def is_mergeable(self):
        if not self.is_pull_request:
            return False
        if self.state == 'closed':
            return False
        if self.mergeable:
            return True
        return self.mergeable_state in self.MERGEABLE_STATES['mergeable']


class WithIssueMixin(WithRepositoryMixin):
    """
    A base class for all models containing data owned by an issue.
    """

    def fetch(self, gh, defaults=None, force_fetch=False, parameters=None,
                                                        meta_base_name=None):
        """
        Enhance the default fetch by setting the current repository and issue as
        default values.
        """
        if self.issue_id:
            if not defaults:
                defaults = {}
            defaults.setdefault('fk', {})['issue'] = self.issue
            defaults.setdefault('related', {}).setdefault('*', {}).setdefaults('fk', {})['issue'] = self.issue

        return super(WithIssueMixin, self).fetch(gh, defaults,
                                               force_fetch=force_fetch,
                                               parameters=parameters,
                                               meta_base_name=meta_base_name)

    def defaults_create_values(self):
        values = super(WithIssueMixin, self).defaults_create_values()
        values['fk']['issue'] = self.issue
        return values


class IssueComment(WithIssueMixin, GithubObjectWithId):
    repository = models.ForeignKey(Repository, related_name='comments')
    issue = models.ForeignKey(Issue, related_name='comments')
    user = models.ForeignKey(GithubUser, related_name='issue_comments')
    body = models.TextField(blank=True, null=True)
    body_html = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)

    objects = IssueCommentManager()

    github_format = '.full+json'
    github_ignore = GithubObjectWithId.github_ignore + ('url', 'html_url', 'issue_url', 'body_text', )
    github_edit_fields = {
        'create': ('body', ),
        'update': ('body', )
    }
    github_date_field = ('updated_at', 'updated', 'desc')

    class Meta:
        ordering = ('created_at', )

    @property
    def github_url(self):
        return self.issue.github_url + '#issuecomment-%s' % self.github_id

    def __unicode__(self):
        return u'on issue #%d' % (self.issue.number if self.issue else '?')

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_issues + [
            'comments',
            self.github_id,
        ]

    @property
    def github_callable_create_identifiers(self):
        return self.issue.github_callable_identifiers_for_comments

    def save(self, *args, **kwargs):
        """
        If the user, which is mandatory, is not defined, use (and create if
        needed) a special user named 'user.deleted'
        """
        if self.user_id is None:
            self.user = GithubUser.objects.get_deleted_user()
            if kwargs.get('update_fields'):
                kwargs['update_fields'].append('user')
        super(IssueComment, self).save(*args, **kwargs)

        if not kwargs.get('updated_field') or 'body_html' in kwargs['updated_field']:
            IssueEvent.objects.check_references(self, ['body_html'])


class PullRequestCommentEntryPoint(GithubObject):
    repository = models.ForeignKey(Repository, related_name='pr_comments_entry_points')
    issue = models.ForeignKey(Issue, related_name='pr_comments_entry_points')
    diff_hunk = models.TextField(blank=True, null=True)
    commit_sha = models.CharField(max_length=40, blank=True, null=True)
    original_commit_sha = models.CharField(max_length=40, blank=True, null=True)
    position = models.PositiveIntegerField(blank=True, null=True)
    original_position = models.PositiveIntegerField(blank=True, null=True)
    path = models.TextField(blank=True, null=True)

    user = models.ForeignKey(GithubUser, related_name='pr_comments_entry_points', blank=True, null=True)
    created_at = models.DateTimeField(db_index=True, blank=True, null=True)
    updated_at = models.DateTimeField(db_index=True, blank=True, null=True)

    objects = PullRequestCommentEntryPointManager()

    github_matching = dict(GithubObject.github_matching)
    github_matching.update({
        'commit_id': 'commit_sha',
        'original_commit_id': 'original_commit_sha',
    })
    github_ignore = GithubObject.github_ignore + ('id', 'commit_sha' + 'original_commit_sha'
                                        ) + ('body_text', 'url', 'html_url', 'pull_request_url', )
    github_identifiers = {
        'repository__github_id': ('repository', 'github_id'),
        'issue__number': ('issue', 'number'),
        'original_commit_sha': 'original_commit_sha',
        'path': 'path',
        'original_position': 'original_position',
    }

    class Meta:
        ordering = ('created_at', )
        unique_together = (
            ('issue', 'original_commit_sha', 'path', 'original_position')
        )

    def __unicode__(self):
        return u'Entry point on PR #%d' % self.issue.number

    @property
    def github_url(self):
        if not self.commit_sha:
            return None
        url = self.repository.github_url + '/blob/%s/%s' % (self.commit_sha, self.path)
        if self.position:
            url += '#L%s' % self.position
        return url

    def update_starting_point(self, save=True):
        try:
            first_comment = self.comments.all()[0]
        except IndexError:
            pass
        else:
            if self.created_at != first_comment.created_at or self.user != first_comment.user:
                self.created_at = first_comment.created_at
                self.user = first_comment.user
                if save:
                    self.save(update_fields=['created_at', 'user'])
                return True
        return False

    def save(self, *args, **kwargs):
        if self.pk:
            self.update_starting_point(save=False)
        super(PullRequestCommentEntryPoint, self).save(*args, **kwargs)


class PullRequestComment(WithIssueMixin, GithubObjectWithId):
    repository = models.ForeignKey(Repository, related_name='pr_comments')
    issue = models.ForeignKey(Issue, related_name='pr_comments')
    user = models.ForeignKey(GithubUser, related_name='pr_comments')
    body = models.TextField(blank=True, null=True)
    body_html = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)

    entry_point = models.ForeignKey('PullRequestCommentEntryPoint', related_name='comments')

    objects = PullRequestCommentManager()

    github_ignore = GithubObjectWithId.github_ignore + ('entry_point', ) + (
                        'body_text', 'url', 'html_url', 'pull_request_url', )
    github_format = '.full+json'
    github_edit_fields = {
        'create': (
           'body',
           ('commit_id', 'entry_point__original_commit_sha'),
           ('path', 'entry_point__path'),
           ('position', 'entry_point__original_position'),
        ),
        'update': (
           'body',
           ('commit_id', 'entry_point__original_commit_sha'),
           ('path', 'entry_point__path'),
           ('position', 'entry_point__original_position'),
        ),
    }
    github_date_field = ('updated_at', 'updated', 'desc')

    class Meta:
        ordering = ('created_at', )

    @property
    def github_url(self):
        return self.repository.github_url + '/pull/%s#discussion_r%s' % (
                                                    self.number, self.github_id)

    def __unicode__(self):
        return u'on PR #%d' % (self.issue.number if self.issue else '?')

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_pr_comments + [
            self.github_id,
        ]

    @property
    def github_callable_create_identifiers(self):
        return self.issue.github_callable_identifiers_for_pr_comments

    def save(self, *args, **kwargs):
        """
        If the user, which is mandatory, is not defined, use (and create if
        needed) a special user named 'user.deleted'
        If it's a creation, update the pr_comments_count of the issue
        If it's an update, update the starting point of the entry-point
        """
        if self.user_id is None:
            self.user = GithubUser.objects.get_deleted_user()
            if kwargs.get('update_fields'):
                kwargs['update_fields'].append('user')
        is_new = not bool(self.pk)
        super(PullRequestComment, self).save(*args, **kwargs)
        if is_new:
            self.issue.update_pr_comments_count()
        else:
            self.entry_point.update_starting_point(save=True)

        if not kwargs.get('updated_field') or 'body_html' in kwargs['updated_field']:
            IssueEvent.objects.check_references(self, ['body_html'])


class IssueEvent(WithIssueMixin, GithubObjectWithId):
    repository = models.ForeignKey(Repository, related_name='issues_events')
    issue = models.ForeignKey(Issue, related_name='events')
    user = models.ForeignKey(GithubUser, related_name='issues_events', blank=True, null=True)
    event = models.CharField(max_length=256, blank=True, null=True, db_index=True)
    commit_sha = models.CharField(max_length=40, blank=True, null=True)
    created_at = models.DateTimeField(db_index=True)

    related_content_type = models.ForeignKey(ContentType, blank=True, null=True)
    related_object_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    related_object = generic.GenericForeignKey('related_content_type',
                                               'related_object_id')

    objects = IssueEventManager()

    github_matching = dict(GithubObjectWithId.github_matching)
    github_matching.update({
        'actor': 'user',
        'commit_id': 'commit_sha',
    })
    github_ignore = GithubObjectWithId.github_ignore + ('related_object_id',
            'related_content_type', 'related_object', 'commit_sha') + ('url', )
    github_date_field = ('created_at', None, None)

    class Meta:
        ordering = ('created_at', 'github_id')

    def __unicode__(self):
        return u'"%s" on Issue #%d' % (self.event, self.issue.number if self.issue else '?')

    @property
    def github_callable_identifiers(self):
        return self.repository.github_callable_identifiers_for_issues_events + [
            self.github_id,
        ]

    @property
    def github_url(self):
        if self.commit_sha:
            return self.repository.github_url + '/commit/%s' % self.commit_sha
        elif self.related_object_id:
            return self.related_object.github_url

    def save(self, *args, **kwargs):
        """
        Create the related Commit object if the event is a reference to a commit.
        Commit will later be fetched by a worker to get its message.
        """
        if self.commit_sha and not self.related_object_id:
            self.related_object, created = Commit.objects.get_or_create(
                repository=self.repository,
                sha=self.commit_sha,
                defaults={
                    'authored_at': self.created_at,
                    'author': self.user,
                })
        super(IssueEvent, self).save(*args, **kwargs)


class PullRequestFile(WithIssueMixin, GithubObject):
    repository = models.ForeignKey(Repository, related_name='pr_files')
    issue = models.ForeignKey(Issue, related_name='files')
    sha = models.CharField(max_length=40, blank=True, null=True)
    path = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=32, blank=True, null=True)
    nb_additions = models.PositiveIntegerField(blank=True, null=True)
    nb_deletions = models.PositiveIntegerField(blank=True, null=True)
    nb_changes = models.PositiveIntegerField(blank=True, null=True)
    patch = models.TextField(blank=True, null=True)
    tree = models.CharField(max_length=40, blank=True, null=True)

    objects = PullRequestFileManager()

    github_matching = dict(GithubObject.github_matching)
    github_matching.update({
        'additions': 'nb_additions',
        'deletions': 'nb_deletions',
        'changes': 'nb_changes',
        'filename': 'path'
    })
    github_ignore = GithubObjectWithId.github_ignore + ('nb_additions', 'nb_deletions',
                                'nb_changes', 'path') + ('raw_url', 'contents_url', 'blob_url', )
    github_identifiers = {
        'tree': 'tree',
        'sha': 'sha',
        'path': 'path',
    }

    class Meta:
        ordering = ('path', )
        unique_together = (
            ('tree', 'sha', 'path',)
        )

    def __unicode__(self):
        return u'"%s" on Issue #%d' % (self.path, self.issue.number if self.issue else '?')

    @property
    def github_url(self):
        return self.repository.github_url + '/blob/%s/%s' % (self.tree, self.path)


from core.tasks import *
