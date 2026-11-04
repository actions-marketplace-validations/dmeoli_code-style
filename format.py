#!/usr/bin/env python3
r"""Formats C++ sources in a house style.

clang-format (with the .clang-format found up the tree of the file) gives
the layout; this script adds what clang-format has no option for:

  - the expression of a return and of a throw in parentheses, with no
    space before them, i.e., return( x ); and throw( x );
  - a space before every comma and before the semicolons inside for( ),
    i.e., f( a , b ) and for( i = 0 ; i != n ; ++i );
  - the closing brace of a block on the indentation of the block, the one
    of a namespace excepted;
  - the opening brace of a function defined out of a class on a line of
    its own;
  - a line that the spaces before the commas have brought past 79
    columns broken after a comma, or after a semicolon of a for;
  - the C++ in the \code ... \endcode blocks of the comments of
    Doxygen, and of its pages (.dox), formatted as the rest, within the
    columns that the prefix of the comment leaves;
  - the arguments of a template in the code within the prose of those
    comments and pages (the text of \ref NAME "TEXT", the word after \c
    or \p, <tt>, <code> and `), spaced as in the code, i.e.,
    EdgeMap< bool > and std::map< int , std::vector< int > >.

Usage: format.py [--check] [--lines FIRST:LAST | --git | --since REF]
                 FILE...
With --lines only the changes that touch those lines are made, with --git
only those that touch the lines changed since HEAD, with --since REF the
ones changed since REF (a file that git does not know is formatted
whole), so that the code around is left as it is;
with --check nothing is written, and the files that would change are
listed, with exit status 1 if there are any. A file with no .clang-format
in its directory or above it is formatted with the one next to this
script, or with the variant styles/NAME/.clang-format of it if the first
.code-format up its tree has the line STYLE NAME. A .dox file only has its
blocks of code formatted.
"""

import functools
import os
import re
import subprocess
import sys

LIMIT = 79

# --------------------------------------------------------------------------
# a tokenizer that knows comments, string and character literals and
# preprocessor lines, which the passes below leave alone


