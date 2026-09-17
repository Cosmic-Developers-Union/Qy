#!/usr/bin/env bash
# Qy Go 宿主一致性（conformance）脚本。
#
# 对 `tests/qy/*.qy` 的每个文件执行三方流程：
#
#   1. uv run --no-sync qy run  FILE            → 期望输出（Python 参考语义）
#   2. uv run --no-sync qy export FILE -o JSON  → 字节码 JSON（唯一契约）
#   3. go run ./qy/backend/golang/cmd/qyvm JSON → Go VM 输出
#   4. diff 1 与 3
#
# 用法：
#   bash qy/backend/golang/conformance.sh                 # 全量，输出通过数与失败清单
#   bash qy/backend/golang/conformance.sh --verbose       # 附带期望/实际片段
#   bash qy/backend/golang/conformance.sh --filter=effect # 只跑文件名匹配的语料
#   bash qy/backend/golang/conformance.sh --keep          # 保留临时目录
#   bash qy/backend/golang/conformance.sh --list          # 只列出失败文件名
#   bash qy/backend/golang/conformance.sh --dialect abstract-machine  # LIR 方言
#
# 注意：Python 命令必须带 UV_CACHE_DIR=/tmp/uv-cache（默认 uv 缓存只读）。

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/../../.." && pwd)"
CORPUS="${ROOT}/tests/qy"

VERBOSE=0
KEEP=0
LIST_ONLY=0
FILTER=""
DIALECT="compat"

while [[ $# -gt 0 ]]; do
  arg="$1"
  case "${arg}" in
    --verbose|-v) VERBOSE=1 ;;
    --keep) KEEP=1 ;;
    --list) LIST_ONLY=1 ;;
    --filter=*) FILTER="${arg#--filter=}" ;;
    --filter) FILTER="${2:-}"; shift ;;
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

# `qy export` 仅在非 compat 方言时才带 --dialect（与 qy/cli/commands/export.py 的
# 默认值一致）。期望输出始终取 Python `qy run`（compat 语义真源）：两种方言语义等价。
EXPORT_DIALECT_ARGS=()
if [[ "${DIALECT}" != "compat" ]]; then
  EXPORT_DIALECT_ARGS=(--dialect "${DIALECT}")
fi

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

# Go 构建缓存：默认位置可能只读（例如受限沙箱），不可写时退化为临时目录。
if [[ -z "${GOCACHE:-}" ]]; then
  DEFAULT_GOCACHE="$(go env GOCACHE 2>/dev/null || true)"
  if [[ -z "${DEFAULT_GOCACHE}" || ! -w "${DEFAULT_GOCACHE}" ]]; then
    export GOCACHE="$(mktemp -d)"
  fi
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

# 先编译一次 qyvm，避免每个语料重复 `go run` 的编译开销。
QYVM="${WORK}/qyvm"
if ! (cd "${ROOT}" && go build -o "${QYVM}" ./qy/backend/golang/cmd/qyvm); then
  echo "go build ./qy/backend/golang/cmd/qyvm 失败" >&2
  exit 2
fi

PASSED=0
TOTAL=0
FAILURES=()
EXCLUDED=()

cd "${ROOT}" || exit 2
while IFS= read -r FILE; do
  NAME="$(basename "${FILE}" .qy)"
  if [[ -n "${FILTER}" && "${NAME}" != *"${FILTER}"* ]]; then
    continue
  fi
  TOTAL=$((TOTAL + 1))

  EXPECTED="${WORK}/${NAME}.expected"
  if ! uv run --no-sync qy run "${FILE}" >"${EXPECTED}" 2>"${WORK}/${NAME}.runerr"; then
    FAILURES+=("${NAME}|Python \`qy run\` 失败|$(head -3 "${WORK}/${NAME}.runerr" | tr '\n' ' ')")
    continue
  fi

  JSON="${JSON_DIR}/${NAME}.json"
  if ! uv run --no-sync qy export "${EXPORT_DIALECT_ARGS[@]}" "${FILE}" -o "${JSON}" >/dev/null 2>"${WORK}/${NAME}.experr" || [[ ! -s "${JSON}" ]]; then
    FAILURES+=("${NAME}|Python \`qy export\` 未产出 JSON|$(head -3 "${WORK}/${NAME}.experr" | tr '\n' ' ')")
    continue
  fi

  # 交换格式缺口：`qy export` 写出 {"type":"unknown"} 时，Python 自己的
  # `load_bytecode_json` 也会抛 ValueError，这是载体缺陷而不是宿主 VM 的缺陷。
  if grep -q '"type"[[:space:]]*:[[:space:]]*"unknown"' "${JSON}"; then
    EXCLUDED+=("${NAME}")
    continue
  fi

  ACTUAL="${WORK}/${NAME}.actual"
  if ! "${QYVM}" "${JSON}" >"${ACTUAL}" 2>"${WORK}/${NAME}.vmerr"; then
    FAILURES+=("${NAME}|Go VM 非零退出|$(head -3 "${WORK}/${NAME}.vmerr" | tr '\n' ' ')")
    continue
  fi

  if diff -q "${EXPECTED}" "${ACTUAL}" >/dev/null; then
    PASSED=$((PASSED + 1))
  else
    DETAIL="$(diff "${EXPECTED}" "${ACTUAL}" | head -6 | tr '\n' ' ')"
    FAILURES+=("${NAME}|输出不一致|${DETAIL}")
  fi
done < <(find "${CORPUS}" -maxdepth 1 -name '*.qy' | sort)

echo ""
echo "dialect: ${DIALECT}"
if [[ "${#EXCLUDED[@]}" -gt 0 ]]; then
  echo "passed ${PASSED}/${TOTAL}（排除交换格式不可编码 ${#EXCLUDED[@]}: $(printf '%s' "${EXCLUDED[*]}")）"
else
  echo "passed ${PASSED}/${TOTAL}"
fi

if [[ "${#FAILURES[@]}" -gt 0 ]]; then
  if [[ "${LIST_ONLY}" == "1" ]]; then
    echo ""
    echo "失败：$(printf '%s\n' "${FAILURES[@]}" | cut -d'|' -f1 | tr '\n' ',' | sed 's/,$//')"
  else
    echo ""
    echo "失败清单（${#FAILURES[@]}）："
    for failure in "${FAILURES[@]}"; do
      IFS='|' read -r name reason detail <<<"${failure}"
      echo "  - ${name}: ${reason}"
      if [[ "${VERBOSE}" == "1" && -n "${detail}" ]]; then
        echo "      ${detail}"
      fi
    done
  fi
  exit 1
fi

exit 0
