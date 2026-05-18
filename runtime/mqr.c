/* Minimal Qy Runtime (MQR) — Implementation
 *
 * Phase Q2 covers: nil/T/int arithmetic, eq/lt/gt, print, alloc
 * Phase Q3 adds: cons cell
 * Phase Q4 adds: effect frame
 * Phase Q5 adds: I/O, string
 *
 * This file is the ONLY C file in the LLVM backend.  Keep it small and clean.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <inttypes.h>

#include "mqr.h"

/* ---------------------------------------------------------------------------
 * Global state
 * ---------------------------------------------------------------------------*/

volatile int mqr_div_by_zero = 0;

/* Simple bump allocator (Phase Q2: no GC) */
static uint8_t* _heap = NULL;
static size_t   _heap_cap = 0;
static size_t   _heap_used = 0;

static const size_t DEFAULT_HEAP_SIZE = 8 * 1024 * 1024;  /* 8 MB */

/* ---------------------------------------------------------------------------
 * Runtime initialization
 * ---------------------------------------------------------------------------*/

void mqr_init(void) {
    if (_heap != NULL) return;
    _heap_cap = DEFAULT_HEAP_SIZE;
    _heap = (uint8_t*)malloc(_heap_cap);
    if (_heap == NULL) {
        fprintf(stderr, "mqr: failed to allocate %zu byte heap\n", _heap_cap);
        abort();
    }
    _heap_used = 0;
    mqr_div_by_zero = 0;
}

/* ---------------------------------------------------------------------------
 * Memory / Allocation
 * ---------------------------------------------------------------------------*/

void* mqr_alloc(size_t size) {
    if (_heap == NULL) mqr_init();
    /* Align to 8 bytes */
    size_t aligned = (size + 7) & ~7;
    if (_heap_used + aligned > _heap_cap) {
        /* Phase Q2: abort on OOM (no GC yet) */
        fprintf(stderr, "mqr: out of memory (used=%zu cap=%zu requested=%zu)\n",
                _heap_used, _heap_cap, aligned);
        abort();
    }
    void* ptr = _heap + _heap_used;
    _heap_used += aligned;
    return ptr;
}

qy_value* mqr_alloc_array(int64_t n) {
    if (n < 0) return NULL;
    qy_value* arr = (qy_value*)mqr_alloc((size_t)n * sizeof(qy_value));
    /* Zero-initialize */
    for (int64_t i = 0; i < n; i++) arr[i] = qy_nil();
    return arr;
}

void mqr_gc(void) {
    /* Phase Q2-Q5: no-op.  Stop-and-copy GC arrives in Phase Q6. */
}

void mqr_gc_threshold(size_t bytes) {
    (void)bytes;
    /* Phase Q2: threshold not used */
}

/* ---------------------------------------------------------------------------
 * Forward declarations for builtin dispatch (needed by mqr_call)
 * ---------------------------------------------------------------------------*/

/* Builtin operator count — must match BUILTIN_OPS in qy/llvm_codegen.py */
enum { _NUM_BUILTINS = 18 };

