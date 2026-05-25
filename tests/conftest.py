import pytest

from qy.core.syntax import list_to_chain
from qy.frontend.reader import Symbol
from qy.runtime import Qy
from qy.session.runtime_space import create_standard_runtime_space as standard_environment


def L(*items, span=None):
    """测试辅助：构造 Chain."""
    return list_to_chain(list(items), span=span)


def S(name, span=None):
    """测试辅助：构造 Symbol."""
    return Symbol(name, span)


@pytest.fixture
def env():
    return standard_environment()


@pytest.fixture
def qy():
    return Qy()
