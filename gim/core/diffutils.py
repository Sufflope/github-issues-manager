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


def split_patch_into_hunks(patch, as_strings=True):
    if not patch or not patch.startswith(HUNK_HEADER_START):
        return []
    hunks = []
    for l in patch.split('\n'):
        if l.startswith(HUNK_HEADER_START):
            hunks.append([])
        hunks[-1].append(l)

    if as_strings:
        return ['\n'.join(hunk) for hunk in hunks]
    else:
        return hunks


def encode_hunk(hunk):
    try:
        return hashlib.sha1(
            '\n'.join(
                HUNK_HEADER_START if l.startswith(HUNK_HEADER_START) else l
                for l in hunk.encode('utf-8').split('\n')
            )
        ).hexdigest()
    except:
        # ignore patch sha that cannot be computed
        return None


def get_encoded_hunks(patch):
    hunk_shas = {}

    if patch:
        hunk_shas = OrderedDict(
            (encode_hunk(hunk), hunk)
            for hunk
            in split_patch_into_hunks(patch)
        )

    return hunk_shas


def parse_hunk(hunk, sha, position, is_reviewed):

    result = [['comment', u'…', u'…', hunk[0], position, sha, is_reviewed]]

    diff = whatthepatch.parse_patch(hunk).next()  # only one file = only one diff

    if hunk[0].endswith(MANUAL_HUNK_SPLIT_NOTE):
        # manual hunks are not included in position as seen by github
        position -= 1

    for old, new, text in diff.changes:
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
        ])

    return result


def increment_line_count(line, start_from, start_to):
    incrementer = LINE_INCREMENTERS[line[0]]
    return start_from + incrementer[0], start_to + incrementer[1]


def compute_hunk_header(lines, start_from, start_to):
    if lines[0].startswith(HUNK_HEADER_START):
        header = lines[0]
        start_from, start_to, text = \
            whatthepatch.patch.unified_hunk_start.match(header).groups()[::2]
        lines = lines[1:]
    else:
        text = MANUAL_HUNK_SPLIT_NOTE

    count_from, count_to = 0, 0
    for line in lines:
        count_from, count_to = increment_line_count(line, count_from, count_to)

    return HUNK_HEADER_TEMPLATE % (
        start_from, count_from, start_to, count_to, text
    )


def split_hunks(hunks, split_lines):
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
        lines = hunk.split('\n')

        header = lines[0]

        start_from, start_to = (
            int(val or 0) for val
            in whatthepatch.patch.unified_hunk_start.match(header).groups()[:4:2]
        )
        line_from, line_to = start_from - 1, start_to - 1

        current_hunk_lines = [header]

        len_lines = len(lines)
        for index, line in enumerate(lines[1:], start=1):
            line_from, line_to = increment_line_count(line, line_from, line_to)

            if 2 < index < len_lines - 2 and line[1:] in split_lines:
                push_hunk(current_hunk_lines, start_from, start_to)
                current_hunk_lines = []
                start_from, start_to = line_from, line_to

            current_hunk_lines.append(line)

        push_hunk(current_hunk_lines, start_from, start_to)

    return final_hunks
