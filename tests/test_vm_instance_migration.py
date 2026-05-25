# coding: utf-8
"""测试 VM 实例迁移的完整性。.

验证 RegisterVirtualMachine 从 qy/register_vm.py 迁移到 qy/vm/instance/machine.py 后：
1. 新位置可以正常导入和使用
2. 旧位置已被移除（迁移完成）
"""


def test_new_location_imports():
    """测试从新位置导入所有公共 API。."""
    from qy.vm.instance.machine import RegisterVirtualMachine
    from qy.vm.instance.machine import call_function_value
    from qy.vm.instance.machine import evaluate_bytecode
    from qy.vm.instance.machine import evaluate_bytecode_async
    from qy.vm.instance.machine import evaluate_bytecode_source
    from qy.vm.instance.machine import evaluate_bytecode_source_async

    assert RegisterVirtualMachine is not None
    assert call_function_value is not None
    assert evaluate_bytecode is not None
    assert evaluate_bytecode_async is not None
    assert evaluate_bytecode_source is not None
    assert evaluate_bytecode_source_async is not None


def test_old_location_removed():
    """测试旧位置已被移除（迁移完成）。."""
    import importlib.util

    spec = importlib.util.find_spec("qy.register_vm")
    assert spec is None, "qy.register_vm should be removed after migration"


def test_vm_instance_module_exports():
    """测试 qy.vm.instance 模块正确导出所有内容。."""
    from qy.vm.instance import RegisterVirtualMachine
    from qy.vm.instance import call_function_value
    from qy.vm.instance import evaluate_bytecode
    from qy.vm.instance import evaluate_bytecode_async
    from qy.vm.instance import evaluate_bytecode_source
    from qy.vm.instance import evaluate_bytecode_source_async

    assert RegisterVirtualMachine is not None
    assert call_function_value is not None
    assert evaluate_bytecode is not None
    assert evaluate_bytecode_async is not None
    assert evaluate_bytecode_source is not None
    assert evaluate_bytecode_source_async is not None


def test_register_vm_basic_functionality():
    """测试 RegisterVirtualMachine 基本功能仍然正常。."""
    from qy.async_utils import run_coro
    from qy.passes.build import bytecode_artifact
    from qy.passes.build import compile_source_to_bytecode_async
    from qy.passes.pass_base import PipelineSession
    from qy.session.runtime_space import create_standard_runtime_space as standard_environment
    from qy.vm.instance.machine import RegisterVirtualMachine

    source = "(+ 1 2)"
    env = standard_environment()
    session = PipelineSession(env=env)
    pipeline_result = run_coro(compile_source_to_bytecode_async(source, session))
    bytecode = bytecode_artifact(pipeline_result)

    vm = RegisterVirtualMachine(bytecode, env)
    result = vm.evaluate()

    # 使用 asyncio 运行
    import asyncio

    result = asyncio.run(result)
    assert result == 3


def test_evaluate_bytecode_source_from_new_location():
    """测试从新位置使用 evaluate_bytecode_source。."""
    from qy.vm.instance.machine import evaluate_bytecode_source

    result = evaluate_bytecode_source("(+ 10 20)")
    assert result == 30


def test_public_api_still_exports_from_qy():
    """测试公共 API (qy.__init__) 仍然导出这些符号。."""
    import qy

    assert hasattr(qy, "RegisterVirtualMachine")
    assert hasattr(qy, "evaluate_bytecode_async")
