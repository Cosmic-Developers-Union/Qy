"""Public Qy API.

Stable pipeline APIs are centered around `Qy`, `RegisterVirtualMachine`, and
`qy.build.pipeline` (the only sanctioned way to compile source → bytecode). All
front-to-back compilation must go through that pipeline; legacy single-stage
helpers (``lower``/``lower_mir``/``compile_*_bytecode``/``macroexpand*``) have
been removed.
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
from qy.backend.vm import dump_bytecode
from qy.build.pipeline import build_default_pipeline
from qy.build.pipeline import bytecode_artifact
from qy.build.pipeline import compile_source_to_bytecode
from qy.build.pipeline import compile_source_to_bytecode_async
from qy.build.pipeline import compile_source_to_kind
from qy.build.pipeline import compile_source_to_kind_async
from qy.build.pipeline import core_ast_artifact
from qy.build.pipeline import hir_artifact
from qy.build.pipeline import lir_artifact
from qy.build.pipeline import mir_artifact
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
from qy.passes.pass_base import PipelineOptions
from qy.passes.pass_base import PipelineSession
from qy.runtime import AsyncQy
from qy.runtime import Qy
from qy.sem.core import NONE as QY_NONE
from qy.sem.core import DictValue
from qy.sem.core import ListValue
from qy.sem.core import NoneValue
from qy.sem.core import SetValue
from qy.sem.core import T as QY_T
from qy.sem.core import TupleValue
from qy.sem.core import TValue as QyT
from qy.sem.runtime import EffectDefinition
from qy.session import ProfileConfig
from qy.session import RuntimeSpace
from qy.session import create_standard_runtime_space
from qy.session.runtime_space import Environment
from qy.session.runtime_space import standard_environment
from qy.symbol_space.profile import OperatorDoc
from qy.symbol_space.profile import OperatorModuleDoc
from qy.symbol_space.profile import collect_supported_operators
from qy.symbol_space.profile import format_operator_docs
from qy.tools.fmt import dump_form
from qy.tools.fmt import dump_program
from qy.tools.fmt import format_form
from qy.tools.fmt import format_program
from qy.tools.fmt import format_source
from qy.vm.bytecode import BytecodeFunctionValue
from qy.vm.instance.frame import QyContinuation
from qy.vm.instance.machine import RegisterVirtualMachine
from qy.vm.instance.machine import evaluate_bytecode_async
from qy.vm.instance.values import HostObjectRef

__version__ = "0.0.4"
__author__ = "Ge"
__all__ = [
    "QY_EMPTY_CHAIN",
    "QY_EMPTY_LIST",
    "QY_NIL",
    "QY_NONE",
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
    "DictValue",
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
    "ListValue",
    "LiteralExpr",
    "MIRBlock",
    "MIRFunction",
    "MIRInstruction",
    "MIRProgram",
    "MIRTerminator",
    "MetaOperator",
    "NoneValue",
    "OperatorDoc",
    "OperatorModuleDoc",
    "OperatorSignature",
    "PipelineOptions",
    "PipelineSession",
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
    "SetValue",
    "SourceSpan",
    "Symbol",
    "SymbolRefExpr",
    "TraceFrame",
    "TupleForm",
    "TupleValue",
    "UnresolvedSymbolExpr",
    "analyze",
    "analyze_source",
    "build_default_pipeline",
    "bytecode_artifact",
    "collect_supported_operators",
    "compile_source_to_bytecode",
    "compile_source_to_bytecode_async",
    "compile_source_to_kind",
    "compile_source_to_kind_async",
    "compile_to_llvm_text",
    "core_ast_artifact",
    "create_standard_runtime_space",
    "dump_bytecode",
    "dump_form",
    "dump_ir",
    "dump_lir",
    "dump_mir",
    "dump_program",
    "emit",
    "evaluate_bytecode_async",
    "form_to_tuple",
    "format_form",
    "format_operator_docs",
    "format_program",
    "format_qy_error",
    "format_source",
    "format_value",
    "hir_artifact",
    "link",
    "lir_artifact",
    "mir_artifact",
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
