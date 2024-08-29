from typing import Literal
from qy.core import qy, symbol

T = qy.symbol('T', True)
NIL = qy.symbol('NIL', False)


@qy.operator('quote')
def quote(exp):
    return exp


@qy.operator('atom')
def atom(exp):
    if isinstance(exp, tuple) and len(exp) != 0:
        return NIL
    return T


@qy.operator('eq')
def eq(x, y) -> Literal['T', 'NIL']:
    # TODO: fix bug: the op may be not work correctly
    if x and y and isinstance(x, tuple) and isinstance(y, tuple):
        return NIL
    if not x and not y and isinstance(x, tuple) and isinstance(y, tuple):
        return T
    return T if x == y else NIL


@qy.operator('car')
def car(exp: tuple):
    return exp[0]


@qy.operator('cdr')
def cdr(exp: tuple):
    return exp[1:]


@qy.operator('cons')
def cons(x, y: tuple):
    return (x,) + y


@qy.operator('cond')
def cond(*cond_ressults: tuple):
    for c, r in cond_ressults:
        if not qy.eval(c) in [(), NIL, False]:
            return qy.eval(r)
    return NIL


@qy.operator('kwargs')
def kw(*args):
    return {args[i]: args[i + 1] for i in range(0, len(args), 2)}


@qy.operator('+')
def add(*args):
    return sum(args)


@qy.operator('-')
def sub(*args):
    return args[0] - sum(args[1:])


@qy.operator('*')
def mul(*args):
    result = 1
    for arg in args:
        result *= arg
    return result


@qy.operator('/')
def div(*args):
    result = args[0]
    for arg in args[1:]:
        result /= arg
    return result
