import logging
import os
import re
import subprocess
from collections import Counter, OrderedDict
from datetime import datetime
from tempfile import NamedTemporaryFile
from time import sleep
from uuid import uuid4

from django.contrib.auth.models import UserManager
from django.contrib.contenttypes.models import ContentType
from django.db import models, IntegrityError
from django.db.models import FieldDoesNotExist
from django.db.models import Max, Q

from .ghpool import Connection, ApiError
from .diffutils import get_encoded_hunks_from_patch
from .utils import queryset_iterator, SavedObjects

MODE_CREATE = {'create'}
MODE_UPDATE = {'update'}
MODE_ALL = MODE_CREATE | MODE_UPDATE


logger = logging.getLogger('django')


class BaseManager(models.Manager):

    def delete_missing_after_fetch(self, queryset):
        """
        All objects matching the given queryset will be deleted, or, if the
        `delete_missing_after_fetch` attribute of the model is set to False,
        the `deleted` attribute of all this objects is set to True
        """

        # we do not delete entries that we are waiting to be created
        if hasattr(self.model, 'GITHUB_STATUS_CHOICES'):
            queryset = queryset.exclude(github_status=self.model.GITHUB_STATUS_CHOICES.WAITING_CREATE)

        if self.model.delete_missing_after_fetch:
            queryset.delete()
        else:
            try:
                self.model._meta.get_field('deleted')
            except FieldDoesNotExist:
                pass
            else:
                queryset.update(deleted=True)


