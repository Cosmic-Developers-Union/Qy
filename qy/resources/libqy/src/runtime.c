/* LibQy — Qy Language Runtime Implementation
 *
 * Phase Q2 covers: nil/T/int arithmetic, eq/lt/gt, alloc
 * Phase Q3 adds: cons cell
 * Phase Q4 adds: effect frame
 * Phase Q5 adds: I/O, string
 *
 * Compiled into libqy.a and linked with Qy LLVM backend output.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <inttypes.h>

#include "qy.h"

/* ---------------------------------------------------------------------------
 * Global state
 * ---------------------------------------------------------------------------*/

volatile int qy_div_by_zero = 0;
const int64_t qy_num_builtins = 18;

/* Simple bump allocator (Phase Q2: no GC) */
static uint8_t* _heap = NULL;
static size_t   _heap_cap = 0;
static size_t   _heap_used = 0;

static const size_t DEFAULT_HEAP_SIZE = 8 * 1024 * 1024;  /* 8 MB */

/* ---------------------------------------------------------------------------
 * Forward declarations — builtin dispatch (needed by qy_call)
 * ---------------------------------------------------------------------------*/

enum { _NUM_BUILTINS = 18 };

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

/*
 * Builtin indices (must match abi.py BUILTIN_NAMES order):
 *   0: +        9: echo
 *   1: -       10: newline
 *   2: *       11: read
 *   3: /       12: read-int
 *   4: =       13: cons
 *   5: eq      14: car
 *   6: <       15: cdr
 *   7: >       16: nil?
 *   8: display 17: not
 */
