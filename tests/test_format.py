#!/usr/bin/env python3
"""Tests of format.py: each case is a source, and the checks on what the
formatter makes of it. Run: python3 tests/test_format.py (clang-format 22
and the .clang-format of the root of the repository are needed)."""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import format as fmt  # noqa: E402

CASES = [
    # name, source, lines that the result must contain, and must not
    ('return and throw in parentheses',
     'int f( int x ) { if( x ) throw 3; return x + 1; }\n',
     ['  throw( 3 );', ' return( x + 1 );'], []),
    ('the return of a lambda inside a return',
     'bool f( const std::vector< int > & v ) {\n'
     ' return std::any_of( v.begin() , v.end() , []( int n ) { '
     'return n > 0; } );\n}\n',
     [], ['( ! n.empty() );', ')( ']),
    ('a throw specification is no throw',
     'struct E { const char * what() const throw() { return m; } };\n',
     ['const throw() {'], ['throw( ()']),
    ('a throw after the condition of an if or a while',
     'void g() { if( x ) throw E(); while( y ) throw 1; throw; }\n',
     ['  throw( E() );', '  throw( 1 );', ' throw;'], []),
    ('a multi-line macro keeps its continuations',
     '#define M( x ) \\\n  inline int h( int a ) \\\n  { return a + x ; }\n',
     [], ['\n{']),
    ('a throw in a macro ending without a semicolon',
     '#define GOODN( n ) if( n <= 0 ) \\\n'
     '  throw std::invalid_argument( "bad" )\n'
     'REGISTER( X );\n',
     ['REGISTER( X );'], ['REGISTER( X ) );']),
    ('the #define of an include guard one space in, not a default',
     '#ifndef GUARD_H\n#define GUARD_H\n#ifndef DIR\n#define DIR "."\n'
     '#endif\n#endif\n',
     [' #define GUARD_H', '\n#define DIR "."'], []),
    ('a directive indented in the code stays where it is',
     'void f()\n{\n if( x ) {\n  #ifndef NDEBUG\n  g();\n  #endif\n'
     '  }\n}\n',
     ['\n  #ifndef NDEBUG\n', '\n  #endif\n'], []),
    ('a long #include stays on its line',
     '#include BOOST_PP_STRINGIZE( BOOST_PP_CAT( BOOST_PP_CAT( CPX , '
     'CPX_VERSION ) , _maps.h ) )\n',
     ['#include BOOST_PP_STRINGIZE('], []),
    ('a space before the commas and the semicolons of a for',
     'void f() { for( int i = 0; i < n; ++i ) g( a, b ); }\n',
     ['for( int i = 0 ; i < n ; ++i )', 'g( a , b );'], []),
    ('a long header of a for broken after a semicolon',
     'void f() { for( notifier()->first( arc ) ; arc != INVALID_ARC_VALUE ; '
     'notifier()->next( arc ) ) g(); }\n',
     [' for( notifier()->first( arc ) ; arc != INVALID_ARC_VALUE ;\n'], []),
    ('the closing brace on the indentation of the block',
     'void f() {\n if( x ) {\n  g();\n }\n}\n',
     ['  }', ' }'], []),
    ('the using-declarations keep their order',
     'struct S : B {\n using B::set_par;\n using B::get_dbl_par;\n};\n',
     [], []),
    ('the C++ of a block of code of a comment formatted as the rest',
     '/// An example:\n///\\code\n///  AddMap<M1,M2> am(m1,m2);\n'
     '///  while (!q.empty()) {\n///    q.pop();\n///  }\n'
     '///\\endcode\nint f();\n',
     ['/// AddMap< M1 , M2 > am( m1 , m2 );\n',
      '/// while( ! q.empty() ) {\n///  q.pop();\n'], []),
    ('a block of code that is no C++ is left alone',
     '///\\code\n///@nodes\n///label  coordinates\n///0  (20,100)\n'
     '///\\endcode\nint f();\n',
     ['///label  coordinates\n///0  (20,100)\n'], []),
    ('a block of code with a token clang-format would change is left alone',
     '///\\code\n///  std::cout << "a" <<\n///    << "b";\n'
     '///\\endcode\nint f();\n',
     ['///  std::cout << "a" <<\n'], ['< <']),
    ('the argument of a macro that makes a string of it is left alone',
     'int f() { cout << GREEN( All tests passed!! ) << endl; }\n',
     ['GREEN( All tests passed!! )'], ['! !']),
    ('a long string literal is not split',
     'void f() { g( "a string literal that is long enough to go past the '
     'limit of the line" ); }\n',
     [], ['" "']),
]


def dox_page():
    """A page of Doxygen has its blocks of code formatted, the text not."""
    import tempfile as tf
    src = ('/**\n\\page p A page\n\nSome text, with(odd , spacing).\n\n'
           '\\code\nDijkstra<>::SetPredMap<NullMap<Node,Arc> >::Create\n'
           '\\endcode\n*/\n')
    out = fmt.format_text(src, path=os.path.join(HERE, 'page.dox'))
    return 'Some text, with(odd , spacing).' in out and \
        'Dijkstra<>::SetPredMap< NullMap< Node , Arc > >::Create' in out


def restrict_keeps_code():
    """A change that the diff pairs with lines of other code (here, the
    lines b() and c() of the old text with c() alone) is not taken: the
    lines restricted to drop or repeat no code."""
    old = 'void f()\n{\n a();\n b();\n c();\n }\n'
    new = 'void f()\n{\n  a();\n  c();\n}\n'
    out = fmt.restrict(old, new, [(4, 5)])
    return fmt.cpp_tokens(out, fmt.LAYOUT_TOKENS) == \
        fmt.cpp_tokens(old, fmt.LAYOUT_TOKENS)