class GithubObjectManager(BaseManager):
    """
    This manager is to be used with GithubObject models.
    It provides stuff to create or update objects with json from the github api.
    """

    def ready(self):
        """
        Ignore all objects that are ready to be deleted, or created, and ones
        that failed to be created.
        To use instead of "all" when needed
        """
        return self.get_queryset().exclude(
                        github_status__in=self.model.GITHUB_STATUS_CHOICES.NOT_READY)

    def exclude_deleting(self):
        """
        Ignore all objects that are in the process of being deleted
        """
        return self.get_queryset().exclude(
                        github_status=self.model.GITHUB_STATUS_CHOICES.WAITING_DELETE)

    def get_github_callable(self, gh, identifiers):
        """
        Return the github callable object for the given identifiers.
        We create it by looping through identifiers to create something like
        gh.{identiers[0].(identifiers[1])(identifiers[2])
        """
        if not identifiers:
            raise Exception('Unable to find the path to the github api.')
        result = getattr(gh, identifiers[0])
        for identifier in identifiers[1:]:
            result = result(identifier)
        return result

    def get_from_github(self, gh, identifiers, modes=MODE_ALL, defaults=None,
                        parameters=None, request_headers=None,
                        response_headers=None, min_date=None,
                        fetched_at_field='fetched_at',
                        etag_field='etag',
                        force_update=False,
                        saved_objects=None):
        """
        Trying to get data for the model related to this manager, by using
        identifiers to generate the API call. gh is the connection to use.
        If the min_date argument is filled, we'll only take into account object
        with the value of the field defined by github_date_field greater (only
        if you got a list from github, and we assume that the list is ordered by
        this field, descending)
        """

        if saved_objects is None:
            saved_objects = SavedObjects()

        if response_headers is None:
            response_headers = {}

        data = self.get_data_from_github(
            gh=gh,
            identifiers=identifiers,
            parameters=parameters,
            request_headers=request_headers,
            response_headers=response_headers
        )
        if isinstance(data, list):
            result = self.create_or_update_from_list(data, modes, defaults,
                        min_date=min_date, fetched_at_field=fetched_at_field,
                        saved_objects=saved_objects, force_update=force_update)
        else:
            etag = response_headers.get('etag') or None
            if etag and '""' in etag:
                etag = None
            result = self.create_or_update_from_dict(data, modes, defaults,
                                            fetched_at_field=fetched_at_field,
                                            etag_field=etag_field,
                                            saved_objects=saved_objects,
                                            force_update=force_update,
                                            etag=etag)
            if not result:
                raise Exception(
                    "Unable to create/update an object of the %s kind (modes=%s)" % (
                        self.model.__name__, ','.join(modes)))

        return result

    def get_data_from_github(self, gh, identifiers, parameters=None,
                             request_headers=None, response_headers=None):
        """
        Use the gh connection to get an object from github using the given
        identifiers
        """
        gh_callable = self.get_github_callable(gh, identifiers)
        if not parameters:
            parameters = {}
        # we'll accept some 502 errors
        tries = 0
        while tries < 5:
            try:
                return gh_callable.get(request_headers=request_headers,
                                       response_headers=response_headers,
                                       **parameters)
            except ApiError, e:
                if e.response and e.response['code'] == 502:
                    tries += 1
                    sleep(1)
                else:
                    raise

    def get_matching_field(self, field_name):
        """
        Use the github_matching attribute of the model to return the field to
        populate for a given json field.
        If no matching found, return the same field.
        """
        return self.model.github_matching.get(field_name, field_name)

    def create_or_update_from_list(self, data, modes=MODE_ALL, defaults=None,
                                min_date=None, fetched_at_field='fetched_at',
                                saved_objects=None, force_update=False):
        """
        Take a list of json objects, call create_or_update for each one, and
        return the list of touched objects. Objects that cannot be created are
        not returned.
        """
        if saved_objects is None:
            saved_objects = SavedObjects()

        objs = []
        for entry in data:
            obj = self.create_or_update_from_dict(entry, modes, defaults,
                                                  fetched_at_field= fetched_at_field,
                                                  saved_objects=saved_objects,
                                                  force_update=force_update)
            if obj:
                objs.append(obj)
                if min_date and obj.github_date_field:
                    obj_min_date = getattr(obj, obj.github_date_field[0])
                    if obj_min_date and obj_min_date < min_date:
                        break
        return objs

    def get_filters_from_identifiers(self, fields, identifiers=None):
        """
        Return the filters to use as argument to a Queryset to retrieve an
        object based on some identifiers.
        See get_from_identifiers for more details
        """
        filters = {}
        if not identifiers:
            identifiers = self.model.github_identifiers
        for field, lookup in identifiers.items():
            if isinstance(lookup, (tuple, list)):
                filters[field] = getattr(fields['fk'][lookup[0]], lookup[1])
            else:
                filters[field] = fields['simple'][lookup]
        return filters

    def get_from_identifiers(self, fields, identifiers=None, saved_objects=None):
        """
        Try to load an existing object from the given fields, using the
        github_identifiers attribute of the model.
        This attribute is a dict, with the left part of the queryset filter as
        key, and the right part as value. If this value is a tuple, we consider
        that this filter entry is for a FK, using the first part for the fk, and
        the right part for the fk's field.
        Return a tuple with, first, the object, or None if no objbect found for
        the given fields, and then a Boolean, set to True if the object was
        found in the saved_objects argument, else False
        If identifiers is given, use it instead of the default one from the model
        """
        if saved_objects is None:
            saved_objects = SavedObjects()

        filters = self.get_filters_from_identifiers(fields, identifiers)

        try:
            return saved_objects.get_object(self.model, filters), True
        except KeyError:
            pass
        try:
            obj = self.get(**filters)
            saved_objects.set_object(self.model, filters, obj)
            return obj, False
        except self.model.DoesNotExist:
            return None, False

    def create_or_update_from_dict(self, data, modes=MODE_ALL, defaults=None,
                            fetched_at_field='fetched_at', etag_field='etag',
                            saved_objects=None, force_update=False, etag=None,
                            ignore_github_status=False):
        """
        Taking a dict (passed in the data argument), try to update an existing
        object that match some fields, or create a new one.
        Return the object, or None if no object could be updated/created.
        """
        fields = self.get_object_fields_from_dict(data, defaults, saved_objects)
        if not fields:
            return None

        if saved_objects is None:
            saved_objects = SavedObjects()

        def _create_or_update(obj=None):
            # abort if locally deleted
            from gim.core.limpyd_models import DeletedInstance
            from gim.core.models.base import GithubObjectWithId
            if issubclass(self.model, GithubObjectWithId):
                github_id = fields.get('simple', {}).get('github_id')
                if github_id and DeletedInstance.exist_for_model_and_id(self.model, github_id):
                    return None, False, []

            # get or create a new object
            to_create = False
            if obj:
                already_saved = False
            else:
                obj, already_saved = self.get_from_identifiers(fields, saved_objects=saved_objects)
            if not obj:
                if 'create' not in modes:
                    return None, False, []
                to_create = True
                obj = self.model()
                obj.is_new = True  # may serve later
            else:
                if 'update' not in modes:
                    return None, False, []
                # don't update object waiting to be updated or deleted
                if not ignore_github_status and obj.github_status in obj.GITHUB_STATUS_CHOICES.ALL_WAITING:
                    if not already_saved:
                        saved_objects.set_object(self.model, self.get_filters_from_identifiers(fields), obj)
                    return obj, True, []
                # don't update object with old data
                if not force_update:
                    updated_at = getattr(obj, 'updated_at', None)
                    if updated_at:
                        new_updated_at = fields['simple'].get('updated_at')
                        if new_updated_at and new_updated_at < updated_at:
                            if not already_saved:
                                saved_objects.set_object(self.model, self.get_filters_from_identifiers(fields), obj)
                            return obj, True, []
                if already_saved:
                    return obj, True, []

            updated_fields = []

            # store simple fields if needed
            if fields['simple']:
                for field, value in fields['simple'].iteritems():
                    if not hasattr(obj, field):
                        # Ignore fields not in model
                        continue
                    if getattr(obj, field) == value:
                        # Ignore not-updated fields
                        continue
                    updated_fields.append(field)
                    setattr(obj, field, value)

            # store FKs if needed
            if fields['fk']:
                for field, value in fields['fk'].iteritems():
                    pk_field = '%s_id' % field
                    if not hasattr(obj, pk_field):
                        # Ignore fields not in model
                        continue
                    pk_value = value.id if value else None
                    if pk_value is None and not obj._meta.get_field(field).null:
                        # do not set None FKs if not allowed
                        continue
                    if getattr(obj, pk_field) == pk_value:
                        # Ignore not-updated fields
                        continue
                    updated_fields.append(field)
                    setattr(obj, field, value)
                    # fill the django cache for FKs
                    if value and not isinstance(value, (int, long, basestring)):
                        setattr(obj, '_%s_cache' % field, value)

            # always update these the date it was fetched
            setattr(obj, fetched_at_field, datetime.utcnow())

            # and a status if changed
            wanted_status = obj.GITHUB_STATUS_CHOICES.FETCHED
            if updated_fields:
                wanted_status = obj.GITHUB_STATUS_CHOICES.SAVING
            else:
                for field, values in fields['many'].iteritems():
                    if not isinstance(values, dict):
                        wanted_status = obj.GITHUB_STATUS_CHOICES.SAVING
                        break

            new_status = obj.github_status != wanted_status
            obj.github_status = wanted_status

            # force update or insert to avoid a exists() call in db
            if to_create:
                save_params = {'force_insert': True}
            else:
                updated_fields.append(fetched_at_field)
                if new_status:
                    updated_fields.append('github_status')
                if etag and hasattr(obj, etag_field) and getattr(obj, etag_field) != etag:
                    setattr(obj, etag_field, etag)
                    updated_fields.append(etag_field)
                save_params = {
                    'force_update': True,
                    # only save updated fields
                    'update_fields': updated_fields,
                }

            try:
                obj.save(**save_params)
            except IntegrityError as e:

                # If it's because of a user or repository, manage it
                from .models import GithubUser, Repository

                if isinstance(obj, GithubUser):
                    from .tasks.githubuser import ManageDualUser
                    ManageDualUser.add_job(obj.username, new_github_id=obj.github_id)
                if isinstance(obj, Repository):
                    from .tasks.repository import ManageDualRepository
                    ManageDualRepository.add_job(
                        '%s/%s' % (obj.owner_id, obj.name),
                        new_github_id=obj.github_id
                    )

                # Log and raise the error, with useful data
                message = 'Integrity error [%s] when saving object %s: %s'
                vars_obj = {
                    k: v for k, v in vars(obj).items()
                    if k != '_state' and not (k.startswith('_') and k.endswith('_cache'))
                }
                args = (e, obj.model_name, vars_obj)
                logger.error(message, *args)
                raise IntegrityError(message % args)

            return obj, False, updated_fields

        obj, already_saved, updated_fields = _create_or_update()

        if not obj:
            return None

        continue_update = not already_saved \
                          or getattr(obj, 'is_new', False) \
                          or ignore_github_status \
                          or obj.github_status not in obj.GITHUB_STATUS_CHOICES.ALL_WAITING

        # finally save lists now that we have an object
        for field, values in fields['many'].iteritems():
            if isinstance(values, dict):
                # we have info for how to create/update fields

                # start by updating defaults with the created/updated object
                defaults = values.get('defaults', {})
                related_name = values.get('related_name')
                if defaults and related_name:
                    if related_name in defaults.get('fk', {}):
                        defaults['fk'][related_name] = obj
                    if related_name in defaults.get('related', {}).get('*', {}).get('fk', {}):
                        # TODO: handle others than '*', but not used for now
                        defaults['related']['*']['fk'][related_name] = obj

                # then update/create related objects
                values = values['model'].objects.create_or_update_from_list(
                    data=values['data'],
                    defaults=defaults,
                    saved_objects=saved_objects
                )

            if not already_saved:
                obj.update_related_field(field, [o.id for o in values])

        if not already_saved:
            # save object in the cache
            saved_objects.set_object(self.model, self.get_filters_from_identifiers(fields), obj)

        if continue_update and obj.github_status != obj.GITHUB_STATUS_CHOICES.FETCHED:
            obj.github_status = obj.GITHUB_STATUS_CHOICES.FETCHED
            # We pass the same updated fields as before as they may be used by the signals
            obj.save(update_fields=list(set(updated_fields).union({'github_status'})))

        return obj

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        Taking a dict (passed in the data argument), return the fields to use
        to update or create an object. The returned dict contains 3 entries:
            - 'simple' to hold values for simple fields
            - 'fk' to hold values (real model instances) for foreign keys
            - 'many' to hold list of real model instances for many to many fields
              or for the related relation of a fk (issues of a repository...)
        Eeach of these entries is a dict with the model field names as key, and
        the values to save in the model as value.
        The "defaults" arguments is to fill fields not found in data. It must
        respect the same format as the return of this method: a dict with
        "simple"/"fk"/"many" as keys, with a dict of fields as values. A
        "related" entry can be present for default values to use for related
        data (if "foo" is a related found in "data", defaults["related"]["foo"]
        will be the "defaults" dict used to create/update "foo)
        """

        # reduce data to keep only wanted fields
        for key in data.keys():
            if key.startswith('_') or \
                key.endswith('etag') or \
                key.endswith('fetched_at') or \
                key in self.model.github_ignore:
                del data[key]

        if saved_objects is None:
            saved_objects = SavedObjects()

        fields = {
            'simple': {},
            'fk': {},
            'many': {}
        }

        # run for each field in the dict
        for key, value in data.iteritems():

            # maybe we use a different field name on our side
            field_name = self.get_matching_field(key)

            try:
                # get information about the field
                field = self.model._meta.get_field(field_name)
            except models.FieldDoesNotExist:
                # there is not field for the given key, we pass to the next key
                continue
            else:
                is_field_direct = not field.auto_created or field.concrete
                is_field_m2m = field.is_relation and field.many_to_many

            # work depending of the field type
            # TODO: manage OneToOneField, not yet used in our models
            if is_field_m2m or not is_field_direct or isinstance(field, models.ForeignKey):
                # we have many objects to create: m2m
                # or we have an external object to create: fk
                if value:
                    model = field.related_model
                    defaults_related = {}

                    if defaults and 'related' in defaults:
                        if field_name in defaults['related']:
                            defaults_related = defaults['related'][field_name]
                        elif field_name in defaults['related'].get('*', {}):
                            defaults_related = defaults['related']['*'][field_name]
                        if '*' in defaults['related'] and '*' not in defaults_related:
                            defaults_related.update(defaults['related']['*'])

                    if is_field_m2m or not is_field_direct:  # not sure: a list for a "not direct ?" (a through ?)
                        # fields['many'][field_name] = model.objects\
                        #     .create_or_update_from_list(data=value,
                        #                                 defaults=defaults_related,
                        #                                 saved_objects=saved_objects)

                        # pass info to create objects later instead of creating
                        # them now as the model may need the current object to
                        # be fully created (a CommitFile need the Commit)
                        fields['many'][field_name] = {
                            'model': model,
                            'related_name': field.field.name if hasattr(field, 'field') else None,
                            'data': value,
                            'defaults': defaults_related,
                        }
                    else:
                        fields['fk'][field_name] = model.objects\
                            .create_or_update_from_dict(data=value,
                                                        defaults=defaults_related,
                                                        saved_objects=saved_objects)
                else:
                    if is_field_m2m or not is_field_direct:
                        fields['many'][field_name] = []
                    else:
                        fields['fk'][field_name] = None

            elif isinstance(field, models.DateTimeField):
                # we need to convert a datetimefield
                if value:
                    # all github datetime are utc, so we can remove the timezome
                    fields['simple'][field_name] = Connection.parse_date(value)
                else:
                    fields['simple'][field_name] = None

            else:
                # it's a simple field
                fields['simple'][field_name] = value

        # add default fields
        if defaults:
            for field_type, default_fields in defaults.iteritems():
                if field_type not in ('simple', 'fk', 'many'):
                    continue
                for field_name, value in default_fields.iteritems():
                    if field_name not in fields[field_type]:
                        fields[field_type][field_name] = value

        return fields


class WithRepositoryManager(GithubObjectManager):
    """
    This manager si to be used for models based on GithubObject which have a
    repository field that is a FK toward the Repository model.
    The get_object_fields_from_dict is enhance to find the matching repository
    based on the url field from github in case of github don't tell us to which
    repository belongs the object.
    """

    repository_url_field = 'url'

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        In addition to the default get_object_fields_from_dict, try to guess the
        repository the objects belongs to, from the url found in the data given
        by the github api. Only set if the repository is found.
        """
        from .models import Repository

        url = data.get(self.repository_url_field)

        fields = super(WithRepositoryManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)
        if not fields:
            return None

        # add the repository if needed
        if not fields['fk'].get('repository'):
            if url:
                repository = Repository.objects.get_by_url(url)
                if repository:
                    fields['fk']['repository'] = repository
            if not fields['fk'].get('repository'):
                # no repository found, don't save the object !
                return None

        return fields


class GithubUserManager(GithubObjectManager, UserManager):
    """
    This manager is for the GithubUser model, and is based on the default
    UserManager, and the GithubObjectManager to allow creation/update from data
    coming from the github api.
    The get_object_fields_from_dict is enhance to compute the is_organization
    flag.
    """

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        In addition to the default get_object_fields_from_dict, set the
        is_organization flag based on the value of the User field given by the
        github api.
        """

        is_org = data.get('type', 'User') == 'Organization'

        fields = super(GithubUserManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)
        if not fields:
            return None

        # add the is_organization field if needed
        if 'is_organization' not in fields['simple']:
            fields['simple']['is_organization'] = is_org

        return fields

    def get_deleted_user(self):
        """
        Return a user to use when the github api doesn't give us a user when
        we really need one
        """
        if not hasattr(self, '_deleted_user'):
            self._deleted_user, created = self.get_or_create(username='user.deleted')
        return self._deleted_user


class RepositoryManager(GithubObjectManager):
    """
    This manager extends the GithubObjectManager with helpers to find a
    repository based on an url or simply a path ({user}/{repos}).
    """
    path_finder = re.compile('^https?://api\.github\.com/repos/(?P<path>[^/]+/[^/]+)(?:/|$)')

    def get_path_from_url(self, url):
        """
        Taking an url, try to return the path ({user}/{repos}) of a repository,
        or None.
        """
        if not url:
            return None
        match = self.path_finder.match(url)
        if not match:
            return None
        return match.groupdict().get('path', None)

    def get_by_path(self, path):
        """
        Taking a path ({user}/{repos}), try to return the matching repository,
        or None if no one is found.
        """
        if not path:
            return None
        try:
            username, name = path.split('/')
        except ValueError:
            return None
        else:
            try:
                return self.get(owner__username=username, name=name)
            except self.model.DoesNotExist:
                return None

    def get_by_url(self, url):
        """
        Taking an url, try to return the matching repository by finding the path
        ({user}/{repos}) from the url and fetching from the db.
        Return None if no path or no matching repository found.
        """
        path = self.get_path_from_url(url)
        return self.get_by_path(path)


class IssueManager(WithRepositoryManager):
    """
    This manager extends the GithubObjectManager with helpers to find an
    issue based on an url or simply a path+number ({user}/{repos}/issues/{number}).
    It also provides an enhanced get_object_fields_from_dict method, to compute the
    is_pull_request flag, and set default values for labels and milestone
    repository.
    """
    issue_finder = re.compile('^https?://api\.github\.com/repos/(?:[^/]+/[^/]+)/(?:issues|pulls)/(?P<number>\w+)(?:/|$)')

    def get_number_from_url(self, url):
        """
        Taking an url, try to return the number of an issue, or None.
        """
        if not url:
            return None
        match = self.issue_finder.match(url)
        if not match:
            return None
        return match.groupdict().get('number', None)

    def get_by_repository_and_number(self, repository, number):
        """
        Taking a repository instance and an issue number, try to return the
        matching issue. or None if no one is found.
        """
        if not repository or not number:
            return None
        try:
            return self.get(repository_id=repository.id, number=number)
        except self.model.DoesNotExist:
            return None

    def get_by_url(self, url, repository=None):
        """
        Taking an url, try to return the matching issue by finding the repository
        by its path, and an issue number, and then fetching the issue from the db.
        Return None if no Issue if found.
        """
        if not repository:
            from .models import Repository
            repository = Repository.objects.get_by_url(url)
        if not repository:
            return None
        number = self.get_number_from_url(url)
        return self.get_by_repository_and_number(repository, number)

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        Override the default "get_object_fields_from_dict" by adding default
        value for the repository of labels, milestone and comments, if one is
        given as default for the issue.
        Also set the is_pull_request flag based on the 'diff_url' attribute of
        the 'pull_request' dict in the data given by the github api.
        If we have data from the pull-requests API (instead of the issues one),
        we also remove the github_id from the fields to avoid replacing it in
        the existing issue (note that github have different ids for a pull
        request and its associated issue, and that when fetching pull requests,
        we only do UPDATE, no CREATE)
        We also move some fields from sub-dicts to the main one to easy access
        (base and head sha/label in pull-request mode)

        """
        # if pull request, we may have the label and sha of base and head
        for boundary in ('base', 'head'):
            dikt = data.get(boundary, {})
            for field in ('label', 'sha'):
                if dikt.get(field):
                    data['%s_%s' % (boundary, field)] = dikt[field]

        try:
            is_pull_request = defaults['simple']['is_pull_request']
        except KeyError:
            is_pull_request = bool(data.get('diff_url', False))\
                   or bool(data.get('pull_request', {}).get('diff_url', False))

        fields = super(IssueManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)
        if not fields:
            return None

        # check if it's a pull request
        if 'is_pull_request' not in fields['simple']:
            fields['simple']['is_pull_request'] = is_pull_request

        # if we have a real pull request data (from the pull requests api instead
        # of the issues one), remove the github_id to not override the issue's one
        # but save it in github_pr_id
        if fields['simple'].get('head_sha') or fields['simple'].get('base_sha'):
            if 'github_id' in fields['simple']:
                fields['simple']['github_pr_id'] = fields['simple']['github_id']
                del fields['simple']['github_id']

        # when we fetch lists, mergeable status are not set, so we remove them from
        # fields to update to avoid losing previous values
        # if 'mergeable' in fields['simple']:
        if 'mergeable' in fields['simple'] and fields['simple']['mergeable'] is None:
            del fields['simple']['mergeable']
        if 'mergeable_state' in fields['simple'] and fields['simple']['mergeable_state'] in (None, 'unknown'):
            del fields['simple']['mergeable_state']

        # idem for "merged"
        if 'merged' in fields['simple'] and fields['simple']['merged'] is None:
            del fields['simple']['merged']

        return fields


class WithIssueManager(GithubObjectManager):
    """
    This base manager is for the models linked to an issue, with an enhanced
    get_object_fields_from_dict method, to get the issue and the repository.
    """

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        In addition to the default get_object_fields_from_dict, try to guess the
        issue the object belongs to, from the issue_url found in the data given
        by the github api. Doing the same for the repository. Only set if found.
        """
        from .models import Issue

        url = data.get('issue_url', data.get('pull_request_url', None))

        fields = super(WithIssueManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)
        if not fields:
            return None

        repository = fields['fk'].get('repository')

        # add the issue if needed
        if not fields['fk'].get('issue'):
            if url:
                issue = Issue.objects.get_by_url(url, repository)
                if issue:
                    fields['fk']['issue'] = issue

            if not fields['fk'].get('issue'):
                # no issue found, don't save the object !
                return None

        # and the repository
        if not repository:
            fields['fk']['repository'] = fields['fk']['issue'].repository

        return fields


class IssueCommentManager(WithIssueManager):
    """
    This manager is for the IssueComment model, with an enhanced
    get_object_fields_from_dict method (from WithIssueManager), to get the issue
    and the repository.
    """
    pass


class LabelTypeManager(models.Manager):
    """
    This manager, for the LabelType model, manage a cache by repository/label-name
    to quickly return label type and typed name for a label.
    """
    _name_cache = {}

    AUTO_TYPES = [
        (
            # Workflow - 1 - Assigned
            re.compile('^(?P<type_name>.+?)(?P<sep1>\s*[:#_\-]\s*)(?P<order>\d+)(?P<sep2>\s*[:#_\-]\s*)(?P<label>.+)$'),
            '%(type_name)s%(sep1)s{order}%(sep2)s{label}'
        ),
        (
            # [1] Workflow : Assigned
            re.compile('^(?P<sep1>[\[\(\{\-\.]?\s*)(?P<order>\d+)(?P<sep2>\s*[:#_\-\]\)\}\-\.]\s*)(?P<type_name>.+?)(?P<sep3>\s*[:#_\-]\s*)(?P<label>.+)$'),
            '%(sep1)s{order}%(sep2)s%(type_name)s%(sep3)s{label}'
        ),
        (
            # [Workflow] #2 Assigned
            re.compile('^(?P<sep1>[\[\(\{\-\.]?\s*)(?P<type_name>[^\[\(\{\]\)\}]+?)(?P<sep2>[\]\)\}\-\.]\s*)(?P<sep3>\s*[:#_\-]\s*)(?P<order>\d+)(?P<sep4>\s*[:#_\-]?\s*)(?P<label>.+)$'),
            '%(sep1)s%(type_name)s%(sep2)s%(sep3)s{order}%(sep4)s{label}'
        ),
        (
            # Estimate: 2
            re.compile('^(?P<type_name>.+?)(?P<sep1>\s*[:#_\-]\s*)(?P<label>(?P<order>\d+))$'),
            '%(type_name)s%(sep1)s{ordered-label}'
        ),
        (
            # Workflow - Assigned
            re.compile('^(?P<type_name>.+?)(?P<sep1>\s*[:#_\-]\s*)(?P<label>.+)$'),
            '%(type_name)s%(sep1)s{label}'
        ),
        (
            # [Workflow] Assigned
            re.compile('^(?P<sep1>[\[\(\{\-\.]?\s*)(?P<type_name>.+?)(?P<sep2>[\]\)\}\-\.]\s*)(?P<label>.+)$'),
            '%(sep1)s%(type_name)s%(sep2)s{label}'
        ),
    ]

    def _reset_cache(self, repository):
        """
        Clear all the cache for the given repository
        """
        self._name_cache.pop(repository.id, None)

    def get_for_name(self, repository, name):
        """
        Return the label_type and typed_name to use for a label in a repository.
        Use an internal cache to speed up future accesses.
        """
        if repository.id not in self._name_cache:
            self._name_cache[repository.id] = {}

        if name not in self._name_cache[repository.id]:
            found_label_type = None

            # search an existing label type
            for label_type in repository.label_types.all():
                if label_type.match(name):
                    found_label_type = label_type
                    break

            # try to add an automatic group
            if found_label_type is None:
                for auto_find_re, auto_format in self.AUTO_TYPES:
                    match = auto_find_re.match(name)
                    if match:
                        parts = match.groupdict()
                        format_string = auto_format % parts

                        found_label_type = repository.label_types.create(
                            name=parts['type_name'].capitalize(),
                            edit_mode=self.model.LABELTYPE_EDITMODE.FORMAT,
                            edit_details={'format_string': format_string},
                            regex=self.model.regex_from_format(format_string)
                        )

                        # stop the loop, we found what we wanted
                        break

            result = None
            if found_label_type:
                typed_name, order = found_label_type.get_name_and_order(name)
                result = (
                    found_label_type,
                    typed_name,
                    int(order) if order is not None else None,
                )

            self._name_cache[repository.id][name] = result

        return self._name_cache[repository.id][name]


class PullRequestCommentManager(WithIssueManager):
    """
    This manager is for the PullRequestComment model, with an enhanced
    get_object_fields_from_dict method to get the issue, the repository, and
    the entry point
    """

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        In addition to the default get_object_fields_from_dict, try to guess the
        issue the comment belongs to, from the pull_request_url found in the
        data given by the github api. Doing the same for the repository.
        Only set if found.
        Also get/create the entry_point: some fetched data are for the entry
        point, some others are for the comment)
        """
        from .models import PullRequestCommentEntryPoint

        fields = super(PullRequestCommentManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)

        if not fields:
            return None

        defaults_entry_points = {
            'fk': {
                'repository': fields['fk']['repository'],
                'issue': fields['fk']['issue'],
            }
        }

        entry_point = PullRequestCommentEntryPoint.objects\
                    .create_or_update_from_dict(data=data,
                                                defaults=defaults_entry_points,
                                                saved_objects=saved_objects)
        if entry_point:
            fields['fk']['entry_point'] = entry_point

        return fields


class CommentEntryPointManagerMixin(GithubObjectManager):
    """
    This manager is for the *CommentEntryPoint models, with an
    enhanced create_or_update_from_dict that will save the created_at (oldest
    from the comments) and updated_at (latest from the comments).
    Also save the user if it's the first one.
    """

    def create_or_update_from_dict(self, data, modes=MODE_ALL, defaults=None,
                                   fetched_at_field='fetched_at', etag_field='etag',
                                   saved_objects=None, force_update=False, etag=None,
                                   ignore_github_status=False):
        from .models import GithubUser

        try:
            created_at = Connection.parse_date(data['created_at'])
        except Exception:
            created_at = None
        try:
            updated_at = Connection.parse_date(data['updated_at'])
        except Exception:
            updated_at = None

        user = data.get('user')

        obj = super(CommentEntryPointManagerMixin, self)\
            .create_or_update_from_dict(data, modes, defaults, fetched_at_field, etag_field,
                                        saved_objects, force_update, etag, ignore_github_status=True)

        if not obj:
            return None

        update_fields = []

        if created_at and (not obj.created_at or created_at < obj.created_at):
            obj.created_at = created_at
            update_fields.append('created_at')
            if user:
                obj.user = GithubUser.objects.create_or_update_from_dict(
                                            user, saved_objects=saved_objects)
                update_fields.append('user')

        if updated_at and (not obj.updated_at or updated_at > obj.updated_at):
            obj.updated_at = updated_at
            update_fields.append('updated_at')

        if update_fields:
            obj.save(update_fields=update_fields)

        return obj


class PullRequestCommentEntryPointManager(CommentEntryPointManagerMixin):
    pass


class CommitManager(WithRepositoryManager):
    """
    This manager is for the Commit model, with an enhanced
    get_object_fields_from_dict method, to get the issue and the repository,
    and to reformat data in a flat way to match the model.
    Provides also an enhanced create_or_update_from_dict that will trigger a
    FetchCommitBySha job if files or comments where not provided
    """

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        Reformat data to have flat values to match the model
        """
        if 'commit' in data:
            c = data['commit']

            if 'message' in c:
                data['message'] = c['message']

            if 'comment_count' in c and 'files' in 'data':
                # In the list of commits of a PR, the comment_count is bugged (often 0)
                # But we know that we are in this case because we don't have the files of the commit
                # So we can keep the comment_count only if we have files, ie only when we directly
                # fetch the commit
                data['comment_count'] = c['comment_count']

            for user_type, date_field in (('author', 'authored'), ('committer', 'committed')):
                if user_type in c:
                    if 'date' in c[user_type]:
                        data['%s_at' % date_field] = c[user_type]['date']
                    for field in ('email', 'name'):
                        if field in c[user_type]:
                            data['%s_%s' % (user_type, field)] = c[user_type][field]

            if 'tree' in c:
                data['tree'] = c['tree']['sha']

        if 'stats' in data:
            for field in ('additions', 'deletions'):
                if field in data['stats']:
                    data[field] = data['stats'][field]

        if 'parents' in data:
            data['parents'] = [parent['sha'] for parent in data['parents']]
        else:
            data['parents'] = []

        return super(CommitManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)

    def create_or_update_from_dict(self, data, modes=MODE_ALL, defaults=None,
                                   fetched_at_field='fetched_at', etag_field='etag',
                                   saved_objects=None, force_update=False, etag=None,
                                   ignore_github_status=False):
        """
        In addition to the default create_or_update_from_dict, check if files
        where fetched and if not, launch a FetchCommitBySha to fetch them
        """
        obj = super(CommitManager, self).create_or_update_from_dict(
            data, modes, defaults,fetched_at_field, etag_field, saved_objects, force_update,
            etag, ignore_github_status=True)  # True because can only be created remotely

        only_commits = defaults and defaults.get('context', {}).get('only_commits', False)

        # We got commits from the list of commits of a PR, so we don't have files and comments
        if obj and not only_commits and (not obj.files_fetched_at or not obj.commit_comments_fetched_at):
            kwargs = {}
            if not obj.files_fetched_at:
                kwargs['force_fetch'] = 1
            else:
                kwargs['fetch_comments_only'] = 1
            if not obj.commit_comments_fetched_at:
                kwargs['fetch_comments'] = 1

            from gim.core.tasks import FetchCommitBySha
            FetchCommitBySha.add_job( '%s#%s' % (obj.repository_id, obj.sha), **kwargs)

        return obj

    def diff(self, first, second, as_files=False):

        first_files, second_files = [
            dict(commit.files.values_list('path', 'patch'))
            for commit in (first, second)
        ]

        all_paths = sorted(set(first_files.keys()) | set(second_files.keys()))

        by_paths = {}

        for path in all_paths:

            try:
                status = None

                if path in first_files and path not in second_files:
                    status = 'restored'
                elif path not in first_files and path in second_files:
                    status = 'added'

                patches = [files.get(path, '') or '' for files in first_files, second_files]
                patches = [patch + '\n' if not patch.endswith('\n') else patch for patch in patches]

                if not status and patches[0] == patches[1]:
                    status = 'same'

                if not status:
                    status =  'modified'

                by_paths[path] = {
                    'status': status,
                }

                if status == 'same':
                    continue

                patch = ''
                type_count = {}

                if status == 'added':
                    patch = patches[1]
                    lines = patch.split('\n')
                    type_count = Counter(line[0] for line in lines if line)

                else:
                    intro = '--- %(path)s\n+++ %(path)s\n' % {'path': path}

                    tmp_files = []
                    for patch in patches:
                        tmp_file = NamedTemporaryFile(delete=False)
                        tmp_file.write(intro)
                        tmp_file.write(patch)
                        tmp_file.close()

                        tmp_files.append(tmp_file.name)

                    try:
                        output = subprocess.check_output(['interdiff', tmp_files[0], tmp_files[1]])
                    except subprocess.CalledProcessError:
                        by_paths[path]['error'] = True
                    else:
                        lines = output.split('\n')[3:]
                        type_count = Counter(line[0] for line in lines if line)
                        patch = '\n'.join(lines)

                    finally:
                        for tmp_file in tmp_files:
                            os.unlink(tmp_file)

                if patch:
                    by_paths[path].update({
                        'patch': patch or '',
                        'nb_additions': type_count.get('+', 0),
                        'nb_deletions': type_count.get('-', 0),
                    })

            except Exception:
                by_paths.setdefault(path, {})['error'] = True

        if not as_files:
            return by_paths

        files = []
        from gim.core.models.files import FileMixin
        for path in sorted(by_paths):
            file_info = by_paths[path]
            status = file_info.get('status', 'modified')
            if status == 'same':
                continue
            random_sha = uuid4().hex
            random_sha += random_sha[:8]
            file = FileMixin(
                path=path,
                status=status,
                nb_additions=file_info.get('nb_additions', 0),
                nb_deletions=file_info.get('nb_deletions', 0),
                patch=file_info.get('patch', ''),
                sha=random_sha,
            )
            file.hunk_shas = list(get_encoded_hunks_from_patch(file.patch).keys())
            files.append(file)

        return files


class WithCommitManager(WithRepositoryManager):
    """
    This base manager is for the models linked to a commit, with an enhanced
    get_object_fields_from_dict method, to get the commit and the repository.
    """

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        In addition to the default get_object_fields_from_dict, try to guess the
        commit the object belongs to, from the commit_sha found in the data given
        by the github api. Only set if found.
        """
        from .models import Commit

        sha = data.get('commit_id', data.get('commit_sha', data.get('sha')))

        fields = super(WithCommitManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)
        if not fields:
            return None

        # add the commit if needed
        if not fields['fk'].get('commit'):
            if sha:
                try:
                    repository = fields['fk'].get('repository')
                    commit = repository.commits.get(sha=sha)
                except Commit.DoesNotExist:
                    pass
                else:
                    fields['fk']['commit'] = commit

            if not fields['fk'].get('commit'):
                if not self.model._meta.get_field('commit').null:
                    # no mandatory commit found, don't save the object !
                    return None

        return fields


class IssueEventManager(WithIssueManager):
    """
    This manager is for the IssueEvent model, with method to check references
    in other objects and create events for found references.
    """

    CHECK_REF = re.compile(r'(?:^|\W)#(\d+)(?:[^d]|$)')

    def check_references(self, obj, fields, user_field='user'):
        """
        Check if the given object has references to some issues in its text.
        The references are looked up from given fields of the object, using
        the CHECK_REF regex of the manager.
        An IssueEvent object is created for each reference.
        Once done for the object, existing events that do not apply anymore are
        removed.
        """
        from gim.core.models import Issue

        type_event = 'referenced_by_%s' % obj._meta.model_name

        existing_events_ids = obj.repository.issues_events.filter(
                                                    event=type_event,
                                                    related_object_id=obj.id
                                                ).values_list('id', flat=True)

        new_events_ids = set()
        for field in fields:
            val = getattr(obj, field)
            if not val:
                continue
            for number in self.CHECK_REF.findall(val):
                try:
                    issue = obj.repository.issues.get(number=number)
                except Issue.DoesNotExist:
                    break

                event, created = self.get_or_create(
                                    repository=obj.repository,
                                    issue=issue,
                                    event=type_event,
                                    related_object_id=obj.id,
                                    defaults={
                                        'user': getattr(obj, user_field),
                                        'created_at': obj.created_at,
                                        'related_object': obj,
                                    }
                                )
                new_events_ids.add(event.id)

        # remove old events
        for existing_event_id in existing_events_ids:
            if existing_event_id not in new_events_ids:
                try:
                    self.get(id=existing_event_id).delete()
                except self.model.DoesNotExist:
                    pass

        return new_events_ids


class PullRequestFileManager(WithIssueManager):
    tree_finder = re.compile('^https?://github\.com/(?:[^/]+/[^/]+)/blob/(?P<tree>[^/]+)')

    def get_tree_in_url(self, url):
        """
        Taking an url, try to return the tree sha
        """
        if not url:
            return None
        match = self.tree_finder.match(url)
        if not match:
            return None
        return match.groupdict().get('tree', None)

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        Set in data the tree got from the blob url
        """
        if 'blob_url' in data:
            data['tree'] = self.get_tree_in_url(data['blob_url'])

        return super(PullRequestFileManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)


class AvailableRepositoryManager(WithRepositoryManager):
    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        We have a dict which is repositories, with a "permissions" field, but we
        want a dict with a repository dict and a "permission" field which is
        normalized from the "permissions" one.
        """
        permission = None

        if 'permissions' in data:
            for perm in ('admin', 'push', 'pull'):  # order is important: higher permission first
                if data['permissions'].get(perm):
                    permission = perm
                    break

        return super(AvailableRepositoryManager, self).get_object_fields_from_dict(
            {'permission': permission, 'repository': data},
            defaults, saved_objects)


class CommitCommentManager(WithCommitManager):
    """
    This manager is for the CommitComment model, with an enhanced
    get_object_fields_from_dict method to get the commit, the repository, and
    the entry point
    """

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        In addition to the default get_object_fields_from_dict, get/create the
        entry_point: some fetched data are for the entry point, some others are
        for the comment)
        """
        from .models import CommitCommentEntryPoint

        fields = super(CommitCommentManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)
        if not fields:
            return None

        defaults_entry_points = {
            'fk': {
                'repository': fields['fk']['repository'],
            }
        }
        if 'commit' in fields['fk']:
            defaults_entry_points['fk']['commit'] = fields['fk']['commit']

        entry_point = CommitCommentEntryPoint.objects\
                    .create_or_update_from_dict(data=data,
                                                defaults=defaults_entry_points,
                                                saved_objects=saved_objects)
        if entry_point:
            fields['fk']['entry_point'] = entry_point

        return fields


class CommitCommentEntryPointManager(CommentEntryPointManagerMixin):
    pass


class IssueCommitsManager(BaseManager):
    pass


class CommitStatusManager(WithCommitManager):
    """
    This manager is for the CommitStatus model, with an enhanced
    get_object_fields_from_dict method to convert the state from a string to a value in
    GITHUB_COMMIT_STATUS_CHOICES
    """

    sha_finder = re.compile('^https://api.github\.com/repos/(?:[^/]+/[^/]+)/commits/(?P<sha>[\da-f]{40})/status')
    sha_finder_legacy = re.compile('^https://api.github\.com/repos/(?:[^/]+/[^/]+)/statuses/(?P<sha>[\da-f]{40})')

    def get_sha_in_url(self, url):
        """
        Taking an url, try to return the sha
        """
        if not url:
            return None
        match = self.sha_finder.match(url) or self.sha_finder_legacy.match(url)
        if not match:
            return None
        return match.groupdict().get('sha', None)

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        Convert the state given as a string from Github, to a value in  GITHUB_COMMIT_STATUS_CHOICES
        """

        if defaults is None:
            defaults = {}

        # To let WithCommitManager find a commit
        if not data.get('commit') and not defaults.get('fk', {}).get('commit') and not data.get('path'):
            if not data.get('url'):
                # We can't if the url of the status is not in the data
                return None
            data['sha'] = self.get_sha_in_url(data['url'])

        # Convert state
        state_str = data['state']
        try:
            data['state'] = [c.value for c in self.model.GITHUB_COMMIT_STATUS_CHOICES.entries
                             if state_str == c.constant.lower()][0]
        except IndexError:
            data['state'] = self.model.GITHUB_COMMIT_STATUS_CHOICES.OTHER

        # Default context
        if not data.get('context'):
            data['context'] = self.model._meta.get_field('context').default

        return super(CommitStatusManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)


