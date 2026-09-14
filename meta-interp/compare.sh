#!/bin/bash
# Compare Python VM output vs Qy meta-interpreter output for given source files.
# Usage: ./compare.sh FILE.qy [FILE2.qy ...]
#
# Requires:
#   - python VM: `uv run qy run FILE` produces reference output
#   - qy meta VM: `uv run qy run meta-interp/main.qy -- FILE...` produces our output
#
# Note: `--no-color` is a top-level option and must precede the subcommand.

set -u

run_py() { uv run qy --no-color run "$1" 2>&1; }
run_qy() { uv run qy --no-color run meta-interp/main.qy -- "$1" 2>&1; }

fail=0
pass=0
for f in "$@"; do
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
