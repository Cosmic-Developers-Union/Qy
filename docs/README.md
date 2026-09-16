# QyLang Documentation Index

This directory contains all design documents and technical documentation for QyLang.

## Architecture & Design

- [pipeline.md](pipeline.md) - Compilation pipeline architecture
- [ir-design.md](ir-design.md) - Intermediate representation design (boundaries, completion status)
- [lir.md](lir.md) - Low-level IR design rationale (target machine model)
- [lir-effect-frame-design.md](lir-effect-frame-design.md) - Effect frame design for LIR
- [package-structure.md](package-structure.md) - Project package structure
- [hir-spec.md](hir-spec.md) - HIR 正式 grammar / 节点语义 / verifier / source → HIR 映射（规范真源）
- [mir-spec.md](mir-spec.md) - MIR 正式 grammar / opcode 语义 / CFG 约束 / HIR → MIR 映射（规范真源）
- [lir-spec.md](lir-spec.md) - LIR 正式 grammar / opcode（按 compat 与 abstract-machine dialect）/ layout / MIR → LIR 映射（规范真源）
- [formal-semantics.md](formal-semantics.md) - IR 良构性谓词 + 管线保义定理（form-proofer plan 配套；Lean 4 骨架见 `formal/`）
- [grammar-spec.md](grammar-spec.md) - 端到端语法规范（lexer → CST → raw AST → surface → core → HIR → MIR → LIR → bytecode）一站式 review
- [core-language-semantics.md](core-language-semantics.md) - 核心语言严格语义（抽象语法 / 静态语义 / 小步操作语义 / 效果系统 / 模块系统）
- [wasm-backend.md](wasm-backend.md) - WebAssembly 后端（LIR → WAT、值编码、调用约定、支持范围、宿主 runtime）
- [llvm-backend.md](llvm-backend.md) - LLVM 后端（LIR → LLVM IR、C ABI sret/byval、libqy 契约、支持范围）

## Roadmap

- [roadmap.yaml](roadmap.yaml) - 最终产品定义与不可漂移事实（语言真源索引，YAML）

## Language Design

- [op.md](op.md) - Operator design and semantics
- [language-core-audit.md](language-core-audit.md) - Language core audit
- [stdlib-operators.md](stdlib-operators.md) - Standard library operator draft

---

**Note**: All design documents must be registered in this index. Do not create long-term unregistered design documents.