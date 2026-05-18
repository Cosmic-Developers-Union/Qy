/* LibQy — Qy Language Runtime
 * A minimal C runtime for the Qy LLVM backend.
 *
 * Value layout: tagged 64-bit union
 *   tag = 0: nil (payload=0)
 *   tag = 1: T   (payload=0)
 *   tag = 2: integer (payload = i64 value)
 *   tag = 3: cons cell (payload[0..7]=car*, payload[8..15]=cdr*)
 *   tag = 4: function (payload[0]=arity, payload[1]=env*, payload[2]=fn_idx)
 *           Special case: if payload[0]==(uint64_t)-1, this is a builtin
 *           and payload[1]=builtin_index (0-17)
 *   tag = 5: effect frame (payload = pointer to EffectFrame struct)
 *   tag = 6: host ref (payload[0..7]=ptr, payload[8..15]=type_id)
 *   tag = 7: string (payload[0..7]=cstr*, payload[8..15]=len)
 *
 * All Qy functions follow this calling convention:
 *   qy_value qy_fn(int64_t argc, qy_value* argv, qy_env* env);
 *
 * Linker provides: qy_fn_table[], qy_fn_table_size, qy_main()
 */

#ifndef QY_H
#define QY_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* ---------------------------------------------------------------------------
 * Qy Value
 * ---------------------------------------------------------------------------*/

typedef struct {
    uint8_t  tag;
    uint64_t payload[3];  /* up to 24 bytes payload (max: string {ptr,len} or cons {car,cdr}) */
} qy_value;

#define QY_TAG_NIL       0
#define QY_TAG_T         1
#define QY_TAG_INT       2
#define QY_TAG_CONS      3
#define QY_TAG_FUNCTION  4
#define QY_TAG_EFFECT    5
#define QY_TAG_HOST      6
#define QY_TAG_STRING    7

/* ---------------------------------------------------------------------------
 * Constructors
 * ---------------------------------------------------------------------------*/

static inline qy_value qy_nil(void) {
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_NIL;
    return v;
}

static inline qy_value qy_T(void) {
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_T;
    return v;
}

static inline qy_value qy_int(int64_t n) {
    qy_value v;
    memset(&v, 0, sizeof(v));
    v.tag = QY_TAG_INT;
    v.payload[0] = (uint64_t)n;
    return v;
}

/* Convenience: check tag without extracting payload */
static inline int qy_is_nil(qy_value v)   { return v.tag == QY_TAG_NIL; }
static inline int qy_is_T(qy_value v)     { return v.tag == QY_TAG_T; }
static inline int qy_is_int(qy_value v)   { return v.tag == QY_TAG_INT; }
static inline int qy_is_cons(qy_value v)  { return v.tag == QY_TAG_CONS; }
static inline int qy_is_function(qy_value v) { return v.tag == QY_TAG_FUNCTION; }
static inline int qy_is_string(qy_value v) { return v.tag == QY_TAG_STRING; }

/* Extract integer payload */
static inline int64_t qy_int_val(qy_value v) {
    return (int64_t)v.payload[0];
}

/* Convenience: branch on nil (false) vs everything-else (true).
 * Used by JUMP_IF_FALSE. */
static inline int qy_is_false(qy_value v) { return v.tag == QY_TAG_NIL; }
static inline int qy_is_true(qy_value v)  { return v.tag != QY_TAG_NIL; }

/* ---------------------------------------------------------------------------
 * Arithmetic (integer only in Phase Q2)
 * ---------------------------------------------------------------------------*/

int64_t  qy_add(int64_t a, int64_t b);
int64_t  qy_sub(int64_t a, int64_t b);
int64_t  qy_mul(int64_t a, int64_t b);
int64_t  qy_div(int64_t a, int64_t b);   /* div-by-zero: returns 0, sets qy_div_by_zero */
int64_t  qy_mod(int64_t a, int64_t b);

