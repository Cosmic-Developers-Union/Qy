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
    def symbol(cls, name: str, value: Any = None) -> symbol:
        s = symbol(name, value)
        cls.SYMBOLSPACE[name] = s
        return s

    @classmethod
    def operator(cls, name: str, func: Callable = None) -> None:
        if not isinstance(name, str):
            raise TypeError('name must be str')
        if func is None:
            return lambda func: cls.operator(name, func)
        if not callable(func):
            raise TypeError('func must be callable')
        s = symbol(name, func)
        cls.SYMBOLSPACE[name] = s
        return s

    def __init__(self, intermediate_lang: INTERMEDIATE_LANG, *, thread=False) -> None:
        ...

    @classmethod
    def eval(cls, s_expression: SEXPRESSION):
        if not isinstance(s_expression, tuple):
            if isinstance(s_expression, (symbol, symbolproxy)):
                return s_expression.value
            return s_expression
        operator, *arguments = s_expression

        if isinstance(operator, (symbol, symbolproxy)):
            from .operator import quote
            if operator is quote:
                if len(arguments) != 1:
                    raise QyEvelError('Error: quote')
                return arguments[0]
            operator = operator.value
        try:
            return operator(*map(cls.eval, arguments))
        except BaseException as e:
            raise QyEvelError(f'Error: {operator} {arguments}')

    @classmethod
    def exec(cls, ast: INTERMEDIATE_LANG):
        cls.eval(ast)