static qy_value (*const _builtin_dispatch[_NUM_BUILTINS])(int64_t, qy_value*, qy_env*) = {
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
 * Runtime initialization
 * ---------------------------------------------------------------------------*/

void qy_init(void) {
    if (_heap != NULL) return;
    _heap_cap = DEFAULT_HEAP_SIZE;
    _heap = (uint8_t*)malloc(_heap_cap);
    if (_heap == NULL) {
        fprintf(stderr, "qy: failed to allocate %zu byte heap\n", _heap_cap);
        abort();
    }
    _heap_used = 0;
    qy_div_by_zero = 0;
}

/* ---------------------------------------------------------------------------
 * Memory / Allocation
 * ---------------------------------------------------------------------------*/

void* qy_alloc(size_t size) {
    if (_heap == NULL) qy_init();
    size_t aligned = (size + 7) & ~7;
    if (_heap_used + aligned > _heap_cap) {
        fprintf(stderr, "qy: out of memory (used=%zu cap=%zu requested=%zu)\n",
                _heap_used, _heap_cap, aligned);
        abort();
    }
    void* ptr = _heap + _heap_used;
    _heap_used += aligned;
    return ptr;
}

qy_value* qy_alloc_array(int64_t n) {
    if (n < 0) return NULL;
    qy_value* arr = (qy_value*)qy_alloc((size_t)n * sizeof(qy_value));
    for (int64_t i = 0; i < n; i++) {
        memset(&arr[i], 0, sizeof(qy_value));
        arr[i].tag = QY_TAG_NIL;
    }
    return arr;
}

void qy_gc(void) {
    /* Phase Q2-Q5: no-op */
}

void qy_gc_threshold(size_t bytes) {
    (void)bytes;
}

/* ---------------------------------------------------------------------------
 * Arithmetic
 * ---------------------------------------------------------------------------*/

int64_t qy_add(int64_t a, int64_t b) { return a + b; }
int64_t qy_sub(int64_t a, int64_t b) { return a - b; }
int64_t qy_mul(int64_t a, int64_t b) { return a * b; }

int64_t qy_div(int64_t a, int64_t b) {
    if (b == 0) { qy_div_by_zero = 1; return 0; }
    return a / b;
}

int64_t qy_mod(int64_t a, int64_t b) {
    if (b == 0) { qy_div_by_zero = 1; return 0; }
    return a % b;
}

/* ---------------------------------------------------------------------------
 * Comparison
 * ---------------------------------------------------------------------------*/

qy_value qy_eq(qy_value a, qy_value b) {
    if (a.tag != b.tag) return qy_nil();
    if (a.tag == QY_TAG_NIL || a.tag == QY_TAG_T) return qy_T();
    if (a.tag == QY_TAG_INT) {
        return a.payload[0] == b.payload[0] ? qy_T() : qy_nil();
    }
    if (a.payload[0] == b.payload[0] && a.payload[1] == b.payload[1]) {
        return qy_T();
    }
    return qy_nil();
}

qy_value qy_lt(qy_value a, qy_value b) {
    if (a.tag == QY_TAG_INT && b.tag == QY_TAG_INT) {
        return (int64_t)a.payload[0] < (int64_t)b.payload[0] ? qy_T() : qy_nil();
    }
    return qy_nil();
}

qy_value qy_gt(qy_value a, qy_value b) {
    if (a.tag == QY_TAG_INT && b.tag == QY_TAG_INT) {
        return (int64_t)a.payload[0] > (int64_t)b.payload[0] ? qy_T() : qy_nil();
    }
    return qy_nil();
}

/* ---------------------------------------------------------------------------
 * Cons cell
 * ---------------------------------------------------------------------------*/

typedef struct {
    qy_value car;
    qy_value cdr;
} _cons_cell;

qy_value qy_cons(qy_value car, qy_value cdr) {
    _cons_cell* cell = (_cons_cell*)qy_alloc(sizeof(_cons_cell));
    cell->car = car;
    cell->cdr = cdr;
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_CONS;
    v.payload[0] = (uint64_t)(uintptr_t)cell;
    return v;
}

qy_value qy_car(qy_value c) {
    if (c.tag != QY_TAG_CONS) qy_abort_fmt("qy_car: expected cons, got tag %d", c.tag);
    return ((_cons_cell*)(uintptr_t)c.payload[0])->car;
}

qy_value qy_cdr(qy_value c) {
    if (c.tag != QY_TAG_CONS) qy_abort_fmt("qy_cdr: expected cons, got tag %d", c.tag);
    return ((_cons_cell*)(uintptr_t)c.payload[0])->cdr;
}

/* ---------------------------------------------------------------------------
 * Function
 * ---------------------------------------------------------------------------*/

qy_value qy_make_function(int64_t arity, qy_env* env, int64_t fn_idx) {
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_FUNCTION;
    v.payload[0] = (uint64_t)arity;
    v.payload[1] = (uint64_t)(uintptr_t)env;
    v.payload[2] = (uint64_t)fn_idx;
    return v;
}

qy_value qy_builtin_fn(int64_t idx) {
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_FUNCTION;
    v.payload[0] = (uint64_t)-1;   /* marker: builtin */
    v.payload[1] = (uint64_t)idx;  /* builtin index (0-17) */
    v.payload[2] = 0;
    return v;
}

/* qy_call: if payload[0]==-1 → builtin, else → user function */
qy_value qy_call(qy_value fn, qy_value* argv, int64_t argc) {
    if (fn.tag != QY_TAG_FUNCTION) {
        qy_abort_fmt("qy_call: expected function, got tag %d", fn.tag);
    }
    if (fn.payload[0] == (uint64_t)-1) {
        int64_t idx = (int64_t)fn.payload[1];
        if (idx < 0 || idx >= _NUM_BUILTINS) {
            qy_abort_fmt("qy_call: builtin index %" PRId64 " out of range", idx);
        }
        return _builtin_dispatch[idx](argc, argv, NULL);
    }
    int64_t fn_idx = (int64_t)fn.payload[2];
    if (fn_idx < 0 || fn_idx >= qy_fn_table_size) {
        qy_abort_fmt("qy_call: fn_idx %" PRId64 " out of range [0, %" PRId64 ")",
                     fn_idx, qy_fn_table_size);
    }
    return qy_fn_table[fn_idx](argc, argv, NULL);
}

qy_value qy_resolve_sym(const char* name) {
    (void)name;
    return qy_nil();
}

/* ---------------------------------------------------------------------------
 * String
 * ---------------------------------------------------------------------------*/

qy_value qy_make_string(const char* cstr, int64_t len) {
    char* copy = (char*)qy_alloc((size_t)len + 1);
    memcpy(copy, cstr, (size_t)len);
    copy[len] = '\0';
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_STRING;
    v.payload[0] = (uint64_t)(uintptr_t)copy;
    v.payload[1] = (uint64_t)len;
    return v;
}

const char* qy_string_cstr(qy_value v) {
    if (v.tag != QY_TAG_STRING) qy_abort_fmt("qy_string_cstr: expected string, got tag %d", v.tag);
    return (const char*)(uintptr_t)v.payload[0];
}

int64_t qy_string_len(qy_value v) {
    if (v.tag != QY_TAG_STRING) qy_abort_fmt("qy_string_len: expected string, got tag %d", v.tag);
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
        case QY_TAG_CONS:   printf("("); _print_value(qy_car(v)); printf(" . "); _print_value(qy_cdr(v)); printf(")"); break;
        case QY_TAG_FUNCTION: printf("<fn#%" PRId64 ">", (int64_t)v.payload[2]); break;
        case QY_TAG_STRING: {
            const char* s = (const char*)(uintptr_t)v.payload[0];
            int64_t len = (int64_t)v.payload[1];
            fwrite(s, 1, (size_t)len, stdout);
            break;
        }
        default: printf("<unknown-tag-%d>", v.tag); break;
    }
}