/* ---------------------------------------------------------------------------
 * Comparison
 * ---------------------------------------------------------------------------*/

qy_value qy_eq(qy_value a, qy_value b);   /* returns QY_T or QY_NIL */
qy_value qy_lt(qy_value a, qy_value b);
qy_value qy_gt(qy_value a, qy_value b);
int8_t   qy_nil_p(qy_value v);   /* returns 1 if nil, 0 otherwise */
int8_t   qy_not(int8_t x);        /* logical not: 1→0, 0→1 */

/* ---------------------------------------------------------------------------
 * Cons cell (Phase Q3)
 * ---------------------------------------------------------------------------*/

qy_value qy_cons(qy_value car, qy_value cdr);
qy_value qy_car(qy_value c);
qy_value qy_cdr(qy_value c);

/* ---------------------------------------------------------------------------
 * Function
 * ---------------------------------------------------------------------------*/

/* Environment stub — Phase Q2 functions have no closure, so env is always NULL */
typedef struct qy_env qy_env;

/* qy_make_function: create a user-defined function value.
 *   arity: number of parameters
 *   env: closure environment (NULL if no closure capture)
 *   fn_idx: index into the compiled function table
 * Returns a qy_value with tag=QY_TAG_FUNCTION.
 */
qy_value qy_make_function(int64_t arity, qy_env* env, int64_t fn_idx);

/* qy_builtin_fn: create a builtin operator function value.
 *   idx: builtin operator index (0-17)
 * Returns a qy_value with tag=QY_TAG_FUNCTION and payload[0]=(uint64_t)-1.
 */
qy_value qy_builtin_fn(int64_t idx);

/* qy_call: invoke a function value.
 *   fn: function value (must have tag=QY_TAG_FUNCTION)
 *   argv: argument array (caller-owned, callee does not take ownership)
 *   argc: argument count
 * Returns the result qy_value.
 */
qy_value qy_call(qy_value fn, qy_value* argv, int64_t argc);

/* qy_resolve_sym: look up a symbol name in the runtime symbol table.
 *   name: null-terminated symbol name
 * Returns: the symbol value (Qy function, builtin, or nil if not found).
 */
qy_value qy_resolve_sym(const char* name);

/* ---------------------------------------------------------------------------
 * I/O (Phase Q5)
 * ---------------------------------------------------------------------------*/

void     qy_print(qy_value v);      /* print without newline */
void     qy_println(qy_value v);    /* print with newline */
void     qy_display(qy_value v);    /* display value to stdout */
void     qy_echo(qy_value v);       /* display value followed by newline */
void     qy_newline(void);           /* print a newline */
qy_value qy_read(void);            /* read line from stdin, return as string */
qy_value qy_read_int(void);         /* read integer from stdin */

/* ---------------------------------------------------------------------------
 * String (Phase Q5)
 * ---------------------------------------------------------------------------*/

/* qy_make_string: create a string value from a C string.
 *   cstr: null-terminated C string (libqy copies the contents)
 *   len: length in bytes (excluding null terminator)
 * Returns a qy_value with tag=QY_TAG_STRING.
 */
qy_value qy_make_string(const char* cstr, int64_t len);

/* qy_string_cstr: extract the C string pointer from a string value.
 *   v must have tag=QY_TAG_STRING.
 */
const char* qy_string_cstr(qy_value v);
int64_t     qy_string_len(qy_value v);

/* ---------------------------------------------------------------------------
 * Effect frame (Phase Q4)
 * ---------------------------------------------------------------------------*/

typedef struct {
    uint64_t pc;
    qy_env*  env;
    void*    saved_registers;
    size_t   nregs;
} qy_effect_frame;

/* qy_save_frame: capture the current continuation.
 *   pc: program counter at the perform site (instruction index)
 *   env: current environment
 *   regs: pointer to register array
 *   nregs: number of registers
 * Returns an effect frame value (tag=QY_TAG_EFFECT).
 */
