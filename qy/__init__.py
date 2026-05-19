"""Public Qy API.

Stable pipeline APIs are centered around `Qy`, `macroexpand`, `lower`, `lower_mir`,
`compile_mir_bytecode`, `compile_bytecode`, and `RegisterVirtualMachine`.
"""

# coding: utf-8

from qy.analyzer import Analysis
from qy.analyzer import Diagnostic
from qy.analyzer import analyze
from qy.analyzer import analyze_source
from qy.analyzer import type_check_source
from qy.backend.llvm import compile_to_llvm_text
from qy.backend.llvm import emit
from qy.backend.llvm import link
from qy.bytecode import BytecodeFunction
from qy.bytecode import BytecodeFunctionValue
from qy.bytecode import BytecodeProgram
from qy.bytecode import Instruction
from qy.bytecode import dump_bytecode
from qy.bytecode_compiler import compile_bytecode
from qy.bytecode_compiler import compile_lir_bytecode
from qy.bytecode_compiler import compile_mir_bytecode
from qy.continuation import QyContinuation
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
from qy.formatter import dump_form
from qy.formatter import dump_program
from qy.formatter import format_form
from qy.formatter import format_program
from qy.formatter import format_source
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
from qy.macroexpand import MacroEffectPolicy
from qy.macroexpand import MacroExpansion
from qy.macroexpand import MacroExpansionOptions
from qy.macroexpand import MacroExpansionTrace
from qy.macroexpand import MacroSourceMapEntry
from qy.macroexpand import macroexpand
from qy.macroexpand import macroexpand_async
from qy.macroexpand import macroexpand_source
from qy.macroexpand import macroexpand_source_async
from qy.operator_docs import OperatorDoc
from qy.operator_docs import OperatorModuleDoc
from qy.operator_docs import collect_supported_operators
from qy.operator_docs import format_operator_docs
from qy.operator_signature import Arity
from qy.operator_signature import EffectSpec
from qy.operator_signature import OperatorSignature
from qy.operators import ControlOperator
from qy.operators import EffectOperator
from qy.operators import MetaOperator
from qy.operators import PureOperator
from qy.operators import ScopeOperator
from qy.passes.lower_hir import lower
from qy.passes.lower_hir import lower_source
from qy.passes.lower_lir import lower_lir
from qy.passes.lower_mir import lower_mir
from qy.reader import DottedTuple
from qy.reader import Form
from qy.reader import ReaderSyntaxError
from qy.reader import Symbol
from qy.reader import TupleForm
from qy.reader import form_to_tuple
from qy.reader import read
from qy.reader import read_one
from qy.reader import read_one_tuple
from qy.reader import read_tuple
from qy.reader import tuple_to_form
from qy.reader import write
from qy.reader import write_program
from qy.reader import write_tuple
from qy.reader import write_tuple_program
from qy.register_vm import RegisterVirtualMachine
from qy.register_vm import evaluate_bytecode
from qy.register_vm import evaluate_bytecode_async
from qy.register_vm import evaluate_bytecode_source
from qy.register_vm import evaluate_bytecode_source_async
from qy.runtime import Qy
from qy.runtime_values import EffectDefinition
from qy.runtime_values import HostObjectRef
from qy.values import QY_EMPTY_CHAIN
from qy.values import QY_EMPTY_LIST
from qy.values import QY_NIL
from qy.values import QY_T
from qy.values import QyChain
from qy.values import QyCons
from qy.values import QyEmptyChain
from qy.values import QyEmptyList
from qy.values import QyNil
from qy.values import QyT

__version__ = "0.0.4"
__author__ = "Ge"
__all__ = [
    "QY_EMPTY_CHAIN",
    "QY_EMPTY_LIST",
    "QY_NIL",
    "QY_T",
    "Analysis",
    "Arity",
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
