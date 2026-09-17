#!/usr/bin/env bash
# Qy Go 宿主大整数（任意精度）一致性脚本。
#
# 背景：Python 侧 `IntValue` 是任意精度 int（`qy/sem/core.py`），所以 Go VM 的整型
# 载荷必须是 `math/big.Int`。本脚本用与 TS 侧 `scripts/bigint_conformance.ts` 相同的
# 用例集，走三方流程逐字节比对：
#
#   1. uv run --no-sync qy run  FILE            → 期望输出（Python 参考语义）
#   2. uv run --no-sync qy export FILE -o JSON  → 字节码 JSON（唯一契约）
#   3. qyvm JSON                                → Go VM 输出
#   4. diff 1 与 3
#
# 覆盖：超过 2^53 的加减乘、负数大整数、30 的阶乘、大整数除法（含异号 float 路径）、
# 比较 / 相等 / 取模、累加（>2^32）、reify 十进制拼写、混合 int/float 报错、浮点 repr 回归。
#
# 用法：
#   bash qy/backend/golang/bigint_conformance.sh
#   bash qy/backend/golang/bigint_conformance.sh --verbose
#   bash qy/backend/golang/bigint_conformance.sh --dialect abstract-machine
#   bash qy/backend/golang/bigint_conformance.sh --keep
#
# 注意：Python 命令必须带 UV_CACHE_DIR=/tmp/uv-cache（默认 uv 缓存只读）。

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../../.." && pwd)"

VERBOSE=0
KEEP=0
DIALECT="compat"

while [[ $# -gt 0 ]]; do
  arg="$1"
  case "${arg}" in
    --verbose|-v) VERBOSE=1 ;;
    --keep) KEEP=1 ;;
    --dialect=*) DIALECT="${arg#--dialect=}" ;;
    --dialect) DIALECT="${2:-}"; shift ;;
    *) echo "unknown option: ${arg}" >&2; exit 2 ;;
  esac
  shift
done

if [[ "${DIALECT}" != "compat" && "${DIALECT}" != "abstract-machine" ]]; then
  echo "unknown dialect: ${DIALECT}（期望 compat 或 abstract-machine）" >&2
  exit 2
fi

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

if [[ -z "${GOCACHE:-}" ]]; then
  DEFAULT_GOCACHE="$(go env GOCACHE 2>/dev/null || true)"
  if [[ -z "${DEFAULT_GOCACHE}" || ! -w "${DEFAULT_GOCACHE}" ]]; then
    export GOCACHE="$(mktemp -d)"
  fi
fi

EXPORT_DIALECT_ARGS=()
if [[ "${DIALECT}" != "compat" ]]; then
  EXPORT_DIALECT_ARGS=(--dialect "${DIALECT}")
fi

WORK="$(mktemp -d)"
JSON_DIR="${WORK}/json"
mkdir -p "${JSON_DIR}"
cleanup() {
  if [[ "${KEEP}" == "1" ]]; then
    echo "临时目录保留：${WORK}"
  else
    rm -rf "${WORK}"
  fi
}
trap cleanup EXIT

QYVM="${WORK}/qyvm"
if ! (cd "${ROOT}" && go build -o "${QYVM}" ./qy/backend/golang/cmd/qyvm); then
  echo "go build ./qy/backend/golang/cmd/qyvm 失败" >&2
  exit 2
fi

PASSED=0
TOTAL=0
EXCLUDED=0
FAILURES=()

cd "${ROOT}" || exit 2

