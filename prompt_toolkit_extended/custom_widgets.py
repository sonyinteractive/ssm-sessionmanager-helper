"""
custom_widgets.py

Contains UI classes used to represent custom widgets that are used in dialogs
"""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

from prompt_toolkit.application.current import get_app

from prompt_toolkit.formatted_text import AnyFormattedText, StyleAndTextTuples

from prompt_toolkit.key_binding.key_bindings import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout.containers import (
    Container,
    Window,
    WindowAlign,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.utils import get_cwidth
from prompt_toolkit.widgets import Button

import obfuscator


_T = TypeVar("_T")
E = KeyPressEvent


class ScrollableButton(Button):
    """
    Clickable button.

    :param text: The caption for the button.
    :param handler: `None` or callable. Called when the button is clicked. No
        parameters are passed to this callable. Use for instance Python's
        `functools.partial` to pass parameters to this callable if needed.
    :param width: Width of the button.
    """

    enable_scrolling: bool = False

    def __init__(
        self,
        handler: Callable[[], None] | None = None,
        width: int = 12,
        left_symbol: str = "<",
        right_symbol: str = ">",
        empty_value_text: str = "",
        values: Sequence[tuple[_T, AnyFormattedText]] | None = None,
        default_value: _T | None = None,
        disable_scrolling: bool = False,
    ) -> None:
        self.left_symbol = left_symbol
        self.right_symbol = right_symbol
        self.handler = handler
        self.width = width
        self.control = FormattedTextControl(
            self._get_text_fragments,
            key_bindings=self._get_key_bindings(),
            focusable=True,
        )
        self.enable_scrolling = not disable_scrolling

        def get_style() -> str:
            if get_app().layout.has_focus(self):
                return "class:button.focused"
            else:
                return "class:button"

        # assert len(values) > 0
        # self.values = values

        if len(values) == 0:
            values = [(0, empty_value_text)]

        self.values = values

        # current_values will be used in multiple_selection,
        # current_value will be used otherwise.
        keys: list[_T] = [value for (value, _) in values]
        # self.current_values: list[_T] = [
        #     value for value in default_values if value in keys
        # ]
        self.current_value: _T = (
            default_value if default_value in keys else self.values[0][0]
        )

        self._selected_index = keys.index(self.current_value)

        self.text = values[self._selected_index]

        # Note: `dont_extend_width` is False, because we want to allow buttons
        #       to take more space if the parent container provides more space.
        #       Otherwise, we will also truncate the text.
        #       Probably we need a better way here to adjust to width of the
        #       button to the text.

        self.window = Window(
            self.control,
            align=WindowAlign.CENTER,
            height=1,
            width=width,
            style=get_style,
            dont_extend_width=False,
            dont_extend_height=True,
        )

    def _get_text_fragments(self) -> StyleAndTextTuples:
        width = self.width - (
            get_cwidth(self.left_symbol) + get_cwidth(self.right_symbol)
        )
        text = (f"{{:^{width}}}").format(self.text[1])

        def handler(mouse_event: MouseEvent) -> None:
            if (
                self.handler is not None
                and mouse_event.event_type == MouseEventType.MOUSE_UP
            ):
                self.handler()

        return [
            ("class:button.arrow", self.left_symbol, handler),
            ("[SetCursorPosition]", ""),
            ("class:button.text", text, handler),
            ("class:button.arrow", self.right_symbol, handler),
        ]

    def _get_key_bindings(self) -> KeyBindings:
        "Key bindings for the Button."
        kb = KeyBindings()

        if self.enable_scrolling:

            @kb.add("left")
            def _left(event: E) -> None:
                self._selected_index = max(0, self._selected_index - 1)
                self.text = self.values[self._selected_index]

            @kb.add("right")
            def _right(event: E) -> None:
                self._selected_index = min(
                    len(self.values) - 1, self._selected_index + 1
                )
                self.text = self.values[self._selected_index]

        @kb.add(" ")
        @kb.add("enter")
        def _(event: E) -> None:
            if self.handler is not None:
                self.handler()

        return kb

    def __pt_container__(self) -> Container:
        return self.window
