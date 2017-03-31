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
