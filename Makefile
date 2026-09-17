.PHONY: bench bench-baseline bench-check ci clean build check examples release test-go test-selfhost lint test test-ts

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

# TypeScript 宿主（qy/backend/typescript）：需要 bun；未安装时给出提示而不是静默跳过
test-ts:
	@command -v bun >/dev/null || { echo "bun not found: TypeScript host tests skipped"; exit 1; }
	cd qy/backend/typescript && bun test
	cd $(CURDIR) && bun qy/backend/typescript/scripts/conformance.ts
	cd $(CURDIR) && bun qy/backend/typescript/scripts/conformance.ts --dialect abstract-machine
	cd $(CURDIR) && bun qy/backend/typescript/scripts/bigint_conformance.ts

# Go 宿主（qy/backend/golang）：本沙箱默认 GOCACHE 可能只读，未设置时用临时目录
test-go:
	@command -v go >/dev/null || { echo "go not found: Go host tests skipped"; exit 1; }
	@GOCACHE="$${GOCACHE:-$$(mktemp -d)}"; export GOCACHE; \
	go build ./...; \
	go vet ./...; \
	go test ./...; \
	bash qy/backend/golang/conformance.sh; \
	bash qy/backend/golang/conformance.sh --dialect abstract-machine; \
	bash qy/backend/golang/bigint_conformance.sh

# 自举：Qy 写的解释器（meta-interp/main.qy）与 Python VM 对拍 + 解释器解释自身
test-selfhost:
	cd $(CURDIR) && bash meta-interp/compare.sh
	QY_META_SELF=1 uv run python -m pytest tests/test_meta_interp.py::test_meta_interp_interprets_its_own_source -q

# 示例（按宿主语言分目录，见 docs/examples.md）：Python 宿主 + TypeScript 宿主
examples:
	uv run python examples/py/run_validation.py
	uv run python examples/py/inject_symbol_space.py
	uv run python examples/py/bytecode_demo.py
	@command -v bun >/dev/null || { echo "bun not found: TypeScript examples skipped"; exit 1; }
	bun examples/ts/run_all.ts
	@command -v go >/dev/null || { echo "go not found: Go examples skipped"; exit 1; }
	@GOCACHE="$${GOCACHE:-$$(mktemp -d)}"; export GOCACHE; go run ./examples/go/run_all

ci:
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check .
	uv run python -m pytest -q
	$(MAKE) test-ts
	$(MAKE) test-go
	$(MAKE) examples
	$(MAKE) test-selfhost

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
	uv run scripts/tokens.py

# ---------------------------------------------------------------------------
# LLVM Native Backend
#    C Runtime: qy/resources/libqy/{include/qy.h,src/runtime.c} -> libqy.a
#    LLVM codegen: qy/backend/llvm -> .ll -> .o -> executable
# ---------------------------------------------------------------------------

LLVM_DIR    ?= build/llvm
LLC         ?= llc
CLANG       ?= clang
CC          ?= $(CLANG)
CFLAGS_C    := -Wall -Wextra -pedantic -std=c11
LIBQY_DIR   := qy/resources/libqy
LIBQY_INC   := $(LIBQY_DIR)/include
LIBQY_OBJ   := $(LIBQY_DIR)/src/runtime.o
LIBQY_A     := $(LIBQY_DIR)/libqy.a

# -- C Runtime targets -------------------------------------------------------

$(LIBQY_OBJ): $(LIBQY_DIR)/src/runtime.c $(LIBQY_DIR)/include/qy.h
	$(CC) $(CFLAGS_C) -I$(LIBQY_INC) -c $(LIBQY_DIR)/src/runtime.c -o $(LIBQY_OBJ)

$(LIBQY_A): $(LIBQY_OBJ)
	ar rcs $@ $<

.PHONY: libqy
libqy: $(LIBQY_A)

$(LLVM_DIR):
	mkdir -p $(LLVM_DIR)

# -- LLVM IR generation -----------------------------------------------------
#
# Generate LLVM IR from Qy source:
#   make llvm-gen SRC=examples/qy/hello.qy
#
# Full pipeline (Qy -> .ll -> .o -> a.out):
#   make llvm SRC=examples/qy/hello.qy OUT=/tmp/hello
#
# Run and compare with register VM:
#   make llvm-verify SRC=examples/qy/hello.qy
#
# 状态（实测，2026-09 本轮）：LLVM 后端是并行验证后端，`examples/qy/validation/` 中
# 00/02/03/09 走通「IR -> llc -> clang(+libqy) -> native」且与 register VM 输出一致；
# 已知限制见 docs/llvm-backend.md §限制。端到端测试见 tests/test_llvm_backend.py
# （缺 llc/clang 时自动跳过）。
# ---------------------------------------------------------------------------

