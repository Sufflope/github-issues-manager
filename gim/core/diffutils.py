# -*-coding: utf8 -*-

import hashlib
from collections import OrderedDict

import whatthepatch



DIFF_LINE_TYPES = {
    '@': 'comment',
    '+': 'added',
    '-': 'removed',
    ' ': '',
}

LINE_INCREMENTERS = {
    '@': [0, 0],
    '+': [0, 1],
    '-': [1, 0],
    ' ': [1, 1],
}


MANUAL_HUNK_SPLIT_NOTE = ' (manual split)'

HUNK_HEADER_TEMPLATE = u'@@ -%s,%s +%s,%s @@%s'

HUNK_HEADER_START = u'@@'


def hunk_as_string(hunk):
    if isinstance(hunk, basestring):
        return hunh
    return '\n'.join(hunk)


def hunk_as_lines(hunk, mas_lines=-1):
    if isinstance(hunk, basestring):
        return hunk.encode('utf-8').split('\n')
    return hunk


def split_patch_into_hunks(patch):
    if not patch or not patch.startswith(HUNK_HEADER_START):
        return []
    hunks = []
    for l in patch.split('\n'):
        if l.startswith(HUNK_HEADER_START):
            hunks.append([])
        hunks[-1].append(l)

    return hunks


def encode_hunk(hunk):

    try:

        if not isinstance(hunk, basestring):
            header = hunk[0]
            rest = hunk_as_string(hunk[1:])
            if header.startswith(HUNK_HEADER_START):
                header = HUNK_HEADER_START

        else:

            header, rest = hunk_as_lines(hunk, 1)
            if header.startswith(HUNK_HEADER_START):
                header = HUNK_HEADER_START

        return hashlib.sha1(header + '\n' + rest).hexdigest()

    except:
        # ignore patch sha that cannot be computed
        return None


def get_encoded_hunks(hunks):
    hunk_shas = {}

    if hunks:
        hunk_shas = OrderedDict(
            (encode_hunk(hunk), hunk)
            for hunk
            in hunks
        )

    return hunk_shas


def get_encoded_hunks_from_patch(patch):
    return get_encoded_hunks(split_patch_into_hunks(patch))


def parse_hunk(hunk, sha, position, is_reviewed):

    hunk = hunk_as_lines(hunk)

    from gim.core.models import LocalHunkSplit

    is_manual = hunk[0].endswith(MANUAL_HUNK_SPLIT_NOTE)

    result = [['comment', u'…', u'…', hunk[0], position, sha, is_reviewed, is_manual, False]]

    diff = whatthepatch.parse_patch(hunk).next()  # only one file = only one diff

    if is_manual:
        # manual hunks are not included in position as seen by github
        position -= 1

    len_changes = len(diff.changes)

    for index, change in enumerate(diff.changes):
        old, new, text = change
        position += 1
        mode = ' ' if old and new else '-' if old else '+'
        result.append([
            DIFF_LINE_TYPES[mode],
            old or '',
            new or '',
            mode + text,
            position,
            sha,
            is_reviewed,
            is_manual,
            LocalHunkSplit.can_split_on_line(text, index, len_changes),
        ])

    return result


def increment_line_count(line, start_from, start_to):
    incrementer = LINE_INCREMENTERS[line[0]]
    return start_from + incrementer[0], start_to + incrementer[1]


def compute_hunk_header(hunk, start_from, start_to):
    hunk = hunk_as_lines(hunk)

    if hunk[0].startswith(HUNK_HEADER_START):
        header = hunk[0]
        start_from, start_to, text = \
            whatthepatch.patch.unified_hunk_start.match(header).groups()[::2]
        hunk = hunk[1:]
    else:
        text = MANUAL_HUNK_SPLIT_NOTE

    count_from, count_to = 0, 0
    for line in hunk:
        count_from, count_to = increment_line_count(line, count_from, count_to)

    return HUNK_HEADER_TEMPLATE % (
        start_from, count_from, start_to, count_to, text
    )


def split_hunks(hunks, split_lines):

    from gim.core.models import LocalHunkSplit

    split_lines = set(split_lines)

    final_hunks = []

    def push_hunk(lines, start_from, start_to):
        if not lines:
            return
        header = compute_hunk_header(lines, start_from, start_to)
        if lines[0].startswith(HUNK_HEADER_START):
            lines[0] = header
        else:
            lines.insert(0, header)

        final_hunks.append(lines)

    for hunk in hunks:
        hunk = hunk_as_lines(hunk)

        header = hunk.pop(0)

        start_from, start_to = (
            int(val or 0) for val
            in extract_hunk_header_starts(header)
        )
        line_from, line_to = max(start_from - 1, 0), max(start_to - 1, 0)

        current_hunk_lines = [header]

        len_lines = len(hunk)
        for index, line in enumerate(hunk):
            line_from, line_to = increment_line_count(line, line_from, line_to)

            if LocalHunkSplit.can_split_on_line(line[1:], index, len_lines) and line[1:] in split_lines:
                push_hunk(current_hunk_lines, start_from, start_to)
                current_hunk_lines = []
                start_from, start_to = line_from, line_to

            current_hunk_lines.append(line)

        push_hunk(current_hunk_lines, start_from, start_to)

    return final_hunks
