// 标准 profile 的装配、CALL_BUILTIN ABI 表、以及模块注册表。
//
// 真源：
//   - `qy/std/profile.py` + `qy/std/__init__.py`：标准 profile 只装 `qy.core` + `qy.io`；
//   - `qy/session/pre_ss.py`：literal 层（lisp-ss → number-ss → char-ss → string-ss）；
//   - `qy/core/operator_builtins.py`：CALL_BUILTIN 的下标顺序（跨后端 ABI，不可改）；
//   - `qy/vm/instance/builtins.py`：下标 → 标准实现体；
//   - `qy/import_/registry.py`：模块注册/加载。
//
// 依赖方向是纯 DAG（values → errors；environment → values；stdlib → 以上），
// 因此不存在循环导入。

import { QyRuntimeError } from '../errors.ts';
import { Env } from '../environment.ts';
import { ModuleValue, PureOperatorValue, RawOperatorValue, QY_NIL, QY_NONE, QY_T, type QyValue } from '../values.ts';
import { add, div, ge, gt, le, lt, mod, mul, numEq, numberP, pyEq, remainder, stringToNumber, sub } from './arithmetic.ts';
import { charBindings } from './chars.ts';
import { carOp, cdrOp, consOp, dataBindings, eq, reifyOp } from './data.ts';
import { bindOp, controlBindings, nilPredicate, notOp, slotOp, thisOp } from './control.ts';
import { ioBindings, newlineOp, printOp } from './io.ts';
import { numberSpaceModules } from './number_spaces.ts';
import { stringBindings } from './strings.ts';

// ---------------------------------------------------------------------------
// CALL_BUILTIN ABI
// ---------------------------------------------------------------------------

/**
 * 内建算子名（顺序即 ABI 下标），来自 `qy/core/operator_builtins.py::BUILTIN_OPERATORS`。
 * 不得改动顺序：它同时是 wasm/llvm 的 ABI。
 */
export const BUILTIN_NAMES: readonly string[] = [
  '+',
  '-',
  '*',
  '/',
  '=',
  'eq',
  '<',
  '>',
  'display',
  'echo',
  'newline',
  'read',
  'read-int',
  'cons',
  'car',
  'cdr',
  'nil?',
  'not',
];

function echoBody(args: QyValue[]): QyValue {
  printOp(args, null);
  return args.length === 0 ? null : args[args.length - 1];
}

function readBody(): QyValue {
  // 宿主 stdin 读取（`read` / `read-int`）：语料不触达，返回 nil 表示无输入。
  return QY_NIL;
}

/** 内建算子的直接实现体（对应 `qy/vm/instance/builtins.py` 的下标取用）。 */
const BUILTIN_IMPLS: (((...args: QyValue[]) => QyValue) | null)[] = [
  add,
  sub,
  mul,
  div,
  numEq,
  eq,
  lt,
  gt,
  echoBody,
  echoBody,
  () => newlineOp([], null),
  readBody,
  readBody,
  consOp,
  carOp,
  cdrOp,
  nilPredicate,
  notOp,
];

/** 执行内建算子（对应 `call_builtin`）。 */
export function callBuiltin(builtinId: number, args: QyValue[]): QyValue {
  if (!Number.isInteger(builtinId) || builtinId < 0 || builtinId >= BUILTIN_IMPLS.length) {
    throw new QyRuntimeError(`unknown builtin operator index ${builtinId}`);
  }
  const impl = BUILTIN_IMPLS[builtinId];
  if (impl === null) {
    throw new QyRuntimeError(
      `builtin operator '${BUILTIN_NAMES[builtinId]}' has no implementation in the standard profile`,
    );
  }
  return impl(...args);
}

// ---------------------------------------------------------------------------
// 标准 symbol-space-chain
// ---------------------------------------------------------------------------

type EagerBindings = Record<string, (...args: QyValue[]) => QyValue>;
type RawBindings = Record<string, (args: QyValue[], env: QyValue) => QyValue>;

function installEager(env: Env, bindings: EagerBindings): void {
  for (const [name, fn] of Object.entries(bindings)) {
    env.define(name, new PureOperatorValue(name, fn));
  }
}

function installRaw(env: Env, bindings: RawBindings): void {
  for (const [name, fn] of Object.entries(bindings)) {
    env.define(name, new RawOperatorValue(name, fn));
  }
}