def mask(text):
    """Returns text with the content of the comments and of the string and
    character literals replaced by spaces of the same length (newlines
    kept), so that the passes can look for code tokens by plain regular
    expressions on the masked text and edit the real one at the same
    offsets."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = ' '
            i = j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if text[k] != '\n':
                    out[k] = ' '
            i = j
        elif c == 'R' and text.startswith('R"', i):
            m = re.match(r'R"([^(]*)\(', text[i:])
            end = text.find(')' + m.group(1) + '"', i)
            j = n if end < 0 else end + len(m.group(1)) + 2
            for k in range(i + 1, j):
                if text[k] != '\n':
                    out[k] = ' '
            i = j
        elif c in '"\'':
            # a digit separator such as 1'000 is no literal
            if c == "'" and i > 0 and text[i - 1].isalnum():
                i += 1
                continue
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == '\\' else 1
            for k in range(i + 1, min(j, n)):
                out[k] = ' '
            i = j + 1
        else:
            i += 1
    return ''.join(out)


def in_directive(text):
    """A function telling whether an offset of text is in a preprocessor
    directive, its continuation lines included."""
    ranges = []
    pos, start, cont = 0, None, False
    for line in text.split('\n'):
        if cont or line.lstrip().startswith('#'):
            if start is None:
                start = pos
            cont = line.endswith('\\')
            if not cont:
                ranges.append((start, pos + len(line)))
                start = None
        pos += len(line) + 1
    if start is not None:
        ranges.append((start, pos))

    def inside(j):
        return any(a <= j <= b for a, b in ranges)
    return inside


def preprocessor_lines(text):
    """The set of the offsets of the lines that are preprocessor
    directives, continuation lines included."""
    lines, offs, cont = text.split('\n'), set(), False
    pos = 0
    for line in lines:
        if cont or line.lstrip().startswith('#'):
            offs.add(pos)
            cont = line.endswith('\\')
        pos += len(line) + 1
    return offs


# --------------------------------------------------------------------------
# return( x ) and throw( x ), before clang-format


def wrap_returns(text):
    m_text = mask(text)
    inside = in_directive(text)
    out, last = [], 0
    for m in re.finditer(r'\b(return|throw)\b', m_text):
        if m.start() < last:
            continue  # inside the expression of the one before, e.g., in
                      # the body of a lambda, which that one carries as is
        if m.group(1) == 'throw' and is_specification(m_text, m.start()):
            continue  # a dynamic exception specification, e.g., throw()
        i = m.end()
        # the end of the expression: the semicolon at depth zero, within the
        # directive if the return is in one (e.g., in the body of a macro,
        # which may end without one)
        end = len(m_text)
        if inside(m.start()):
            end = m_text.find('\n', m.start())
            while end > 0 and m_text[end - 1] == '\\':
                end = m_text.find('\n', end + 1)
            end = len(m_text) if end < 0 else end
        depth, j = 0, i
        while j < end:
            c = m_text[j]
            if c in '([{':
                depth += 1
            elif c in ')]}':
                depth -= 1
                if depth < 0:
                    break
            elif c == ';' and depth == 0:
                break
            j += 1
        if j >= end or m_text[j] != ';':
            continue  # not a statement, e.g., at the end of a macro
        expr = m_text[i:j].strip()
        if not expr or expr.startswith('{'):
            continue  # return; and return { ... };
        a = i + len(m_text[i:j]) - len(m_text[i:j].lstrip())
        b = j - (len(m_text[i:j]) - len(m_text[i:j].rstrip()))
        if m_text[a] == '(' and matching(m_text, a) == b - 1:
            out.append(text[last:i])
            out.append(text[a:b])
            last = b
            continue
        out.append(text[last:i])
        out.append('( ' + text[a:b] + ' )')
        last = b
    out.append(text[last:])
    return ''.join(out)


def is_specification(m_text, j):
    """Whether the throw at j is a dynamic exception specification, i.e.,
    it follows the parameters of a function (and maybe const, volatile, &),
    not the condition of an if, a while, a for or a switch."""
    head = m_text[:j].rstrip()
    while re.search(r'(\bconst|\bvolatile|&&|&)$', head):
        head = re.sub(r'(\bconst|\bvolatile|&&|&)$', '', head).rstrip()
    if not head.endswith(')'):
        return False
    depth, k = 0, len(head) - 1
    while k >= 0:
        if head[k] == ')':
            depth += 1
        elif head[k] == '(':
            depth -= 1
            if depth == 0:
                break
        k -= 1
    before = head[:k].rstrip()
    return not re.search(r'\b(if|while|for|switch|catch)$', before)


def matching(m_text, a):
    depth = 0
    for j in range(a, len(m_text)):
        if m_text[j] in '([{':
            depth += 1
        elif m_text[j] in ')]}':
            depth -= 1
            if depth == 0:
                return j
    return -1


# --------------------------------------------------------------------------
# after clang-format


def tight_returns(text):
    """return( x ) and throw( x ), which clang-format writes return ( x )."""
    m_text = mask(text)
    out = list(text)
    for m in reversed(list(re.finditer(r'\b(return|throw) \(', m_text))):
        del out[m.end() - 2]
    return ''.join(out)


def space_commas(text):
    """A space before every comma, and before the semicolons of for( )."""
    m_text = mask(text)
    pp = preprocessor_lines(text)
    out = list(text)
    # the semicolons of for( ): mark them by depth
    fors = []
    for m in re.finditer(r'\bfor\s*\(', m_text):
        a = m.end() - 1
        b = matching(m_text, a)
        if b < 0:
            continue
        depth = 0
        for j in range(a, b):
            c = m_text[j]
            if c in '([{':
                depth += 1
            elif c in ')]}':
                depth -= 1
            elif c == ';' and depth == 1:
                fors.append(j)
    targets = set(fors)
    for m in re.finditer(r',', m_text):
        j = m.start()
        if re.search(r'\boperator\s*$', m_text[max(0, j - 20):j]):
            continue
        targets.add(j)
    line_start = 0
    starts = {}
    for k, line in enumerate(text.split('\n')):
        starts[k] = line_start
        line_start += len(line) + 1
    for j in sorted(targets, reverse=True):
        ls = text.rfind('\n', 0, j) + 1
        if ls in pp:
            continue
        if j > 0 and text[j - 1] not in ' \t\n(':
            out.insert(j, ' ')
    return ''.join(out)


def blocks(text):
    """Yields, for every closing brace that begins a line, its offset and
    whether it closes a namespace."""
    m_text = mask(text)
    stack = []
    res = []
    i = 0
    for m in re.finditer(r'[{}]', m_text):
        j = m.start()
        if m_text[j] == '{':
            head = m_text[max(0, j - 300):j]
            stmt = re.split(r'[;{}]', head)[-1]
            stack.append(bool(re.search(r'\bnamespace\b', stmt)))
        else:
            ns = stack.pop() if stack else False
            ls = text.rfind('\n', 0, j) + 1
            if text[ls:j].strip() == '':
                res.append((ls, j, ns))
    return res


def indent_closing(text):
    """The closing brace of a block on the indentation of the block."""
    out = text
    inside = in_directive(text)
    for ls, j, ns in sorted(blocks(text), reverse=True):
        if ns or inside(j):
            continue
        out = out[:j] + ' ' + out[j:]
    return out


def own_line_brace(text):
    """The opening brace of a function defined out of a class, i.e., of a
    block that opens a function body directly in a namespace or in the
    file, on a line of its own."""
    m_text = mask(text)
    kinds = []      # for every open brace: 'ns', 'class', 'func' or 'other'
    moves = []
    for m in re.finditer(r'[{}]', m_text):
        j = m.start()
        if m_text[j] == '}':
            if kinds:
                kinds.pop()
            continue
        stmt = re.split(r'[;{}]', m_text[max(0, j - 2000):j])[-1]
        if re.search(r'\bnamespace\b', stmt):
            kinds.append('ns')
        elif re.search(r'\b(class|struct|union|enum)\b[^()]*$', stmt):
            kinds.append('class')
        elif ')' in stmt and all(k == 'ns' for k in kinds) and \
                not re.search(r'=\s*$', stmt.strip()) and \
                not re.match(r'\s*(if|for|while|switch|catch)\b', stmt):
            kinds.append('func')
            ls = text.rfind('\n', 0, j) + 1
            if text[ls:j].strip():   # the brace is not alone on its line
                moves.append(j)
        else:
            kinds.append('other')
    out = text
    inside = in_directive(text)
    moves = [j for j in moves if not inside(j)]
    for j in reversed(moves):
        k = j
        while k > 0 and out[k - 1] in ' \t':
            k -= 1
        out = out[:k] + '\n{' + out[j + 1:]
    return out


def column_zero(text):
    """The banners /*---...---*/ and the group markers of the
    documentation at column zero, and the #define of an include guard (a
    name with no value, right after the #ifndef of the same name) one space
    in."""
    lines = text.split('\n')
    out = []
    in_group = False
    for k, line in enumerate(lines):
        s = line.strip()
        if re.match(r'/\*-.*-\*/$', s) or s.startswith('/** @name') or \
           s.startswith('/** @}') or s.startswith('/** @defgroup'):
            out.append(s)
            in_group = s.startswith('/** @') and not s.endswith('*/')
            continue
        if in_group:
            out.append(' ' + s if s.startswith('*') else s)
            in_group = not s.endswith('*/')
            continue
        if s.startswith('#define') and k > 0 and len(s.split()) == 2 and \
           re.match(r'#ifndef\s+(\w+)', lines[k - 1].strip()) and \
           s.split()[1] == lines[k - 1].split()[1]:
            out.append(' ' + s)
            continue
        out.append(line)
    return '\n'.join(out)


def align_continuations(text):
    """The backslashes that continue a preprocessor directive in one
    column again, the rightmost they reach (clang-format aligns them, and
    the passes after it move some)."""
    lines = text.split('\n')
    k = 0
    while k < len(lines):
        if lines[k].lstrip().startswith('#') and lines[k].endswith('\\'):
            j = k
            while j < len(lines) and lines[j].endswith('\\'):
                j += 1
            block = range(k, j)
            col = max(len(lines[i][:-1].rstrip().expandtabs(8)) + 1
                      for i in block)
            col = max(col, max(len(lines[i].expandtabs(8)) - 1
                               for i in block))
            for i in block:
                code = lines[i][:-1].rstrip()
                pad = col - len(code.expandtabs(8))
                lines[i] = code + ' ' * pad + '\\'
            k = j
        k += 1
    return '\n'.join(lines)


def brackets(m_line):
    """For each offset of a masked line, the offsets of the brackets open
    there, the outermost first: parentheses, braces, square brackets and
    the angle brackets of a template, i.e., a < right after a name, as in
    vector< int >, where a comparison has a space before it."""
    res, stack = [], []
    for k, c in enumerate(m_line):
        if c in '([{':
            stack.append(k)
        elif c in ')]}':
            while stack and m_line[stack[-1]] == '<':
                stack.pop()             # a < that was not a template
            if stack:
                stack.pop()
        elif c == '<' and k and (m_line[k - 1].isalnum() or
                                 m_line[k - 1] == '_'):
            stack.append(k)
        elif c == '>' and stack and m_line[stack[-1]] == '<' and \
                m_line[k - 1] != '-':
            stack.pop()
        res.append(list(stack))
    return res


def break_long(text, limit=None, tabs=True):
    """A line past the limit broken after the last comma that fits among
    the least nested ones, or the last semicolon of the header of a for,
    the rest aligned with the first argument of the call (or the first
    part of the for, or the first item of the braced list) it is in, by
    tabs and spaces if tabs, else by spaces alone."""
    limit = limit or LIMIT
    res = []
    inside = in_directive(text)
    m_text = mask(text)     # a line in the middle of a comment is masked
    pos = 0
    for line in text.split('\n'):
        start = pos
        pos += len(line) + 1
        if inside(start):
            res.append(line)   # a directive is left to clang-format
            continue
        m_line = m_text[start:start + len(line)]
        while len(line.expandtabs(8)) > limit:
            opens = brackets(m_line)
            # the last cut that fits among the least nested ones
            cut, depth = -1, None
            for m in re.finditer(r' ,| ;(?= )', m_line):
                if len(line[:m.end()].expandtabs(8)) > limit:
                    continue
                d = len(opens[m.start()])
                if depth is None or d <= depth:
                    cut, depth = m.end(), d
            if cut < 0:
                break
            # the column of the first item of the innermost open call,
            # braced list or template
            stack = opens[cut - 1]
            indent = len(line.expandtabs(8)) - len(line.lstrip())
            if stack:
                col = len(line[:stack[-1] + 1].expandtabs(8)) + 1
            elif res and res[-1].rstrip()[-1:] in (',', '(', '{', '['):
                col = indent           # an item of a list open above
            else:
                col = indent + 2
            head, tail = line[:cut].rstrip(), line[cut:].lstrip()
            if not tail:
                break
            res.append(head)
            pad = '\t' * (col // 8) + ' ' * (col % 8) if tabs else ' ' * col
            m_line = pad + m_line[len(line) - len(tail):]
            line = pad + tail
        res.append(line)
    return '\n'.join(res)


@functools.lru_cache(maxsize=None)
def uses_tabs(clang_format, style, path):
    """Whether the style that clang-format finds for path indents by tabs,
    i.e., its UseTab is not Never."""
    out = subprocess.run([clang_format, '--style=' + style,
                          '--assume-filename=' + path, '--dump-config'],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(r'^UseTab:\s*(\w+)', out, re.M)
    return m is not None and m.group(1) != 'Never'


def format_code(text, clang_format='clang-format', path='file.h',
                limit=None):
    """The code formatted: clang-format, then the passes above."""
    style = 'file'
    if limit:
        # the code of a comment, where a tab would show as Doxygen likes
        style = ('{BasedOnStyle: InheritParentConfig, ColumnLimit: %d, '
                 'UseTab: Never}' % limit)
    text = wrap_returns(text)
    text = subprocess.run([clang_format, '--style=' + style,
                           '--assume-filename=' + path],
                          input=text, capture_output=True, text=True,
                          check=True).stdout
    text = tight_returns(text)
    text = own_line_brace(text)
    text = space_commas(text)
    text = indent_closing(text)
    text = column_zero(text)
    text = align_continuations(text)
    text = break_long(text, limit, uses_tabs(clang_format, style, path))
    return text


# a line that opens or closes a block of code of Doxygen, in a comment
# (///, //!, a * of a /** */ block, or nothing in a .dox page)
CODE_OPEN = re.compile(r'^(\s*(?://[/!]|\*)?\s?)[\\@]code(\{[^}]*\})?\s*$')
CODE_CLOSE = re.compile(r'^\s*(?://[/!]|\*)?\s*[\\@]endcode\s*$')


# the tokens of C++, the operators of more characters as one token (so that
# a << that became < < is a change), but >> as two >, which closes two
# template argument lists as well as it shifts
CPP_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\w+|'
                       r'<<=|->\*|\.\.\.|<<|->|::|\+\+|--|&&|\|\||==|!=|<=|'
                       r'>=|\+=|-=|\*=|/=|%=|&=|\|=|\^=|\S')


def cpp_tokens(code, ignore=''):
    """The tokens of the code, but the characters in ignore."""
    return [t for t in CPP_TOKEN.findall(code) if t not in ignore]


def looks_like_cpp(lines):
    """Whether a block of code is C++, rather than, e.g., the sections of a
    file format (lines that start with @) or a command of the shell."""
    body = '\n'.join(lines)
    if any(l.lstrip().startswith(('@', '$ ', '#!')) for l in lines):
        return False
    return re.search(r'[;{}()]|::|<[^<>]*>', body) is not None


def format_doc_code(text, clang_format='clang-format', path='file.h'):
    """The C++ of the blocks \\code ... \\endcode of the comments formatted
    as the rest, within the columns that the prefix of the comment leaves;
    a block that is no C++, that says it is another language, or that
    clang-format would change in more than the spaces, is left alone."""
    lines = text.split('\n')
    out = []
    k = 0
    while k < len(lines):
        m = CODE_OPEN.match(lines[k])
        if not m:
            out.append(lines[k])
            k += 1
            continue
        j = k + 1
        while j < len(lines) and not CODE_CLOSE.match(lines[j]):
            j += 1
        if j == len(lines):
            out.extend(lines[k:])
            break
        lang = (m.group(2) or '').strip('{}.').lower()
        marker = re.match(r'^\s*(?://[/!]|\*)?', lines[k]).group(0)
        # the code one space after the marker of the comment, however the
        # line of \code is written
        prefix = marker + ' ' if marker.strip() else marker
        body = lines[k + 1:j]
        inner = []
        ok = lang in ('', 'cpp', 'c++', 'cc', 'h')
        for l in body:
            if l.strip() == marker.strip() or not l.strip():
                inner.append('')
            elif l.startswith(marker):
                inner.append(l[len(marker):].lstrip(' ') if marker.strip()
                             else l)
            else:
                ok = False
                break
        if ok and inner and looks_like_cpp(inner):
            width = len(prefix.expandtabs(8))
            code = '\n'.join(inner).strip('\n') + '\n'
            new = format_code(code, clang_format, path, LIMIT - width)
            same = cpp_tokens(new) == cpp_tokens(code) or \
                cpp_tokens(new, '()') == cpp_tokens(code, '()')
            if same:
                body = [(prefix + l).rstrip() if l.strip()
                        else marker.rstrip()
                        for l in new.rstrip('\n').split('\n')]
        out.append(lines[k])
        out.extend(body)
        out.append(lines[j])
        k = j + 1
    return '\n'.join(out)


def comment_spans(text):
    """The spans ( start , end ) of the comments of the text, by the same
    scan as mask(), which skips the string and character literals."""
    spans = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith('//', i):
            j = text.find('\n', i)
            j = n if j < 0 else j
            spans.append((i, j))
            i = j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            spans.append((i, j))
            i = j
        elif c == 'R' and text.startswith('R"', i):
            m = re.match(r'R"([^(]*)\(', text[i:])
            end = text.find(')' + m.group(1) + '"', i)
            i = n if end < 0 else end + len(m.group(1)) + 2
        elif c in '"\'':
            if c == "'" and i > 0 and text[i - 1].isalnum():
                i += 1
                continue
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == '\\' else 1
            i = j + 1
        else:
            i += 1
    return spans


def angle_end(code, i):
    """The position of the > that closes the < at i, or -1."""
    depth = 0
    for j in range(i, len(code)):
        if code[j] == '<':
            depth += 1
        elif code[j] == '>':
            depth -= 1
            if depth == 0:
                return j
    return -1


def split_top(inner):
    """The parts of inner between its commas out of any angle brackets."""
    parts, depth, start = [], 0, 0
    for j, c in enumerate(inner):
        if c == '<':
            depth += 1
        elif c == '>':
            depth -= 1
        elif c == ',' and depth == 0:
            parts.append(inner[start:j])
            start = j + 1
    parts.append(inner[start:])
    return parts


def space_templates(code):
    """The arguments of the templates of a piece of code spaced as in the
    code: one space inside the angle brackets, and before and after a
    comma; a < that closes nothing, follows no name or operator, or opens
    something that is no list of types and values (an HTML tag) stays."""
    out, i = [], 0
    while i < len(code):
        c = code[i]
        if c == '<' and i > 0 and (code[i - 1].isalnum() or
                                   code[i - 1] == '_') \
                and not re.search(r'\boperator$', code[:i]):
            j = angle_end(code, i)
            inner = code[i + 1:j] if j > 0 else ''
            if inner.strip() and re.fullmatch(r'[\w:\s,*&<>.\[\]]*', inner) \
                    and not inner.lstrip().startswith(('/', '<')):
                args = ' , '.join(space_templates(p.strip())
                                  for p in split_top(inner))
                out.append('< ' + args + ' >')
                i = j + 1
                continue
        out.append(c)
        i += 1
    return ''.join(out)


# the code within the prose of Doxygen: the text of \ref NAME "TEXT", the
# word after \c or \p, <tt> ... </tt>, <code> ... </code> and ` ... `
INLINE_CODE = re.compile(r'([\\@]ref\s+\S+\s+")([^"\n]*)(")'
                         r'|([\\@][cp][ \t]+)(\S+)()'
                         r'|(<tt>)(.*?)(</tt>)'
                         r'|(<code>)(.*?)(</code>)'
                         r'|(`)([^`\n]+)(`)')

# what in the prose is no prose: blocks of code, formulas, verbatim text
NOT_PROSE = re.compile(r'[\\@]code\b.*?[\\@]endcode\b'
                       r'|[\\@]f\$.*?[\\@]f\$|[\\@]f\[.*?[\\@]f\]'
                       r'|[\\@]f\{.*?[\\@]f\}'
                       r'|[\\@]verbatim\b.*?[\\@]endverbatim\b', re.S)


def space_prose(doc):
    """The code within the prose of doc, a comment or a page of Doxygen,
    with the arguments of its templates spaced as in the code."""
    def inline(m):
        g = m.groups()
        for k in range(0, len(g), 3):
            if g[k] is not None:
                return g[k] + space_templates(g[k + 1]) + g[k + 2]
        return m.group(0)
    out, last = [], 0
    for m in NOT_PROSE.finditer(doc):
        out.append(INLINE_CODE.sub(inline, doc[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(INLINE_CODE.sub(inline, doc[last:]))
    return ''.join(out)


def format_doc_inline(text, path='file.h'):
    """The code within the prose of the comments, or of a page of Doxygen
    (.dox) whole, with the arguments of its templates spaced as in the
    code [see space_prose()]."""
    if path.endswith('.dox'):
        return space_prose(text)
    out, last = [], 0
    for a, b in comment_spans(text):
        out.append(text[last:a])
        out.append(space_prose(text[a:b]))
        last = b
    out.append(text[last:])
    return ''.join(out)


def format_text(text, clang_format='clang-format', path='file.h'):
    if path.endswith('.dox'):
        return format_doc_inline(format_doc_code(text, clang_format, path),
                                 path)
    text = format_code(text, clang_format, path)
    return format_doc_inline(format_doc_code(text, clang_format, path),
                             path)


# the characters that a formatting may add to the tokens of the code: the
# parentheses of wrap_returns, and the // and * of a comment split in two
LAYOUT_TOKENS = '()/*'


def restrict(old, new, ranges):
    """new, with only the changes that touch the lines of old in ranges
    (pairs of 1-based first and last lines) taken, and old elsewhere. A
    change is taken only if the lines of new have the tokens of the lines
    of old they replace: when the two texts are far apart (e.g., formatted
    in another style), the diff may pair lines of different code, and
    taking them would drop or repeat it."""
    import difflib
    a, b = old.split('\n'), new.split('\n')
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, a, b, autojunk=False).get_opcodes():
        if tag == 'equal':
            out.extend(a[i1:i2])
            continue
        lo, hi = i1 + 1, max(i2, i1 + 1)
        if (any(lo <= r[1] and r[0] <= hi for r in ranges) and
                cpp_tokens('\n'.join(a[i1:i2]), LAYOUT_TOKENS) ==
                cpp_tokens('\n'.join(b[j1:j2]), LAYOUT_TOKENS)):
            out.extend(b[j1:j2])
        else:
            out.extend(a[i1:i2])
    return '\n'.join(out)


def git_ranges(path, ref='HEAD'):
    """The lines of path changed since ref, as for git diff -U0."""
    import os
    d = os.path.dirname(os.path.abspath(path))
    try:
        diff = subprocess.run(['git', 'diff', '-U0', ref, '--',
                               os.path.basename(path)], cwd=d,
                              capture_output=True, text=True,
                              check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if not diff and subprocess.run(
            ['git', 'ls-files', '--error-unmatch', os.path.basename(path)],
            cwd=d, capture_output=True).returncode != 0:
        return None   # a file git does not know: all of it is new
    ranges = []
    for m in re.finditer(r'^@@ -\S+ \+(\d+)(?:,(\d+))? @@', diff, re.M):
        first, count = int(m.group(1)), int(m.group(2) or 1)
        if count:
            ranges.append((first, first + count - 1))
    return ranges


def has_style(path):
    """Whether a .clang-format is in the directory of path or above it:
    without one, the one next to this script is used [see main()]."""
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if any(os.path.isfile(os.path.join(d, n))
               for n in ('.clang-format', '_clang-format')):
            return True
        if os.path.dirname(d) == d:
            return False
        d = os.path.dirname(d)


def named_style(path):
    """The variant of the style (a directory of styles/, next to this
    script) that the first .code-format up the tree of path chooses by its
    line STYLE NAME, or None."""
    d = os.path.dirname(os.path.abspath(path))
    while True:
        f = os.path.join(d, '.code-format')
        if os.path.isfile(f):
            with open(f, encoding='utf-8') as g:
                for line in g:
                    words = line.split()
                    if len(words) == 2 and words[0] == 'STYLE':
                        return words[1]
            return None
        if os.path.dirname(d) == d:
            return None
        d = os.path.dirname(d)


def style_path(path):
    """The name that clang-format is given for path, which it looks for
    the style up the tree of: path itself if it has a .clang-format above
    it, else the same name next to this script, or in the directory of the
    variant that its .code-format chooses."""
    if has_style(path):
        return path
    d = os.path.dirname(os.path.realpath(__file__))
    name = named_style(path)
    if name is not None:
        d = os.path.join(d, 'styles', name)
        if not os.path.isfile(os.path.join(d, '.clang-format')):
            raise ValueError('no style %s, chosen by the .code-format of %s'
                             % (name, path))
    return os.path.join(d, os.path.basename(path))


def generated(text):
    """Whether the file says in its first lines that a program writes it
    (DO NOT EDIT, @generated): its layout is the one of that program."""
    head = '\n'.join(text.split('\n', 10)[:10])
    return re.search(r'DO NOT EDIT|@generated', head, re.I) is not None


def usage():
    """The part of the documentation that says how to run the script."""
    return __doc__[__doc__.index('Usage:'):].rstrip()


def main(argv):
    if '-h' in argv or '--help' in argv:
        print(usage())
        return 0
    check = '--check' in argv
    use_git = '--git' in argv
    ref = 'HEAD'
    ranges = None
    files = []
    k = 0
    while k < len(argv):
        a = argv[k]
        if a == '--since':
            use_git = True
            ref = argv[k + 1]
            k += 2
            continue
        if a == '--lines':
            lo, hi = argv[k + 1].split(':')
            ranges = [(int(lo), int(hi))]
            k += 2
            continue
        if a.startswith('-') and a not in ('--check', '--git'):
            print('format.py: unknown option %s\n%s' % (a, usage()),
                  file=sys.stderr)
            return 2
        if a not in ('--check', '--git'):
            files.append(a)
        k += 1
    changed = []
    status = 0
    for path in files:
        with open(path, encoding='latin-1') as f:
            text = f.read()
        if generated(text):
            continue
        try:
            new = format_text(text, path=style_path(path))
        except ValueError as e:
            print('format.py: %s' % e, file=sys.stderr)
            return 2
        r = ranges
        if use_git:
            r = git_ranges(path, ref)
        if r is not None:
            new = restrict(text, new, r)
        if new != text:
            changed.append(path)
            if not check:
                with open(path, 'w', encoding='latin-1') as f:
                    f.write(new)
    for p in changed:
        print(p)
    return status or (1 if check and changed else 0)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
