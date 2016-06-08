# -*- coding: utf-8 -*-

from django.utils.html import escape

from gim.core.models import GITHUB_COMMIT_STATUS_CHOICES, GithubUser
from gim.front.diff import HtmlDiff, HtmlDiffWithoutControl
from gim.front.templatetags.frontutils import avatar_size


class Renderer(object):
    USER_HTML_TEMPLATE = '<strong><img class="avatar-tiny img-circle lazyload" src="%(default_avatar)s" data-src="%(full_avatar_url)s"> %(username)s</strong>'
    STRONG = '<strong>%s</strong>'

    def __init__(self, event):
        self.event = event

    def helper_render_user(self, user, mode):
        if mode == 'text':
            return user['username']
        else:
            data = dict(user,
                default_avatar=GithubUser.get_default_avatar(),
                full_avatar_url=avatar_size(user['full_avatar_url'], 24),
            )
            return self.USER_HTML_TEMPLATE % data

    def helper_strong(self, value, mode, quote_if_text=True):
        if mode == 'text':
            return '"%s"' % value if quote_if_text else value
        else:
            return self.STRONG % escape(value)


class IssueRenderer(Renderer):

    def render_event_title(self, mode):
        return '[%(is_update)s] %(type)s #%(number)s "%(title)s"' % {
            'is_update': 'changed' if self.event.is_update else 'created',
            'type': self.event.issue.type.capitalize(),
            'number': self.event.issue.number,
            'title': self.event.issue.title,
        }

    def render_part_title(self, part, mode):
        new, old = part.new_value, part.old_value

        if mode == 'html':
            diff = HtmlDiffWithoutControl.diff(old['title'], new['title'], n=0, css=False)
            return '<span>Title has changed:</span>' + diff

        # part must not be created if no old title
        title = 'Old title was "%(title)s"'
        params = {'title': self.helper_strong(old['title'], mode, quote_if_text=False)}
        return title % params

    def render_part_body(self, part, mode):
        new, old = part.new_value, part.old_value

        if mode == 'html':
            diff = HtmlDiff.diff(old['body'], new['body'], n=2, css=False)
            return '<span>Description has changed:</span>' + diff

        raise NotImplementedError()

    def render_part_state(self, part, mode):
        new, old = part.new_value, part.old_value

        title = 'Reopened' if new['state'] == 'open' else 'Closed'

        if 'by' in new:
            title += ' by %(by)s'
            params = {'by': self.helper_render_user(new['by'], mode)}
            title = title % params

        return title

    def render_part_mergeable(self, part, mode):
        new, old = part.new_value, part.old_value

        mergeable_state = ''
        if 'mergeable_state' in new:
            mergeable_state = (' (reason: %s)' if mode == 'text' else ' (reason: <strong>%s</strong>)') % new['mergeable_state']

        if old:
            title = 'Now mergeable' if new['mergeable'] else 'Not mergeable anymore'
        else:
            title = 'Mergeable' if new['mergeable'] else 'Not mergeable'

        if mode == 'html':
            klass = 'open' if new['mergeable'] else 'closed'
            title = '<strong class="text-%s">%s</strong>' % (klass, title)
        if not new['mergeable']:
            title += mergeable_state

        return title

    def render_part_mergeable_state(self, part, mode):
        new, old = part.new_value, part.old_value

        # let the mergeable part display all if it exists
        if part.event.get_part('mergeable'):
            return None

        klass = 'open' if new['mergeable'] else 'closed'
        title = ('New mergeable status: %s, reason: %s'
                 if mode == 'text'
                else 'New mergeable status: <strong class="text-%s">%s</strong>, reason: <strong>%s</strong>') % (
                        klass,
                        'Mergeable' if new['mergeable'] else 'Not mergeable',
                        new['mergeable_state'])

        if (old.get('mergeable_state') or 'unknown') != 'unknown':
            title += (' (was %s)' if mode == 'text' else ' (was: <strong>%s</strong>)') % old['mergeable_state']

        return title

    def render_part_merged(self, part, mode):
        new, old = part.new_value, part.old_value

        if old and old['merged'] is False:
            title = 'Merged' if new['merged'] else 'Unmerged ?!?'
        else:
            title = 'Merged' if new['merged'] else 'Not merged'

        if 'by' in new:
            title += ' by %(by)s'
            params = {'by': self.helper_render_user(new['by'], mode)}
            title = title % params

        return title

    def helper_get_commit_status(self, value):
        return GITHUB_COMMIT_STATUS_CHOICES.for_value(int(value or 0))

    def render_part_last_head_status(self, part, mode):
        new, old = part.new_value, part.old_value
        new_status = self.helper_get_commit_status(new['last_head_status'])

        if mode == 'text':
            title = 'New checks status: %s' % new_status.display
        else:
            title = 'New checks status: <strong><span class="state-%s">%s</span></strong>' % (
                new_status.constant.lower(),
                new_status.display,
            )

        if 'count_by_state' in new:
            parts = []
            for state, count in new['count_by_state'].items():
                status = self.helper_get_commit_status(state or 0)
                if mode == 'text':
                    parts.append('%s %s' % (count, status.display.lower()))
                else:
                    parts.append('%s <span class="state-%s">%s</span>' % (
                        count, status.constant.lower(), status.display.lower()))
            if len(parts) == 1:
                title += ', with %s.' % parts[0]
            elif len(parts) > 1:
                title += ', with %s and %s.' % (', '.join(parts[:-1]), parts[-1])

        if old['last_head_status']:
            old_status = self.helper_get_commit_status(old['last_head_status'])
            if mode == 'text':
                title += ' (previously %s)' % old_status.display
            else:
                title += ' (previously <span class="state-%s">%s</span>)' % (
                old_status.constant.lower(),
                old_status.display,
            )

        return title

    def render_part_assignee(self, part, mode):
        # now we have a m2m, not a fk, but we keep this method for old events

        new, old = part.new_value, part.old_value

        if new and old:
            title = 'Assigned to %(new_assignee)s (previously %(old_assignee)s)'
        elif new:
            title = 'Assigned to %(new_assignee)s'
        elif old:
            title = '%(unassigned)s (previously assigned to %(old_assignee)s)'
        else:
            title = '%(unassigned)s'

        params = {'unassigned': self.helper_strong('Unassigned', mode, quote_if_text=False)}
        if new:
            params['new_assignee'] = self.helper_render_user(new, mode)
        if old:
            params['old_assignee'] = self.helper_render_user(old, mode)

        return title % params

    def render_part_assignees(self, part, mode):

        new, old = part.new_value, part.old_value
        tag = ('', '') if mode == 'text' else ('<span>', '</span>')
        sep = '\n' if mode == 'text' else '<br/>'

        result_parts = []
        if new and new.get('assignees'):
            result_parts.append((
                '%(tag0)sAdded assignee%(plural)s: %(tag1)s %(assignees)s',
                new['assignees'],
            ))

        if old and old.get('assignees'):
            result_parts.append((
                '%(tag0)sRemoved assignee%(plural)s: %(tag1)s %(assignees)s',
                old['assignees'],
            ))

        result = []
        for title, assignees in result_parts:
            params = {
                'tag0': tag[0],
                'tag1': tag[1],
                'assignees': ', '.join(self.helper_render_user(assignee, mode) for assignee in assignees),
                'plural': 's' if len(assignees) < 1 else '',
            }
            result.append(title % params)

        return sep.join(result)

    def render_part_milestone(self, part, mode):
        new, old = part.new_value, part.old_value

        if new and old:
            title = 'Milestone set to "%(new_milestone)s" (previously "%(old_milestone)s")'
        elif new:
            title = 'Milestone set to "%(new_milestone)s"'
        elif old:
            title = 'Milestone %(removed)s (previously set to "%(old_milestone)s")'
        else:
            title = 'No milestone set'

        params = {'removed': self.helper_strong('removed', mode, quote_if_text=False)}
        if new:
            params['new_milestone'] = self.helper_strong(new['title'], mode, quote_if_text=False)
        if old:
            params['old_milestone'] = self.helper_strong(old['title'], mode, quote_if_text=False)

        return title % params

    def helper_render_labels(self, labels, mode):
        if mode == 'text':
            return ', '.join(['"%s"' % l['name'] for l in labels])
        else:
            return '<ul class="unstyled">%s</ul>' % (''.join([
                '<li style="border-bottom-color: #%(color)s;">%(name)s</li>' % {
                    'name': escape(l['name']),
                    'color': l['color']
                } for l in labels
            ]))

    def render_part_labels(self, part, mode):
        new, old = part.new_value, part.old_value
        tag = ('', '') if mode == 'text' else ('<span>', '</span>')
        if new and new.get('labels'):
            title = '%(tag0)sAdded label%(plural)s:%(tag1)s %(labels)s'
            labels = new['labels']
        else:
            title = '%(tag0)sRemoved label%(plural)s:%(tag1)s %(labels)s'
            labels = old['labels']

        params = {
            'tag0': tag[0],
            'tag1': tag[1],
            'labels': self.helper_render_labels(labels, mode),
            'plural': 's' if len(labels) > 1 else '',
        }

        return title % params

    def render_part_label_type(self, part, mode):
        new, old = part.new_value, part.old_value
        if new['labels'] == old['labels']:
            return None

        added = new.get('added')
        removed = new.get('removed')

        params = {'type': self.helper_strong(new['label_type']['name'], mode, quote_if_text=False)}

        if new['labels'] and old['labels']:
            title = '%(type)s was set to %(after)s'
            changed = ''
            if len(new['labels']) == len(old['labels']) == 1:
                changed += 'previously %(before)s'
            else:
                if added:
                    changed += 'added %(added)s'
                if removed:
                    if added:
                        changed += ', '
                    changed += 'removed %(removed)s'
            if changed:
                title += ' (' + changed + ')'
        elif new['labels']:
            title = '%(type)s was set to %(after)s'
        else:
            title = '%(type)s was unset (previously %(before)s)'

        if new['labels']:
            params['after'] = self.helper_render_labels(new['labels'], mode)
        if old['labels']:
            params['before'] = self.helper_render_labels(old['labels'], mode)
        if added:
            params['added'] = self.helper_render_labels(added, mode)
        if removed:
            params['removed'] = self.helper_render_labels(removed, mode)

        return title % params


class IssueRendererCollapsableTitleAndBody(IssueRenderer):

    def render_part_title(self, part, mode):
        new, old = part.new_value, part.old_value

        if mode == 'html':
            diff = HtmlDiffWithoutControl.diff(old['title'], new['title'], n=0, css=False)
            collaspe_id = u'part-' + str(part.id)
            return u'<span class="collapsible">Title has changed</span><span data-toggle="collapse" data-target="#' + collaspe_id + u'" title="Toggle diff">…</span><div class="collapse" id="' + collaspe_id + u'">' + diff + u'</div>'

        return super(IssueRendererCollapsableTitleAndBody, self).render_part_title(part, mode)

    def render_part_body(self, part, mode):
        new, old = part.new_value, part.old_value

        if mode == 'html':
            diff = HtmlDiff.diff(old['body'], new['body'], n=2, css=False)
            collaspe_id = u'part-' + str(part.id)
            return u'<span class="collapsible">Description has changed</span><span data-toggle="collapse" data-target="#' + collaspe_id + u'" title="Toggle diff">…</span><div class="collapse" id="' + collaspe_id + u'">' + diff + u'</div>'

        return super(IssueRendererCollapsableTitleAndBody, self).render_part_body(part, mode)
