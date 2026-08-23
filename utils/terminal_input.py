"""Interactive CLI input with working backspace/delete and arrow keys."""

from __future__ import annotations

import sys

_readline_configured = False
_non_tty_warning_shown = False


def _configure_readline() -> None:
    """Enable GNU readline / libedit line editing for built-in input()."""
    global _readline_configured
    if _readline_configured:
        return
    _readline_configured = True

    try:
        import readline
    except ImportError:
        return

    readline.parse_and_bind("set editing-mode emacs")

    doc = readline.__doc__ or ""
    if "libedit" in doc:
        # macOS ships libedit instead of GNU readline.
        for binding in (
            "bind ^I rl_complete",
            "bind ^? ed-delete-prev-char",
            "bind ^[[3~ ed-delete-next-char",
        ):
            try:
                readline.parse_and_bind(binding)
            except ValueError:
                pass
    else:
        for binding in (
            '"\\177": backward-delete-char',
            '"\\033[3~": delete-char',
        ):
            try:
                readline.parse_and_bind(f"bind {binding}")
            except ValueError:
                pass


def _warn_if_not_a_tty() -> None:
    global _non_tty_warning_shown
    if _non_tty_warning_shown or sys.stdin.isatty():
        return
    _non_tty_warning_shown = True
    print(
        "\nNote: stdin is not a real terminal (e.g. Debug Console). "
        "Backspace and arrow keys may not work.\n"
        "Run from a terminal instead:\n"
        "  source botenv/bin/activate && python app.py\n",
        file=sys.stderr,
    )


def read_user_query(prompt: str = "Engineer Query > ") -> str:
    """Read one line of user input with line editing when the terminal supports it."""
    _configure_readline()
    _warn_if_not_a_tty()
    try:
        return input(prompt).strip()
    except EOFError:
        return "exit"
