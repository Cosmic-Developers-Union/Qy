# coding: utf-8

__all__ = [
    'symbol',
    'symbolproxy',
    'qy'
]

"""
Created on 2024-08-15

"""

from typing import Callable, Any

SEXPRESSION = tuple['symbol']
INTERMEDIATE_LANG = tuple[
    'INTERMEDIATE_LANG',
    'symbol',
    int, float, str, bool, None, bytes
]


class QyEvelError(Exception):
    pass


class symbol:
    __solts__ = ('name', 'value')

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


class symbolproxy:
    __solts__ = ('name')

    def __init__(self, name: str) -> None:
        self.name = name

    @property
    def value(self) -> symbol:
        return qy.SYMBOLSPACE[self.name].value


class qy:
    SYMBOLSPACE: dict[str, symbol] = {}

    @classmethod
    def operator(cls, name: str, func: Callable = None) -> None:
        if func is None:
            return lambda func: cls.operator(name, func)
        s = symbol(name, func)
        cls.SYMBOLSPACE[name] = s
        return s

    def __init__(self, intermediate_lang: INTERMEDIATE_LANG, *, thread=False) -> None:
        ...

    @classmethod
    def atom(cls, s: symbol | Any):
        if isinstance(s, symbol):
            return s.value
        return s

    @classmethod
    def eval(cls, s_expression: SEXPRESSION):
        """
        eval

        Args:
            s_expression (SEXPRESSION): s_expression
                operator: symbol(recommand), Callable, str
                *argumnets: symbol
        """
        if not isinstance(s_expression, tuple):
            if isinstance(s_expression, (symbol, symbolproxy)):
                return s_expression.value
            return s_expression
        operator, *arguments = s_expression
        if isinstance(operator, (symbol, symbolproxy)):
            operator = operator.value
        try:
            return operator(*map(cls.eval, arguments))
        except BaseException as e:
            raise QyEvelError(f'Error: {operator} {arguments}')

    @classmethod
    def exec(cls, ast: INTERMEDIATE_LANG):
        cls.eval(ast)
