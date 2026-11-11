import os
import sys
from concurrent.futures import Future
from types import SimpleNamespace
from typing import cast

import pytest
from typer.testing import CliRunner

import sys_eden.interactive_cli as interactive_cli_module
import sys_eden.terminal_navigation as terminal_navigation_module
from sys_eden.cli import app
from sys_eden.config import Settings
from sys_eden.core_application import CoreLifecycleState, CoreRuntimeStatus
from sys_eden.core_rpc import CoreRpcError, LocalCoreClient, RpcError
from sys_eden.interactive_cli import RUNNING_BUTTONS, InteractiveCli
from sys_eden.terminal_navigation import (
    ChatBarResult,
    LiveTerminal,
    TerminalButton,
    TerminalCommand,
    TerminalListItem,
    read_chat_bar,
    select_button,
    select_list,
    show_escape_view,
)

BUTTONS = (
    TerminalButton("Start Core", "start-core"),
    TerminalButton("Help", "help"),
    TerminalButton("Settings", "settings"),
    TerminalButton("Exit", "exit-client"),
)

COMMANDS = (
    TerminalCommand("/new", "/new", "Start a new chat."),
    TerminalCommand("/home", "/home", "Return home."),
    TerminalCommand("/help", "/help", "Show help."),
    TerminalCommand("/chats", "/chats", "Browse chats."),
    TerminalCommand("/corestart", "/corestart", "Start Core."),
    TerminalCommand("/corestop", "/corestop", "Stop Core."),
    TerminalCommand("/resume", "/resume ", "Resume a chat."),
)


def _reader(*keys: str):
    remaining = iter(keys)
    return lambda: next(remaining)


def test_arrow_keys_move_between_inline_buttons_and_enter_selects():
    output: list[str] = []

    selected = select_button(
        BUTTONS,
        read_key=_reader("right", "right", "enter"),
        write=output.append,
    )

    assert selected == "settings"
    assert ">[Start Core]<" in output[0]
    assert ">[Settings]<" in output[-2]


def test_navigation_wraps_and_escape_returns_without_action():
    assert (
        select_button(
            BUTTONS,
            read_key=_reader("left", "enter"),
            write=lambda _: None,
        )
        == "exit-client"
    )


def test_vertical_lists_use_arrows_and_enter_to_open_an_item():
    selected = select_list(
        (
            TerminalListItem("CHT-1  First", "CHT-1", "full"),
            TerminalListItem("CHT-2  Second", "CHT-2", "compact"),
        ),
        title="Conversations",
        read_key=_reader("down", "enter"),
        write=lambda _: None,
    )

    assert selected == "CHT-2"
    assert (
        select_button(
            BUTTONS,
            read_key=_reader("escape"),
            write=lambda _: None,
        )
        is None
    )


def test_running_chat_bar_accepts_text_without_opening_a_new_chat_menu():
    output: list[str] = []

    result = read_chat_bar(
        BUTTONS[1:],
        context="New temporary chat",
        read_key=_reader("text:H", "text:i", "enter"),
        write=output.append,
    )

    assert result.message == "Hi"
    assert result.action is None
    assert "New temporary chat" in output[-2]


def test_empty_chat_bar_uses_arrows_to_open_secondary_navigation():
    result = read_chat_bar(
        BUTTONS[1:],
        context="TMP-1",
        read_key=_reader("down", "right", "enter"),
        write=lambda _: None,
    )

    assert result.message is None
    assert result.action == "settings"


def test_chat_navigation_moves_between_button_and_composer_rows():
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("down", "right", "up", "text:x", "enter"),
        write=lambda _: None,
    )

    assert result.message == "x"
    assert result.action is None


def test_left_and_right_do_not_change_buttons_while_composer_is_selected():
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("right", "down", "enter"),
        write=lambda _: None,
    )

    assert result.action == "conversations"


def test_composer_arrow_is_white_in_chat_and_leaves_when_buttons_are_selected():
    button_output: list[str] = []
    terminal = LiveTerminal(button_output.append, fullscreen=True)
    read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("down", "escape"),
        surface=terminal,
    )
    button_frame = "".join(button_output).rsplit("\x1b[H", maxsplit=1)[-1]
    assert ">[Conversations]<" in button_frame
    assert "›" not in button_frame

    chat_output: list[str] = []
    terminal = LiveTerminal(chat_output.append, fullscreen=True)
    read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("escape"),
        surface=terminal,
    )
    chat_frame = "".join(chat_output).rsplit("\x1b[H", maxsplit=1)[-1]
    assert "\x1b[38;5;255m› " in chat_frame


def test_backspace_deletes_one_character_without_clearing_draft():
    result = read_chat_bar(
        BUTTONS[1:],
        context="TMP-1",
        read_key=_reader("text:a", "text:b", "backspace", "text:c", "enter"),
        write=lambda _: None,
    )

    assert result.message == "ac"


def test_left_right_insert_and_backspace_edit_at_cursor():
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("text:abcd", "left", "left", "text:X", "right", "backspace", "enter"),
        write=lambda _: None,
    )

    assert result.message == "abXd"


def test_delete_removes_character_at_cursor_without_moving_it():
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("text:abcd", "left", "left", "delete", "text:X", "enter"),
        write=lambda _: None,
    )

    assert result.message == "abXd"


def test_delete_at_end_does_not_remove_previous_character():
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("text:abcd", "delete", "enter"),
        write=lambda _: None,
    )

    assert result.message == "abcd"


def test_up_down_move_within_wrapped_composer_before_buttons(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 24)
    original = "abcdefghijklmnopqrstuvwx"
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader(f"text:{original}", "up", "text:X", "down", "text:Y", "enter"),
        write=lambda _: None,
    )

    assert result.message == original[:7] + "X" + original[7:] + "Y"


def test_down_from_last_composer_row_reaches_buttons(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 24)
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("text:abcdefghijklmnopqrstuvwx", "down", "enter"),
        write=lambda _: None,
    )

    assert result.action == "conversations"


def test_wrapped_composer_renders_cursor_inside_text_and_keeps_help_visible(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 24)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 20)
    frame = terminal_navigation_module._render_fullscreen_chat(
        "Ready", RUNNING_BUTTONS, selected=0, buttons_focused=False,
        context="TMP-1", buffer="abcdefghijklmnopqrstuvwx", cursor_index=5,
        header_title="SYS EDEN", command_suggestions=(), selected_suggestion=0,
        window_focused=True,
    )

    assert "abcde\x1b[sfghijklmnopq" in frame
    assert "rstuvwx" in frame
    assert "/help for commands" in frame
    assert len(frame.splitlines()) <= 20


