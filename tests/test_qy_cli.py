import unittest

try:
    from typer.testing import CliRunner
except ModuleNotFoundError as e:
    if e.name == "typer":
        raise unittest.SkipTest("typer is an optional cli dependency") from e
    raise

from qy.cli import create_app


class TestQyCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.app = create_app()

    def test_evaluates_target_file(self):
        result = self.runner.invoke(self.app, ["examples/codes/code001.qy"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("51926.26973684211", result.output)

    def test_check_command(self):
        result = self.runner.invoke(self.app, ["check", "examples/codes/code001.qy"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("ok", result.output)

    def test_fmt_command(self):
        result = self.runner.invoke(self.app, ["fmt", "examples/codes/code001.qy"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("(+", result.output)
        self.assertIn("(* 123 456)", result.output)

    def test_ast_command(self):
        result = self.runner.invoke(self.app, ["ast", "examples/codes/code001.qy"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Symbol('+')", result.output)

    def test_operators_command(self):
        result = self.runner.invoke(self.app, ["operators"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("## 内建算子", result.output)
        self.assertIn("模块：`qy.core`", result.output)
        self.assertIn("`py` - Effect 算子", result.output)
        self.assertIn("## 模块 qy.io", result.output)
        self.assertIn("`print`", result.output)
        self.assertIn("## 模块 qy.str", result.output)
        self.assertIn("`str-upper`", result.output)

    def test_repl_keeps_session_environment(self):
        result = self.runner.invoke(
            self.app,
            input="(defun square (x) (* x x))\n(square 12)\n.exit\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("144", result.output)


if __name__ == "__main__":
    unittest.main()