class GithubNotificationManager(WithRepositoryManager):
    issue_finder = re.compile('^https?://api\.github\.com/repos/(?:[^/]+/[^/]+)/(?:issues|pulls)/(?P<number>\w+)(?:/|$)')

    def get_number_from_url(self, url):
        """
        Taking an url, try to return the number of an issue, or None.
        """
        if not url:
            return None
        match = self.issue_finder.match(url)
        if not match:
            return None
        return match.groupdict().get('number', None)

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):

        if data.get('subject'):

            if data['subject'].get('type').lower() not in ('issue', 'pullrequest'):
                return None

            if not data['subject'].get('url'):
                return None

            # We'll use the subject url to get the issue number
            data['url'] = data['subject']['url']

            data['issue_number'] = self.get_number_from_url(data['url'])

            if not data['issue_number']:
                return None

            data['title'] = data['subject'].get('title')

        fields = super(GithubNotificationManager, self).get_object_fields_from_dict(data, defaults,
                                                                                    saved_objects)

        if not fields:
            return None

        if not fields['fk']['repository']:
            return None

        # Fill the issue if we don't have it and we have the number
        if not fields['fk'].get('issue') and data.get('issue_number'):
            from gim.core.models import Issue

            repository = fields['fk']['repository']
            issue_number = data['issue_number']

            try:
                fields['fk']['issue'] = repository.issues.get(number=issue_number)
            except Issue.DoesNotExist:
                pass

        return fields

    def delete_missing_after_fetch(self, queryset):
        """
        By default we don't touch entries not fetched, but in the case with the parameter
        `all=false`, and a force-fetch, we get only unread ones, so it allows you to mark all the
        others (not fetched) as `read` (ie `unread=False`)
        """
        for notification in queryset.filter(manual_unread=False):
            notification.unread = False
            notification.save(update_fields=['unread'])


