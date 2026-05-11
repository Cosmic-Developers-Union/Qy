import pytest

from qy.evaluator import standard_environment
from qy.reader import Symbol
from qy.runtime import Qy

S = Symbol


@pytest.fixture
def env():
    return standard_environment()


@pytest.fixture
def qy():
    return Qy()
