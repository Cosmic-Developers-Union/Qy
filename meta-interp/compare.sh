#!/bin/bash
# Compare Python VM output vs Qy meta-interpreter output for given source files.
# Usage: ./compare.sh [FILE.qy ...]      # 省略参数即跑 meta-interp/cases/*.qy
#
# Requires:
#   - python VM: `uv run qy run FILE` produces reference output
#   - qy meta VM: `uv run qy run meta-interp/main.qy -- FILE...` produces our output
#
# Note: `--no-color` is a top-level option and must precede the subcommand.

set -u

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"

# 无参数时默认跑全部用例（避免调用方猜 glob/相对路径）
if [ "$#" -eq 0 ]; then
  set -- "$here"/cases/*.qy
fi

run_py() { uv run qy --no-color run "$1" 2>&1; }
run_qy() { uv run qy --no-color run meta-interp/main.qy -- "$1" 2>&1; }

fail=0
pass=0
cd "$root"

for f in "$@"; do
  if [ ! -f "$f" ]; then
    echo "SKIP  $f (not found; 用法: $0 [FILE.qy ...]，省略参数即跑 meta-interp/cases/*.qy)"
    fail=$((fail+1))
    continue
  fi
  py_out=$(run_py "$f" | sed 's/\x1b\[[0-9;]*m//g')
  qy_out=$(run_qy "$f" | sed 's/\x1b\[[0-9;]*m//g')
  if echo "$qy_out" | grep -qE 'Traceback|QY_[A-Z_]+ERROR|QY_RUNTIME_ERROR'; then
    echo "ERROR $f (qy interpreter crashed)"
    echo "$qy_out" | sed 's/^/    /'
    fail=$((fail+1))
  elif [ "$py_out" = "$qy_out" ]; then
    echo "PASS  $f"
    pass=$((pass+1))
  else
    echo "FAIL  $f"
    echo "  PY:"
    echo "$py_out" | sed 's/^/    /'
    echo "  QY:"
    echo "$qy_out" | sed 's/^/    /'
    fail=$((fail+1))
  fi
done

echo ""
echo "Summary: pass=$pass fail=$fail"
exit $fail