# run_case <name> <source>
run_case() {
  local name="$1"
  local source="$2"
  TOTAL=$((TOTAL + 1))

  local SRC="${WORK}/${name}.qy"
  printf '%s\n' "${source}" >"${SRC}"

  local EXPECTED="${WORK}/${name}.expected"
  if ! uv run --no-sync qy run "${SRC}" >"${EXPECTED}" 2>"${WORK}/${name}.runerr"; then
    FAILURES+=("${name}|Python \`qy run\` 失败|$(head -3 "${WORK}/${name}.runerr" | tr '\n' ' ')")
    return
  fi

  local JSON="${JSON_DIR}/${name}.json"
  if ! uv run --no-sync qy export "${EXPORT_DIALECT_ARGS[@]}" "${SRC}" -o "${JSON}" >/dev/null 2>"${WORK}/${name}.experr" || [[ ! -s "${JSON}" ]]; then
    FAILURES+=("${name}|Python \`qy export\` 未产出 JSON|$(head -3 "${WORK}/${name}.experr" | tr '\n' ' ')")
    return
  fi

  if grep -q '"type"[[:space:]]*:[[:space:]]*"unknown"' "${JSON}"; then
    EXCLUDED=$((EXCLUDED + 1))
    return
  fi

  local ACTUAL="${WORK}/${name}.actual"
  if ! "${QYVM}" "${JSON}" >"${ACTUAL}" 2>"${WORK}/${name}.vmerr"; then
    FAILURES+=("${name}|Go VM 非零退出|$(head -3 "${WORK}/${name}.vmerr" | tr '\n' ' ')")
    return
  fi

  if diff -q "${EXPECTED}" "${ACTUAL}" >/dev/null; then
    PASSED=$((PASSED + 1))
    if [[ "${VERBOSE}" == "1" ]]; then
      echo "  ok ${name}: $(head -1 "${EXPECTED}")"
    fi
    return
  fi
  FAILURES+=("${name}|输出不一致|$(diff "${EXPECTED}" "${ACTUAL}" | head -6 | tr '\n' ' ')")
}

# -- 用例集（与 TS scripts/bigint_conformance.ts 对齐） ----------------------

# 2^53 = 9007199254740992；9007199254740993 在 double 里不可表示。
run_case add_2p53 '(+ 9007199254740993 1)'
run_case mul_2p53 '(* 9007199254740993 9007199254740993)'
run_case neg_2p53 '(- 0 9007199254740993)'
run_case factorial_30 $'(defun f (n acc)\n  (cond ((= n 0) acc)\n        (T (f (- n 1) (* acc n)))))\n(f 30 1)'
# 结果 5000050000 > 2^32，验证累加不会掉回 32 位。
run_case accumulate_100000 $'(defun g (n acc)\n  (cond ((= n 0) acc)\n        (T (g (- n 1) (+ acc n)))))\n(g 100000 0)'
run_case ordering_big '(< 100000000000000000000 100000000000000000001)'
run_case equality_big '(= 9007199254740993 9007199254740993)'
run_case modulo_big '(mod 100000000000000000000000000007 97)'
run_case division_big '(/ -100000000000000000000 7)'
# 运行时（非常量折叠）的异号大整数除法：Python 走 `int(a/b)` float 路径，
# 必须逐字节复刻，验证 Go 没有"改成精确截断"。
run_case division_runtime_big $'(defun build (n acc)\n  (cond ((= n 0) acc)\n        (T (build (- n 1) (* acc 10)))))\n(defun h (a b) (/ a b))\n(h (- 0 (build 20 1)) 7)'
# reify 的整数 symbol 拼写：必须是十进制，不能出现宿主 big.Int 后缀。
run_case reify_big '(reify 9007199254740993)'
# 大整数 + 浮点：同 concrete 类型检查触发 unsupported-operation，用 handler 收敛。
run_case mixed_int_float_error $'(defeffect unsupported-operation)\n(handle (+ 1.5 9007199254740993)\n        ((unsupported-operation (arg k) "mixed-type-error")))'
# 浮点仍走 Python repr 规则（回归保护）。
run_case float_repr_regression '(+ 1.5 2.5)'

# -- 汇总 --------------------------------------------------------------------

echo ""
echo "dialect: ${DIALECT}"
if [[ "${EXCLUDED}" -gt 0 ]]; then
  echo "passed ${PASSED}/${TOTAL}（排除交换格式不可编码 ${EXCLUDED}）"
else
  echo "passed ${PASSED}/${TOTAL}"
fi

if [[ "${#FAILURES[@]}" -gt 0 ]]; then
  echo ""
  echo "失败清单（${#FAILURES[@]}）："
  for failure in "${FAILURES[@]}"; do
    IFS='|' read -r name reason detail <<<"${failure}"
    echo "  - ${name}: ${reason}"
    if [[ "${VERBOSE}" == "1" && -n "${detail}" ]]; then
      echo "      ${detail}"
    fi
  done
  exit 1
fi

exit 0