def test_escape_does_not_erase_the_draft():
    result = read_chat_bar(
        BUTTONS[1:],
        context="TMP-1",
        read_key=_reader("text:a", "escape", "text:b", "enter"),
        write=lambda _: None,
    )

    assert result.message == "ab"


def test_slash_palette_filters_commands_and_enter_completes_before_submitting():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        command_suggestions=COMMANDS,
        read_key=_reader("text:/", "text:h", "enter", "enter"),
        surface=terminal,
    )

    rendered = "".join(output)
    matching_frame = [
        frame
        for frame in rendered.split("\x1b[H")
        if "Commands" in frame and "/help" in frame and "/home" in frame
    ][-1]
    assert "/new" not in matching_frame
    assert result.message == "/home"


def test_filtered_slash_palette_clears_every_row_from_the_previous_frame():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        command_suggestions=COMMANDS,
        read_key=_reader("text:/", "text:h", "ctrl_c"),
        surface=terminal,
    )

    matching_frame = [
        frame
        for frame in "".join(output).split("\x1b[H")
        if "Commands" in frame and "/help" in frame and "/home" in frame
    ][-1]
    assert "/new" not in matching_frame
    assert "\n\n" not in matching_frame


def test_slash_palette_shows_five_commands_and_scrolls_with_arrows():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        command_suggestions=COMMANDS,
        read_key=_reader("text:/", "down", "down", "down", "down", "down", "enter", "enter"),
        surface=terminal,
    )

    palette_frames = [frame for frame in "".join(output).split("\x1b[H") if "Commands" in frame]
    assert all(sum(command.label in frame for command in COMMANDS) <= 5 for frame in palette_frames)
    assert "/corestop" in palette_frames[-1]
    assert result.message == "/corestop"


def test_slash_palette_completes_argument_commands_without_submitting_early():
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        command_suggestions=COMMANDS,
        read_key=_reader(
            "text:/",
            "text:r",
            "enter",
            "text:C",
            "text:H",
            "text:T",
            "text:-",
            "text:1",
            "enter",
        ),
        write=lambda _: None,
    )

    assert result.message == "/resume CHT-1"


def test_slash_palette_suggests_matching_ids_after_command_and_chooses_newest_first():
    suggestions = (
        TerminalCommand("/resume <id>", "/resume ", "Resume a chat."),
        TerminalCommand("/resume CHT-NEW", "/resume CHT-NEW", "New chat"),
        TerminalCommand("/resume CHT-OLD", "/resume CHT-OLD", "Old chat"),
    )
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        command_suggestions=suggestions,
        read_key=_reader("text:/resume", "enter", "enter"),
        write=lambda _: None,
    )

    assert result.message == "/resume CHT-NEW"

    filtered = read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        command_suggestions=suggestions,
        read_key=_reader("text:/resume CHT-O", "enter"),
        write=lambda _: None,
    )
    assert filtered.message == "/resume CHT-OLD"


def test_running_home_uses_a_composer_instead_of_a_new_chat_button():
    assert [button.label for button in RUNNING_BUTTONS] == [
        "Conversations",
        "Monitoring",
    ]


def test_escape_on_empty_chat_bar_returns_to_the_parent_view():
    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="TMP-1",
        read_key=_reader("escape"),
        write=lambda _: None,
    )

    assert result.canceled
    assert result.cancel_key == "escape"


def test_fullscreen_terminal_uses_and_restores_the_alternate_screen():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    terminal.update("First")
    terminal.update("Second")
    terminal.exit()

    rendered = "".join(output)
    assert "\x1b[?1049h" in rendered
    assert "\x1b[?1004h" in rendered
    assert "\x1b[?1000h" in rendered
    assert "\x1b[?1006h" in rendered
    assert "\x1b[?25l\x1b[0m\x1b[HSecond\x1b[0m\x1b[J" in rendered
    assert "\x1b[0 q" in rendered
    assert "\x1b[?1004l" in rendered
    assert "\x1b[?1000l" in rendered
    assert "\x1b[?1006l" in rendered
    assert "\x1b[?1049l" in rendered


def test_fullscreen_terminal_restores_original_input_mode(monkeypatch):
    restored: list[int | None] = []
    monkeypatch.setattr(
        terminal_navigation_module, "_enable_windows_virtual_terminal_input", lambda: 123
    )
    monkeypatch.setattr(
        terminal_navigation_module, "_restore_windows_input_mode", restored.append
    )
    terminal = LiveTerminal(lambda _: None, fullscreen=True)

    terminal.enter()
    terminal.exit()

    assert restored == [123]


def test_composer_uses_native_block_cursor_at_the_typing_position():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="New temporary chat",
        read_key=_reader("text:H", "enter"),
        surface=terminal,
    )

    final_frame = "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]
    assert result.message == "H"
    assert "".join(output).count("\x1b[?25l\x1b[0m\x1b[H") >= 2
    assert "H\x1b[s " in final_frame
    assert "\x1b[0m\x1b[J\x1b[u\x1b[0m\x1b[2 q\x1b[?25h" in final_frame
    assert "\x1b[48;5;255m\x1b[38;5;0m " not in final_frame


def test_composer_arrow_dims_when_window_loses_focus_and_brightens_on_return():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        read_key=_reader("focus_out", "focus_in", "escape"),
        surface=terminal,
    )

    frames = "".join(output).split("\x1b[H")
    assert "\x1b[38;5;255m› " in frames[1]
    assert "\x1b[38;5;245m› " in frames[2]
    assert "\x1b[38;5;255m› " in frames[3]


def test_long_conversation_line_wraps_without_losing_text_after_resize(monkeypatch):
    width = [70]
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: width[0])
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 30)
    message = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)
    terminal.set_activity(["Eden", "  " + message], title=None)
    keys = iter(("resize", "escape"))

    def read_key() -> str:
        key = next(keys)
        if key == "resize":
            width[0] = 30
        return key

    read_chat_bar(
        RUNNING_BUTTONS,
        context="Test thread",
        read_key=read_key,
        surface=terminal,
    )

    final_frame = "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]
    expected = terminal_navigation_module._wrap_activity_line("  " + message, 28)
    assert len(expected) > 3
    assert all(part in final_frame for part in expected)
    assert "".join(part[2:] for part in expected) == message


