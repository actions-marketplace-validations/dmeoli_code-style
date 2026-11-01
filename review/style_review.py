#!/usr/bin/env python3
"""Posts on a merge request of GitLab, or on a pull request of GitHub, the
changes that put its files in the style of the project, as suggestions that
the author applies with one click.

The patch is the one that the check of the style makes by running the
formatters on the files of the request (git diff after them). A hunk whose
lines are all among the ones that the request adds becomes a suggestion on
them; the other hunks (e.g., of a file that is formatted whole) go together
in one comment, as a patch. The comments of the last run are deleted first,
so that a request carries only the ones of its last pipeline; they are told
by a marker in their body.

Usage: style_review.py [--dry-run] PATCH BASE
Where to post is said by the variables of the pipeline. On GitLab these are
CI_API_V4_URL, CI_PROJECT_ID and CI_MERGE_REQUEST_IID, and STYLE_TOKEN is
the token of the user that posts (a project access token with the role
Reporter and the scope api). On GitHub (GITHUB_ACTIONS set) they are
GITHUB_API_URL, GITHUB_REPOSITORY and GITHUB_EVENT_PATH, and STYLE_TOKEN is
a token that can write on pull requests (the GITHUB_TOKEN of the job, with
the permission pull-requests: write). With --dry-run nothing is posted, and
what would be is printed.
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

MARKER = '<!-- code-style -->'
HEAD = (MARKER + '\n**Style**: this change puts the lines in the style that '
        'the pipeline checks.\n\n')
REST = ('The changes that cannot be suggested on the lines of the request '
        '(e.g., in a file that is formatted whole):\n\n')
TAIL = '\n\nThe whole patch is the artifact `style.patch` of the check.'


def hunks(patch):
    """The hunks of the patch: (path, first old line, old lines, new
    lines), the lines without their +, - or space."""
    res = []
    path = None
    lines = patch.split('\n')
    k = 0
    while k < len(lines):
        line = lines[k]
        if line.startswith('+++ '):
            path = line[4:]
            path = path[2:] if path.startswith('b/') else path
        m = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
        if m and path:
            start = int(m.group(1))
            old, new = [], []
            k += 1
            while k < len(lines) and lines[k][:1] in (' ', '-', '+', '\\'):
                t = lines[k]
                if t[:1] in (' ', '-'):
                    old.append(t[1:])
                if t[:1] in (' ', '+'):
                    new.append(t[1:])
                k += 1
            # the context around the change is kept out of the suggestion
            while old and new and old[0] == new[0]:
                old.pop(0)
                new.pop(0)
                start += 1
            while old and new and old[-1] == new[-1]:
                old.pop()
                new.pop()
            res.append((path, start, old, new))
            continue
        k += 1
    return res


def added_lines(base, path):
    """The numbers of the lines of path at HEAD that the merge request adds
    or changes."""
    out = subprocess.run(['git', 'diff', '-U0', base, 'HEAD', '--', path],
                         capture_output=True, text=True).stdout
    lines = set()
    for m in re.finditer(r'^@@ -\S+ \+(\d+)(?:,(\d+))? @@', out, re.M):
        first, count = int(m.group(1)), int(m.group(2) or 1)
        lines.update(range(first, first + count))
    return lines



class GitLab:
    """Discussions on a merge request of GitLab."""

    def __init__(self, dry):
        self.dry = dry
        self.api = os.environ.get('CI_API_V4_URL', '')
        self.project = os.environ.get('CI_PROJECT_ID', '')
        self.iid = os.environ.get('CI_MERGE_REQUEST_IID', '')
        self.token = os.environ.get('STYLE_TOKEN', '')
        self.refs = None

    def ready(self):
        return bool(self.token and self.iid)

    def call(self, method, path, data=None):
        url = '%s/projects/%s/merge_requests/%s%s' % (
            self.api, self.project, self.iid, path)
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={'PRIVATE-TOKEN': self.token})
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
        return json.loads(text) if text else None

    def clear(self):
        """Deletes the notes of the last run."""
        page = 1
        while True:
            ds = self.call('GET', '/discussions?per_page=100&page=%d' % page)
            if not ds:
                break
            for d in ds:
                n = d['notes'][0]
                if MARKER in n['body']:
                    self.call('DELETE', '/notes/%d' % n['id'])
            page += 1
        self.refs = self.call('GET', '')['diff_refs']

    def post(self, data):
        if self.dry:
            print(json.dumps(data, indent=1))
            return True
        try:
            self.call('POST', '/discussions', data)
            return True
        except urllib.error.HTTPError:
            return False

    def suggest(self, path, start, old, new):
        body = HEAD + '```suggestion:-0+%d\n%s\n```' % (
            len(old) - 1, '\n'.join(new))
        data = {'body': body,
                'position[position_type]': 'text',
                'position[new_path]': path,
                'position[old_path]': path,
                'position[new_line]': start}
        if self.refs:
            data['position[base_sha]'] = self.refs['base_sha']
            data['position[start_sha]'] = self.refs['start_sha']
            data['position[head_sha]'] = self.refs['head_sha']
        return self.post(data)

    def note(self, text):
        self.post({'body': text})


class GitHub:
    """A review on a pull request of GitHub."""

    def __init__(self, dry):
        self.dry = dry
        self.api = os.environ.get('GITHUB_API_URL', 'https://api.github.com')
        self.repo = os.environ.get('GITHUB_REPOSITORY', '')
        self.token = os.environ.get('STYLE_TOKEN', '')
        self.number = None
        self.head = None
        try:
            with open(os.environ['GITHUB_EVENT_PATH'],
                      encoding='utf-8') as f:
                pr = json.load(f).get('pull_request', {})
            self.number = pr.get('number')
            self.head = pr.get('head', {}).get('sha')
        except (KeyError, OSError, ValueError):
            pass
        self.comments = []
        self.hunks = []

    def ready(self):
        return bool(self.token and self.number)

    def call(self, method, path, data=None):
        url = '%s/repos/%s%s' % (self.api, self.repo, path)
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={'Authorization': 'Bearer ' + self.token,
                     'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
        return json.loads(text) if text else None

    def clear(self):
        """Deletes the comments of the last run."""
        page = 1
        while True:
            cs = self.call('GET', '/pulls/%d/comments?per_page=100&page=%d'
                           % (self.number, page))
            if not cs:
                break
            for c in cs:
                if MARKER in c['body']:
                    self.call('DELETE', '/pulls/comments/%d' % c['id'])
            page += 1
        page = 1
        while True:
            cs = self.call('GET', '/issues/%d/comments?per_page=100&page=%d'
                           % (self.number, page))
            if not cs:
                break
            for c in cs:
                if MARKER in c['body']:
                    self.call('DELETE', '/issues/comments/%d' % c['id'])
            page += 1

    def suggest(self, path, start, old, new):
        c = {'path': path, 'side': 'RIGHT', 'line': start + len(old) - 1,
             'body': HEAD + '```suggestion\n%s\n```' % '\n'.join(new)}
        if len(old) > 1:
            c['start_line'] = start
            c['start_side'] = 'RIGHT'
        self.comments.append(c)
        self.hunks.append((path, start, old, new))
        return True

    def note(self, text):
        if self.dry:
            print(json.dumps({'body': text}, indent=1))
            return
        self.call('POST', '/issues/%d/comments' % self.number,
                  {'body': text})

    def flush(self):
        """Posts the suggestions as one review; if GitHub refuses it (e.g.,
        a line it does not take as part of the diff), one by one, and those
        it still refuses are returned, as hunks."""
        if not self.comments:
            return []
        review = {'event': 'COMMENT', 'body': MARKER,
                  'comments': self.comments}
        if self.head:
            review['commit_id'] = self.head
        if self.dry:
            print(json.dumps(review, indent=1))
            return []
        try:
            self.call('POST', '/pulls/%d/reviews' % self.number, review)
            return []
        except urllib.error.HTTPError:
            pass
        refused = []
        for c, h in zip(self.comments, self.hunks):
            one = dict(c, commit_id=self.head) if self.head else dict(c)
            try:
                self.call('POST', '/pulls/%d/comments' % self.number, one)
            except urllib.error.HTTPError:
                refused.append(h)
        return refused


def main(argv):
    if '-h' in argv or '--help' in argv:
        print(__doc__[__doc__.index('Usage:'):].rstrip())
        return 0
    dry = '--dry-run' in argv
    args = [a for a in argv if a != '--dry-run']
    if len(args) != 2:
        print('style_review.py: PATCH and BASE are needed', file=sys.stderr)
        return 2
    patch = open(args[0], encoding='utf-8').read()
    base = args[1]
    host = GitHub(dry) if os.environ.get('GITHUB_ACTIONS') else GitLab(dry)
    if not dry and not host.ready():
        print('style-review: no STYLE_TOKEN or no request, nothing posted')
        return 0
    if not dry:
        host.clear()
    rest = []
    added = {}
    for path, start, old, new in hunks(patch):
        if path not in added:
            added[path] = added_lines(base, path)
        span = range(start, start + max(len(old), 1))
        if old and all(n in added[path] for n in span):
            if host.suggest(path, start, old, new):
                continue
        rest.append((path, start, old, new))
    if isinstance(host, GitHub):
        rest += host.flush()
    if rest:
        text = []
        for path, start, old, new in rest:
            text.append('%s, line %d:\n```diff\n%s\n```' % (
                path, start, '\n'.join(['-' + x for x in old] +
                                       ['+' + x for x in new])))
        host.note(HEAD + REST + '\n\n'.join(text) + TAIL)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
