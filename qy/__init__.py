"""Public Qy API.

Stable pipeline APIs are centered around `Qy`, `macroexpand`, `lower`, `lower_mir`,
`compile_mir_bytecode`, `compile_bytecode`, and `RegisterVirtualMachine`.
"""

# coding: utf-8

from qy.analysis import Analysis
from qy.analysis import Diagnostic
from qy.analysis import analyze
from qy.analysis import analyze_source
from qy.analysis import type_check_source
from qy.backend.llvm import compile_to_llvm_text
from qy.backend.llvm import emit
from qy.backend.llvm import link
from qy.backend.vm import BytecodeFunction
from qy.backend.vm import BytecodeProgram
from qy.backend.vm import Instruction
from qy.backend.vm import compile_bytecode
from qy.backend.vm import compile_lir_bytecode
from qy.backend.vm import compile_mir_bytecode
from qy.backend.vm import dump_bytecode
from qy.core.operator_signature import Arity
from qy.core.operator_signature import EffectSpec
from qy.core.operator_signature import OperatorSignature
from qy.core.operators import ControlOperator
from qy.core.operators import EffectOperator
from qy.core.operators import MetaOperator
from qy.core.operators import PureOperator
from qy.core.operators import ScopeOperator
from qy.core.syntax import Chain as QyChain
from qy.core.syntax import Chain as QyCons
from qy.core.syntax import QyNil
from qy.core.syntax import QyNil as QyEmptyChain
from qy.core.syntax import QyNil as QyEmptyList
from qy.core.syntax import nil as QY_EMPTY_CHAIN
from qy.core.syntax import nil as QY_EMPTY_LIST
from qy.core.syntax import nil as QY_NIL
from qy.display import format_value
from qy.environment import Environment
from qy.environment import standard_environment
from qy.errors import EvaluationError
from qy.errors import QyAggregateError
from qy.errors import QyArityError
from qy.errors import QyCancelledError
from qy.errors import QyCapabilityError
from qy.errors import QyEffectError
from qy.errors import QyEffectSignal
from qy.errors import QyError
from qy.errors import QyPythonError
from qy.errors import QyResolveError
from qy.errors import QyRuntimeError
from qy.errors import QySyntaxError
from qy.errors import QyTimeoutError
from qy.errors import QyTypeError
from qy.errors import SourceSpan
from qy.errors import TraceFrame
from qy.errors import format_qy_error
from qy.frontend.reader import DottedTuple
from qy.frontend.reader import Form
from qy.frontend.reader import ReaderSyntaxError
from qy.frontend.reader import Symbol
from qy.frontend.reader import TupleForm
from qy.frontend.reader import form_to_tuple
from qy.frontend.reader import read
from qy.frontend.reader import read_one
from qy.frontend.reader import read_one_tuple
from qy.frontend.reader import read_tuple
from qy.frontend.reader import tuple_to_form
from qy.frontend.reader import write
from qy.frontend.reader import write_program
from qy.frontend.reader import write_tuple
from qy.frontend.reader import write_tuple_program
from qy.ir import Binding
from qy.ir import CallExpr
from qy.ir import LiteralExpr
from qy.ir import ProgramIR
from qy.ir import SymbolRefExpr
from qy.ir import UnresolvedSymbolExpr
from qy.ir import dump_ir
from qy.ir.lir import LIRBindingAddr
from qy.ir.lir import LIRBindingSlot
from qy.ir.lir import LIRContinuationLayout
from qy.ir.lir import LIRFrameLayout
from qy.ir.lir import LIRFunction
from qy.ir.lir import LIRHandlerLayout
from qy.ir.lir import LIRInstruction
from qy.ir.lir import LIRProgram
from qy.ir.lir import LIRSymbolMeta
from qy.ir.lir import LIRSymbolSpaceLayout
from qy.ir.lir import dump_lir
from qy.ir.mir import MIRBlock
from qy.ir.mir import MIRFunction
from qy.ir.mir import MIRInstruction
from qy.ir.mir import MIRProgram
from qy.ir.mir import MIRTerminator
from qy.ir.mir import dump_mir
from qy.ir.mir import verify_mir
from qy.macro import MacroDefinition
from qy.macro import MacroEffectPolicy
from qy.macro import MacroExpansion
from qy.macro import MacroExpansionOptions
from qy.macro import MacroExpansionTrace
from qy.macro import MacroSourceMapEntry
from qy.macro import macroexpand
from qy.macro import macroexpand_async
from qy.macro import macroexpand_source
from qy.macro import macroexpand_source_async
from qy.passes.lower_hir import lower
from qy.passes.lower_hir import lower_source
from qy.passes.lower_lir import lower_lir
from qy.passes.lower_mir import lower_mir
from qy.runtime import AsyncQy
from qy.runtime import Qy
from qy.sem.core import T as QY_T
from qy.sem.core import TValue as QyT
from qy.sem.runtime import EffectDefinition
from qy.session import ProfileConfig
from qy.session import RuntimeSpace
from qy.session import create_standard_runtime_space
from qy.std.profile import OperatorDoc
from qy.std.profile import OperatorModuleDoc
from qy.std.profile import collect_supported_operators
from qy.std.profile import format_operator_docs
from qy.tools.fmt import dump_form
from qy.tools.fmt import dump_program
from qy.tools.fmt import format_form
from qy.tools.fmt import format_program
from qy.tools.fmt import format_source
from qy.vm.bytecode import BytecodeFunctionValue
from qy.vm.instance.frame import QyContinuation
from qy.vm.instance.machine import RegisterVirtualMachine
from qy.vm.instance.machine import evaluate_bytecode
from qy.vm.instance.machine import evaluate_bytecode_async
from qy.vm.instance.machine import evaluate_bytecode_source
from qy.vm.instance.machine import evaluate_bytecode_source_async
from qy.vm.instance.values import HostObjectRef

