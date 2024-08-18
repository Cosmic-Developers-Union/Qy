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
