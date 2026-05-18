/* mqr basic unit tests — run with: make test-mqr */
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

#include "mqr.h"

/* ---------------------------------------------------------------------------
 * Test helpers
 * ---------------------------------------------------------------------------*/

static void check_T(qy_value v, const char* expr) {
    if (!qy_is_T(v)) {
        printf("  FAIL: expected T, got tag=%d for %s\n", v.tag, expr);
        abort();
    }
}

static void check_nil(qy_value v, const char* expr) {
    if (!qy_is_nil(v)) {
        printf("  FAIL: expected nil, got tag=%d for %s\n", v.tag, expr);
        abort();
    }
}

static void check_int(qy_value v, int64_t expected, const char* expr) {
    if (!qy_is_int(v) || qy_int_val(v) != expected) {
        printf("  FAIL: expected int %" PRId64 ", got tag=%d for %s\n",
               expected, v.tag, expr);
        abort();
    }
}

/* ---------------------------------------------------------------------------
 * Mock Qy runtime symbols (normally provided by LLVM codegen / linker)
 * ---------------------------------------------------------------------------*/

static qy_value _null_fn(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)argv; (void)env;
    return qy_nil();
}

/* qy_fn_table: array of compiled Qy function pointers.  Indexed by fn_idx. */
qy_value (*qy_fn_table[])(int64_t, qy_value*, qy_env*) = { _null_fn };
const int64_t qy_fn_table_size = 1;

/* ---------------------------------------------------------------------------
 * test_main — the test entry point (called by mqr_main via qy_main)
 * ---------------------------------------------------------------------------*/

static void test_main(void) {
    mqr_init();

    /* ---- nil/T ---- */
    assert(qy_is_nil(qy_nil()));
    assert(qy_is_Tt(qy_T()));
    assert(!qy_is_nil(qy_T()));
    assert(!qy_is_Tt(qy_nil()));
    printf("  [PASS] nil/T constructors\n");

    /* ---- integer ---- */
    qy_value i = qy_int(42);
    assert(qy_is_int(i));
    assert(qy_int_val(i) == 42);
    assert(!qy_is_int(qy_nil()));
    printf("  [PASS] integer constructor\n");

    /* ---- arithmetic ---- */
    assert(mqr_add(1, 2) == 3);
    assert(mqr_sub(5, 3) == 2);
    assert(mqr_mul(3, 4) == 12);
    assert(mqr_div(10, 2) == 5);
    assert(mqr_div(5, 0) == 0);           /* sets mqr_div_by_zero */
    assert(mqr_div_by_zero);
    assert(mqr_mod(10, 3) == 1);
    printf("  [PASS] arithmetic\n");

    /* ---- comparison ---- */
    check_T(mqr_eq(qy_int(1), qy_int(1)), "eq(1,1)");
    check_nil(mqr_eq(qy_int(1), qy_int(2)), "eq(1,2)");
    check_T(mqr_eq(qy_nil(), qy_nil()), "eq(nil,nil)");
    check_T(mqr_eq(qy_T(), qy_T()), "eq(T,T)");
    check_nil(mqr_eq(qy_nil(), qy_T()), "eq(nil,T)");
    check_T(mqr_lt(qy_int(1), qy_int(2)), "lt(1,2)");
    check_nil(mqr_lt(qy_int(2), qy_int(1)), "lt(2,1)");
    check_T(mqr_gt(qy_int(3), qy_int(2)), "gt(3,2)");
    printf("  [PASS] eq/lt/gt\n");

    /* ---- cons cell ---- */
    qy_value cons = mqr_cons(qy_int(1), qy_int(2));
    assert(qy_is_cons(cons));
    check_int(mqr_car(cons), 1, "car(cons)");
    check_int(mqr_cdr(cons), 2, "cdr(cons)");

    /* list: (1 . (2 . (3 . nil))) */
    qy_value lst = mqr_cons(qy_int(1),
                     mqr_cons(qy_int(2),
                     mqr_cons(qy_int(3), qy_nil())));
    check_int(mqr_car(lst), 1, "car(list)");
    check_int(mqr_car(mqr_cdr(lst)), 2, "car(cdr(list))");
    check_int(mqr_car(mqr_cdr(mqr_cdr(lst))), 3, "car(cdr(cdr(list)))");
    check_nil(mqr_cdr(mqr_cdr(mqr_cdr(lst))), "cdr(cdr(cdr(list)))");
    printf("  [PASS] cons/car/cdr/list\n");

    /* ---- function value ---- */
    qy_value fn = mqr_make_function(3, NULL, 42);
    assert(fn.tag == QY_TAG_FUNCTION);
    assert(fn.payload[0] == 3);    /* arity */
    assert(fn.payload[1] == 0);    /* env = NULL */
    assert(fn.payload[2] == 42);   /* fn_idx */
    printf("  [PASS] function value\n");

    /* ---- string ---- */
    qy_value s = mqr_make_string("hello", 5);
    assert(s.tag == QY_TAG_STRING);
    assert(mqr_string_len(s) == 5);
    assert(mqr_string_cstr(s)[4] == 'o');
    printf("  [PASS] string\n");

    /* ---- effect frame (stubs) ---- */
    qy_value ef = mqr_save_frame(99, NULL, NULL, 0);
    assert(ef.tag == QY_TAG_EFFECT);
    printf("  [PASS] effect frame\n");

    printf("\n  mqr unit tests: ALL PASSED\n");
}

/* ---------------------------------------------------------------------------
 * qy_main — test wrapper (mock; mqr_main calls this)
 * ---------------------------------------------------------------------------*/

qy_value qy_main(int64_t argc, qy_value* argv, qy_env* env) {
    (void)argc; (void)argv; (void)env;
    test_main();
    return qy_int(0);
}

/* ---------------------------------------------------------------------------
 * main — entry point for direct execution (bypasses mqr_main)
 * ---------------------------------------------------------------------------*/

int main(void) {
    test_main();
    return 0;
}