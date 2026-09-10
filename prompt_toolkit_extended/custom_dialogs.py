"""
custom_dialogs.py

Contains UI classes used to represent custom dialogs
"""

from __future__ import annotations
import obfuscator
from settings import SSM_CONNECTION_MODE_PORT_FORWARDING, SSM_CONNECTION_MODE_TERMINAL
from asyncio import get_running_loop
from typing import Any, List, Tuple
from prompt_toolkit_extended.custom_widgets import ScrollableButton
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import (
    AnyContainer,
    HSplit,
    VSplit,
    VerticalAlign,
    HorizontalAlign,
    WindowAlign,
)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import BaseStyle
from prompt_toolkit.widgets import Button, Dialog, Label, RadioList, TextArea, Frame


def ssm_port_selector_dialog(
    instance_id: str,
    instance_name: str,
    local_port: int,
    remote_port: int,
    selected_profile: str,
    selected_region: str,
    yes_text: str = "Connect",
    no_text: str = "Back",
    style: BaseStyle | None = None,
) -> Application[bool]:

    __local_port = local_port
    __remote_port = remote_port

    kb = KeyBindings()

    def yes_handler() -> None:
        get_app().exit(
            result={
                "result": "Connect",
                "value": {
                    "local-port": local_port_textarea.text,
                    "remote-port": remote_port_textarea.text,
                },
            }
        )

    def no_handler() -> None:
        get_app().exit(
            result={
                "result": "Quit",
                "value": {
                    "local-port": local_port_textarea.text,
                    "remote-port": remote_port_textarea.text,
                },
            }
        )

    def back_handler() -> None:
        get_app().exit(
            result={
                "result": "Back",
                "value": {
                    "local-port": local_port_textarea.text,
                    "remote-port": remote_port_textarea.text,
                },
            }
        )

    remote_port_textarea = TextArea(text=str(__remote_port))
    local_port_textarea = TextArea(text=str(__local_port))

    dialog = Dialog(
        title="SSM Session Manager Port Selector",
        body=HSplit(
            [
                Frame(
                    body=HSplit(
                        [
                            VSplit(
                                [Label("AWS Profile:"), Label(selected_profile)],
                                align=HorizontalAlign.JUSTIFY,
                            ),
                            VSplit([Label("Region:"), Label(selected_region)]),
                        ]
                    )
                ),
                Frame(
                    body=HSplit(
                        [
                            VSplit(
                                [
                                    Label("Instance:"),
                                    Label(f"{instance_id} ({instance_name})"),
                                ]
                            ),
                            HSplit(
                                [
                                    Label("Port Configuration"),
                                    VSplit(
                                        [Label("Remote Port:"), remote_port_textarea]
                                    ),
                                    VSplit([Label("Local Port:"), local_port_textarea]),
                                ],
                            ),
                        ],
                        padding=Dimension(preferred=1, max=1),
                    ),
                ),
            ],
        ),
        buttons=[
            Button(text=yes_text, handler=yes_handler),
            Button(text=no_text, handler=back_handler),
        ],
        with_background=True,
    )

    return _create_app(dialog, style)


