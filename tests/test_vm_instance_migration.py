# coding: utf-8
"""测试 VM 实例迁移的完整性。.

验证 RegisterVirtualMachine 从 qy/register_vm.py 迁移到 qy/vm/instance/machine.py 后：
1. 新位置可以正常导入和使用
2. 旧位置仍然可以导入（向后兼容）
3. 两者引用同一个类
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


def test_old_location_backward_compatibility():
    """测试旧位置仍然可以导入（向后兼容）。."""
    from qy.register_vm import RegisterVirtualMachine
    from qy.register_vm import call_function_value
    from qy.register_vm import evaluate_bytecode
    from qy.register_vm import evaluate_bytecode_async
    from qy.register_vm import evaluate_bytecode_source
    from qy.register_vm import evaluate_bytecode_source_async

    assert RegisterVirtualMachine is not None
    assert call_function_value is not None
    assert evaluate_bytecode is not None
    assert evaluate_bytecode_async is not None
    assert evaluate_bytecode_source is not None
    assert evaluate_bytecode_source_async is not None


def test_both_locations_reference_same_class():
    """测试新旧位置引用同一个类。."""
    from qy.register_vm import RegisterVirtualMachine as OldVM
    from qy.register_vm import call_function_value as old_call
    from qy.vm.instance.machine import RegisterVirtualMachine as NewVM
    from qy.vm.instance.machine import call_function_value as new_call

    assert OldVM is NewVM
    assert old_call is new_call


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
    from qy.backend.vm.compiler import compile_bytecode
    from qy.environment import standard_environment
    from qy.frontend.reader import read
    from qy.ir import ProgramIR
    from qy.passes.lower_hir import lower
    from qy.vm.instance.machine import RegisterVirtualMachine

    source = "(+ 1 2)"
    forms = read(source)
    env = standard_environment()
    program_ir = lower(forms, env)
    bytecode = compile_bytecode(ProgramIR(program_ir.body, program_ir.diagnostics))

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
    assert hasattr(qy, "evaluate_bytecode")
    assert hasattr(qy, "evaluate_bytecode_async")
    assert hasattr(qy, "evaluate_bytecode_source")
    assert hasattr(qy, "evaluate_bytecode_source_async")
