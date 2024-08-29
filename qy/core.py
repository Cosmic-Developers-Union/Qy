# coding: utf-8

__all__ = [
    'symbol',
    'symbolproxy',
    'qy'
]

"""
Created on 2024-08-15

"""

import traceback
from typing import Callable, Any, Union
import warnings

import lark
PYOBJECT = object
ATOM = Union[
    str, int, float, bytes, bool, None, 'symbol',
    object
]

SEXPRESSION = Union[ATOM, tuple[ATOM]]

INTERMEDIATE_LANG = tuple[
    'INTERMEDIATE_LANG',
    'symbol',
    int, float, str, bool, None, bytes
]

GRAMMER = f"""
?start: expressions
expressions: expression*
?expression: atom
    | list
    | quote_expression -> quote
?quote_expression: "'" expression
?list: "(" expression* ")"
?atom: STRING   -> string
    | SYMBOL    -> symbol
STRING: /"[^"]*"/
SYMBOL: /[a-zA-Z0-9_\-@:\.\+\/]+/
%import common.WS
%ignore WS
"""

parser = lark.Lark(GRAMMER)


@lark.v_args(inline=True)
class QyTransformer(lark.Transformer):
    def expressions(self, *tokens):
        return list(tokens)

    def quote(self, tokens):
        return ('quote', tokens)

    def string(self, token):
        return str(token[1:-1])

    def symbol(self, name):
        return symbolproxy(name)

    def list(self, *items):
        return items


def reader(source: str):
    tree = parser.parse(source)
    return QyTransformer().transform(tree)


class QyError(Exception):
    ...


class QySyntaxError(QyError):
    ...


class QyRuntimeError(QyError):
    ...


class QySymbolError(QyError):
    ...


class QyEvelError(QyError):
    pass


class symbol:
    """
    symbol is different from other symbol.
    we can use symbol as a function, and we can use symbol as a value.
    it should be differenciated from the symbol in the symbol space.

    when the symbol is used as a function, it should be evaluated.
    when the symbol is used as a value, it should be returned

    so, if the symbol is the first element of the s-expression, 
        evaluator will use symbol.__call__ to evaluate it.
        for operator, user can require evaluator use orginal value (s-exp)
        ...
    if the symbol is not the first element,
        evaluator will use symbol.value to return the symbol object.

    name is the name of the symbol.

    """
    __solts__ = ('name', 'value', 'require_eval')

    def __init__(self, name: str, value: Any = None) -> None:
        self.name = name
        self.value = value

    def __eq__(self, value: object) -> bool:
        return (
            isinstance(value, symbol)
            and value.name == self.name
            and value.value == self.value
        )

    def __hash__(self) -> int:
        return hash((self.name, self.value))

    def __repr__(self) -> str:
        return f'<symbol {self.name}>'

    def __str__(self) -> str:
        return self.name

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.value(*args, **kwds)

    def __bool__(self) -> bool:
        return bool(self.value)


class symbolproxy:
    __solts__ = ('name')

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f'<symbolproxy {self.name}>'


