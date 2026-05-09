import sys
import unittest


class TestOperator(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, ".")

    def test_quote(self):
        from qy.operator import quote
        from qy.operator import qy

        self.assertEqual(qy.eval((quote, "exp")), "exp")
        self.assertEqual(qy.eval((quote, ("exp", "exp"))), ("exp", "exp"))

    def test_atom(self):
        from qy.operator import NIL
        from qy.operator import T
        from qy.operator import atom
        from qy.operator import quote
        from qy.operator import qy

        self.assertEqual(qy.eval((atom, "exp")), T)
        self.assertEqual(qy.eval((atom, (quote, ("exp", "exp")))), NIL)
        self.assertEqual(qy.eval((atom, (quote, ()))), T)

    def test_eq(self):
        from qy.operator import NIL
        from qy.operator import T
        from qy.operator import eq
        from qy.operator import quote
        from qy.operator import qy

        self.assertEqual(qy.eval((eq, "exp", "exp")), T)
        self.assertEqual(qy.eval((eq, "exp", "ex")), NIL)
        self.assertEqual(qy.eval((eq, (quote, ()), (quote, ()))), T)
        self.assertEqual(qy.eval((eq, (quote, ("exp",)), (quote, ("exp",)))), NIL)

    def test_car_cdr(self):
        from qy.operator import car
        from qy.operator import cdr
        from qy.operator import quote
        from qy.operator import qy

        self.assertEqual(qy.eval((car, (quote, ("exp", "exp")))), "exp")
        self.assertEqual(qy.eval((cdr, (quote, ("exp", "exp")))), ("exp",))

    def test_cons(self):
        from qy.operator import cons
        from qy.operator import quote
        from qy.operator import qy

        self.assertEqual(qy.eval((cons, "exp", (quote, ("exp",)))), ("exp", "exp"))
        # (a b c)
        self.assertEqual(
            qy.eval((cons, "a", (cons, "b", (cons, "c", (quote, ()))))), ("a", "b", "c")
        )

    def test_cond(self):
        from qy.operator import NIL
        from qy.operator import T
        from qy.operator import cond
        from qy.operator import quote
        from qy.operator import qy

        self.assertEqual(qy.eval((cond, (NIL, (quote, "exp")), (T, (quote, "exp")))), "exp")
        self.assertEqual(qy.eval((cond, (NIL, (quote, "exp")), (NIL, (quote, "exp")))), NIL)

    def test_kwargs(self):
        from qy.operator import kw
        from qy.operator import qy

        self.assertEqual(qy.eval((kw, "a", 1, "b", 2)), {"a": 1, "b": 2})

        def test_kwargs(a, b):
            return [a, b]

        self.assertEqual(qy.eval((test_kwargs, (kw, "a", 1, "b", 2))), [1, 2])

    def tearDown(self):
        pass


if __name__ == "__main__":
    unittest.main()
