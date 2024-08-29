# coding: utf-8

__version__ = '0.0.4'
__author__ = 'Ge'
__all__ = [
    'qy',
    'symbol',
    'symbolproxy',
    't', 'T',
    'nil', 'NIL',
    'quote', 'atom', 'eq', 'car', 'cdr', 'cons', 'cond'
]

"""
Created on 2024-08-15

"""

from qy.core import symbol, symbolproxy
from qy.operator import qy, T, NIL
from qy.operator import quote, atom, eq, car, cdr, cons, cond

t = T
nil = NIL
