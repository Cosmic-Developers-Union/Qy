import unittest
import sys


class TestOperator(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, '.')

    def test_quote(self):
        from qy.operator import qy
        from qy.operator import quote
        print(qy.SYMBOLSPACE)
        self.assertEqual(qy.eval((quote, 'exp')), 'exp')
        self.assertEqual(qy.eval((quote, ('exp', 'exp'))), ('exp', 'exp'))

    def tearDown(self):
        pass


if __name__ == '__main__':
    unittest.main()
