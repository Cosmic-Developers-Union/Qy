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