class Qy:

    def __init__(self, *, thread=False) -> None:
        self.SYMBOLSPACE: dict[str, symbol] = {}

    def symbol(self, name: str, value: Any = None) -> symbol:
        s = symbol(name, value)
        if name in self.SYMBOLSPACE:  # warning
            warnings.warn(f'{name} is already in the symbol space')
        self.SYMBOLSPACE[name] = s
        return s

    def operator(self, name: str, func: Callable = None) -> None:
        if not isinstance(name, str):
            raise TypeError('name must be str')
        if func is None:
            return lambda func: self.operator(name, func)
        if not callable(func):
            raise TypeError('func must be callable')
        s = symbol(name, func)
        self.SYMBOLSPACE[name] = s
        return s

    def eval(self, s_expression: SEXPRESSION):
        """
        if s-expression is atom (symbol? NIL T), return it.

        if s-exp only is exp(need eval) or aotm

        TODO: should I return the symbol object or the value of the symbol?

        """
        # symbol evaluation
        if isinstance(s_expression, symbol):
            return s_expression.value
        if isinstance(s_expression, symbolproxy):
            if s_expression.name in self.SYMBOLSPACE:
                return self.SYMBOLSPACE[s_expression.name].value
            try:
                return int(s_expression.name)
            except ValueError:
                pass
            try:
                return float(s_expression.name)
            except ValueError:
                pass
            raise QySymbolError(
                f'{s_expression.name} is not in the symbol space')
        if not isinstance(s_expression, tuple):
            return s_expression

        # s-expression evaluation
        operator, *arguments = s_expression

        # search symbol from symbol space
        if isinstance(operator, symbolproxy):
            operator: symbol = self.SYMBOLSPACE[operator.name]

        # TODO: optimize the code
        if isinstance(operator, symbol):
            from .operator import quote, car, cdr, cons, cond
            if operator is quote:
                if len(arguments) != 1:
                    raise QyEvelError('Error: quote')
                return arguments[0]
            if operator is car:
                if len(arguments) != 1:
                    raise QyEvelError('Error: car')
                return car(self.eval(arguments[0]))
            if operator is cdr:
                if len(arguments) != 1:
                    raise QyEvelError('Error: cdr')
                return cdr(self.eval(arguments[0]))
            if operator is cons:
                if len(arguments) != 2:
                    raise QyEvelError('Error: cons')
                return cons(self.eval(arguments[0]), self.eval(arguments[1]))
            if operator is cond:
                return cond(*arguments)
        try:
            from .operator import kw
            args, kwargs = [], {}
            for arg in arguments:
                if isinstance(arg, tuple) and arg and arg[0] is kw:
                    kwargs.update(kw(*arg[1:]))
                else:
                    args.append(arg)
            for k, v in kwargs.items():
                kwargs[k] = self.eval(v)
            return operator(*map(self.eval, args), **kwargs)
        except SystemExit as e:
            raise e from None
        except BaseException as e:
            e = '\n'.join(traceback.format_exception(e))
            raise QyEvelError(
                f'Error: {operator} {tuple(arguments)}\n\n{e}'
            ) from None

    async def aeval(self, s_expression: SEXPRESSION):
        from .operator import T, NIL, atom

        if atom(s_expression) is T:
            return s_expression

        # when s-expression is (), return NIL
        # if you want to return (), you should use quote
        if s_expression == ():
            return NIL

        if not isinstance(s_expression, tuple):
            if isinstance(s_expression, (symbol, symbolproxy)):
                return s_expression.value
            return s_expression

        operator, *arguments = s_expression

        if isinstance(operator, (symbol, symbolproxy)):
            from .operator import quote, car, cdr, cons, cond
            if operator is quote:
                if len(arguments) != 1:
                    raise QyEvelError('Error: quote')
                return arguments[0]
            if operator is car:
                if len(arguments) != 1:
                    raise QyEvelError('Error: car')
                return car(await self.aeval(arguments[0]))
            if operator is cdr:
                if len(arguments) != 1:
                    raise QyEvelError('Error: cdr')
                return cdr(await self.aeval(arguments[0]))
            if operator is cons:
                if len(arguments) != 2:
                    raise QyEvelError('Error: cons')
                return cons(await self.aeval(arguments[0]), await self.aeval(arguments[1]))
            if operator is cond:
                return await cond(*arguments)
        try:
            arguments_result = []

            for arg in arguments:
                arguments_result.append(await self.aeval(arg))
            return await operator(*arguments_result)
        except SystemExit as e:
            raise e
        except BaseException as e:
            e = '\n'.join(traceback.format_exception(e))
            raise QyEvelError(
                f'Error: {operator} {arguments}\n\n{e}'
            ) from None

    def exec(self, ast: INTERMEDIATE_LANG):
        self.eval(ast)


qy = Qy()