def ssm_session_type_selector_dialog(
    instance_id: str,
    local_port: int,
    remote_port: int,
    profile_values: List[Tuple[str, str]],
    selected_profile: str,
    filter_values: List[Tuple[str, str]],
    selected_filter: str,
    region_values: List[Tuple[str, str]],
    selected_region: str,
    instance_values: List[Tuple[str, str]],
    selected_ssm_mode: str,
    yes_text: str = "Connect",
    no_text: str = "Quit",
    error_message: str = None,
    style: BaseStyle | None = None,
) -> Application[bool]:

    __local_port = local_port
    __remote_port = remote_port

    kb = KeyBindings()

    def yes_handler() -> None:
        get_app().exit(
            result={"result": "Connect", "mode": mode_selector.current_value}
        )

    def no_handler() -> None:
        get_app().exit(result={"result": "Quit", "mode": mode_selector.current_value})

    def profile_button_handler() -> None:
        get_app().exit(
            result={"result": "PROFILE", "mode": mode_selector.current_value}
        )

    def region_button_handler() -> None:
        get_app().exit(result={"result": "REGION", "mode": mode_selector.current_value})

    def filter_button_handler() -> None:
        get_app().exit(result={"result": "FILTER", "mode": mode_selector.current_value})

    def instance_button_handler() -> None:
        get_app().exit(
            result={
                "result": "INSTANCE",
                "mode": mode_selector.current_value,
                "result_value": instance_button.current_value,
            }
        )

    empty_value_text = "*** no instances found in this region ***"
    if error_message is not None:
        empty_value_text = f"*** Error: {error_message} ***"
    elif instance_id == "" or instance_id is None:
        empty_value_text = "*** no instances found in this region ***"

    remote_port_textarea = TextArea(text=str(__remote_port))
    local_port_textarea = TextArea(text=str(__local_port))

    instance_button = ScrollableButton(
        width=60,
        handler=instance_button_handler,
        left_symbol="[",
        right_symbol="]",
        values=instance_values,
        default_value=instance_id,
        empty_value_text=empty_value_text,
        disable_scrolling=True,
    )
    mode_selector = RadioList(
        [
            (SSM_CONNECTION_MODE_TERMINAL, "Terminal Session"),
            (SSM_CONNECTION_MODE_PORT_FORWARDING, "Port Forwarding Session"),
        ],
        default=selected_ssm_mode,
    )
    dialog = Dialog(
        title="SSM Session Manager Configurator",
        body=HSplit(
            [
                Frame(
                    body=HSplit(
                        [
                            HSplit(
                                [
                                    VSplit(
                                        [
                                            Label("AWS Profile:"),
                                            ScrollableButton(
                                                width=60,
                                                handler=profile_button_handler,
                                                left_symbol="[",
                                                right_symbol="]",
                                                values=profile_values,
                                                default_value=selected_profile,
                                                disable_scrolling=True,
                                            ),
                                        ],
                                        align=HorizontalAlign.JUSTIFY,
                                    ),
                                    VSplit(
                                        [
                                            Label("Region:"),
                                            ScrollableButton(
                                                width=60,
                                                handler=region_button_handler,
                                                left_symbol="[",
                                                right_symbol="]",
                                                values=region_values,
                                                default_value=selected_region,
                                                disable_scrolling=True,
                                            ),
                                        ]
                                    ),
                                ]
                            ),
                        ],
                        # padding=Dimension(preferred=1, max=1),
                    )
                ),
                Frame(
                    body=HSplit(
                        [
                            HSplit(
                                [
                                    VSplit(
                                        [
                                            Label("Filter:"),
                                            ScrollableButton(
                                                width=60,
                                                handler=filter_button_handler,
                                                left_symbol="[",
                                                right_symbol="]",
                                                values=filter_values,
                                                default_value=selected_filter,
                                                disable_scrolling=True,
                                            ),
                                        ]
                                    ),
                                    VSplit(
                                        [
                                            Label("Instance:"),
                                            instance_button,
                                        ]
                                    ),
                                ]
                            ),
                            Label("Connection Type:"),
                            mode_selector,
                        ],
                        padding=Dimension(preferred=1, max=1),
                    ),
                ),
            ],
        ),
        buttons=[
            Button(text=yes_text, handler=yes_handler),
            Button(text=no_text, handler=no_handler),
        ],
        with_background=True,
    )

    return _create_app(dialog, style)


def _create_app(dialog: AnyContainer, style: BaseStyle | None) -> Application[Any]:
    # Key bindings.
    bindings = KeyBindings()
    bindings.add("tab")(focus_next)
    bindings.add("s-tab")(focus_previous)

    return Application(
        layout=Layout(dialog),
        key_bindings=merge_key_bindings([load_key_bindings(), bindings]),
        mouse_support=True,
        style=style,
        full_screen=True,
    )
