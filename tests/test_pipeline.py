# coding: utf-8
"""测试 qy.passes.pipeline 模块。."""

from __future__ import annotations

from qy.passes.pass_base import Pass
from qy.passes.pass_base import PassContext
from qy.passes.pass_base import PassResult
from qy.passes.pipeline import Pipeline


class MockPass(Pass):
    """用于测试的 mock pass。."""

    def __init__(self, name: str, should_fail: bool = False):
        """初始化 mock pass。."""
        self.name = name
        self.should_fail = should_fail
        self.executed = False

    def run(self, context: PassContext) -> PassResult:
        """执行 pass。."""
        self.executed = True
        if self.should_fail:
            return PassResult(
                success=False,
                artifact=context.input_artifact,
                diagnostics=[],
            )
        # 简单地将 artifact 加上 pass 名称
        new_artifact = f"{context.input_artifact}+{self.name}"
        return PassResult(
            success=True,
            artifact=new_artifact,
            diagnostics=[],
        )


def test_pipeline_creation():
    """测试创建 pipeline。."""
    pipeline = Pipeline()
    assert pipeline.passes == []


def test_pipeline_add_pass():
    """测试添加 pass 到 pipeline。."""
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2")

    pipeline.add_pass(pass1)
    assert len(pipeline.passes) == 1
    assert pipeline.passes[0] is pass1

    pipeline.add_pass(pass2)
    assert len(pipeline.passes) == 2
    assert pipeline.passes[1] is pass2


def test_pipeline_run_empty():
    """测试运行空 pipeline。."""
    pipeline = Pipeline()
    context = PassContext(
        input_artifact="initial",
        diagnostics=[],
        options={},
    )
    result = pipeline.run(context)
    assert result.success is True
    assert result.artifact == "initial"
    assert result.diagnostics == []


def test_pipeline_run_single_pass():
    """测试运行单个 pass。."""
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pipeline.add_pass(pass1)

    context = PassContext(
        input_artifact="initial",
        diagnostics=[],
        options={},
    )
    result = pipeline.run(context)

    assert pass1.executed is True
    assert result.success is True
    assert result.artifact == "initial+pass1"
    assert result.diagnostics == []


def test_pipeline_run_multiple_passes():
    """测试运行多个 pass。."""
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2")
    pass3 = MockPass("pass3")

    pipeline.add_pass(pass1)
    pipeline.add_pass(pass2)
    pipeline.add_pass(pass3)

    context = PassContext(
        input_artifact="initial",
        diagnostics=[],
        options={},
    )
    result = pipeline.run(context)

    assert pass1.executed is True
    assert pass2.executed is True
    assert pass3.executed is True
    assert result.success is True
    assert result.artifact == "initial+pass1+pass2+pass3"


def test_pipeline_stops_on_failure():
    """测试 pipeline 在 pass 失败时停止。."""
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2", should_fail=True)
    pass3 = MockPass("pass3")

    pipeline.add_pass(pass1)
    pipeline.add_pass(pass2)
    pipeline.add_pass(pass3)

    context = PassContext(
        input_artifact="initial",
        diagnostics=[],
        options={},
    )
    result = pipeline.run(context)

    assert pass1.executed is True
    assert pass2.executed is True
    assert pass3.executed is False  # 不应该执行
    assert result.success is False
    assert result.artifact == "initial+pass1"


def test_pipeline_run_with_target():
    """测试使用 target 参数运行 pipeline。."""
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2")
    pass3 = MockPass("pass3")

    pipeline.add_pass(pass1)
    pipeline.add_pass(pass2)
    pipeline.add_pass(pass3)

    context = PassContext(
        input_artifact="initial",
        diagnostics=[],
        options={},
    )
    result = pipeline.run(context, target="pass2")

    assert pass1.executed is True
    assert pass2.executed is True
    assert pass3.executed is False  # 应该在 pass2 后停止
    assert result.success is True
    assert result.artifact == "initial+pass1+pass2"


def test_pipeline_run_with_after():
    """测试使用 after 参数运行 pipeline。."""
    pipeline = Pipeline()
    pass1 = MockPass("pass1")
    pass2 = MockPass("pass2")
    pass3 = MockPass("pass3")

    pipeline.add_pass(pass1)
    pipeline.add_pass(pass2)
    pipeline.add_pass(pass3)

    context = PassContext(
        input_artifact="initial",
        diagnostics=[],
        options={},
    )
    # after 参数目前只是占位，不影响执行
    result = pipeline.run(context, after="pass2")

    assert pass1.executed is True
    assert pass2.executed is True
    assert pass3.executed is True
    assert result.success is True
    assert result.artifact == "initial+pass1+pass2+pass3"
