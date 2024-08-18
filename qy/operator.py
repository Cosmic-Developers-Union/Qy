from qy.core import qy, symbol


@qy.operator('quote')
def quote(exp):
    return exp
