# code-style

[![CI](https://github.com/dmeoli/code-style/actions/workflows/ci.yml/badge.svg)](https://github.com/dmeoli/code-style/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

This repository holds a formatter for C++ in a style that clang-format
cannot express by its options, the tools that apply it (from the command
line, from the IDE and from a hook of git), and a check of merge requests
(GitLab) and pull requests (GitHub). The check fails until the lines that
a request changes are in the style, and posts on those lines, as
suggestions, the changes that put them there. Only the lines touched by a
change are checked; hence, a project formatted by hand can adopt the style
without rewriting its history. A project may also hand files of other kinds
(e.g., configurations) to formatters of its choice, which the same tools
then run.

## The style

`format.py` runs clang-format with the `.clang-format` found up the tree of
the file (cf. the one of this repository, which is the reference), and
then applies the rules that clang-format has no option for:

- the expression of a `return` and of a `throw` in parentheses, with no
  space before them: `return( x );`, `throw( e );`;
- a space before every comma and before the semicolons of a `for`:
  `f( a , b )`, `for( i = 0 ; i != n ; ++i )`;
- the closing brace of a block on the indentation of the block, the one of
  a namespace excepted;
- the opening brace of a function defined out of a class on a line of its
  own;
- a line that the spaces before the commas have brought past 79 columns
  broken after a comma, or after a semicolon of a `for`;
- the C++ of the `\code ... \endcode` blocks of the comments of Doxygen,
  and of its pages (`.dox`, of which nothing else is touched), formatted as
  the rest within the columns that the prefix of the comment leaves; a
  block that is no C++ (e.g., a file format, a shell command) or that
  clang-format would change in more than the spaces is left alone.

The `.clang-format` sets the rest: an indentation of one space, the spaces
inside parentheses, brackets and angles (`if( x )`, `v[ i ]`,
`std::vector< int >`), `T * p` and `T & r`, `! x`, and a limit of 79
columns. It does not touch what is usually a choice of the author, i.e.,
the comments, the order of the includes and of the using-declarations, the
string literals and the indentation of the preprocessor directives. A file
that a program writes (`DO NOT EDIT` or `@generated` in its first lines) is
skipped. A file with no `.clang-format` up its tree is formatted with the
one of this repository; hence, a project in this style needs no copy of
it, and one with a style of its own keeps its `.clang-format` at its root,
which then takes precedence.

Each change that `format.py` makes is compared with the tokens of the
lines it replaces, and it is dropped if it would add, remove or reorder
any. This is a safeguard for files far from the style, where the diff of
the two layouts may pair lines of different code.

## Usage

```
format.py   [--check] [--lines FIRST:LAST | --git | --since REF] FILE...
code-format [--check] [--only-known] [--lines FIRST:LAST | --git | --since REF] FILE...
```

Without options the files are formatted entirely. With `--lines` only the
changes that touch those lines are made, with `--git` only those that touch
the lines changed since `HEAD`, and with `--since REF` those that touch the
lines changed since `REF` (a file unknown to git is formatted entirely).
The code around them stays as it was written: a formatter cannot reproduce
the choices of layout of a person (where to break a long line, how to align
a continuation), and reformatting old files would bury their history under
changes of layout. With `--check` nothing is written; the files that would
change are listed, and the exit status is 1 if there are any.

`code-format` is the entry point of the other tools. It sends a C++ source
to `format.py`, and any other file to the formatter that the project names
in the first file `.code-format` up the tree of the file (that of a
repository serves also its submodules), one per line:

```
# PATTERN  COMMAND...
*.txt      python3 scripts/cfgformat.py
```

The pattern is matched against the name of the file, and the command is
run from the directory of the `.code-format` with `--check` (if given) and
the files that match; it formats them entirely, and exits with status 1
when some file would change. A file that no formatter takes is skipped with
a message, which `--only-known` suppresses.

## In the IDE

`ide-format FILE` runs on the file the formatter of the project (a
`scripts/*-format` up the tree), if there is one, and `code-format --git`
otherwise; an IDE can then bind it to the key of its formatter. For
CLion, `clion-settings/` holds an external tool that runs it (its path
assumes this repository in `~/code-style`) and a keymap that binds it to
Ctrl+Alt+L. They are copied in the directory of the settings of CLion
while CLion is closed.

## The hook of git

`hooks/install-hooks [REPOSITORY]` installs `hooks/pre-commit` in a
repository and in its submodules, as a link; a repository that already has
a pre-commit hook keeps it. The hook checks the files of the commit with
`code-format --check --only-known --git` (or with `$CODE_FORMAT`, or with
the `scripts/*-format` of the project, if any). It stops a commit whose
files are not in the style, and prints the command that puts them there;
`git commit --no-verify` commits anyway.

## The check of the requests

On GitHub, a workflow runs the action of this repository on the pull
requests:

```yaml
on: pull_request
permissions:
  contents: read
  pull-requests: write          # for the suggestions, else leave it out
jobs:
  style:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: dmeoli/code-style@v1
```

On GitLab, the pipeline includes the template of this repository, which
adds the job `style` to the merge requests:

```yaml
include:
  - remote: https://raw.githubusercontent.com/dmeoli/code-style/v1/gitlab/style.yml
```

In both cases the check (`ci/check-style`) runs `code-format --check
--since` on the files that the request changes, from the base of the
request. If a file is not in the style, the check fails and keeps the
changes that put the files in it as `style.patch`, an artifact that the
author applies with `git apply`; it also posts them on the request as
suggestions on its lines, which the author applies with one click. On
GitHub the suggestions are posted with the token of the job, which needs
`pull-requests: write` (on a pull request from a fork the token is
read-only, and only the patch is kept). On GitLab they need the variable
`STYLE_TOKEN`, i.e., a masked project access token of the role Reporter
with the scope `api`. A change that cannot be suggested on the lines of the
request (e.g., in a file formatted entirely) goes as a patch into one
comment, and the comments of the previous run are replaced at each run. A
merge request of GitLab that has to keep a different layout says so with
`[skip style]` in its title. A project changes the job by defining it
again in its pipeline (e.g., `style: stage: build`), which GitLab merges
with the one of the template; the variable `STYLE_SETUP` of the job holds a
command run before the check (e.g., one that fetches the formatter of some
files and writes the `.code-format` that names it).

The tags are versions: `v1` follows the releases `1.x`, whose changes of
layout are only fixes, and therefore a project that pins it is not
reformatted by surprise.

## Requirements

Python 3, git and clang-format 22 (e.g., `pip install
clang-format==22.1.5`), whose layout changes slightly from one version to
the next; bash for the hook and for the check. The tests run with
`python3 tests/test_format.py` and `python3 tests/test_tools.py`.

## License

MIT, see [LICENSE](LICENSE).