.PHONY: llvm-gen
llvm-gen: | $(LLVM_DIR)
	@if [ -z "$(SRC)" ]; then \
		echo "Usage: make llvm-gen SRC=path/to/file.qy OUT=build/out.ll"; \
		exit 1; \
	fi
	@out="$(if $(OUT),$(OUT),$(LLVM_DIR)/$(notdir $(patsubst %.qy,%.ll,$(SRC))))"; \
		echo "  gen  $(SRC) -> $$out"; \
		uv run python -m qy llvm $(SRC) > "$$out" 2>&1 && \
		echo "  OK   $$out" || { cat "$$out"; exit 1; }

# Compile .ll -> .o
.PHONY: llvm-obj
llvm-obj: | $(LLVM_DIR)
	@if [ -z "$(IN)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make llvm-obj IN=in.ll OUT=out.o [LLC=$(LLC)]"; \
		exit 1; \
	fi
	$(LLC) -filetype=obj $(IN) -o $(OUT)

# Link .o + libqy runtime -> executable
.PHONY: llvm-link
llvm-link: $(LIBQY_OBJ)
	@if [ -z "$(OBJS)" ] || [ -z "$(OUT)" ]; then \
		echo "Usage: make llvm-link OBJS=\"a.o b.o\" OUT=out [CLANG=$(CLANG)]"; \
		exit 1; \
	fi
	$(CLANG) $(OBJS) $(LIBQY_OBJ) -o $(OUT)

# Full pipeline: Qy -> LLVM IR -> object -> executable -> run
#   make llvm SRC=examples/qy/hello.qy OUT=/tmp/hello
#   make llvm SRC=examples/qy/hello.qy OUT=/tmp/hello RUN=1
.PHONY: llvm
llvm: $(LIBQY_OBJ) | $(LLVM_DIR)
	@if [ -z "$(SRC)" ]; then \
		echo "Usage: make llvm SRC=path/to/file.qy OUT=/tmp/out [RUN=1]"; \
		exit 1; \
	fi
	@out="$(if $(OUT),$(OUT),$(LLVM_DIR)/$$(basename "$(SRC)" .qy))"; \
	base=$(LLVM_DIR)/$$(basename "$(SRC)" .qy); \
	echo "  [1/4] Qy -> LLVM IR  ($(SRC))"; \
	uv run python -m qy llvm $(SRC) > "$$base.ll" 2>&1 || { cat "$$base.ll"; exit 1; }; \
	echo "  [2/4] llc -> object   ($$base.o)"; \
	$(LLC) -filetype=obj "$$base.ll" -o "$$base.o" || { echo "llc failed"; exit 1; }; \
	echo "  [3/4] clang -> binary  ($$out)"; \
	$(CLANG) $(LIBQY_OBJ) "$$base.o" -o "$$out" || { echo "link failed"; exit 1; }; \
	if [ "$(RUN)" = "1" ]; then \
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

# Convenience: llvm-examples — compile all examples to LLVM IR
.PHONY: llvm-examples
llvm-examples: | $(LLVM_DIR)
	@for f in examples/qy/*.qy; do \
		name=$$(basename $$f .qy); \
		out=$(LLVM_DIR)/$$name.ll; \
		echo "  gen  $$f -> $$out"; \
		uv run python -m qy llvm $$f > "$$out" 2>&1 || { echo "FAIL: $$f"; exit 1; }; \
	done
	@echo "  llvm-examples: all generated"

clean-llvm:
	rm -rf $(LLVM_DIR) $(LIBQY_OBJ) $(LIBQY_A)

## Dev Container
dc-up:
	devcontainer up --workspace-folder .
dc-reup:
	devcontainer up --workspace-folder . --remove-existing-container
dc-stop:
	docker stop $$(docker ps -q --filter label=devcontainer.local_folder=$$(pwd))
dc-rm:
	docker rm $$(docker ps -a -q --filter label=devcontainer.local_folder=$$(pwd))
dc-enter:
	devcontainer exec --workspace-folder . -- zsh
dc-build:
	devcontainer build --workspace-folder .


demo:
	for cmd in ast expand hir mir lir bytecode run; do \
		echo "=== $${cmd} ==="; \
		qy $${cmd} examples/qy/hello.qy; \
	done

download-tlaplus:
	mkdir -p tools
	curl -L -o tools/tla2tools.jar https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar