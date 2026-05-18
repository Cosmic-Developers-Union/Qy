/* Minimal Qy Runtime (MQR)
 * A minimal C runtime for the Qy LLVM backend.
 *
 * Value layout: tagged 64-bit union
 *   tag = 0: nil (payload=0)
 *   tag = 1: T   (payload=0)
 *   tag = 2: integer (payload = i64 value)
 *   tag = 3: cons cell (payload[0..7]=car*, payload[8..15]=cdr*)
 *   tag = 4: function (payload[0..7]=arity+i64, payload[8..15]=env*, payload[16..23]=fn_idx)
 *   tag = 5: effect frame (payload = pointer to EffectFrame struct)
 *   tag = 6: host ref (payload[0..7]=ptr, payload[8..15]=type_id)
 *   tag = 7: string (payload[0..7]=cstr*, payload[8..15]=len)
 *
 * All Qy functions follow this calling convention:
 *   qy_value qy_fn(int64_t argc, qy_value* argv, qy_env* env);
 *
 * The MQR provides the primitive operations that the LLVM IR codegen
 * calls directly.  It does not perform GC in Phase Q2 (simple bump allocator).
 */

#ifndef MQR_H
#define MQR_H

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
    return (qy_value){QY_TAG_NIL, {0, 0, 0}};
}

static inline qy_value qy_T(void) {
    return (qy_value){QY_TAG_T, {0, 0, 0}};
}

static inline qy_value qy_int(int64_t n) {
    qy_value v = {QY_TAG_INT, {0, 0, 0}};
    v.payload[0] = (uint64_t)n;
    return v;
}

/* Convenience: check tag without extracting payload */
static inline int qy_is_nil(qy_value v)   { return v.tag == QY_TAG_NIL; }
static inline int qy_is_T(qy_value v)    { return v.tag == QY_TAG_T; }
static inline int qy_is_int(qy_value v)  { return v.tag == QY_TAG_INT; }
static inline int qy_is_cons(qy_value v) { return v.tag == QY_TAG_CONS; }
static inline int qy_is_Tt(qy_value v)   { return v.tag == QY_TAG_T; } /* alias for QY_T */

/* Extract integer payload */
static inline int64_t qy_int_val(qy_value v) {
    return (int64_t)v.payload[0];
}

/* ---------------------------------------------------------------------------
 * Arithmetic (integer only in Phase Q2)
 * ---------------------------------------------------------------------------*/

int64_t  mqr_add(int64_t a, int64_t b);
int64_t  mqr_sub(int64_t a, int64_t b);
int64_t  mqr_mul(int64_t a, int64_t b);
int64_t  mqr_div(int64_t a, int64_t b);   /* div-by-zero: returns 0, sets mqr_div_by_zero */
int64_t  mqr_mod(int64_t a, int64_t b);

/* ---------------------------------------------------------------------------
 * Comparison
 * ---------------------------------------------------------------------------*/

qy_value mqr_eq(qy_value a, qy_value b);   /* returns QY_T or QY_NIL */
qy_value mqr_lt(qy_value a, qy_value b);
qy_value mqr_gt(qy_value a, qy_value b);
int8_t   mqr_nil_p(qy_value v);   /* returns 1 if nil, 0 otherwise */
int8_t   mqr_not(int8_t x);        /* logical not: 1→0, 0→1 */

/* Convenience: branch on nil (false) vs everything-else (true).
 * Used by JUMP_IF_FALSE. */
static inline int qy_is_false(qy_value v) { return v.tag == QY_TAG_NIL; }
static inline int qy_is_true(qy_value v)  { return v.tag != QY_TAG_NIL; }

/* ---------------------------------------------------------------------------
 * Cons cell (Phase Q3)
 * ---------------------------------------------------------------------------*/

qy_value mqr_cons(qy_value car, qy_value cdr);
qy_value mqr_car(qy_value c);
qy_value mqr_cdr(qy_value c);

/* ---------------------------------------------------------------------------
 * Function (Phase Q3)
 * ---------------------------------------------------------------------------*/

/* Environment stub — Phase Q2 functions have no closure, so env is always NULL */
typedef struct qy_env qy_env;

/* mqr_make_function: create a function value.
 *   arity: number of parameters
 *   env: closure environment (NULL if no closure capture)
 *   fn_idx: index into the compiled function table
 * Returns a qy_value with tag=QY_TAG_FUNCTION.
 */
qy_value mqr_make_function(int64_t arity, qy_env* env, int64_t fn_idx);

/* mqr_call: invoke a function value.
 *   fn: function value (must have tag=QY_TAG_FUNCTION)
 *   argv: argument array (caller-owned, callee does not take ownership)
 *   argc: argument count
 * Returns the result qy_value.
 */
qy_value mqr_call(qy_value fn, qy_value* argv, int64_t argc);

/* ---------------------------------------------------------------------------
 * I/O (Phase Q5)
 * ---------------------------------------------------------------------------*/

void mqr_print(qy_value v);     /* print without newline */
void mqr_println(qy_value v);   /* print with newline */
void mqr_display(qy_value v);  /* display: write value to stdout (like print, but for REPL) */
void mqr_echo(qy_value v);      /* echo: display value followed by newline */
void mqr_newline(void);          /* print a newline */
qy_value mqr_read(void);        /* read line from stdin, return as string */
qy_value mqr_read_int(void);     /* read integer from stdin */

/* ---------------------------------------------------------------------------
 * String (Phase Q5)
 * ---------------------------------------------------------------------------*/

