.PHONY: bench bench-baseline bench-check clean build check release lint test

BENCH_BASELINE ?= benchmarks/baseline.json
BENCH_MAX_REGRESSION_PERCENT ?= 10

test:
	uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing

bench:
	uv run python -m qy.benchmark

bench-baseline:
	uv run python -m qy.benchmark --write-baseline $(BENCH_BASELINE)

bench-check:
	uv run python -m qy.benchmark --baseline $(BENCH_BASELINE) --max-regression-percent $(BENCH_MAX_REGRESSION_PERCENT)

clean:
	rm -rf dist/ build/ *.egg-info

build: clean
	uv build
	uv run twine check dist/*

check:
	uv run twine check dist/*

lint:
	uv run ruff check .
	uv run ruff format .
	uv run ty check .

lint-fix:
	uv run ruff check . --fix --unsafe-fixes
	uv run ruff format .
	uv run ty check .

release:
	git push
	$(MAKE) build
	uv run twine upload -r testpypi dist/*
	uv run twine upload dist/*

tokens:
	python scripts/tokens.py

# ---------------------------------------------------------------------------
# LLVM Native Backend (Phase Q)
#    C Runtime: runtime/mqr.{c,h} → runtime/mqr.o → runtime/libmqr.a
#    LLVM codegen: qy/llvm_codegen.py → .ll → .o → executable
# ---------------------------------------------------------------------------

LLVM_DIR    ?= build/llvm
LLC         ?= llc
CLANG       ?= clang
CC          ?= $(CLANG)
CFLAGS_C    := -Wall -Wextra -pedantic -std=c11

# -- C Runtime targets -------------------------------------------------------

runtime/mqr.o: runtime/mqr.c runtime/mqr.h
	$(CC) $(CFLAGS_C) -c runtime/mqr.c -o runtime/mqr.o

runtime/libmqr.a: runtime/mqr.o
	ar rcs $@ $<

mqr: runtime/libmqr.a

# -- MQR C unit tests -------------------------------------------------------

C_TEST_SOURCES := $(wildcard runtime/test_*.c)

$(LLVM_DIR):
	mkdir -p $(LLVM_DIR)

test-mqr: runtime/libmqr.a | $(LLVM_DIR)
	@set -e; for src in $(C_TEST_SOURCES); do \
		name=$$(basename $$src .c); \
		bin=$(LLVM_DIR)/$$name; \
		echo "  CC  $$src"; \
		$(CC) $(CFLAGS_C) -I. $$src runtime/libmqr.a -o $$bin && \
		echo "  RUN $$bin" && $$bin || { echo "FAIL: $$src"; exit 1; }; \
	done
	@echo "  mqr tests: all passed"

# -- LLVM IR generation (requires qy/llvm_codegen.py) ---------------------
#
# Generate LLVM IR from Qy source:
#   make llvm-gen SRC=examples/hello.qy
#
# Full pipeline (Qy → .ll → .o → a.out):
#   make llvm SRC=examples/hello.qy OUT=/tmp/hello
#
# Run and compare with register VM:
#   make llvm-verify SRC=examples/hello.qy
#
# ---------------------------------------------------------------------------

.PHONY: llvm-gen
llvm-gen: | $(LLVM_DIR)
	@if [ -z "$(SRC)" ]; then \
		echo "Usage: make llvm-gen SRC=path/to/file.qy OUT=build/out.ll"; \
		exit 1; \
	fi
	@out="$(if $(OUT),$(OUT),$(LLVM_DIR)/$(notdir $(patsubst %.qy,%.ll,$(SRC))))"; \
		echo "  gen  $(SRC) -> $$out"; \
		uv run python -m qy llvm --ll $(SRC) > "$$out" 2>&1 && \
		echo "  OK   $$out" || { cat "$$out"; exit 1; }

# Compile .ll → .o
.PHONY: llvm-obj
llvm-obj: | $(LLVM_DIR)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make llvm-obj IN=in.ll OUT=out.o [LLC=$(LLC)]"; \
		exit 1; \
	fi
	$(LLC) -filetype=obj $(IN) -o $(OUT)

# Link .o + mqr.o → executable
.PHONY: llvm-link
llvm-link: runtime/libmqr.a
	@if [ -z "$(OBJS)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make llvm-link OBJS=\"a.o b.o\" OUT=out [CLANG=$(CLANG)]"; \
		exit 1; \
	fi
	$(CLANG) $(OBJS) runtime/mqr.o -o $(OUT)

# Full pipeline: Qy → LLVM IR → object → executable → run
#   make llvm SRC=examples/hello.qy OUT=/tmp/hello
#   make llvm SRC=examples/hello.qy OUT=/tmp/hello RUN=1
.PHONY: llvm
llvm: runtime/libmqr.a | $(LLVM_DIR)
	@if [ -z "$(SRC)" ]; then \
		echo "Usage: make llvm SRC=path/to/file.qy OUT=/tmp/out [RUN=1]"; \
		exit 1; \
	fi
	@out="$(if $(OUT),$(OUT),$(LLVM_DIR)/a.out)"; \
	base=$(LLVM_DIR)/$$(basename "$(SRC)" .qy); \
	echo "  [1/4] Qy -> LLVM IR  ($(SRC))"; \
	uv run python -m qy llvm --ll $(SRC) > "$$base.ll" 2>&1 || { cat "$$base.ll"; exit 1; }; \
	echo "  [2/4] llc -> object   ($$base.o)"; \
	$(LLC) -filetype=obj "$$base.ll" -o "$$base.o" || { echo "llc failed"; exit 1; }; \
	echo "  [3/4] clang -> binary  ($$out)"; \
	$(CLANG) runtime/mqr.o "$$base.o" -o "$$out" || { echo "link failed"; exit 1; }; \
	@if [ "$(RUN)" = "1" ]; then \
		echo "  [4/4] run             ($$out)"; \
		$$out || exit 1; \
	else \
		echo "  [4/4] done            ($$out)"; \
	fi

# Verify LLVM output matches register VM output
.PHONY: llvm-verify
llvm-verify: llvm
	@out=$(LLVM_DIR)/$$(basename "$(SRC)" .qy); \
	ref=$$(uv run python -m qy run $(SRC) 2>/dev/null); \
	act=$$($$out 2>/dev/null); \
	if [ "$$ref" = "$$act" ]; then \
		echo "  verify: PASS (register VM == native)"; \
	else \
		echo "  verify: FAIL"; \
		echo "  register VM: $$ref"; \
		echo "  native:       $$act"; \
		exit 1; \
	fi

# Convenience: llvm-all — compile all examples to LLVM IR
.PHONY: llvm-examples
llvm-examples: | $(LLVM_DIR)
	@for f in examples/*.qy; do \
		name=$$(basename $$f .qy); \
		out=$(LLVM_DIR)/$$name.ll; \
		echo "  gen  $$f -> $$out"; \
		uv run python -m qy llvm --ll $$f > "$$out" 2>&1 || { echo "FAIL: $$f"; exit 1; }; \
	done
	@echo "  llvm-examples: all generated"

clean-llvm:
	rm -rf $(LLVM_DIR) runtime/*.o runtime/libmqr.a
