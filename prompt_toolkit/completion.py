"""
"""
from __future__ import unicode_literals
from abc import ABCMeta, abstractmethod
from six import with_metaclass
from .eventloop import Future, run_in_executor

__all__ = (
    'Completion',
    'Completer',
    'ThreadedCompleter',
    'DummyCompleter',
    'DynamicCompleter',
    'CompleteEvent',
    'get_common_complete_suffix',
)


class Completion(object):
    """
    :param text: The new string that will be inserted into the document.
    :param start_position: Position relative to the cursor_position where the
        new text will start. The text will be inserted between the
        start_position and the original cursor position.
    :param display: (optional string) If the completion has to be displayed
        differently in the completion menu.
    :param display_meta: (Optional string) Meta information about the
        completion, e.g. the path or source where it's coming from.
    :param get_display_meta: Lazy `display_meta`. Retrieve meta information
        only when meta is displayed.
    :param style: Style string.
    :param selected_style: Style string, used for a selected completion.
        This can override the `style` parameter.
    """
    def __init__(self, text, start_position=0, display=None, display_meta=None,
                 get_display_meta=None, style='', selected_style=''):
        self.text = text
        self.start_position = start_position
        self._display_meta = display_meta
        self._get_display_meta = get_display_meta

        if display is None:
            self.display = text
        else:
            self.display = display

        self.style = style
        self.selected_style = selected_style

        assert self.start_position <= 0

    def __repr__(self):
        if self.display == self.text:
            return '%s(text=%r, start_position=%r)' % (
                self.__class__.__name__, self.text, self.start_position)
        else:
            return '%s(text=%r, start_position=%r, display=%r)' % (
                self.__class__.__name__, self.text, self.start_position,
                self.display)

    def __eq__(self, other):
        return (
            self.text == other.text and
            self.start_position == other.start_position and
            self.display == other.display and
            self.display_meta == other.display_meta)

    def __hash__(self):
        return hash((self.text, self.start_position, self.display, self.display_meta))

    @property
    def display_meta(self):
        # Return meta-text. (This is lazy when using "get_display_meta".)
        if self._display_meta is not None:
            return self._display_meta

        elif self._get_display_meta:
            self._display_meta = self._get_display_meta()
            return self._display_meta

        else:
            return ''

    def new_completion_from_position(self, position):
        """
        (Only for internal use!)
        Get a new completion by splitting this one. Used by `Application` when
        it needs to have a list of new completions after inserting the common
        prefix.
        """
        assert isinstance(position, int) and position - self.start_position >= 0

        return Completion(
            text=self.text[position - self.start_position:],
            display=self.display,
            display_meta=self._display_meta,
            get_display_meta=self._get_display_meta)


class CompleteEvent(object):
    """
    Event that called the completer.

    :param text_inserted: When True, it means that completions are requested
        because of a text insert. (`Buffer.complete_while_typing`.)
    :param completion_requested: When True, it means that the user explicitely
        pressed the `Tab` key in order to view the completions.

    These two flags can be used for instance to implemented a completer that
    shows some completions when ``Tab`` has been pressed, but not
    automatically when the user presses a space. (Because of
    `complete_while_typing`.)
    """
    def __init__(self, text_inserted=False, completion_requested=False):
        assert not (text_inserted and completion_requested)

        #: Automatic completion while typing.
        self.text_inserted = text_inserted

        #: Used explicitely requested completion by pressing 'tab'.
        self.completion_requested = completion_requested

    def __repr__(self):
        return '%s(text_inserted=%r, completion_requested=%r)' % (
            self.__class__.__name__, self.text_inserted, self.completion_requested)


class Completer(with_metaclass(ABCMeta, object)):
    """
    Base class for completer implementations.
    """
    @abstractmethod
    def get_completions(self, document, complete_event):
        """
        Yield :class:`.Completion` instances.

        :param document: :class:`~prompt_toolkit.document.Document` instance.
        :param complete_event: :class:`.CompleteEvent` instance.
        """
        while False:
            yield

    def get_completions_future(self, document, complete_event):
        """
        Return a `Future` which is set when the completions are ready.
        This function can be overloaded in order to provide an asynchronous
        implementation.
        """
        f = Future()
        result = self.get_completions(document, complete_event)
        f.set_result(result)
        return f


class ThreadedCompleter(Completer):
    """
    Wrapper that runs completions in a thread.
    (Use this to prevent the user interface from becoming unresponsive if the
    generation of completions takes too much time.)
    """
    def __init__(self, completer):
        assert isinstance(completer, Completer)
        self.completer = completer

    def get_completions(self, document, complete_event):
        return self.completer.get_completions(document, complete_event)

    def get_completions_future(self, document, complete_event):
        """
        Run the `get_completions` function in a thread.
        """
        def run_get_completions_thread():
            return self.get_completions(document, complete_event)
        f = run_in_executor(run_get_completions_thread)
        return f


class DummyCompleter(Completer):
    """
    A completer that doesn't return any completion.
    """
    def get_completions(self, document, complete_event):
        return []


class DynamicCompleter(Completer):
    """
    Completer class that can dynamically returns any Completer.

    :param get_completer: Callable that returns a :class:`.Completer` instance.
    """
    def __init__(self, get_completer):
        assert callable(get_completer)
        self.get_completer = get_completer

    def get_completions(self, document, complete_event):
        completer = self.get_completer() or DummyCompleter()
        return completer.get_completions(document, complete_event)

    def get_completions_future(self, document, complete_event):
        completer = self.get_completer() or DummyCompleter()
        return completer.get_completions_future(document, complete_event)


def get_common_complete_suffix(document, completions):
    """
    Return the common prefix for all completions.
    """
    # Take only completions that don't change the text before the cursor.
    def doesnt_change_before_cursor(completion):
        end = completion.text[:-completion.start_position]
        return document.text_before_cursor.endswith(end)

    completions2 = [c for c in completions if doesnt_change_before_cursor(c)]

    # When there is at least one completion that changes the text before the
    # cursor, don't return any common part.
    if len(completions2) != len(completions):
        return ''

    # Return the common prefix.
    def get_suffix(completion):
        return completion.text[-completion.start_position:]

    return _commonprefix([get_suffix(c) for c in completions2])


def _commonprefix(strings):
    # Similar to os.path.commonprefix
    if not strings:
        return ''

    else:
        s1 = min(strings)
        s2 = max(strings)

        for i, c in enumerate(s1):
            if c != s2[i]:
                return s1[:i]

        return s1