__version__ = "0.0.4"
__author__ = "Ge"
__all__ = [
    "QY_EMPTY_CHAIN",
    "QY_EMPTY_LIST",
    "QY_NIL",
    "QY_T",
    "Analysis",
    "Arity",
    "AsyncQy",
    "Binding",
    "BytecodeFunction",
    "BytecodeFunctionValue",
    "BytecodeProgram",
    "CallExpr",
    "ControlOperator",
    "Diagnostic",
    "DottedTuple",
    "EffectDefinition",
    "EffectOperator",
    "EffectSpec",
    "Environment",
    "EvaluationError",
    "Form",
    "HostObjectRef",
    "Instruction",
    "LIRBindingAddr",
    "LIRBindingSlot",
    "LIRContinuationLayout",
    "LIRFrameLayout",
    "LIRFunction",
    "LIRHandlerLayout",
    "LIRInstruction",
    "LIRProgram",
    "LIRSymbolMeta",
    "LIRSymbolSpaceLayout",
    "LiteralExpr",
    "MIRBlock",
    "MIRFunction",
    "MIRInstruction",
    "MIRProgram",
    "MIRTerminator",
    "MacroDefinition",
    "MacroEffectPolicy",
    "MacroExpansion",
    "MacroExpansionOptions",
    "MacroExpansionTrace",
    "MacroSourceMapEntry",
    "MetaOperator",
    "OperatorDoc",
    "OperatorModuleDoc",
    "OperatorSignature",
    "ProfileConfig",
    "ProgramIR",
    "PureOperator",
    "Qy",
    "QyAggregateError",
    "QyArityError",
    "QyCancelledError",
    "QyCapabilityError",
    "QyChain",
    "QyCons",
    "QyContinuation",
    "QyEffectError",
    "QyEffectSignal",
    "QyEmptyChain",
    "QyEmptyList",
    "QyError",
    "QyNil",
    "QyPythonError",
    "QyResolveError",
    "QyRuntimeError",
    "QySyntaxError",
    "QyT",
    "QyTimeoutError",
    "QyTypeError",
    "ReaderSyntaxError",
    "RegisterVirtualMachine",
    "RuntimeSpace",
    "ScopeOperator",
    "SourceSpan",
    "Symbol",
    "SymbolRefExpr",
    "TraceFrame",
    "TupleForm",
    "UnresolvedSymbolExpr",
    "analyze",
    "analyze_source",
    "collect_supported_operators",
    "compile_bytecode",
    "compile_lir_bytecode",
    "compile_mir_bytecode",
    "compile_to_llvm_text",
    "create_standard_runtime_space",
    "dump_bytecode",
    "dump_form",
    "dump_ir",
    "dump_lir",
    "dump_mir",
    "dump_program",
    "emit",
    "emit_llvm_module",
    "evaluate_bytecode",
    "evaluate_bytecode_async",
    "evaluate_bytecode_source",
    "evaluate_bytecode_source_async",
    "form_to_tuple",
    "format_form",
    "format_operator_docs",
    "format_program",
    "format_qy_error",
    "format_source",
    "format_value",
    "link",
    "lower",
    "lower_lir",
    "lower_mir",
    "lower_source",
    "macroexpand",
    "macroexpand_async",
    "macroexpand_source",
    "macroexpand_source_async",
    "read",
    "read_one",
    "read_one_tuple",
    "read_tuple",
    "standard_environment",
    "tuple_to_form",
    "type_check_source",
    "verify_mir",
    "write",
    "write_program",
    "write_tuple",
    "write_tuple_program",
]
