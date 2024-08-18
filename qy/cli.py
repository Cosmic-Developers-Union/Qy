# coding: utf-8

"""
Created on 2024-08-15

"""
import code
from qy import *

LOCALS = globals()


def main():
    code.interact(
        banner='Qy Lang, a Lisp language implemented in and based on Python',
        readfunc=lambda prompt='': f"qy.eval((print, {input(prompt)}))",
        local=LOCALS,
        exitmsg='Goodbye!')
