import io
import unittest
from unittest.mock import patch

from utils import terminal_input


class TerminalInputTests(unittest.TestCase):
    def setUp(self):
        terminal_input._readline_configured = False
        terminal_input._non_tty_warning_shown = False

    def test_read_user_query_strips_whitespace(self):
        with patch("builtins.input", return_value="  hello  "):
            self.assertEqual(terminal_input.read_user_query("> "), "hello")

    def test_read_user_query_eof_returns_exit(self):
        with patch("builtins.input", side_effect=EOFError):
            self.assertEqual(terminal_input.read_user_query(), "exit")

    def test_warns_when_stdin_not_tty(self):
        stderr = io.StringIO()
        with (
            patch.object(terminal_input.sys.stdin, "isatty", return_value=False),
            patch("builtins.input", return_value="test"),
            patch.object(terminal_input.sys.stderr, "write", stderr.write),
        ):
            terminal_input.read_user_query()
        self.assertIn("not a real terminal", stderr.getvalue())

    def test_configure_readline_is_idempotent(self):
        terminal_input._configure_readline()
        terminal_input._configure_readline()
        self.assertTrue(terminal_input._readline_configured)


if __name__ == "__main__":
    unittest.main()