/* mqr_make_string: create a string value from a C string.
 *   cstr: null-terminated C string (MQR copies the contents)
 *   len: length in bytes (excluding null terminator)
 * Returns a qy_value with tag=QY_TAG_STRING.
 */
qy_value mqr_make_string(const char* cstr, int64_t len);

/* mqr_string_cstr: extract the C string pointer from a string value.
 *   v must have tag=QY_TAG_STRING.
 */
const char* mqr_string_cstr(qy_value v);
int64_t     mqr_string_len(qy_value v);

/* ---------------------------------------------------------------------------
 * Effect frame (Phase Q4)
 * ---------------------------------------------------------------------------*/

typedef struct {
    uint64_t pc;
    qy_env*  env;
    void*    saved_registers;
    size_t   nregs;
} mqr_effect_frame;

/* mqr_save_frame: capture the current continuation.
 *   pc: program counter at the perform site (instruction index)
 *   env: current environment
 *   regs: pointer to register array
 *   nregs: number of registers
 * Returns an effect frame value (tag=QY_TAG_EFFECT).
 */
qy_value mqr_save_frame(uint64_t pc, qy_env* env, void* regs, size_t nregs);

/* mqr_resume: resume computation from a saved frame with a value.
 *   frame: effect frame value (tag=QY_TAG_EFFECT)
 *   val: value to resume with
 * Returns the result of the handler (if any), or the resumed value.
 */
qy_value mqr_resume(qy_value frame, qy_value val);

/* mqr_perform: trigger an effect.
 *   effect_name: null-terminated effect name (e.g. "state", "io")
 *   arg: effect argument value
 * Returns: if there is a matching handler in the current continuation,
 *          the handler result; otherwise the effect is unhandled and this
 *          may abort or return QY_NIL (depending on effect declaration).
 */
qy_value mqr_perform(const char* effect_name, qy_value arg);

/* mqr_handle: set up an effect handler around a body function.
 *   body_fn_idx: index of the body function to run with protection
 *   num_handlers: number of handlers
 *   handler_names: array of effect name strings (num_handlers entries)
 *   handler_fn_indices: array of handler function indices (num_handlers entries)
 * Returns the result of body_fn (or the handler result if an effect is performed).
 */
qy_value mqr_handle(int64_t body_fn_idx,
                    int64_t num_handlers,
                    const char** handler_names,
                    int64_t* handler_fn_indices);

/* ---------------------------------------------------------------------------
 * Builtin operator (Phase Q5)
 * ---------------------------------------------------------------------------*/

/* mqr_builtin_fn: create a builtin operator function value.
 *   idx: builtin operator index (see mqr.c BUILTIN_OPS table)
 * Returns a qy_value with tag=QY_TAG_FUNCTION.
 */
qy_value mqr_builtin_fn(int64_t idx);

/* mqr_resolve_sym: look up a symbol name in the runtime symbol table.
 *   name: null-terminated symbol name
 * Returns: the symbol value (Qy function, builtin, or nil if not found).
 * Phase Q5: minimal stub that returns nil for undefined symbols.
 */
qy_value mqr_resolve_sym(const char* name);

/* ---------------------------------------------------------------------------
 * Memory / Allocation
 * ---------------------------------------------------------------------------*/

/* mqr_alloc: allocate memory (Phase Q2: simple bump allocator, no GC).
 *   size: bytes to allocate
 * Returns a pointer, or NULL on allocation failure.
 * The returned memory is uninitialized.
 */
void* mqr_alloc(size_t size);

/* mqr_alloc_array: allocate and zero-initialize an array of qy_value.
 */
qy_value* mqr_alloc_array(int64_t n);

/* mqr_gc: run the garbage collector (Phase Q6: stop-and-copy).
 *   Currently a no-op in Phase Q2-Q5.
 */
void mqr_gc(void);

/* mqr_gc_threshold: set the allocation threshold at which GC triggers.
 *   Set to 0 to disable GC.
 */
void mqr_gc_threshold(size_t bytes);

/* ---------------------------------------------------------------------------
 * Runtime state
 * ---------------------------------------------------------------------------*/

/* Set by mqr_div when div-by-zero occurs.  User code can check this. */
extern volatile int mqr_div_by_zero;

/* mqr_abort: abort with a message.  Used for unhandled effects, etc. */
__attribute__((noreturn))
void mqr_abort(const char* msg);

/* mqr_abort_fmt: abort with a printf-formatted message. */
__attribute__((noreturn))
void mqr_abort_fmt(const char* fmt, ...);

/* ---------------------------------------------------------------------------
 * Runtime entry point
 * ---------------------------------------------------------------------------*/

/* mqr_init: initialize the runtime.  Called automatically by mqr_main. */
void mqr_init(void);

/* mqr_main: the C entry point.  Calls qy_main (the compiled Qy program).
 *   argc, argv: as in main(int argc, char** argv)
 * Returns the exit code (converted from Qy integer result).
 */
int64_t mqr_main(int64_t argc, char** argv);

/* qy_main: the Qy program entry point, generated by the LLVM codegen.
 *   This is implemented in the LLVM-generated code, not in mqr.c.
 *   Declaration only — the linker resolves this symbol.
 */
extern qy_value qy_main(int64_t argc, qy_value* argv, qy_env* env);

/* qy_fn_table: array of Qy function pointers, populated by the linker.
 *   Indexed by fn_idx in function values.
 *   Declaration only — populated at link time by the LLVM codegen output.
 */
extern qy_value (*qy_fn_table[])(int64_t argc, qy_value* argv, qy_env* env);
extern const int64_t qy_fn_table_size;

#endif /* MQR_H */