class MentionManager(models.Manager):

    content_types = {}

    @classmethod
    def get_content_type(cls, instance):
        model = instance.__class__
        if model not in cls.content_types:
            cls.content_types[model] = ContentType.objects.get_for_model(model)
        return cls.content_types[model]

    def add_users(self, issues, users, position, obj, users_cache=None):
        from gim.core.models import GithubUser

        if not users:
            self.remove_users(issues, position, obj)
            return

        users = OrderedDict((user.lower(), None) for user in users)

        for username in users:
            if users_cache is not None and username in users_cache:
                users[username] = users_cache[username]
            else:
                try:
                    users[username] = GithubUser.objects.get(username_lower=username)
                except GithubUser.DoesNotExist:
                    pass
                except GithubUser.MultipleObjectsReturned:
                    users[username] = GithubUser.objects.filter(username_lower=username)[0]
                finally:
                    if users_cache is not None:
                        users_cache[username] = users[username]

        content_type = self.get_content_type(obj)

        for issue in issues:

            existing_users = set(self.filter(
                issue=issue,
                position=position,
                content_type=content_type,
                object_id=obj.pk
            ).values_list('username', flat=True))

            if existing_users:
                usernames_to_remove = existing_users.difference(users.keys())
                if usernames_to_remove:
                    self.remove_users([issue], position, obj, usernames_to_remove)

                if len(existing_users - usernames_to_remove) == len(users):
                    # We already have all the users
                    return

            for username, user in users.items():
                self.get_or_create(
                    issue=issue,
                    username=username,
                    position=position,
                    content_type=content_type,
                    object_id=obj.pk,
                    defaults={
                        'user': user
                    }
                )

    def remove_users(self, issues, position, obj, usernames=None):
        filters = dict(
            issue_id__in=[i.id for i in issues],
            position=position,
            content_type=self.get_content_type(obj),
            object_id=obj.pk
        )

        if usernames:
            filters['username__in'] = list(usernames)

        self.filter(**filters).delete()

    def _set_for_body(self, issues, position, obj, users_cache=None, forced_users=None):
        if obj.body_html:
            self.add_users(
                issues,
                self.model.RE_HTML.findall(obj.body_html) if forced_users is None else forced_users,
                position,
                obj,
                users_cache
            )
        elif obj.body:
            self.add_users(
                issues,
                self.model.RE_TEXT.findall(obj.body) if forced_users is None else forced_users,
                position,
                obj,
                users_cache
            )

    def set_for_issue(self, issue, users_cache=None, forced_users=None):
        if issue.title:
            self.add_users(
                [issue],
                self.model.RE_TEXT.findall(issue.title) if forced_users is None else forced_users,
                self.model.MENTION_POSITIONS.ISSUE_TITLE,
                issue,
                users_cache
            )
        self._set_for_body([issue], self.model.MENTION_POSITIONS.ISSUE_BODY, issue, users_cache,
                           forced_users)

    def set_for_issue_comment(self, issue_comment, users_cache=None, forced_users=None):
        self._set_for_body([issue_comment.issue], self.model.MENTION_POSITIONS.ISSUE_COMMENT,
                            issue_comment, users_cache, forced_users)

    def set_for_pr_comment(self, pr_comment, users_cache=None, forced_users=None):
        self._set_for_body([pr_comment.issue], self.model.MENTION_POSITIONS.PR_CODE_COMMENT,
                            pr_comment, users_cache, forced_users)

    def set_for_commit(self, commit, users_cache=None, forced_users=None):
        issues = list(commit.issues.all())
        if not issues:
            return

        if commit.message:
            self.add_users(
                issues,
                self.model.RE_TEXT.findall(commit.message) if forced_users is None else forced_users,
                self.model.MENTION_POSITIONS.COMMIT_BODY,
                commit,
                users_cache
            )

    def set_for_commit_comment(self, commit_comment, users_cache=None, forced_users=None):
        issues = list(commit_comment.commit.issues.all())
        if not issues:
            return

        if not commit_comment.entry_point_id or commit_comment.entry_point.position is None:
            position = self.model.MENTION_POSITIONS.COMMIT_COMMENT
        else:
            position = self.model.MENTION_POSITIONS.COMMIT_CODE_COMMENT

        self._set_for_body(issues, position, commit_comment, users_cache, forced_users)

    def _set_for_many(self, qs, filters, method, users_cache=None):
        if users_cache is None:
            users_cache = {}

        qs = queryset_iterator(qs.filter(filters))

        for obj in qs:
            method(obj, users_cache)

    def set_for_issues(self, qs=None, users_cache=None):
        from gim.core.models import Issue

        self._set_for_many(
            qs or Issue.objects,
            Q(body_html__contains='class="user-mention"') | Q(title__iregex='(^|[^\w])@\w+'),
            self.set_for_issue,
            users_cache
        )

    def set_for_commits(self, qs=None, users_cache=None):
        from gim.core.models import Commit

        self._set_for_many(
            qs or Commit.objects,
            Q(message__iregex='(^|[^\w])@\w+'),
            self.set_for_commit,
            users_cache
        )

    def set_for_issue_comments(self, qs=None, users_cache=None):
        from gim.core.models import IssueComment

        self._set_for_many(
            (qs or IssueComment.objects).select_related('issue'),
            Q(body_html__contains='class="user-mention"'),
            self.set_for_issue_comment,
            users_cache
        )

    def set_for_pr_comments(self, qs=None, users_cache=None):
        from gim.core.models import PullRequestComment

        self._set_for_many(
            (qs or PullRequestComment.objects).select_related('issue'),
            Q(body_html__contains='class="user-mention"'),
            self.set_for_pr_comment,
            users_cache
        )

    def set_for_commit_comments(self, qs=None, users_cache=None):
        from gim.core.models import CommitComment

        self._set_for_many(
            (qs or CommitComment.objects).select_related('commit'),
            Q(body_html__contains='class="user-mention"'),
            self.set_for_commit_comment,
            users_cache
        )


