#!/usr/bin/env python3
"""Tests of code-format, ci/check-style, review/style_review.py and of the
hook of git, each on a git repository made for it in a temporary directory.
Run: python3 tests/test_tools.py (git and clang-format 22 are needed)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_FORMAT = os.path.join(ROOT, 'code-format')

BAD = 'int f( int x ) { return x + 1; }\n'          # not in the style
GOOD = 'int f( int x ) { return( x + 1 ); }\n'      # formatted whole later

# a formatter that a project names in its .code-format: a file is in its
# style when it is upper case
UPPER = '''import sys
check = '--check' in sys.argv
bad = 0
for f in [a for a in sys.argv[1:] if a != '--check']:
    t = open(f).read()
    if t != t.upper():
        print(f)
        bad = 1
        if not check:
            open(f, 'w').write(t.upper())
sys.exit(bad if check else 0)
'''

failed = 0


def check(ok, what):
    global failed
    print(('ok   ' if ok else 'FAIL ') + what)
    if not ok:
        failed += 1


def run(cmd, cwd, env=None, **kw):
    e = dict(os.environ, **(env or {}))
    return subprocess.run(cmd, cwd=cwd, env=e, capture_output=True,
                          text=True, **kw)


def repo():
    """A repository with the .clang-format of this one, a .code-format that
    sends the .txt files to UPPER, and a first commit."""
    d = tempfile.mkdtemp()
    shutil.copy(os.path.join(ROOT, '.clang-format'), d)
    with open(os.path.join(d, 'upper.py'), 'w') as f:
        f.write(UPPER)
    with open(os.path.join(d, '.code-format'), 'w') as f:
        f.write('# the notes are upper case\n*.txt  %s upper.py\n'
                % sys.executable)
    with open(os.path.join(d, 'a.cc'), 'w') as f:
        f.write(GOOD)
    run([sys.executable, os.path.join(ROOT, 'format.py'), 'a.cc'], d)
    for c in (['git', 'init', '-q', '-b', 'main'],
              ['git', 'config', 'user.email', 't@t'],
              ['git', 'config', 'user.name', 't'],
              ['git', 'add', '-A'], ['git', 'commit', '-qm', 'first']):
        run(c, d)
    return d


def write(d, name, text):
    with open(os.path.join(d, name), 'w') as f:
        f.write(text)


def read(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read()


def test_code_format():
    d = repo()
    write(d, 'b.cc', BAD)
    write(d, 'n.txt', 'a note\n')
    write(d, 'x.md', 'whatever\n')

    r = run([CODE_FORMAT, '--check', 'b.cc', 'n.txt'], d)
    check(r.returncode == 1 and 'b.cc' in r.stdout and 'n.txt' in r.stdout,
          'code-format --check lists a C++ source and a file of .code-format')
    check(read(d, 'b.cc') == BAD and read(d, 'n.txt') == 'a note\n',
          'and changes nothing')

    r = run([CODE_FORMAT, 'b.cc', 'n.txt'], d)
    check('return( x + 1 );' in read(d, 'b.cc'),
          'code-format formats the C++ source with format.py')
    check(read(d, 'n.txt') == 'A NOTE\n',
          'and the other file with the formatter of .code-format')
    r = run([CODE_FORMAT, '--check', 'b.cc', 'n.txt'], d)
    check(r.returncode == 0 and not r.stdout, 'after which both are in it')

    r = run([CODE_FORMAT, '--check', 'x.md'], d)
    check(r.returncode == 0 and 'no formatter for x.md' in r.stderr,
          'a file that no formatter takes is left alone, and said')
    r = run([CODE_FORMAT, '--check', '--only-known', 'x.md'], d)
    check(r.returncode == 0 and not r.stderr, 'in silence with --only-known')

    r = run([CODE_FORMAT, '--chek', 'b.cc'], d)
    check(r.returncode == 2 and 'unknown option' in r.stderr,
          'an unknown option stops it')
    r = run([CODE_FORMAT, '--help'], d)
    check(r.returncode == 0 and r.stdout.startswith('Usage:'),
          '--help says how to run it')
    shutil.rmtree(d)


def test_check_style():
    d = repo()
    base = run(['git', 'rev-parse', 'HEAD'], d).stdout.strip()

    write(d, 'c.cc', BAD)
    run(['git', 'add', '-A'], d)
    run(['git', 'commit', '-qm', 'bad'], d)
    r = run([os.path.join(ROOT, 'ci', 'check-style'), base], d,
            env={'STYLE_TOKEN': ''})
    check(r.returncode == 1 and 'c.cc' in r.stdout,
          'check-style fails on a file out of the style, naming it')
    patch = read(d, 'style.patch') if os.path.exists(
        os.path.join(d, 'style.patch')) else ''
    check('return( x + 1 )' in patch,
          'and keeps the change that puts it there as style.patch')

    run(['git', 'checkout', '-q', '--', '.'], d)
    os.remove(os.path.join(d, 'style.patch'))
    write(d, 'c.cc', read(d, 'c.cc').replace('return x + 1;',
                                              'return( x + 1 );'))
    run([CODE_FORMAT, 'c.cc'], d)
    run(['git', 'add', '-A'], d)
    run(['git', 'commit', '-qm', 'good'], d)
    r = run([os.path.join(ROOT, 'ci', 'check-style'), base], d)
    check(r.returncode == 0, 'and passes once it is in the style')

    # a project without .clang-format is checked with the one of the tools
    os.remove(os.path.join(d, '.clang-format'))
    run(['git', 'add', '-A'], d)
    run(['git', 'commit', '-qm', 'no style'], d)
    write(d, 'e.cc', BAD)
    run(['git', 'add', '-A'], d)
    run(['git', 'commit', '-qm', 'bad again'], d)
    r = run([os.path.join(ROOT, 'ci', 'check-style'), base], d)
    check(r.returncode == 1 and 'e.cc' in r.stdout,
          'a project with no .clang-format is checked with this one')
    shutil.rmtree(d)


def test_style_review():
    d = repo()
    base = run(['git', 'rev-parse', 'HEAD'], d).stdout.strip()
    write(d, 'c.cc', BAD)
    run(['git', 'add', '-A'], d)
    run(['git', 'commit', '-qm', 'bad'], d)
    run([CODE_FORMAT, 'c.cc'], d)
    write(d, 'style.patch', run(['git', 'diff'], d).stdout)

    event = os.path.join(d, 'event.json')
    with open(event, 'w') as f:
        json.dump({'pull_request': {'number': 7, 'head': {'sha': 'abc'}}}, f)
    r = run([sys.executable, os.path.join(ROOT, 'review', 'style_review.py'),
             '--dry-run', 'style.patch', base], d,
            env={'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_PATH': event,
                 'GITHUB_REPOSITORY': 'o/r'})
    ok = False
    try:
        review = json.loads(r.stdout)
        c = review['comments'][0]
        ok = (c['path'] == 'c.cc' and c['side'] == 'RIGHT' and
              '```suggestion' in c['body'] and 'return( x + 1 )' in c['body']
              and review['commit_id'] == 'abc')
    except (ValueError, KeyError, IndexError):
        pass
    check(ok, 'style_review.py makes a review with a suggestion on GitHub')

    r = run([sys.executable, os.path.join(ROOT, 'review', 'style_review.py'),
             '--dry-run', 'style.patch', base], d, env={'GITHUB_ACTIONS': ''})
    check('```suggestion:-0+0' in r.stdout and
          '"position[new_path]": "c.cc"' in r.stdout,
          'and a discussion with a suggestion on GitLab')
    shutil.rmtree(d)


def test_hook():
    d = repo()
    r = run([os.path.join(ROOT, 'hooks', 'install-hooks'), d], d)
    check(r.returncode == 0 and 'installed' in r.stdout,
          'install-hooks installs the hook')
    write(d, 'h.cc', BAD)
    run(['git', 'add', 'h.cc'], d)
    r = run(['git', 'commit', '-qm', 'bad'], d)
    check(r.returncode != 0 and 'h.cc' in r.stderr,
          'the hook stops a commit out of the style')
    run([CODE_FORMAT, 'h.cc'], d)
    run(['git', 'add', 'h.cc'], d)
    write(d, 'x.md', 'whatever\n')
    run(['git', 'add', 'x.md'], d)
    r = run(['git', 'commit', '-qm', 'good'], d)
    check(r.returncode == 0, 'and lets it through once it is in the style')
    shutil.rmtree(d)


if __name__ == '__main__':
    if not shutil.which('clang-format'):
        print('test_tools.py: no clang-format')
        sys.exit(2)
    test_code_format()
    test_check_style()
    test_style_review()
    test_hook()
    print('%d failed' % failed)
    sys.exit(1 if failed else 0)