/* Forward declarations of builtin implementations */
static qy_value _builtin_plus(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_minus(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_times(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_div(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_eq(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_lt(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_gt(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_cons(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_car(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_cdr(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_nil_p(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_not(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_display(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_echo(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_newline(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_read(int64_t argc, qy_value* argv, qy_env* env);
static qy_value _builtin_read_int(int64_t argc, qy_value* argv, qy_env* env);

/* Indices match BUILTIN_OPS in qy/llvm_codegen.py:
 *   0: +       9: echo
 *   1: -      10: newline
 *   2: *      11: read
 *   3: /      12: read-int
 *   4: =      13: cons
 *   5: eq     14: car
 *   6: <      15: cdr
 *   7: >      16: nil?
 *   8: display 17: not
 */
static qy_value (*const _builtin_dispatch[])(int64_t, qy_value*, qy_env*) = {
    _builtin_plus,    /*  0: + */
    _builtin_minus,   /*  1: - */
    _builtin_times,   /*  2: * */
    _builtin_div,     /*  3: / */
    _builtin_eq,      /*  4: = */
    _builtin_eq,      /*  5: eq */
    _builtin_lt,      /*  6: < */
    _builtin_gt,      /*  7: > */
    _builtin_display, /*  8: display */
    _builtin_echo,    /*  9: echo */
    _builtin_newline, /* 10: newline */
    _builtin_read,    /* 11: read */
    _builtin_read_int,/* 12: read-int */
    _builtin_cons,    /* 13: cons */
    _builtin_car,     /* 14: car */
    _builtin_cdr,     /* 15: cdr */
    _builtin_nil_p,   /* 16: nil? */
    _builtin_not,     /* 17: not */
};

/* ---------------------------------------------------------------------------
 * Arithmetic (integer only in Phase Q2)
 * ---------------------------------------------------------------------------*/

int64_t mqr_add(int64_t a, int64_t b) { return a + b; }
int64_t mqr_sub(int64_t a, int64_t b) { return a - b; }
int64_t mqr_mul(int64_t a, int64_t b) { return a * b; }

int64_t mqr_div(int64_t a, int64_t b) {
    if (b == 0) {
        mqr_div_by_zero = 1;
        return 0;
    }
    return a / b;
}

int64_t mqr_mod(int64_t a, int64_t b) {
    if (b == 0) {
        mqr_div_by_zero = 1;
        return 0;
    }
    return a % b;
}

/* ---------------------------------------------------------------------------
 * Comparison
 * ---------------------------------------------------------------------------*/

qy_value mqr_eq(qy_value a, qy_value b) {
    /* Identity comparison for Qy runtime values.
     * Two qy_values are equal iff they have the same tag and payload.
     * This matches Qy eq semantics: nil==nil, T==T, 1==1, etc.
     */
    if (a.tag != b.tag) return qy_nil();
    /* For nil/T (tag 0/1), payload is always zero — they're always equal */
    if (a.tag == QY_TAG_NIL || a.tag == QY_TAG_T) return qy_T();
    /* For integer: compare payload[0] */
    if (a.tag == QY_TAG_INT) {
        return a.payload[0] == b.payload[0] ? qy_T() : qy_nil();
    }
    /* For other types: compare by identity (pointer equality for cons/func/effect/host/string) */
    if (a.payload[0] == b.payload[0] && a.payload[1] == b.payload[1]) {
        return qy_T();
    }
    return qy_nil();
}

qy_value mqr_lt(qy_value a, qy_value b) {
    if (a.tag == QY_TAG_INT && b.tag == QY_TAG_INT) {
        int64_t av = (int64_t)a.payload[0];
        int64_t bv = (int64_t)b.payload[0];
        return av < bv ? qy_T() : qy_nil();
    }
    return qy_nil();  /* non-integer comparison: not implemented in Phase Q2 */
}

qy_value mqr_gt(qy_value a, qy_value b) {
    if (a.tag == QY_TAG_INT && b.tag == QY_TAG_INT) {
        int64_t av = (int64_t)a.payload[0];
        int64_t bv = (int64_t)b.payload[0];
        return av > bv ? qy_T() : qy_nil();
    }
    return qy_nil();
}

/* ---------------------------------------------------------------------------
 * Cons cell (Phase Q3 — implemented here for early testing)
 * ---------------------------------------------------------------------------*/

typedef struct {
    qy_value car;
    qy_value cdr;
} _cons_cell;

qy_value mqr_cons(qy_value car, qy_value cdr) {
    _cons_cell* cell = (_cons_cell*)mqr_alloc(sizeof(_cons_cell));
    cell->car = car;
    cell->cdr = cdr;
    qy_value v = {QY_TAG_CONS, {0, 0, 0}};
    /* Store pointer in payload[0] — aligned to 8 bytes so pointer fits */
    v.payload[0] = (uint64_t)(uintptr_t)cell;
    return v;
}

qy_value mqr_car(qy_value c) {
    if (c.tag != QY_TAG_CONS) {
        mqr_abort_fmt("mqr_car: expected cons, got tag %d", c.tag);
    }
    _cons_cell* cell = (_cons_cell*)(uintptr_t)c.payload[0];
    return cell->car;
}

qy_value mqr_cdr(qy_value c) {
    if (c.tag != QY_TAG_CONS) {
        mqr_abort_fmt("mqr_cdr: expected cons, got tag %d", c.tag);
    }
    _cons_cell* cell = (_cons_cell*)(uintptr_t)c.payload[0];
    return cell->cdr;
}

/* ---------------------------------------------------------------------------
 * Function (Phase Q3)
 * ---------------------------------------------------------------------------*/

qy_value mqr_make_function(int64_t arity, qy_env* env, int64_t fn_idx) {
    qy_value v = {QY_TAG_FUNCTION, {0, 0, 0}};
    v.payload[0] = (uint64_t)arity;
    v.payload[1] = (uint64_t)(uintptr_t)env;
    v.payload[2] = (uint64_t)fn_idx;
    return v;
}

qy_value mqr_call(qy_value fn, qy_value* argv, int64_t argc) {
    if (fn.tag != QY_TAG_FUNCTION) {
        mqr_abort_fmt("mqr_call: expected function, got tag %d", fn.tag);
    }
    /* Check if this is a builtin function (marker in payload[0]) */
    if (fn.payload[0] == (uint64_t)-1) {
        int64_t idx = (int64_t)fn.payload[1];
        if (idx < 0 || idx >= _NUM_BUILTINS) {
            mqr_abort_fmt("mqr_call: builtin index %" PRId64 " out of range", idx);
        }
        return _builtin_dispatch[idx](argc, argv, NULL);
    }
    int64_t arity = (int64_t)fn.payload[0];
    qy_env* env = (qy_env*)(uintptr_t)fn.payload[1];
    int64_t fn_idx = (int64_t)fn.payload[2];
    if (fn_idx < 0 || fn_idx >= qy_fn_table_size) {
        mqr_abort_fmt("mqr_call: fn_idx %" PRId64 " out of range [0, %" PRId64 ")",
                      fn_idx, qy_fn_table_size);
    }
    /* Verify arity */
    (void)arity;  /* Phase Q3: arity check optional */
    return qy_fn_table[fn_idx](argc, argv, env);
}

/* ---------------------------------------------------------------------------
 * String (Phase Q5)
 * ---------------------------------------------------------------------------*/

qy_value mqr_make_string(const char* cstr, int64_t len) {
    /* Allocate copy on the heap */
    char* copy = (char*)mqr_alloc((size_t)len + 1);
    memcpy(copy, cstr, (size_t)len);
    copy[len] = '\0';
    qy_value v = {QY_TAG_STRING, {0, 0, 0}};
    v.payload[0] = (uint64_t)(uintptr_t)copy;
    v.payload[1] = (uint64_t)len;
    return v;
}

const char* mqr_string_cstr(qy_value v) {
    if (v.tag != QY_TAG_STRING) {
        mqr_abort_fmt("mqr_string_cstr: expected string, got tag %d", v.tag);
    }
    return (const char*)(uintptr_t)v.payload[0];
}

int64_t mqr_string_len(qy_value v) {
    if (v.tag != QY_TAG_STRING) {
        mqr_abort_fmt("mqr_string_len: expected string, got tag %d", v.tag);
    }
    return (int64_t)v.payload[1];
}

/* ---------------------------------------------------------------------------
 * I/O
 * ---------------------------------------------------------------------------*/

static void _print_value(qy_value v) {
    switch (v.tag) {
        case QY_TAG_NIL:    printf("nil");   break;
        case QY_TAG_T:      printf("T");     break;
        case QY_TAG_INT:    printf("%" PRId64, (int64_t)v.payload[0]); break;
        case QY_TAG_CONS:   printf("("); _print_value(mqr_car(v)); printf(" . "); _print_value(mqr_cdr(v)); printf(")"); break;
        case QY_TAG_FUNCTION: printf("<fn#%" PRId64 ">", (int64_t)v.payload[2]); break;
        case QY_TAG_STRING:  {
            const char* s = (const char*)(uintptr_t)v.payload[0];
            int64_t len = (int64_t)v.payload[1];
            fwrite(s, 1, (size_t)len, stdout);
            break;
        }
        default: printf("<unknown-tag-%d>", v.tag); break;
    }
}

void mqr_print(qy_value v) {
    _print_value(v);
}

void mqr_println(qy_value v) {
    _print_value(v);
    printf("\n");
}

void mqr_display(qy_value v) {
    _print_value(v);
}

void mqr_echo(qy_value v) {
    _print_value(v);
    printf("\n");
}

void mqr_newline(void) {
    printf("\n");
}

/* ---------------------------------------------------------------------------
 * Predicate helpers
 * ---------------------------------------------------------------------------*/

int8_t mqr_nil_p(qy_value v) {
    return v.tag == QY_TAG_NIL ? 1 : 0;
}

int8_t mqr_not(int8_t x) {
    return x ? 0 : 1;
}

/* ---------------------------------------------------------------------------
 * Builtin operator dispatch (Phase Q5)
 * ---------------------------------------------------------------------------*/

/* Builtin operators indexed in this order (matches BUILTIN_OPS in llvm_codegen.py).
 *   0: +       8: cons
 *   1: -       9: car
 *   2: *      10: cdr
 *   3: /      11: nil?
 *   4: =      12: not
 *   5: eq     13: display
 *   6: <      14: echo
 *   7: >      15: newline
 *           16: read
 *           17: read-int
 */

/* The actual builtin implementations — each takes (argc, argv, env). */
static qy_value _builtin_plus(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt("+: expected 2 args, got %" PRId64, argc); }
    int64_t a = qy_int_val(argv[0]);
    int64_t b = qy_int_val(argv[1]);
    return qy_int(a + b);
}
static qy_value _builtin_minus(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt("-: expected 2 args, got %" PRId64, argc); }
    int64_t a = qy_int_val(argv[0]);
    int64_t b = qy_int_val(argv[1]);
    return qy_int(a - b);
}
static qy_value _builtin_times(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt("*: expected 2 args, got %" PRId64, argc); }
    int64_t a = qy_int_val(argv[0]);
    int64_t b = qy_int_val(argv[1]);
    return qy_int(a * b);
}
static qy_value _builtin_div(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt("/: expected 2 args, got %" PRId64, argc); }
    int64_t a = qy_int_val(argv[0]);
    int64_t b = qy_int_val(argv[1]);
    return qy_int(mqr_div(a, b));
}
static qy_value _builtin_eq(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt("=: expected 2 args, got %" PRId64, argc); }
    return mqr_eq(argv[0], argv[1]);
}
static qy_value _builtin_lt(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt("<: expected 2 args, got %" PRId64, argc); }
    return mqr_lt(argv[0], argv[1]);
}
static qy_value _builtin_gt(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt(">: expected 2 args, got %" PRId64, argc); }
    return mqr_gt(argv[0], argv[1]);
}
static qy_value _builtin_cons(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt("cons: expected 2 args, got %" PRId64, argc); }
    return mqr_cons(argv[0], argv[1]);
}
static qy_value _builtin_car(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 1) { mqr_abort_fmt("car: expected 1 arg, got %" PRId64, argc); }
    return mqr_car(argv[0]);
}
static qy_value _builtin_cdr(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) { mqr_abort_fmt("cdr: expected 1 arg, got %" PRId64, argc); }
    return mqr_cdr(argv[0]);
}
static qy_value _builtin_nil_p(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 1) { mqr_abort_fmt("nil?: expected 1 arg, got %" PRId64, argc); }
    return mqr_nil_p(argv[0]) ? qy_T() : qy_nil();
}
static qy_value _builtin_not(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 1) { mqr_abort_fmt("not: expected 1 arg, got %" PRId64, argc); }
    return mqr_not(mqr_nil_p(argv[0])) ? qy_T() : qy_nil();
}
static qy_value _builtin_display(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)env;
    mqr_display(argv[0]);
    return qy_nil();
}
static qy_value _builtin_echo(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)env;
    mqr_echo(argv[0]);
    return argv[0];
}
static qy_value _builtin_newline(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)argv; (void)env;
    mqr_newline();
    return qy_nil();
}
static qy_value _builtin_read(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)argv; (void)env;
    return mqr_read();
}
static qy_value _builtin_read_int(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)argv; (void)env;
    return mqr_read_int();
}