qy_value qy_save_frame(uint64_t pc, qy_env* env, void* regs, size_t nregs);

/* qy_resume: resume computation from a saved frame with a value.
 *   frame: effect frame value (tag=QY_TAG_EFFECT)
 *   val: value to resume with
 * Returns the result of the handler (if any), or the resumed value.
 */
qy_value qy_resume(qy_value frame, qy_value val);

/* qy_perform: trigger an effect.
 *   effect_name: null-terminated effect name (e.g. "state", "io")
 *   arg: effect argument value
 * Returns: if there is a matching handler in the current continuation,
 *          the handler result; otherwise the effect is unhandled.
 */
qy_value qy_perform(const char* effect_name, qy_value arg);

/* qy_handle: set up an effect handler around a body function.
 *   body_fn_idx: index of the body function to run with protection
 *   num_handlers: number of handlers
 *   handler_names: array of effect name strings (num_handlers entries)
 *   handler_fn_indices: array of handler function indices (num_handlers entries)
 * Returns the result of body_fn (or the handler result if an effect is performed).
 */
qy_value qy_handle(int64_t body_fn_idx,
                    int64_t num_handlers,
                    const char** handler_names,
                    int64_t* handler_fn_indices);

/* ---------------------------------------------------------------------------
 * Memory / Allocation
 * ---------------------------------------------------------------------------*/

/* qy_alloc: allocate memory (Phase Q2: simple bump allocator, no GC).
 *   size: bytes to allocate
 * Returns a pointer, or NULL on allocation failure.
 * The returned memory is uninitialized.
 */
void* qy_alloc(size_t size);

/* qy_alloc_array: allocate and zero-initialize an array of qy_value.
 */
qy_value* qy_alloc_array(int64_t n);

/* qy_gc: run the garbage collector (Phase Q6: stop-and-copy).
 *   Currently a no-op in Phase Q2-Q5.
 */
void qy_gc(void);

/* qy_gc_threshold: set the allocation threshold at which GC triggers.
 *   Set to 0 to disable GC.
 */
void qy_gc_threshold(size_t bytes);

/* ---------------------------------------------------------------------------
 * Runtime state
 * ---------------------------------------------------------------------------*/

/* Set by qy_div when div-by-zero occurs.  User code can check this. */
extern volatile int qy_div_by_zero;

/* qy_abort: abort with a message.  Used for unhandled effects, etc. */
__attribute__((noreturn))
void qy_abort(const char* msg);

/* qy_abort_fmt: abort with a printf-formatted message. */
__attribute__((noreturn))
void qy_abort_fmt(const char* fmt, ...);

/* ---------------------------------------------------------------------------
 * Runtime entry point
 * ---------------------------------------------------------------------------*/

/* qy_init: initialize the runtime.  Called automatically by qy_main. */
void qy_init(void);

/* qy_main: the Qy program entry point, generated by the LLVM backend.
 *   Declaration only — the linker resolves this symbol.
 */
extern qy_value qy_main(int64_t argc, qy_value* argv, qy_env* env);

/* qy_fn_table: array of Qy function pointers, populated by the linker.
 *   Indexed by fn_idx in function values.
 *   Declaration only — populated at link time by the LLVM backend output.
 */
extern qy_value (*qy_fn_table[])(int64_t argc, qy_value* argv, qy_env* env);
extern const int64_t qy_fn_table_size;

/* qy_num_builtins: number of builtin operators.
 *   Used by the LLVM backend to emit the correct constant.
 */
extern const int64_t qy_num_builtins;

/* qy_main_c: the C entry point.  Calls qy_main (the compiled Qy program).
 *   argc, argv: as in main(int argc, char** argv)
 * Returns the exit code (converted from Qy integer result).
 */
int64_t qy_main_c(int64_t argc, char** argv);

#endif /* QY_H */