class ProjectManager(WithRepositoryManager):
    repository_url_field = 'owner_url'
    project_finder_by_number = re.compile('^https?://api\.github\.com/repos/(?:[^/]+/[^/]+)/projects/(?P<number>\d+)(?:/|$)')
    project_finder_by_id = re.compile('^https?://api\.github\.com/projects/(?P<github_id>\d+)(?:/|$)')

    def get_number_from_url(self, url):
        """
        Taking an url, try to return the number of a project, or None.
        """
        if not url:
            return None
        match = self.project_finder_by_number.match(url)
        if not match:
            return None
        return match.groupdict().get('number', None)

    def get_github_id_from_url(self, url):
        """
        Taking an url, try to return the github_id of a project, or None.
        """
        if not url:
            return None
        match = self.project_finder_by_id.match(url)
        if not match:
            return None
        return match.groupdict().get('github_id', None)

    def get_by_repository_and_number(self, repository, number):
        """
        Taking a repository instance and a project number, try to return the
        matching project. or None if no one is found.
        """
        if not repository or not number:
            return None
        try:
            return self.get(repository_id=repository.id, number=number)
        except self.model.DoesNotExist:
            return None

    def get_by_github_id(self, github_id):
        """
        Taking a project github_id, try to return the
        matching project. or None if no one is found.
        """
        if not github_id:
            return None
        try:
            return self.get(github_id=github_id)
        except self.model.DoesNotExist:
            return None

    def get_by_url(self, url, repository=None):
        """
        Taking an url, try to return the matching project by finding its github id, or
        its repository by its path and a project number, then fetching the project from the db.
        Return None if no Project if found.
        """
        github_id = self.get_github_id_from_url(url)
        if github_id:
            return self.get_by_github_id(github_id)

        if not repository:
            from .models import Repository
            repository = Repository.objects.get_by_url(url)
        if not repository:
            return None
        number = self.get_number_from_url(url)
        return self.get_by_repository_and_number(repository, number)