def test_conversation_wrap_moves_whole_words_to_the_next_line():
    wrapped = terminal_navigation_module._wrap_activity_line(
        "  hello beautiful world", 12
    )

    assert wrapped == ["  hello ", "  beautiful ", "  world"]
    assert "".join(part[2:] for part in wrapped) == "hello beautiful world"


def test_word_longer_than_the_window_still_wraps_without_losing_letters():
    word = "supercalifragilisticexpialidocious"
    wrapped = terminal_navigation_module._wrap_activity_line("  " + word, 12)

    assert all(len(part) <= 12 for part in wrapped)
    assert "".join(part[2:] for part in wrapped) == word


def test_windows_key_reader_notices_resize_without_waiting_for_a_key(monkeypatch):
    sizes = iter((os.terminal_size((80, 30)), os.terminal_size((40, 30))))
    monkeypatch.setattr(
        terminal_navigation_module.shutil,
        "get_terminal_size",
        lambda _fallback: next(sizes),
    )
    monkeypatch.setattr(terminal_navigation_module.sys, "platform", "win32")
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(kbhit=lambda: False),
    )

    assert terminal_navigation_module._read_windows_key() == "resize"


def test_windows_key_reader_decodes_mouse_wheel_without_calling_it_an_arrow(monkeypatch):
    characters = list("\x1b[<64;20;8M")
    monkeypatch.setattr(terminal_navigation_module.sys, "platform", "win32")
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(
            kbhit=lambda: bool(characters),
            getwch=lambda: characters.pop(0),
        ),
    )
    assert terminal_navigation_module._read_windows_key() == "wheel_up"
    assert terminal_navigation_module._decode_csi("<65;20;8M") == "wheel_down"
    assert terminal_navigation_module._decode_csi("A") == "up"
    assert terminal_navigation_module._decode_csi("<0;20;8M") == "mouse"


@pytest.mark.parametrize(
    ("characters", "expected"),
    [("\x08", "backspace"), ("\x7f", "backspace"),
     ("\xe0S", "delete"), ("\x1b[3~", "delete")],
)
def test_windows_key_reader_recognizes_backspace_and_delete(monkeypatch, characters, expected):
    remaining = list(characters)
    monkeypatch.setattr(terminal_navigation_module.sys, "platform", "win32")
    monkeypatch.setitem(
        sys.modules,
        "msvcrt",
        SimpleNamespace(kbhit=lambda: bool(remaining), getwch=lambda: remaining.pop(0)),
    )

    assert terminal_navigation_module._read_windows_key() == expected


def test_wheel_scrolls_only_transcript_and_keeps_header_buttons_composer_fixed(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 62)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 22)
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)
    terminal.set_activity(
        [f"Message {index}" for index in range(40)],
        title=None,
        identity="CHT-TEST",
        redraw=False,
    )

    read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        header_title="CHT-TEST",
        read_key=_reader("wheel_up", "wheel_up", "wheel_down", "escape"),
        surface=terminal,
    )

    frames = [
        frame for frame in "".join(output).split("\x1b[H")
        if "CHT-TEST" in frame and "Ask Eden anything" in frame
    ]
    assert len(frames) >= 3
    assert "Message 39" in frames[0]
    assert "Message 39" not in frames[-1]
    for frame, last_row in zip(frames, (39, 37, 35, 37), strict=True):
        assert f"Message {last_row}" in frame
        assert f"Message {last_row + 1}" not in frame
    for label in ("CHT-TEST", "[Conversations]", "Ask Eden anything"):
        positions = [
            next(index for index, line in enumerate(frame.splitlines()) if label in line)
            for frame in frames
        ]
        assert len(set(positions)) == 1

    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        read_key=_reader("down", "wheel_down", "enter"),
        write=lambda _: None,
    )
    assert result.action == "conversations"


def test_page_up_reveals_earlier_wrapped_reply_rows(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 30)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 18)
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)
    terminal.set_activity(["Eden", "  " + "A" * 200], title=None)

    read_chat_bar(
        RUNNING_BUTTONS,
        context="Test thread",
        read_key=_reader("page_up", "escape"),
        surface=terminal,
    )

    frames = "".join(output).split("\x1b[H")
    assert "\n Eden" not in frames[-2]
    assert "\n Eden" in frames[-1]


def test_thread_feed_keeps_more_than_two_hundred_rows_available_for_scrollback(
    monkeypatch,
):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 50)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 20)
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)
    terminal.set_activity([f"Message row {index}" for index in range(250)], title=None)

    read_chat_bar(
        RUNNING_BUTTONS,
        context="Test thread",
        read_key=_reader("escape"),
        surface=terminal,
    )
    terminal.scroll_activity(1000)

    first_page = "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]
    assert "Message row 0" in first_page


def test_fullscreen_chat_boxes_status_but_not_the_dark_composer():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    result = read_chat_bar(
        RUNNING_BUTTONS,
        context="New temporary chat",
        content="Core: running",
        read_key=_reader("text:H", "text:i", "enter"),
        surface=terminal,
    )

    rendered = "".join(output)
    final_frame = rendered.rsplit("\x1b[H", maxsplit=1)[-1]
    assert result.message == "Hi"
    assert "SYS EDEN" in final_frame
    assert final_frame.count("╭") == 1
    assert "\x1b[48;5;236m" in final_frame
    assert "\x1b[38;5;255m› \x1b[38;5;255mHi" in final_frame
    assert "Ask Eden anything" not in final_frame
    assert "Enter to send" not in final_frame
    assert "Esc back" not in final_frame
    assert final_frame.index("[Conversations]") > final_frame.index("\x1b[48;5;236m")
    assert final_frame.index("\x1b[48;5;236m") < final_frame.index("/help for commands")