/* mqr_builtin_fn: create a builtin function value.
 *   idx: builtin operator index (0-17)
 * Returns a qy_value with tag=QY_TAG_FUNCTION and marker payload[0]=(uint64_t)-1.
 */
qy_value mqr_builtin_fn(int64_t idx) {
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_FUNCTION;
    v.payload[0] = (uint64_t)-1;   /* marker: this is a builtin */
    v.payload[1] = (uint64_t)idx;  /* builtin index */
    v.payload[2] = 0;
    return v;
}

/* mqr_resolve_sym: look up a symbol name. Phase Q5: stub that returns nil. */
qy_value mqr_resolve_sym(const char* name) {
    (void)name;
    /* Phase Q5: no user-defined symbols yet — return nil.
     * Full implementation will need a symbol table populated from
     * the compiled Qy program's global definitions. */
    return qy_nil();
}

qy_value mqr_read(void) {
    /* Read a line from stdin */
    char buf[4096];
    if (fgets(buf, sizeof(buf), stdin) == NULL) {
        return qy_nil();
    }
    /* Strip trailing newline */
    size_t len = strlen(buf);
    if (len > 0 && buf[len-1] == '\n') {
        buf[len-1] = '\0';
        len--;
    }
    return mqr_make_string(buf, (int64_t)len);
}