class ColumnManager(GithubObjectManager):

    column_finder = re.compile('^https?://api\.github\.com/projects/columns/(?P<id>\d+)(?:/|$)')

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        In addition to the default get_object_fields_from_dict, try to guess the
        project the objects belongs to, from the url found in the data given
        by the github api. Only set if the project is found.
        And finally get the position from the context and increment it.
        """
        from .models import Column, Project

        # we need a project
        project = defaults.get('fk', {}).get('project')
        if not project:
            url = data.get('project_url')
            if url:
                project = Project.objects.get_by_url(url)
                defaults.setdefault('fk', {})['project'] = project

        if not project:
            # no project found, don't save the object !
            return None

        if 'position' not in data and hasattr(saved_objects, 'context'):
            position_key = 'project#%s:column-position' % project.github_id
            position = saved_objects.context.get(position_key, 0) + 1
            data['position'] = saved_objects.context[position_key] = position
        else:
            # do we have this column  positioned?
            try:
                project.columns.get(github_id=data['id'], position__isnull=False)
            except Column.DoesNotExist:
                # we don't have it so we'll put it at the end
                last_position = project.columns.exclude(github_id=data['id']).aggregate(Max('position'))['position__max']
                data['position'] = last_position + 1 if last_position else 1

        fields = super(ColumnManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)
        if not fields:
            return None

        return fields

    def get_github_id_from_url(self, url):
        """
        Taking an url, try to return the github_id of a column, or None.
        """
        if not url:
            return None
        match = self.column_finder.match(url)
        if not match:
            return None
        return match.groupdict().get('id', None)

    def get_by_github_id(self, github_id):
        """
        Taking a project instance and a column id, try to return the
        matching column. or None if no one is found.
        """
        if not github_id:
            return None
        try:
            return self.get(github_id=github_id)
        except self.model.DoesNotExist:
            return None

    def get_by_url(self, url, project=None):
        """
        Taking an url, try to return the matching column by finding the project
        by its path, and a column github_id, and then fetching the column from the db.
        Return None if no Issue if found.
        """
        github_id = self.get_github_id_from_url(url)
        return self.get_by_github_id(github_id)


class CardIssueNotAvailable(ValueError):
    def __init__(self, repository_id, issue_number):
        self.repository_id = repository_id
        self.issue_number = issue_number
        super(CardIssueNotAvailable, self).__init__(
            'Issue %s:%s not yet available' % (repository_id, issue_number)
        )


class CardManager(GithubObjectManager):

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):
        """
        In addition to the default get_object_fields_from_dict, try to guess the
        column the objects belongs to, from the url found in the data given
        by the github api. Only set if the column is found.
        """
        from .models import Card, Column, Issue

        # we need a column
        column = defaults.get('fk', {}).get('column')
        if not column:
            url = data.get('column_url')
            if url:
                column = Column.objects.get_by_url(url)

        if not column:
            # no column found, don't save the object !
            return None

        issue_url = data.get('content_url')
        is_issue_expected = issue_url and not data.get('note')

        # we may have an issue
        issue = defaults.get('fk', {}).get('issue')
        if not issue:
            url = issue_url
            if url:
                issue = Issue.objects.get_by_url(url)

        if 'position' not in data and 'position' not in defaults.get('simple', {}):
            if hasattr(saved_objects, 'context'):
                position_key = 'column#%s:card-position' % column.github_id
                position = saved_objects.context.get(position_key, 0) + 1
                data['position'] = saved_objects.context[position_key] = position
            else:
                # do we have the card, and in this column, positioned?
                try:
                    column.cards.get(github_id=data['id'], position__isnull=False)
                except Card.DoesNotExist:
                    # we don't have it so we'll put it at the end
                    last_position = column.cards.exclude(github_id=data['id']).aggregate(Max('position'))['position__max']
                    data['position'] = last_position + 1 if last_position else 1

        fields = super(CardManager, self).get_object_fields_from_dict(
                                                data, defaults, saved_objects)
        if not fields:
            return None

        if not fields['fk'].get('column'):
            fields['fk']['column'] = column

        if is_issue_expected and not fields['fk'].get('issue'):
            if not issue:
                raise CardIssueNotAvailable(
                    fields['fk']['column'].project.repository_id,
                    Issue.objects.get_number_from_url(issue_url)
                )

            fields['fk']['issue'] = issue

        fields['simple']['type'] = Card.CARDTYPE.ISSUE if fields['fk'].get('issue') else Card.CARDTYPE.NOTE

        return fields


class ProtectedBranchManager(WithRepositoryManager):

    repository_url_field = 'protection_url'

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):

        # convert data tree to usable data
        if data.get('protection_url'):  # we're from the list of branches
            # we want only protected branches
            if not data.get('protected', False):
                return None

            # but we do nothing more, we let the fetch of individual branch protection info do the rest

        else:  # we're from a single branch
            data['protection_url'] = data.pop('url')  # to find the repository

            required_status_checks = data.pop('required_status_checks', {})
            if required_status_checks:
                data['require_status_check'] = True
                data['require_status_check_include_admins'] = required_status_checks.get('include_admins', False)
                data['require_up_to_date'] = required_status_checks.get('strict', False)
            else:
                data['require_status_check'] = data['require_status_check_include_admins'] = data['require_up_to_date'] = False

            required_pull_request_reviews = data.pop('required_pull_request_reviews', {})
            if required_pull_request_reviews:
                data['require_approved_review'] = True
                data['require_approved_review_include_admins'] = required_pull_request_reviews.get('include_admins', False)
            else:
                data['require_approved_review'] = data['require_approved_review_include_admins'] = False

        return super(ProtectedBranchManager, self).get_object_fields_from_dict(data, defaults, saved_objects)


class PullRequestReviewManager(WithIssueManager):
    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):

        if not defaults:
            defaults = {}
        if 'fk' not in defaults:
            defaults['fk'] = {}

        # we should have a pull request
        issue = defaults['fk'].get('issue')
        if not issue:
            if not data.get('pull_request_url'):  # rest api

                if not data.get('pullRequest'):  # graphql
                    return None

                issue_number = data['pullRequest']['number']
                repository_github_id = data['pullRequest']['repository']['id']

                from gim.core.models import Issue
                try:
                    defaults['fk']['issue'] = Issue.objects.get(
                        repository__github_id=repository_github_id,
                        number=issue_number
                    )
                except Issue.DoesNotExist:
                    return None

                # remove issue information from data
                data.pop('pullRequest', None)

        if data.get('author') and not data['author'].get('type'):
            # we know the author is not an organisation
            data['author']['type'] = 'User'

        # convert the commit sha
        if data.get('commit'):
            data['head_sha'] = data['commit']['oid']
            del data['commit']

        # and the comments count
        if data.get('comments'):
            data['comments_count'] = data['comments'].get('totalCount', 0)
            del data['comments']

        fields = super(PullRequestReviewManager, self).get_object_fields_from_dict(data, defaults, saved_objects)

        if not fields['fk'].get('author'):
            from gim.core.models import GithubUser
            fields['fk']['author'] = GithubUser.objects.get_deleted_user()

        fields['simple']['displayable'] = bool(
            fields['simple']['state'] != self.model.REVIEW_STATES.COMMENTED
            or fields['simple']['comments_count'] > 1
            or (fields['simple'].get('body') or '').strip()
        )

        return fields


class GitHeadManager(WithRepositoryManager):

    def get_object_fields_from_dict(self, data, defaults=None, saved_objects=None):

        # Only for heads
        if not data.get('ref', '').startswith('refs/heads/'):
            return None

        # Remove 'refs/heads/' prefix
        data['ref'] = data['ref'][11:]

        # Only if commits
        if data.get('object', {}).get('type', '') != 'commit':
            return None

        # Extract the sha of the commit
        data['sha'] = data['object']['sha']
        if not data['sha']:
            return None

        del data['object']

        return super(GitHeadManager, self).get_object_fields_from_dict(data, defaults, saved_objects)