def test_home_header_centers_its_open_box_against_the_tree(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 100)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 30)
    tree = terminal_navigation_module._HOME_TREE
    rows = terminal_navigation_module._render_home_tree_panel(
        "Core: running\n\nMonitoring\n  None", 100, max_lines=18
    )

    assert rows is not None
    assert len(rows) == len(tree) == 18
    assert sum("╭ SYS EDEN" in row for row in rows) == 1
    assert sum("╰" in row for row in rows) == 1
    top = next(index for index, row in enumerate(rows) if "╭ SYS EDEN" in row)
    bottom = next(index for index, row in enumerate(rows) if "╰" in row)
    assert top == 3
    assert bottom == 14
    for row in (rows[top], rows[bottom]):
        rule_end = max(row.rfind("─"), row.rfind("EDEN"))
        assert row[rule_end + 1 :].startswith("  ")
    assert any("Core: running" in row for row in rows)
    assert terminal_navigation_module._render_home_tree_panel(
        "Core: running", 60, max_lines=18
    ) is None
    assert terminal_navigation_module._render_home_tree_panel(
        "Core: running", 100, max_lines=14
    ) is None

    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)
    read_chat_bar(
        RUNNING_BUTTONS,
        context="",
        content="Core: running\n\nMonitoring\n  None",
        read_key=_reader("escape"),
        surface=terminal,
    )
    frame = "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]
    assert "╭ SYS EDEN" in frame
    assert "@%+***@@@@" in frame
    assert "Ask Eden anything" in frame


def test_popup_warning_wraps_and_pages_without_losing_text(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 42)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 14)
    warning = (
        "Delete this conversation? " +
        "You can restore it until the Eden terminal closes. " * 12 +
        "After that, it is deleted for good."
    )
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    select_button(
        (TerminalButton("Cancel", "cancel"), TerminalButton("Delete", "delete")),
        content=warning,
        read_key=_reader("page_down", "page_down", "page_down", "escape"),
        surface=terminal,
    )

    frames = "".join(output).split("\x1b[H")
    assert any("Delete this conversation?" in frame for frame in frames)
    assert any("After that, it is deleted for good." in frame for frame in frames)
    assert all(
        len(terminal_navigation_module._ANSI_ESCAPE.sub("", line)) <= 42
        for frame in frames for line in frame.splitlines()
        if line and not line.startswith("\x1b[")
    )


def test_scrollable_popup_wraps_before_paging(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 36)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 14)
    content = "Safety notice " + "explanation " * 35 + "FINAL-WARNING-END"
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    show_escape_view(
        content,
        read_key=_reader("page_down", "page_down", "page_down", "escape"),
        surface=terminal,
    )

    frames = "".join(output).split("\x1b[H")
    assert any("Safety notice" in frame for frame in frames)
    assert any("FINAL-WARNING-END" in frame for frame in frames)


def test_long_list_labels_reflow_without_hiding_selected_item(monkeypatch):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: 36)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: 14)
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)
    items = tuple(
        TerminalListItem(
            label=f"CHT-{index} A conversation with a descriptive title",
            description="saved conversation",
            action=f"CHT-{index}",
        )
        for index in range(6)
    )

    selected = select_list(
        items,
        title="Conversations",
        read_key=_reader("down", "down", "down", "down", "down", "enter"),
        surface=terminal,
    )

    assert selected == "CHT-5"
    assert "CHT-5" in "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]


def test_empty_composer_shows_placeholder_with_help_below():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    read_chat_bar(
        RUNNING_BUTTONS,
        context="New temporary chat",
        content="Core: running",
        read_key=_reader("escape"),
        surface=terminal,
    )

    rendered = "".join(output)
    final_frame = rendered.rsplit("\x1b[H", maxsplit=1)[-1]
    lines = final_frame.splitlines()
    button_line = next(index for index, line in enumerate(lines) if "[Conversations]" in line)
    composer_lines = [index for index, line in enumerate(lines) if "\x1b[48;5;236m" in line]
    assert composer_lines == [button_line - 3, button_line - 2, button_line - 1]
    assert "/help for commands" in lines[button_line + 1]
    assert "Ask Eden anything" not in lines[composer_lines[0]]
    assert "Ask Eden anything" in lines[composer_lines[1]]
    assert "Ask Eden anything" not in lines[composer_lines[2]]
    assert "\x1b[s " in rendered
    assert "Ask Eden anything" in rendered
    assert "/help for commands" in rendered
    assert "Enter to send" not in rendered
    assert "Ctrl+C stop" not in rendered


def test_activity_panel_only_appears_after_output_is_available():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)

    terminal.update("{{EDEN_ACTIVITY_TOP}}\n{{EDEN_ACTIVITY}}\n{{EDEN_ACTIVITY_BOTTOM}}")
    empty_frame = "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]
    assert "Activity" not in empty_frame
    assert "╭" not in empty_frame

    terminal.print_above("Eden is working...")
    active_frame = "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]
    assert "╭ Activity " in active_frame
    assert "│ Eden is working..." in active_frame
    assert "╰" in active_frame


def test_thread_feed_outlines_user_messages_only_and_keeps_one_header_id():
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)
    terminal.set_activity(["You", "  Hello", "", "Eden", "  Hi"], title=None)

    read_chat_bar(
        (
            TerminalButton("Home", "home"),
            TerminalButton("Monitoring", "monitoring"),
        ),
        context="",
        content="",
        header_title="TMP-THREAD",
        read_key=_reader("escape"),
        surface=terminal,
    )

    final_frame = "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]
    assert final_frame.count("TMP-THREAD") == 1
    assert "Activity" not in final_frame
    assert "You" in final_frame
    assert "Eden" in final_frame
    assert "\x1b[38;5;245m╭" in final_frame
    assert "\x1b[38;5;245m╰" in final_frame


def test_user_message_outline_reflows_with_wrapped_text_without_touching_eden():
    message = "Please keep these words together when the window gets narrower."
    lines = ["You", "  " + message, "", "Eden", "  I will."]

    rows = terminal_navigation_module._thread_activity_rows(lines, 28)
    user_body = [row.text for row in rows if row.kind == "user_body"]
    eden_rows = [row for row in rows if row.text == "Eden"]

    assert "".join(user_body) == message
    assert len(user_body) > 1
    assert len(eden_rows) == 1 and eden_rows[0].kind == "plain"
    assert [row.kind for row in rows].count("user_top") == 1
    assert [row.kind for row in rows].count("user_bottom") == 1
    assert all(
        len(terminal_navigation_module._ANSI_ESCAPE.sub(
            "", terminal_navigation_module._render_thread_activity_row(row, 28)
        )) <= 28
        for row in rows
    )


def test_scrollable_view_uses_escape_as_back():
    output: list[str] = []

    show_escape_view(
        "Conversations\n\nCHT-1  Example",
        read_key=_reader("escape"),
        write=output.append,
    )

    assert any("[Esc] Back" in item for item in output)