void qy_print(qy_value v)     { _print_value(v); }
void qy_println(qy_value v)   { _print_value(v); printf("\n"); }
void qy_display(qy_value v)  { _print_value(v); }
void qy_echo(qy_value v)     { _print_value(v); printf("\n"); }
void qy_newline(void)        { printf("\n"); }

int8_t qy_nil_p(qy_value v)  { return v.tag == QY_TAG_NIL ? 1 : 0; }
int8_t qy_not(int8_t x)      { return x ? 0 : 1; }

/* ---------------------------------------------------------------------------
 * Builtin implementations
 * ---------------------------------------------------------------------------*/

static qy_value _builtin_plus(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) qy_abort_fmt("+: expected 2 args, got %" PRId64, argc);
    return qy_int(qy_add(qy_int_val(argv[0]), qy_int_val(argv[1])));
}
static qy_value _builtin_minus(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) qy_abort_fmt("-: expected 2 args, got %" PRId64, argc);
    return qy_int(qy_sub(qy_int_val(argv[0]), qy_int_val(argv[1])));
}
static qy_value _builtin_times(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) qy_abort_fmt("*: expected 2 args, got %" PRId64, argc);
    return qy_int(qy_mul(qy_int_val(argv[0]), qy_int_val(argv[1])));
}
static qy_value _builtin_div(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) qy_abort_fmt("/: expected 2 args, got %" PRId64, argc);
    return qy_int(qy_div(qy_int_val(argv[0]), qy_int_val(argv[1])));
}
static qy_value _builtin_eq(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) qy_abort_fmt("=: expected 2 args, got %" PRId64, argc);
    return qy_eq(argv[0], argv[1]);
}
static qy_value _builtin_lt(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) qy_abort_fmt("<: expected 2 args, got %" PRId64, argc);
    return qy_lt(argv[0], argv[1]);
}
static qy_value _builtin_gt(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) qy_abort_fmt(">: expected 2 args, got %" PRId64, argc);
    return qy_gt(argv[0], argv[1]);
}
static qy_value _builtin_cons(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 2) qy_abort_fmt("cons: expected 2 args, got %" PRId64, argc);
    return qy_cons(argv[0], argv[1]);
}
static qy_value _builtin_car(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 1) qy_abort_fmt("car: expected 1 arg, got %" PRId64, argc);
    return qy_car(argv[0]);
}
static qy_value _builtin_cdr(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 1) qy_abort_fmt("cdr: expected 1 arg, got %" PRId64, argc);
    return qy_cdr(argv[0]);
}
static qy_value _builtin_nil_p(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 1) qy_abort_fmt("nil?: expected 1 arg, got %" PRId64, argc);
    return qy_nil_p(argv[0]) ? qy_T() : qy_nil();
}
static qy_value _builtin_not(int64_t argc, qy_value* argv, qy_env* env) {
    (void)env;
    if (argc != 1) qy_abort_fmt("not: expected 1 arg, got %" PRId64, argc);
    return qy_not(qy_nil_p(argv[0])) ? qy_T() : qy_nil();
}
static qy_value _builtin_display(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)env;
    qy_display(argv[0]);
    return qy_nil();
}
static qy_value _builtin_echo(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)env;
    qy_echo(argv[0]);
    return argv[0];
}
static qy_value _builtin_newline(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)argv; (void)env;
    qy_newline();
    return qy_nil();
}
static qy_value _builtin_read(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)argv; (void)env;
    return qy_read();
}
static qy_value _builtin_read_int(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)argv; (void)env;
    return qy_read_int();
}

