import logging
import subprocess
import os
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import (
    completion_is_selected,
    is_searching,
    has_completions,
    has_selection,
    vi_mode,
)

from .pgbuffer import buffer_should_be_handled

_logger = logging.getLogger(__name__)


def pgcli_bindings(pgcli):
    """Custom key bindings for pgcli."""
    kb = KeyBindings()

    tab_insert_text = " " * 4

    @kb.add("f1")
    def _(event):
        """force remove the lock file to unblock any tmux stuff"""
        _logger.debug("Detected F1 key.")
        p = "/tmp/pgclilock"
        if os.path.isfile(p):
            _logger.error("removing lock")
            os.remove("/tmp/pgclilock")
        else:
            _logger.error("creating lock")
            with open("/tmp/pgclilock", "w+") as fp:
                pass

    @kb.add("f2")
    def _(event):
        """Enable/Disable SmartCompletion Mode."""
        _logger.debug("Detected F2 key.")
        pgcli.completer.smart_completion = not pgcli.completer.smart_completion

    @kb.add("f3")
    def _(event):
        """Enable/Disable Multiline Mode."""
        _logger.debug("Detected F3 key.")
        pgcli.multi_line = not pgcli.multi_line

    @kb.add("f4")
    def _(event):
        """Toggle between Vi and Emacs mode."""
        _logger.debug("Detected F4 key.")
        pgcli.vi_mode = not pgcli.vi_mode
        event.app.editing_mode = EditingMode.VI if pgcli.vi_mode else EditingMode.EMACS

    @kb.add("tab")
    def _(event):
        """Force autocompletion at cursor on non-empty lines."""

        _logger.debug("Detected <Tab> key.")

        buff = event.app.current_buffer
        doc = buff.document

        if doc.on_first_line or doc.current_line.strip():
            if buff.complete_state:
                buff.complete_next()
            else:
                buff.start_completion(select_first=True)
        else:
            buff.insert_text(tab_insert_text, fire_event=False)

    # tmux bindings: note - you'll see odd behavior if
    # running pgcli outside of a tmux session
    @kb.add("c-l", filter=completion_is_selected)
    def _(event):
        _logger.error("c-l 1")
        event.current_buffer.complete_state = None
        event.app.current_buffer.complete_state = None

    @kb.add("c-l", filter=~completion_is_selected)
    def _(event):
        _logger.error("c-l 2")
        subprocess.run(["tmux", "select-pane", "-R"])

    # note: ctrl-h is unbound because of issues with backspace, but we could potentially fix
    # this with https://github.com/prompt-toolkit/python-prompt-toolkit/pull/1384/files
    # @kb.add("c-h")
    # def _(event):
    #     buff = event.app.current_buffer
    #     doc = buff.document
    #     _logger.error("c-h")
    #     if not doc.current_line.strip():
    #         subprocess.run(["tmux", "select-pane", "-L"])
    #     else:
    #         doc.current_line = doc.current_line[:-1]

    @kb.add("c-j")
    def _(event):
        # _logger.error("c-j")
        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            subprocess.run(["tmux", "select-pane", "-D"])
        _logger.error("c-j after")

    @kb.add("c-k")
    def _(event):
        b = event.app.current_buffer
        if b.complete_state:
            b.complete_previous()
        else:
            subprocess.run(["tmux", "select-pane", "-U"])

    @kb.add("escape", filter=has_completions)
    def _(event):
        """Force closing of autocompletion."""
        _logger.debug("Detected <Esc> key.")

        event.current_buffer.complete_state = None
        event.app.current_buffer.complete_state = None

    @kb.add("c-space", "c-f")
    def _(event):
        """
        Initialize autocompletion at cursor.

        If the autocompletion menu is not showing, display it with the
        appropriate completions for the context.

        If the menu is showing, select the next completion.
        """
        _logger.debug("Detected <C-Space> key.")

        b = event.app.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=False)

    @kb.add("enter", filter=completion_is_selected)
    def _(event):
        """Makes the enter key work as the tab key only when showing the menu.

        In other words, don't execute query when enter is pressed in
        the completion dropdown menu, instead close the dropdown menu
        (accept current selection).

        """
        _logger.debug("Detected enter key during completion selection.")

        event.current_buffer.complete_state = None
        event.app.current_buffer.complete_state = None

    # When using multi_line input mode the buffer is not handled on Enter (a new line is
    # inserted instead), so we force the handling if we're not in a completion or
    # history search, and one of several conditions are True
    @kb.add(
        "enter",
        filter=~(completion_is_selected | is_searching)
        & buffer_should_be_handled(pgcli),
    )
    def _(event):
        _logger.debug("Detected enter key.")
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter", filter=~vi_mode)
    def _(event):
        """Introduces a line break regardless of multi-line mode or not."""
        _logger.debug("Detected alt-enter key.")
        event.app.current_buffer.insert_text("\n")

    @kb.add("c-p", filter=~has_selection)
    def _(event):
        """Move up in history."""
        event.current_buffer.history_backward(count=event.arg)

    @kb.add("c-n", filter=~has_selection)
    def _(event):
        """Move down in history."""
        event.current_buffer.history_forward(count=event.arg)

    return kb