/**
 * 建立标准运行环境。
 *
 * 链布局（自上而下 = 解析顺序）：
 *   head → qy.io → qy.core → number-ss → lisp-ss
 * `head` 是顶层可写空间（对应 Python 的 `pre-ssc-head`）：顶层 `define` /
 * `from` fold 落在这一层，不会与 `qy.io` 模块自身的绑定冲突。
 * 全链 miss 之后才走字面量解析（number/char/string/T/nil/none），与
 * `RuntimeSpace.resolve` + `ProfileConfig.resolve_literal` 的行为一致。
 */
export function createStandardEnvironment(): Env {
  const lisp = new Env(null, new Map<string, QyValue>(), 'lisp-ss');
  lisp.define('T', QY_T);
  lisp.define('nil', QY_NIL);
  lisp.define('true', QY_T);
  lisp.define('false', QY_NIL);
  lisp.define('none', QY_NONE);

  const numbers = lisp.child();
  installEager(numbers, {
    '=': numEq,
    '==': pyEq,
    '+': add,
    '-': sub,
    '*': mul,
    '/': div,
    mod,
    '<': lt,
    '>': gt,
    '<=': le,
    '>=': ge,
    'string->number': stringToNumber,
    'number?': numberP,
    remainder,
  });

  const core = numbers.child();
  installEager(core, dataBindings());
  installEager(core, controlBindings());
  installRaw(core, { reify: reifyOp, this: thisOp, slot: slotOp, bind: bindOp });

  const io = core.child();
  installRaw(io, ioBindings());

  return io.child();
}

// ---------------------------------------------------------------------------
// 模块注册表
// ---------------------------------------------------------------------------

const MODULE_REGISTRY = new Map<string, ModuleValue>();

/** 注册模块（`qy/import_/registry.py::register_module`）。 */
export function registerModule(module: ModuleValue): void {
  MODULE_REGISTRY.set(module.name, module);
}

/** 清空注册表（每次 `createVm` 调用，避免跨实例泄漏）。 */
export function resetModuleRegistry(): void {
  MODULE_REGISTRY.clear();
}

/** 查找已注册模块。 */
export function lookupModule(name: string): ModuleValue | undefined {
  return MODULE_REGISTRY.get(name);
}

function makeModule(name: string, bindings: EagerBindings): ModuleValue {
  const exports = new Map<string, QyValue>();
  for (const [symbol, fn] of Object.entries(bindings)) {
    exports.set(symbol, new PureOperatorValue(symbol, fn));
  }
  return new ModuleValue(name, exports, new Map());
}

/** 内置模块（对应 `qy/std/__init__.py` 的模块 loader 注册表）。 */
export function builtinModules(): Map<string, ModuleValue> {
  const modules = new Map<string, ModuleValue>();

  const core = makeModule('qy.core', { ...dataBindings(), ...controlBindings() });
  core.exports.set('reify', new RawOperatorValue('reify', reifyOp));
  core.exports.set('this', new RawOperatorValue('this', thisOp));
  core.exports.set('slot', new RawOperatorValue('slot', slotOp));
  core.exports.set('bind', new RawOperatorValue('bind', bindOp));
  modules.set('qy.core', core);

  const io = new ModuleValue('qy.io', new Map(), new Map());
  for (const [name, fn] of Object.entries(ioBindings())) {
    io.exports.set(name, new RawOperatorValue(name, fn as (args: QyValue[], env: QyValue) => QyValue));
  }
  modules.set('qy.io', io);

  modules.set(
    'qy.num',
    makeModule('qy.num', {
      '=': numEq,
      '==': pyEq,
      '+': add,
      '-': sub,
      '*': mul,
      '/': div,
      mod,
      '<': lt,
      '>': gt,
      '<=': le,
      '>=': ge,
      'string->number': stringToNumber,
      'number?': numberP,
      remainder,
    }),
  );

  modules.set('qy.str', makeModule('qy.str', stringBindings()));
  modules.set('qy.char', makeModule('qy.char', charBindings()));

  // 具体数值空间（qy.int8..qy.float128）：算子包成 PureOperatorValue，
  // min-value / max-value / bits 是直接值绑定。
  for (const space of numberSpaceModules()) {
    const module = new ModuleValue(`qy.${space.name}`, new Map(), new Map());
    for (const [key, value] of Object.entries(space.values)) module.exports.set(key, value);
    for (const [key, fn] of Object.entries(space.operators)) {
      module.exports.set(key, new PureOperatorValue(key, fn));
    }
    modules.set(`qy.${space.name}`, module);
  }
  return modules;
}