qy_value mqr_read_int(void) {
    char buf[256];
    if (fgets(buf, sizeof(buf), stdin) == NULL) return qy_int(0);
    /* Strip trailing newline */
    size_t len = strlen(buf);
    if (len > 0 && buf[len-1] == '\n') buf[len-1] = '\0';
    return qy_int(strtoll(buf, NULL, 10));
}

/* ---------------------------------------------------------------------------
 * Effect frame (Phase Q4 — minimal stubs for early compilation)
 * ---------------------------------------------------------------------------*/

static mqr_effect_frame* _alloc_effect_frame(uint64_t pc, qy_env* env,
                                              void* regs, size_t nregs) {
    mqr_effect_frame* frame = (mqr_effect_frame*)mqr_alloc(sizeof(mqr_effect_frame));
    frame->pc = pc;
    frame->env = env;
    frame->saved_registers = regs;
    frame->nregs = nregs;
    return frame;
}

qy_value mqr_save_frame(uint64_t pc, qy_env* env, void* regs, size_t nregs) {
    mqr_effect_frame* frame = _alloc_effect_frame(pc, env, regs, nregs);
    qy_value v = {QY_TAG_EFFECT, {0, 0, 0}};
    v.payload[0] = (uint64_t)(uintptr_t)frame;
    return v;
}