class FakeLifecycleClient:
    def __init__(self) -> None:
        self.state = CoreLifecycleState.RUNNING
        self.stop_calls = 0

    async def status(self) -> CoreRuntimeStatus:
        return CoreRuntimeStatus(state=self.state)

    async def stop_core(self) -> CoreRuntimeStatus:
        self.stop_calls += 1
        self.state = CoreLifecycleState.STOPPED
        return CoreRuntimeStatus(state=self.state)


class FakeConversationClient:
    def __init__(self) -> None:
        self.conversation_id = "TMP-THREAD"
        self.title = "Hello Eden"
        self.messages: list[dict[str, str]] = []
        self.last_send_params: dict[str, object] | None = None
        self.warnings: list[dict[str, str]] = []

    def call(self, method: str, **params):
        if method == "conversation.create_temporary":
            self.title = str(params["title"])
            return {"conversation": {"id": self.conversation_id, "title": self.title}}
        if method == "conversation.send":
            self.last_send_params = params
            self.messages.extend(
                [
                    {"role": "user", "content": str(params["message"])},
                    {"role": "eden", "content": "Hello. How can I help?"},
                ]
            )
            return {"response": "Hello. How can I help?", "summary_warning": None}
        if method == "conversation.get":
            return {
                "conversation": {"id": self.conversation_id, "title": self.title},
                "messages": self.messages,
            }
        if method == "conversation.client_temporary":
            return [
                {
                    "conversation": {
                        "id": self.conversation_id,
                        "title": self.title,
                        "transcript_state": "full",
                    },
                    "working": False,
                }
            ]
        if method == "conversation.list":
            return [
                {
                    "id": "CHT-SAVED",
                    "title": "Saved chat",
                    "transcript_state": "full",
                }
            ]
        if method == "conversation.restorable":
            return []
        if method == "task.list":
            return []
        if method == "conversation.work_status":
            return {
                "detail": "Generating a response with the fake local model."
            }
        if method == "conversation.warnings":
            return self.warnings
        raise AssertionError(f"Unexpected fake RPC method: {method}")


def test_non_stoppable_warning_appears_once_in_chat_without_prompting(tmp_path):
    client = FakeConversationClient()
    client.warnings = [{
        "id": "EVT-WARN", "message": "WARNING: Provider wait; stop at next safe boundary."
    }]
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"

    first = cli._thread_feed_lines(client.conversation_id)
    second = cli._thread_feed_lines(client.conversation_id)

    assert "WARNING: Provider wait; stop at next safe boundary." in "\n".join(first)
    assert "\n".join(second).count("WARNING: Provider wait") == 1


def test_non_stoppable_chat_warning_heading_is_bold():
    rows = terminal_navigation_module._thread_activity_rows(
        ["System", "  WARNING: Upcoming non-stoppable step: generated wait"], 80
    )
    rendered = terminal_navigation_module._render_thread_activity_row(rows[-1], 80)
    assert rendered.startswith("\x1b[1m\x1b[93m")


def test_interactive_report_close_works_from_home_and_shows_retention(
    tmp_path, monkeypatch
):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    calls: list[tuple[str, dict[str, object]]] = []
    shown: list[str] = []

    def call(method: str, **params: object):
        calls.append((method, params))
        return {"retention_candidates": [
            {"conversation_id": "CHT-TEST", "eligible": False,
             "reason": "Unique evidence still needs review."}
        ]}

    client.call = call  # type: ignore[method-assign]
    monkeypatch.setattr(
        interactive_cli_module, "show_escape_view",
        lambda content, **_kwargs: shown.append(content),
    )
    try:
        assert cli._handle(
            "/report close rpt-test failed | Generated summary | Generated outcome",
            core_running=True,
        )
        assert calls == [(
            "report.close",
            {"report_id": "rpt-test", "status": "failed",
             "summary": "Generated summary", "outcome": "Generated outcome"},
        )]
        assert "Protected: CHT-TEST" in shown[0]
    finally:
        cli._workers.shutdown(wait=True)


def test_interactive_core_stop_keeps_the_cli_running_for_the_stopped_menu(
    tmp_path, monkeypatch
):
    client = FakeLifecycleClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    monkeypatch.setattr(
        interactive_cli_module, "select_button", lambda *_args, **_kwargs: "stop-core"
    )

    keep_running = cli._handle("/corestop", core_running=True)

    assert keep_running
    assert client.state is CoreLifecycleState.STOPPED
    assert client.stop_calls == 1
    cli._workers.shutdown(wait=True)


def test_core_stop_confirmation_defaults_to_cancel_and_preserves_chat(
    tmp_path, monkeypatch
):
    client = FakeLifecycleClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.current_conversation_id = "CHT-SAVED"
    shown: list[str] = []

    def cancel(buttons, **kwargs):
        assert [button.action for button in buttons] == ["cancel", "stop-core"]
        shown.append(kwargs["content"])

    monkeypatch.setattr(interactive_cli_module, "select_button", cancel)
    monkeypatch.setattr(cli, "_refresh_visible_feed", lambda: None)

    assert cli._handle("/corestop", core_running=True)
    assert client.state is CoreLifecycleState.RUNNING
    assert client.stop_calls == 0
    assert cli.current_conversation_id == "CHT-SAVED"
    assert not cli._show_stopped_once
    assert "Unsaved temporary chats" in shown[0]
    assert "CLI will stay open" in shown[0]
    cli._workers.shutdown(wait=True)


def test_core_stop_connection_race_still_opens_stopped_home(tmp_path, monkeypatch):
    class ClosingLifecycleClient(FakeLifecycleClient):
        async def stop_core(self) -> CoreRuntimeStatus:
            self.state = CoreLifecycleState.STOPPED
            raise ConnectionError("Core closed its endpoint before replying")

    client = ClosingLifecycleClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    shown: list[str] = []
    monkeypatch.setattr(cli, "_command_suggestions", lambda: ())
    monkeypatch.setattr(
        interactive_cli_module,
        "read_chat_bar",
        lambda *_args, **_kwargs: ChatBarResult(message="/corestop"),
    )

    def choose(buttons, **kwargs):
        shown.append(kwargs["content"])
        if len(shown) == 1:
            return "stop-core"
        return "more" if len(shown) == 2 else "exit"

    monkeypatch.setattr(interactive_cli_module, "select_button", choose)

    cli._run_screen()

    assert client.state is CoreLifecycleState.STOPPED
    assert "Eden Core: stopped" in shown[1]
    assert "Core stopped. The Eden client is still open." in shown[1]
    cli._workers.shutdown(wait=True)


