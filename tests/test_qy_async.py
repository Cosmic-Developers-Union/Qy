import unittest
import sys
import asyncio


class TestOperator(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, '')

    def test_quote(self):
        from qy.operator import qy
        from qy.operator import quote
        self.assertEqual(qy.eval((quote, 'exp')), 'exp')
        self.assertEqual(qy.eval((quote, ('exp', 'exp'))), ('exp', 'exp'))

    def test_atom(self):
        from qy.operator import qy, T, NIL
        from qy.operator import atom, quote
        self.assertEqual(qy.eval((atom, 'exp')), T)
        self.assertEqual(qy.eval((atom, (quote, ('exp', 'exp')))), NIL)
        self.assertEqual(qy.eval((atom, (quote, ()))), T)

    def test_eq(self):
        from qy.operator import qy, T, NIL
        from qy.operator import eq, quote
        self.assertEqual(qy.eval((eq, 'exp', 'exp')), T)
        self.assertEqual(qy.eval((eq, 'exp', 'ex')), NIL)
        self.assertEqual(qy.eval((eq, (quote, ()), (quote, ()))), T)
        self.assertEqual(
            qy.eval((eq, (quote, ('exp',)), (quote, ('exp',)))), NIL)

    def test_car_cdr(self):
        from qy.operator import qy
        from qy.operator import car, cdr, quote
        self.assertEqual(qy.eval((car, (quote, ('exp', 'exp')))), 'exp')
        self.assertEqual(qy.eval((cdr, (quote, ('exp', 'exp')))), ('exp',))

    def test_cons(self):
        from qy.operator import qy
        from qy.operator import cons, quote
        self.assertEqual(
            qy.eval((cons, 'exp', (quote, ('exp',)))), ('exp', 'exp'))
        # (a b c)
        self.assertEqual(
            qy.eval((cons, 'a', (cons, 'b', (cons, 'c', (quote, ()))))),
            ('a', 'b', 'c')
        )

    def test_cond(self):
        from qy.operator import qy, T, NIL
        from qy.operator import cond, quote
        self.assertEqual(
            qy.eval(
                (cond,
                 (NIL, (quote, 'exp')),
                 (T, (quote, 'exp')))
            ),
            'exp'
        )
        self.assertEqual(
            qy.eval(
                (cond,
                 (NIL, (quote, 'exp')),
                 (NIL, (quote, 'exp'))
                 )
            ),
            NIL
        )

    def test_aeval(self):
        from qy import qy

        async def add(a, b):
            return a + b
        v = asyncio.run(qy.aeval((add, 1, 2)))
        self.assertEqual(v, 3)

    def tearDown(self):
        pass


if __name__ == '__main__':
    unittest.main()