qy_value mqr_resume(qy_value frame, qy_value val) {
    if (frame.tag != QY_TAG_EFFECT) {
        mqr_abort_fmt("mqr_resume: expected effect frame, got tag %d", frame.tag);
    }
    mqr_effect_frame* ef = (mqr_effect_frame*)(uintptr_t)frame.payload[0];
    /* Phase Q4: resume is implemented as a computed goto / longjmp.
     * For simplicity, we use a switch-on-pc approach in the generated code.
     * This stub returns val; the actual resume logic is in the codegen.
     * TODO: implement proper continuation using setjmp/longjmp.
     */
    (void)ef;
    return val;
}

qy_value mqr_perform(const char* effect_name, qy_value arg) {
    (void)effect_name;
    (void)arg;
    /* Phase Q4: unhandled effect — abort for now.
     * Full handler routing arrives with mqr_handle.
     */
    mqr_abort_fmt("mqr_perform: unhandled effect '%s'", effect_name);
}

qy_value mqr_handle(int64_t body_fn_idx,
                    int64_t num_handlers,
                    const char** handler_names,
                    int64_t* handler_fn_indices) {
    (void)num_handlers;
    (void)handler_names;
    (void)handler_fn_indices;
    /* Phase Q4: call the body function and return result */
    if (body_fn_idx < 0 || body_fn_idx >= qy_fn_table_size) {
        mqr_abort_fmt("mqr_handle: body_fn_idx %" PRId64 " out of range", body_fn_idx);
    }
    qy_value* argv = mqr_alloc_array(0);
    return qy_fn_table[body_fn_idx](0, argv, NULL);
}

/* ---------------------------------------------------------------------------
 * Abort / error
 * ---------------------------------------------------------------------------*/

void mqr_abort(const char* msg) {
    fprintf(stderr, "mqr: fatal error: %s\n", msg);
    abort();
}

void mqr_abort_fmt(const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    fprintf(stderr, "mqr: fatal error: ");
    vfprintf(stderr, fmt, args);
    fprintf(stderr, "\n");
    va_end(args);
    abort();
}

/* ---------------------------------------------------------------------------
 * Runtime entry point
 * ---------------------------------------------------------------------------*/

int64_t mqr_main(int64_t argc, char** argv) {
    mqr_init();
    /* Build argv as qy_value array */
    qy_value* qy_argv = mqr_alloc_array(argc);
    for (int64_t i = 0; i < argc; i++) {
        qy_argv[i] = mqr_make_string(argv[i], (int64_t)strlen(argv[i]));
    }
    qy_value result = qy_main(argc, qy_argv, NULL);
    /* Convert result to exit code: integer → cast to int, nil → 0, T → 1 */
    if (result.tag == QY_TAG_INT) {
        return (int64_t)result.payload[0];
    } else if (result.tag == QY_TAG_NIL) {
        return 0;
    } else if (result.tag == QY_TAG_T) {
        return 1;
    }
    return 0;
}