def test_failed_core_stop_keeps_client_open_on_running_screen(tmp_path, monkeypatch):
    class FailedLifecycleClient(FakeLifecycleClient):
        async def stop_core(self) -> CoreRuntimeStatus:
            raise ConnectionError("temporary RPC failure")

    client = FailedLifecycleClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    monkeypatch.setattr(cli, "_refresh_visible_feed", lambda: None)
    monkeypatch.setattr(
        interactive_cli_module, "select_button", lambda *_args, **_kwargs: "stop-core"
    )

    assert cli._handle("/corestop", core_running=True)
    assert client.state is CoreLifecycleState.RUNNING
    assert not cli._show_stopped_once
    assert "not confirmed" in cli._home_notices[-1]
    cli._workers.shutdown(wait=True)


def test_first_home_message_opens_a_thread_and_home_tracks_its_completion(tmp_path):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"

    cli._send_message("Hello Eden")
    conversation_id = cli.current_conversation_id
    assert conversation_id == "TMP-THREAD"
    cli._work[conversation_id].result(timeout=1)

    thread = cli._thread_feed_lines(conversation_id)
    assert thread == ["You", "  Hello Eden", "", "Eden", "  Hello. How can I help?"]
    assert all(conversation_id not in line for line in thread)
    activity = cli._conversation_activity()
    assert activity[0].id == conversation_id
    assert activity[0].activity == "complete"

    cli.current_conversation_id = None
    assert cli._handle(f"/resume {conversation_id.lower()}", core_running=True)
    assert cli.current_conversation_id == conversation_id
    cli._workers.shutdown(wait=True)


def test_inspect_command_runs_a_diagnosis_inside_the_current_thread(tmp_path):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"

    assert cli._handle("/inspect gpu", core_running=True)
    conversation_id = cli.current_conversation_id
    assert conversation_id == "TMP-THREAD"
    cli._work[conversation_id].result(timeout=1)

    assert client.last_send_params is not None
    assert client.last_send_params["message"] == "/inspect gpu"
    assert client.last_send_params["diagnostic_component"] == "gpu"
    cli._workers.shutdown(wait=True)


def test_interactive_compact_only_requests_context_summary(tmp_path):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.current_conversation_id = "TMP-THREAD"
    called: list[str] = []
    original_call = client.call

    def call(method: str, **_params):
        called.append(method)
        if method == "conversation.summarize":
            return {"summary": "Generated test summary", "through_sequence": 2}
        return original_call(method, **_params)

    client.call = call  # type: ignore[method-assign]

    assert cli._handle("/compact", core_running=True)
    assert called[0] == "conversation.summarize"
    assert "conversation.compact" not in called
    cli._workers.shutdown(wait=True)


def test_report_link_from_temporary_chat_requires_explicit_save_choice(
    tmp_path, monkeypatch
):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.current_conversation_id = "TMP-THREAD"
    called: list[str] = []

    def call(method: str, **_params):
        called.append(method)
        if method == "report.show":
            return {"report": {"id": "RPT-TEST"}}
        raise AssertionError(f"Unexpected fake RPC method: {method}")

    client.call = call  # type: ignore[method-assign]
    monkeypatch.setattr(interactive_cli_module, "select_button", lambda *_args, **_kwargs: "cancel")
    monkeypatch.setattr(cli, "_refresh_visible_feed", lambda: None)

    assert cli._handle("/report RPT-TEST", core_running=True)
    assert called == ["report.show"]
    assert cli.current_conversation_id == "TMP-THREAD"
    cli._workers.shutdown(wait=True)


def test_first_message_uses_local_pending_state_while_core_thread_load_is_in_flight(
    tmp_path,
):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"
    cli.current_conversation_id = "TMP-THREAD"
    cli._pending_messages["TMP-THREAD"] = "First prompt"
    waiting: Future[object] = Future()
    cli._work["TMP-THREAD"] = waiting

    original_call = client.call

    def fail_get(method: str, **params):
        if method == "conversation.get":
            raise ConnectionError("generated transient test failure")
        return original_call(method, **params)

    client.call = fail_get  # type: ignore[method-assign]

    feed = cli._thread_feed_lines("TMP-THREAD")
    assert feed[:4] == ["You", "  First prompt", "", "Eden"]
    assert "Generating a response with the fake local model." in feed[4]
    waiting.cancel()
    cli._workers.shutdown(wait=True)


def test_conversations_view_includes_this_clients_temporary_chats(tmp_path, monkeypatch):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"
    shown: list[TerminalListItem] = []
    monkeypatch.setattr(
        interactive_cli_module,
        "select_list",
        lambda items, **_kwargs: shown.extend(items),
    )

    cli._show_saved_conversations()

    assert {item.action for item in shown} == {"TMP-THREAD", "CHT-SAVED"}
    cli._workers.shutdown(wait=True)


def test_opening_saved_chat_adds_it_to_this_terminals_activity(tmp_path, monkeypatch):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"
    monkeypatch.setattr(
        interactive_cli_module, "select_list", lambda *_args, **_kwargs: "CHT-SAVED"
    )

    cli._show_saved_conversations()

    assert cli.current_conversation_id == "CHT-SAVED"
    assert [item.id for item in cli._conversation_activity()] == ["CHT-SAVED"]
    cli._workers.shutdown(wait=True)


