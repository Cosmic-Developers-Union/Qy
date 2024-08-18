import unittest
import sys


class TestOperator(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, '.')

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

    def tearDown(self):
        pass


if __name__ == '__main__':
    unittest.main()
