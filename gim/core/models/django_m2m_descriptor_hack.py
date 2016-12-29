"""
In the old days, django did a clear+add when updating m2m values.
We changed this by doing a remove of values not present anymore, and
adding the new one, surrounding the remove + add by sending a "replace"
signal: "pre_replace" and "post_replace"
Now django correctly does a remove + add, but without a global signal,
and we prefer to keep the "replace" way to allow better tracking of updates.
So we replace the "set" method of the related manager, adding our signal
"""

from django.db import router, transaction
from django.db.models import signals
from django.db.models.fields.related_descriptors import (
    create_forward_many_to_many_manager as default_create_forward_many_to_many_manager,
    ManyToManyDescriptor,
    create_reverse_many_to_one_manager as default_create_reverse_many_to_one_manager,
    ReverseManyToOneDescriptor,

)
from django.utils.functional import cached_property


def create_forward_many_to_many_manager(superclass, rel, reverse):
    klass = default_create_forward_many_to_many_manager(superclass, rel, reverse)

    def ManyRelatedManager__set(self, objs, **kwargs):
        if not rel.through._meta.auto_created:
            opts = self.through._meta
            raise AttributeError(
                "Cannot set values on a ManyToManyField which specifies an "
                "intermediary model. Use %s.%s's Manager instead." %
                (opts.app_label, opts.object_name)
            )

        # Force evaluation of `objs` in case it's a queryset whose value
        # could be affected by `manager.clear()`. Refs #19816.
        objs = tuple(objs)

        clear = False  # CHANGED: we enforce False instead of `kwargs.pop('clear', False)`

        db = router.db_for_write(self.through, instance=self.instance)
        with transaction.atomic(using=db, savepoint=False):
            if clear:
                self.clear()
                self.add(*objs)
            else:
                old_ids = set(self.using(db).values_list(self.target_field.target_field.attname, flat=True))

                new_objs = []
                obj_ids = set()  # ADDED
                for obj in objs:
                    obj_ids.add(obj.pk if isinstance(obj, self.model) else obj)  # ADDED
                    fk_val = (
                        self.target_field.get_foreign_related_value(obj)[0]
                        if isinstance(obj, self.model) else obj
                    )
                    if fk_val in old_ids:
                        old_ids.remove(fk_val)
                    else:
                        new_objs.append(obj)

                # ADDED
                if not hasattr(self.instance, '_signal_replace_mode'):
                    self.instance._signal_replace_mode = {}
                self.instance._signal_replace_mode[self.model] = True

                signals.m2m_changed.send(sender=self.through, action='pre_replace',
                    instance=self.instance, reverse=self.reverse,
                    model=self.model, pk_set=obj_ids, using=db)
                # /ADDED

                self.remove(*old_ids)
                self.add(*new_objs)

                # ADDED
                signals.m2m_changed.send(sender=self.through, action='post_replace',
                    instance=self.instance, reverse=self.reverse,
                    model=self.model, pk_set=obj_ids, using=db)

                self.instance._signal_replace_mode[self.model] = False
                # /ADDED

    ManyRelatedManager__set.alters_data = True

    klass.set = ManyRelatedManager__set

    return klass


def ManyToManyDescriptor__related_manager_cls(self):
    related_model = self.rel.related_model if self.reverse else self.rel.model

    return create_forward_many_to_many_manager(
        related_model._default_manager.__class__,
        self.rel,
        reverse=self.reverse,
    )

ManyToManyDescriptor.related_manager_cls = cached_property(ManyToManyDescriptor__related_manager_cls)


def create_reverse_many_to_one_manager(superclass, rel):
    klass = default_create_reverse_many_to_one_manager(superclass, rel)

    def RelatedManager__set(self, objs, **kwargs):
        # Force evaluation of `objs` in case it's a queryset whose value
        # could be affected by `manager.clear()`. Refs #19816.
        objs = tuple(objs)

        bulk = kwargs.pop('bulk', True)
        clear = False  # CHANGED: we enforce False instead of `kwargs.pop('clear', False)`

        if self.field.null:
            db = router.db_for_write(self.model, instance=self.instance)
            with transaction.atomic(using=db, savepoint=False):
                if clear:
                    self.clear()
                    self.add(*objs, bulk=bulk)
                else:
                    old_objs = set(self.using(db).all())
                    new_objs = []
                    obj_ids = set()  # ADDED
                    for obj in objs:
                        obj_ids.add(obj.pk)  # ADDED
                        if obj in old_objs:
                            old_objs.remove(obj)
                        else:
                            new_objs.append(obj)

                    # ADDED
                    if not hasattr(self.instance, '_signal_replace_mode'):
                        self.instance._signal_replace_mode = {}
                    self.instance._signal_replace_mode[self.model] = True

                    signals.m2m_changed.send(sender=self.through, action='pre_replace',
                        instance=self.instance, reverse=self.reverse,
                        model=self.model, pk_set=obj_ids, using=db)
                    # /ADDED

                    self.remove(*old_objs, bulk=bulk)
                    self.add(*new_objs, bulk=bulk)

                    # ADDED
                    signals.m2m_changed.send(sender=self.through, action='post_replace',
                        instance=self.instance, reverse=self.reverse,
                        model=self.model, pk_set=obj_ids, using=db)

                    self.instance._signal_replace_mode[self.model] = False
                    # /ADDED

        else:
            # ADDED NOTHING BUT IT'S NOT REALLY A REPLACE, HERE :-/
            self.add(*objs, bulk=bulk)

    RelatedManager__set.alters_data = True

    klass.set = RelatedManager__set

    return klass


def ReverseManyToOneDescriptor__related_manager_cls(self):
    related_model = self.rel.related_model

    return create_reverse_many_to_one_manager(
        related_model._default_manager.__class__,
        self.rel,
    )


ReverseManyToOneDescriptor.related_manager_cls = cached_property(ReverseManyToOneDescriptor__related_manager_cls)