def test_id_suggestions_and_conversation_browser_are_newest_first(tmp_path, monkeypatch):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"
    shown: list[TerminalListItem] = []

    def call(method: str, **_params):
        if method == "conversation.list":
            return [
                {"id": "CHT-OLD", "title": "Old", "transcript_state": "full",
                 "updated_at": "2026-01-01T00:00:00Z"},
                {"id": "CHT-DELETED", "title": "Gone", "transcript_state": "deleted",
                 "updated_at": "2026-12-01T00:00:00Z"},
                {"id": "CHT-NEW", "title": "New", "transcript_state": "full",
                 "updated_at": "2026-02-01T00:00:00Z"},
            ]
        if method == "conversation.client_temporary":
            return []
        if method == "conversation.restorable":
            return [
                {"id": "CHT-OLD", "title": "Old"},
                {"id": "CHT-NEW", "title": "New"},
            ]
        if method == "task.list":
            return [
                {"id": "TSK-OLD", "title": "Old watch", "state": "monitoring",
                 "updated_at": "2026-01-01T00:00:00Z"},
                {"id": "TSK-NEW", "title": "New watch", "state": "monitoring",
                 "updated_at": "2026-02-01T00:00:00Z"},
            ]
        raise AssertionError(method)

    client.call = call  # type: ignore[method-assign]
    monkeypatch.setattr(
        interactive_cli_module, "select_list",
        lambda items, **_kwargs: shown.extend(items),
    )
    cli._show_saved_conversations()
    suggestions = cli._command_suggestions()

    assert [item.action for item in shown] == ["CHT-NEW", "CHT-OLD"]
    assert [item.completion for item in suggestions if item.completion.startswith("/resume CHT-")] == [
        "/resume CHT-NEW", "/resume CHT-OLD"
    ]
    assert [item.completion for item in suggestions if item.completion.startswith("/restore CHT-")] == [
        "/restore CHT-NEW", "/restore CHT-OLD"
    ]
    assert [item.completion for item in suggestions if item.completion.startswith("/monitoring TSK-")] == [
        "/monitoring TSK-NEW", "/monitoring TSK-OLD"
    ]
    cli._workers.shutdown(wait=True)


def test_monitoring_id_suggestion_opens_its_conversation(tmp_path):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"

    def call(method: str, **_params):
        if method == "task.list":
            return [{"id": "TSK-NEW", "title": "Watch", "state": "monitoring"}]
        if method == "task.get":
            return {"task": {"state": "monitoring"},
                    "conversations": [{"conversation_id": "CHT-SAVED"}]}
        raise AssertionError(method)

    client.call = call  # type: ignore[method-assign]
    assert cli._handle("/monitoring TSK-NEW", core_running=True)
    assert cli.current_conversation_id == "CHT-SAVED"
    assert cli._activity_history == ["CHT-SAVED"]
    cli._workers.shutdown(wait=True)


def test_tasks_view_includes_diagnostic_work_while_monitoring_stays_filtered(
    tmp_path, monkeypatch
):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    shown: list[list[str]] = []

    def call(method: str, **_params):
        if method == "task.list":
            return [
                {"id": "TSK-DIAG", "title": "Investigate GPU", "state": "completed",
                 "updated_at": "2026-01-02"},
                {"id": "TSK-WATCH", "title": "Watch", "state": "monitoring",
                 "updated_at": "2026-01-01"},
            ]
        if method == "task.get":
            return {"conversations": [{"conversation_id": "CHT-DIAG"}]}
        raise AssertionError(method)

    def choose(items, **_kwargs):
        shown.append([item.action for item in items])

    client.call = call  # type: ignore[method-assign]
    monkeypatch.setattr(interactive_cli_module, "select_list", choose)
    try:
        assert cli._handle("/tasks", core_running=True)
        assert cli._handle("/monitoring", core_running=True)
        assert shown == [["TSK-DIAG", "TSK-WATCH"], ["TSK-WATCH"]]
    finally:
        cli._workers.shutdown(wait=True)


def test_thread_work_detail_uses_live_task_progress(tmp_path):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))

    def call(method: str, **_params):
        assert method == "conversation.work_status"
        return {
            "detail": "Collecting read-only GPU evidence.",
            "elapsed_seconds": 4.25,
            "task": {"progress": {"completed_major_steps": ["Preparing investigation"],
                                  "eta_status": "unavailable"}},
        }

    client.call = call  # type: ignore[method-assign]
    try:
        detail = cli._work_detail("CHT-TEST", detailed=True)
        assert "Elapsed 4s" in detail
        assert "Completed: Preparing investigation" in detail
        assert "ETA unavailable" in detail
    finally:
        cli._workers.shutdown(wait=True)


def test_delete_requires_confirmation_and_restore_reopens_chat(tmp_path, monkeypatch):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"
    cli.current_conversation_id = "CHT-SAVED"
    cli._record_activity("CHT-SAVED")
    warning: list[str] = []
    calls: list[str] = []
    choice = "cancel"

    def choose(_buttons, **kwargs):
        warning.append(kwargs["content"])
        return choice

    def call(method: str, **_params):
        calls.append(method)
        if method == "conversation.delete_staged":
            return {"id": "CHT-SAVED", "title": "Saved chat"}
        if method == "conversation.restorable":
            return [{"id": "CHT-SAVED", "title": "Saved chat"}]
        if method == "conversation.restore":
            return {"conversation": {"id": "CHT-SAVED"}, "messages": []}
        return FakeConversationClient.call(client, method, **_params)

    client.call = call  # type: ignore[method-assign]
    monkeypatch.setattr(interactive_cli_module, "select_button", choose)
    monkeypatch.setattr(
        interactive_cli_module, "select_list", lambda *_args, **_kwargs: "CHT-SAVED"
    )
    monkeypatch.setattr(cli, "_refresh_visible_feed", lambda: None)

    assert cli._handle("/delete", core_running=True)
    assert "conversation.delete_staged" not in calls
    assert cli.current_conversation_id == "CHT-SAVED"
    assert "until this Eden CLI session closes" in warning[-1]
    choice = "delete"
    assert cli._handle("/delete", core_running=True)
    assert cli.current_conversation_id is None
    assert cli._activity_history == ["CHT-SAVED"]
    assert cli._conversation_activity()[0].activity == "deleted"
    cli._show_home_activity(redraw=False)
    assert "Deleted" in cli._terminal._activity[0]
    assert cli._handle("/restore", core_running=True)
    assert cli.current_conversation_id == "CHT-SAVED"
    assert cli._activity_history == ["CHT-SAVED"]
    assert cli._conversation_activity()[0].activity == "complete"
    cli._workers.shutdown(wait=True)


