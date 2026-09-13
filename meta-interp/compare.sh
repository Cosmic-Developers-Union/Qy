#!/bin/bash
# Compare Python VM output vs Qy-VM output for given source files.
# Usage: ./compare.sh FILE.qy [FILE2.qy ...]
#
# Requires:
#   - python VM: `uv run qy run FILE` produces reference output
#   - qy VM: `uv run qy run meta-interp/main.qy -- FILE` produces our output
#   - both must use --no-color

set -u

PY_VM="uv run qy run --no-color"
QY_VM="uv run qy run --no-color meta-interp/main.qy --"

fail=0
pass=0
for f in "$@"; do
  py_out=$(eval "$PY_VM" "$f" 2>&1 | sed 's/\x1b\[[0-9;]*m//g')
  qy_out=$(eval "$QY_VM" "$f" 2>&1 | sed 's/\x1b\[[0-9;]*m//g')
  if [ "$py_out" = "$qy_out" ]; then
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