def style_default():
    """A file with no .clang-format above it is formatted with the one of
    this repository, and one with its own is formatted with that."""
    work = tempfile.mkdtemp()
    try:
        path = os.path.join(work, 'case.cpp')
        with open(path, 'w') as f:
            f.write('int f(int x){if(x)return x;return 0;}\n')
        if fmt.has_style(path) or fmt.main([path]) != 0:
            return False
        with open(path) as f:
            if ' if( x )' not in f.read():
                return False
        # a project with a style of its own: two spaces, no space in ()
        with open(os.path.join(work, '.clang-format'), 'w') as f:
            f.write('BasedOnStyle: LLVM\nIndentWidth: 2\n')
        with open(path, 'w') as f:
            f.write('int f(int x){if(x)return x;return 0;}\n')
        fmt.main([path])
        with open(path) as f:
            return fmt.has_style(path) and '  if (x)' in f.read()
    finally:
        shutil.rmtree(work)


def style_variant():
    """A file with no .clang-format above it, whose .code-format chooses the
    variant spaces, is indented by spaces only and has a space after a
    cast; with no .code-format it takes tabs and no such space, and a
    variant that does not exist is refused."""
    src = ('void f(){if(a){if(b){x = some_function(first_argument_value, '
           'second_argument_value, third_argument);(void)h(x);}}}\n')
    work = tempfile.mkdtemp()
    try:
        path = os.path.join(work, 'case.cpp')
        with open(path, 'w') as f:
            f.write(src)
        if fmt.main([path]) != 0:
            return False
        with open(path) as f:
            plain = f.read()
        with open(os.path.join(work, '.code-format'), 'w') as f:
            f.write('# the variant of the style\nSTYLE spaces\n')
        with open(path, 'w') as f:
            f.write(src)
        if fmt.main([path]) != 0:
            return False
        with open(path) as f:
            spaces = f.read()
        with open(os.path.join(work, '.code-format'), 'w') as f:
            f.write('STYLE nonesuch\n')
        refused = fmt.main([path]) == 2
        return ('\t' in plain) and ('( void )h' in plain) and \
            ('\t' not in spaces) and ('( void ) h' in spaces) and refused
    finally:
        shutil.rmtree(work)


def break_aligned():
    """A call that the spaces before the commas push past the limit, deep
    enough for its arguments to start past the eighth column: each line
    broken goes on in the column of the first argument, by tabs with the
    style of this repository and by spaces alone with the variant
    spaces."""
    args = ','.join('a%d' % i for i in range(40))
    src = 'void f(){if(x){if(y){if(z){if(w){g(%s);}}}}}\n' % args
    outs = []
    for variant in (None, 'spaces'):
        work = tempfile.mkdtemp()
        try:
            path = os.path.join(work, 'case.cpp')
            with open(path, 'w') as f:
                f.write(src)
            if variant:
                with open(os.path.join(work, '.code-format'), 'w') as f:
                    f.write('STYLE %s\n' % variant)
            if fmt.main([path]) != 0:
                return False
            with open(path) as f:
                outs.append(f.read())
        finally:
            shutil.rmtree(work)
    for out in outs:
        lines = out.split('\n')
        first = next(i for i, l in enumerate(lines) if 'g( a0' in l)
        col = lines[first].expandtabs(8).index('a0')
        last = next(i for i in range(first, len(lines))
                    if lines[i].rstrip().endswith(');'))
        if last == first or any(
                len(l.expandtabs(8)) - len(l.expandtabs(8).lstrip()) != col
                for l in lines[first + 1:last + 1]):
            return False
    return '\t' in outs[0] and '\t' not in outs[1]


def generated_skipped():
    """A file that says it is generated is left as it is."""
    return fmt.generated('/* FILE GENERATED AUTOMATICALLY, DO NOT EDIT */\n') \
        and not fmt.generated('int f( int x );\n')


def run():
    work = tempfile.mkdtemp()
    style = os.path.join(HERE, '.clang-format')   # beside it, or one above
    if not os.path.exists(style):
        style = os.path.join(os.path.dirname(HERE), '.clang-format')
    shutil.copy(style, work)
    failed = 0
    try:
        for name, src, want, avoid in CASES:
            path = os.path.join(work, 'case.cpp')
            out = fmt.format_text(src, path=path)
            bad = [w for w in want if w not in out] + \
                  [a for a in avoid if a in out]
            if name == 'the using-declarations keep their order':
                if out.index('set_par') > out.index('get_dbl_par'):
                    bad.append('order')
            if bad:
                failed += 1
                print('FAIL %s: %s\n%s' % (name, bad, out))
            else:
                print('ok   %s' % name)
    finally:
        shutil.rmtree(work)
    if dox_page():
        print('ok   a page of Doxygen has only its blocks of code formatted')
    else:
        failed += 1
        print('FAIL a page of Doxygen has only its blocks of code formatted')
    if generated_skipped():
        print('ok   a generated file is left as it is')
    else:
        failed += 1
        print('FAIL a generated file is left as it is')
    for check, name in ((restrict_keeps_code, 'a change paired with other '
                         'code is not taken'),
                        (style_default, 'a file with no .clang-format above '
                         'it takes the one of this repository'),
                        (style_variant, 'the variant of the style that '
                         '.code-format chooses'),
                        (break_aligned, 'a line broken after a comma goes '
                         'on in the column of the first argument')):
        if check():
            print('ok   %s' % name)
        else:
            failed += 1
            print('FAIL %s' % name)
    print('%d of %d failed' % (failed, len(CASES) + 4))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(run())
