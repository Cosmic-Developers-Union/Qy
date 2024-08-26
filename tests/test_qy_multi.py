import unittest


class TestQyMulti(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, '')

    def test_imap(self):
        from qy.operators import qimap
        self.assertEqual(
            list(qimap(lambda x: x + 1, [1, 2, 3])),
            [2, 3, 4]
        )
        self.assertEqual(
            list(qimap(lambda x, y: x + y, (1, 2, 3), (1, 2, 3))),
            [2, 4, 6]
        )

    def tearDown(self):
        pass


if __name__ == '__main__':
    unittest.main()