/* ---------------------------------------------------------------------------
 * Read / read-int
 * ---------------------------------------------------------------------------*/

qy_value qy_read(void) {
    char buf[4096];
    if (fgets(buf, sizeof(buf), stdin) == NULL) return qy_nil();
    size_t len = strlen(buf);
    if (len > 0 && buf[len-1] == '\n') { buf[len-1] = '\0'; len--; }
    return qy_make_string(buf, (int64_t)len);
}

qy_value qy_read_int(void) {
    char buf[256];
    if (fgets(buf, sizeof(buf), stdin) == NULL) return qy_int(0);
    size_t len = strlen(buf);
    if (len > 0 && buf[len-1] == '\n') buf[len-1] = '\0';
    return qy_int(strtoll(buf, NULL, 10));
}

/* ---------------------------------------------------------------------------
 * Effect frame
 * ---------------------------------------------------------------------------*/

static qy_effect_frame* _alloc_effect_frame(uint64_t pc, qy_env* env,
                                             void* regs, size_t nregs) {
    qy_effect_frame* frame = (qy_effect_frame*)qy_alloc(sizeof(qy_effect_frame));
    frame->pc = pc;
    frame->env = env;
    frame->saved_registers = regs;
    frame->nregs = nregs;
    return frame;
}

qy_value qy_save_frame(uint64_t pc, qy_env* env, void* regs, size_t nregs) {
    qy_effect_frame* frame = _alloc_effect_frame(pc, env, regs, nregs);
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_EFFECT;
    v.payload[0] = (uint64_t)(uintptr_t)frame;
    return v;
}

qy_value qy_resume(qy_value frame, qy_value val) {
    if (frame.tag != QY_TAG_EFFECT) qy_abort_fmt("qy_resume: expected effect frame, got tag %d", frame.tag);
    (void)frame;
    return val;  /* Phase Q4: stub */
}

qy_value qy_perform(const char* effect_name, qy_value arg) {
    (void)effect_name;
    (void)arg;
    qy_abort_fmt("qy_perform: unhandled effect");
}

qy_value qy_handle(int64_t body_fn_idx,
                   int64_t num_handlers,
                   const char** handler_names,
                   int64_t* handler_fn_indices) {
    (void)num_handlers; (void)handler_names; (void)handler_fn_indices;
    if (body_fn_idx < 0 || body_fn_idx >= qy_fn_table_size) {
        qy_abort_fmt("qy_handle: body_fn_idx %" PRId64 " out of range", body_fn_idx);
    }
    qy_value* argv = qy_alloc_array(0);
    return qy_fn_table[body_fn_idx](0, argv, NULL);
}

/* ---------------------------------------------------------------------------
 * Abort
 * ---------------------------------------------------------------------------*/

void qy_abort(const char* msg) {
    fprintf(stderr, "qy: fatal error: %s\n", msg);
    abort();
}

void qy_abort_fmt(const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    fprintf(stderr, "qy: fatal error: ");
    vfprintf(stderr, fmt, args);
    fprintf(stderr, "\n");
    va_end(args);
    abort();
}

/* ---------------------------------------------------------------------------
 * C entry point
 * ---------------------------------------------------------------------------*/

int64_t qy_main_c(int64_t argc, char** argv) {
    qy_init();
    qy_value* qy_argv = qy_alloc_array(argc);
    for (int64_t i = 0; i < argc; i++) {
        qy_argv[i] = qy_make_string(argv[i], (int64_t)strlen(argv[i]));
    }
    qy_value result = qy_main(argc, qy_argv, NULL);
    if (result.tag == QY_TAG_INT) return (int64_t)result.payload[0];
    if (result.tag == QY_TAG_NIL) return 0;
    if (result.tag == QY_TAG_T)   return 1;
    return 0;
}