def test_delete_explains_outdated_core_without_claiming_deletion(tmp_path, monkeypatch):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"
    cli.current_conversation_id = "CHT-SAVED"

    def call(method: str, **_params):
        if method == "conversation.delete_staged":
            raise CoreRpcError(
                RpcError(
                    code="request.invalid",
                    message="Unknown Core method: conversation.delete_staged",
                )
            )
        raise AssertionError(method)

    client.call = call  # type: ignore[method-assign]
    monkeypatch.setattr(interactive_cli_module, "select_button", lambda *_args, **_kwargs: "delete")
    monkeypatch.setattr(cli, "_refresh_visible_feed", lambda: None)

    assert cli._handle("/delete", core_running=True)
    assert cli.current_conversation_id == "CHT-SAVED"
    assert cli._deleted_activity == {}
    assert "Nothing was deleted" in cli._conversation_notices["CHT-SAVED"][-1].text
    assert "/corestop and /corestart" in cli._conversation_notices["CHT-SAVED"][-1].text
    cli._workers.shutdown(wait=True)


def test_discard_is_the_initial_exit_choice_for_temporary_chats(tmp_path, monkeypatch):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"
    selected_order: list[str] = []

    def call(method: str, **_params):
        if method == "client.assess_close":
            return {
                "active_temporary_ids": [],
                "meaningful_temporary_ids": ["TMP-THREAD"],
            }
        raise AssertionError(f"Unexpected fake RPC method: {method}")

    def choose(buttons, **_kwargs):
        selected_order.extend(button.action for button in buttons)
        return "cancel"

    client.call = call  # type: ignore[method-assign]
    monkeypatch.setattr(interactive_cli_module, "select_button", choose)

    assert not cli._exit()
    assert selected_order == ["discard", "save", "cancel"]
    cli._workers.shutdown(wait=True)


def test_cli_presentation_switch_command_is_removed():
    result = CliRunner().invoke(app, ["settings", "presentation", "simple"])

    assert result.exit_code == 2


@pytest.mark.parametrize("width, height", [(24, 14), (62, 22), (100, 30)])
@pytest.mark.parametrize("message_count", [3, 100])
def test_thread_fills_rows_between_gray_header_and_composer(
    monkeypatch, width, height, message_count,
):
    monkeypatch.setattr(terminal_navigation_module, "_terminal_width", lambda: width)
    monkeypatch.setattr(terminal_navigation_module, "_terminal_height", lambda: height)
    output: list[str] = []
    terminal = LiveTerminal(output.append, fullscreen=True)
    terminal.set_activity(
        [f"Transcript row {index}" for index in range(message_count)],
        title=None, identity="CHT-LAYOUT", redraw=False,
    )
    read_chat_bar(
        RUNNING_BUTTONS, context="", content="SAVED — Full", header_title="CHT-LAYOUT",
        read_key=_reader("escape"), surface=terminal,
    )
    frame = "".join(output).rsplit("\x1b[H", maxsplit=1)[-1]
    rows = frame.splitlines()
    assert len(rows) == height
    assert all("\x1b[40m\x1b[38;5;242m" in row for row in rows[:3])
    assert all("\x1b[48;" not in row for row in rows[:3])
    assert "CHT-LAYOUT" in rows[0] and "SAVED — Full" in rows[1]
    assert "╭" in rows[0] and "╮" in rows[0]
    assert "╰" in rows[2] and "╯" in rows[2]
    composer_top = next(i for i, row in enumerate(rows) if "\x1b[s" in row) - 1
    feed = rows[3:composer_top]
    if message_count < len(feed):
        assert "Transcript row 0" in feed[0]
        assert f"Transcript row {message_count - 1}" in feed[message_count - 1]
        assert all(not row.strip() for row in feed[message_count:])
    else:
        assert all("Transcript row " in row for row in feed)
        assert f"Transcript row {message_count - 1}" in feed[-1]
    assert "[Conversations]" in rows[-2]
    assert "\x1b[40m\x1b[38;5;242m" in rows[-2]
    assert "/help for commands" in rows[-1]


def test_up_at_first_composer_row_does_not_select_buttons_below():
    result = read_chat_bar(
        RUNNING_BUTTONS, context="", read_key=_reader("up", "text:Hello", "enter"),
        write=lambda _: None,
    )
    assert result.message == "Hello" and result.action is None


def test_save_and_pin_notices_stay_between_turns_after_promotion(tmp_path):
    client = FakeConversationClient()
    client.messages = [{"role": "user", "content": "First question"},
                       {"role": "eden", "content": "First answer"}]
    original_call = client.call

    def call(method: str, **params):
        if method == "conversation.persist":
            client.conversation_id = "CHT-SAVED"
            return {"conversation": {"id": client.conversation_id}}
        if method == "conversation.pin":
            return {"pinned": params["pinned"]}
        return original_call(method, **params)

    client.call = call  # type: ignore[method-assign]
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.client_id = "CLI-TEST"
    cli.current_conversation_id = "TMP-THREAD"
    try:
        cli._notice("Temporary thread notice.")
        cli._save_current()
        assert cli._handle("/pin", core_running=True)
        client.messages.extend([{"role": "user", "content": "Later question"},
                                {"role": "eden", "content": "Later answer"}])
        for _ in range(2):
            feed = "\n".join(cli._thread_feed_lines("CHT-SAVED"))
            assert feed.index("First answer") < feed.index("Temporary thread notice.")
            assert feed.index("Conversation saved") < feed.index("Later question")
            assert feed.index("Conversation pinned.") < feed.index("Later question")
            assert feed.count("Conversation saved") == 1
            assert feed.count("Conversation pinned.") == 1
            assert feed.endswith("  Later answer")
        assert "TMP-THREAD" not in cli._conversation_notices
        assert len(client.messages) == 4  # UI notices never enter stored/model messages.
    finally:
        cli._workers.shutdown(wait=True)


def test_notice_during_pending_turn_stays_before_the_later_answer(tmp_path):
    client = FakeConversationClient()
    cli = InteractiveCli(Settings(data_directory=tmp_path), cast(LocalCoreClient, client))
    cli.current_conversation_id = client.conversation_id
    pending: Future[object] = Future()
    cli._work[client.conversation_id] = pending
    cli._pending_messages[client.conversation_id] = "Queued question"
    try:
        cli._notice("Conversation state changed.")
        client.messages = [{"role": "user", "content": "Queued question"},
                           {"role": "eden", "content": "Completed answer"}]
        pending.set_result({})
        feed = "\n".join(cli._thread_feed_lines(client.conversation_id))
        assert feed.index("Queued question") < feed.index("Conversation state changed.")
        assert feed.index("Conversation state changed.") < feed.index("Completed answer")
        assert feed.count("Queued question") == 1
    finally:
        cli._workers.shutdown(wait=True)
