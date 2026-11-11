"""Dependency-free keyboard navigation and terminal-screen rendering."""

from __future__ import annotations

import re
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Literal

KeyReader = Callable[[], str]
TextWriter = Callable[[str], object]

_ACTIVITY_TOP_MARKER = "{{EDEN_ACTIVITY_TOP}}"
_ACTIVITY_MARKER = "{{EDEN_ACTIVITY}}"
_ACTIVITY_BOTTOM_MARKER = "{{EDEN_ACTIVITY_BOTTOM}}"
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_MUTED_CONTROLS = "\x1b[40m\x1b[38;5;242m"


def _load_home_tree() -> tuple[str, ...]:
    """Prefer the workspace artwork, with a packaged copy for installed Eden."""
    paths = (
        Path(__file__).resolve().parents[2] / "ascii-tree-small.txt",
        Path(__file__).with_name("ascii-tree-small.txt"),
    )
    for path in paths:
        try:
            lines = [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]
        except OSError:
            continue
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        if lines:
            return tuple(lines)
    return ()


_HOME_TREE = _load_home_tree()


@dataclass(frozen=True)
class TerminalButton:
    label: str
    action: str


@dataclass(frozen=True)
class TerminalCommand:
    label: str
    completion: str
    description: str


@dataclass(frozen=True)
class TerminalListItem:
    label: str
    action: str
    description: str = ""


@dataclass(frozen=True)
class ChatBarResult:
    message: str | None = None
    action: str | None = None
    canceled: bool = False
    cancel_key: str | None = None


@dataclass(frozen=True)
class _ActivityRow:
    text: str = ""
    kind: Literal["plain", "user_top", "user_body", "user_bottom"] = "plain"


class LiveTerminal:
    """Own and redraw the interactive client's alternate terminal screen."""

    def __init__(self, write: TextWriter | None = None, *, fullscreen: bool = False) -> None:
        if write is None:
            _enable_windows_virtual_terminal()
        self._write = write or _stdout_write
        self.fullscreen = fullscreen
        self._entered = False
        self._line_count = 0
        self._last_text = ""
        self._activity: list[str] = []
        self._activity_title: str | None = "Activity"
        self._activity_align: Literal["top", "bottom"] = "bottom"
        self._activity_identity: str | None = None
        self._activity_scroll_rows = 0
        self._original_input_mode: int | None = None
        self._lock = RLock()

    def enter(self) -> None:
        with self._lock:
            if self.fullscreen and not self._entered:
                self._original_input_mode = _enable_windows_virtual_terminal_input()
                self._write(
                    "\x1b[?1049h\x1b[?1004h\x1b[?1000h\x1b[?1006h\x1b[?25l"
                )
                self._entered = True

    def exit(self) -> None:
        with self._lock:
            if self.fullscreen and self._entered:
                self._write(
                    "\x1b[0 q\x1b[?25h\x1b[?1006l\x1b[?1000l"
                    "\x1b[?1004l\x1b[?1049l"
                )
                _restore_windows_input_mode(self._original_input_mode)
                self._original_input_mode = None
                self._entered = False
                self._last_text = ""
                self._line_count = 0

    def update(self, text: str) -> None:
        with self._lock:
            if self.fullscreen:
                self._last_text = text.rstrip("\n")
                self._render_fullscreen_unlocked()
                return
            self._clear_unlocked()
            normalized = text.rstrip("\n")
            self._write(normalized + "\n")
            self._last_text = normalized
            self._line_count = _display_line_count(normalized)

    def clear(self) -> None:
        with self._lock:
            if not self.fullscreen:
                self._clear_unlocked()

    def print_above(self, text: str) -> None:
        with self._lock:
            if self.fullscreen:
                if self._activity:
                    self._activity.append("")
                self._activity.extend(text.rstrip("\n").splitlines())
                self._render_fullscreen_unlocked()
                return
            previous = self._last_text
            self._clear_unlocked()
            self._write(text.rstrip("\n") + "\n")
            if previous:
                self._write(previous + "\n")
                self._last_text = previous
                self._line_count = _display_line_count(previous)

    def set_activity(
        self,
        lines: Sequence[str],
        *,
        title: str | None = "Activity",
        align: Literal["top", "bottom"] = "bottom",
        identity: str | None = None,
        redraw: bool = True,
    ) -> None:
        """Replace the current screen's central feed and redraw it in place."""
        with self._lock:
            if identity != self._activity_identity or align != self._activity_align:
                self._activity_scroll_rows = 0
            self._activity.clear()
            self._activity.extend(lines)
            self._activity_title = title
            self._activity_align = align
            self._activity_identity = identity
            if redraw and self.fullscreen and self._last_text:
                self._render_fullscreen_unlocked()

    def scroll_activity(self, rows: int, *, redraw: bool = True) -> None:
        """Move through wrapped transcript rows without changing retained content."""
        with self._lock:
            self._activity_scroll_rows = max(self._activity_scroll_rows + rows, 0)
            if redraw and self.fullscreen and self._last_text:
                self._render_fullscreen_unlocked()

    def _render_fullscreen_unlocked(self) -> None:
        if not self._entered:
            self.enter()
        width = _terminal_width()
        marker_count = self._last_text.count(_ACTIVITY_MARKER)
        if self._activity_title is None:
            values = _thread_activity_rows(self._activity, width)
        else:
            activity_width = max(width - 6, 1)
            values = [
                _ActivityRow(part)
                for value in self._activity
                for part in _wrap_activity_line(value, activity_width)
            ]
        if self._activity_align == "top":
            activity = values[:marker_count] if marker_count else []
        else:
            self._activity_scroll_rows = min(
                self._activity_scroll_rows, max(len(values) - marker_count, 0)
            )
            end = len(values) - self._activity_scroll_rows
            activity = values[max(end - marker_count, 0) : end] if marker_count else []
        padding = [_ActivityRow()] * (marker_count - len(activity))
        rows = (
            [*activity, *padding]
            if self._activity_align == "top" or self._activity_title is None
            else [*padding, *activity]
        )
        rendered = self._last_text
        if activity and self._activity_title is not None:
            rendered = rendered.replace(
                _ACTIVITY_TOP_MARKER,
                _panel_top(self._activity_title, width),
                1,
            )
            rendered = rendered.replace(
                _ACTIVITY_BOTTOM_MARKER,
                _panel_bottom(width),
                1,
            )
        else:
            rendered = rendered.replace(_ACTIVITY_TOP_MARKER, _screen_line("", width), 1)
            rendered = rendered.replace(_ACTIVITY_BOTTOM_MARKER, _screen_line("", width), 1)
        for row in rows:
            line = (
                _activity_panel_line(row.text, width)
                if activity and self._activity_title is not None
                else _render_thread_activity_row(row, width)
            )
            rendered = rendered.replace(_ACTIVITY_MARKER, line, 1)
        native_cursor = "\x1b[s" in rendered
        self._write(
            "\x1b[?25l\x1b[0m\x1b[H"
            + rendered
            + "\x1b[0m\x1b[J"
            + ("\x1b[u\x1b[0m\x1b[2 q\x1b[?25h" if native_cursor else "")
        )

    def _clear_unlocked(self) -> None:
        if self._line_count:
            self._write(f"\x1b[{self._line_count}F\x1b[J")
        self._line_count = 0
        self._last_text = ""


def select_button(
    buttons: Sequence[TerminalButton],
    *,
    read_key: KeyReader | None = None,
    write: TextWriter | None = None,
    content: str = "",
    surface: LiveTerminal | None = None,
) -> str | None:
    """Select one button with arrows and Enter."""
    if not buttons:
        raise ValueError("at least one terminal button is required")
    reader = read_key or _read_windows_key
    terminal = surface or LiveTerminal(write)
    selected = 0
    content_offset = 0
    while True:
        rendered = _render_buttons(buttons, selected, focused=True)
        if terminal.fullscreen:
            wrapped = _wrap_view_content(content, _terminal_width())
            visible_rows = max(_terminal_height() - 3, 1)
            content_offset = min(content_offset, max(len(wrapped) - visible_rows, 0))
            footer = (
                rendered + "  [PgUp/PgDn] Read"
                if len(wrapped) > visible_rows else rendered
            )
            terminal.update(_render_fullscreen_view(content, footer, offset=content_offset))
        else:
            terminal.update("\n".join(part for part in (content, rendered) if part))
        key = reader()
        if key in {"left", "up"}:
            selected = (selected - 1) % len(buttons)
        elif key in {"right", "down", "tab"}:
            selected = (selected + 1) % len(buttons)
        elif key == "page_down":
            content_offset += max(_terminal_height() - 3, 1)
        elif key == "page_up":
            content_offset = max(content_offset - max(_terminal_height() - 3, 1), 0)
        elif key == "wheel_down":
            content_offset += 3
        elif key == "wheel_up":
            content_offset = max(content_offset - 3, 0)
        elif key == "enter":
            terminal.clear()
            return buttons[selected].action
        elif key in {"escape", "ctrl_c"}:
            terminal.clear()
            return None


def select_list(
    items: Sequence[TerminalListItem],
    *,
    title: str,
    read_key: KeyReader | None = None,
    write: TextWriter | None = None,
    surface: LiveTerminal | None = None,
) -> str | None:
    """Select a vertically rendered item with arrows and Enter."""
    if not items:
        return None
    reader = read_key or _read_windows_key
    terminal = surface or LiveTerminal(write)
    selected = 0
    while True:
        row_budget = max(_terminal_height() - 5, 1)
        row_counts = [
            len(_wrap_view_content(f"  {item.label} — {item.description}", _terminal_width()))
            for item in items
        ]
        offset = selected
        used_rows = row_counts[selected]
        while offset > 0 and used_rows + row_counts[offset - 1] <= row_budget:
            offset -= 1
            used_rows += row_counts[offset]
        end = selected + 1
        while end < len(items) and used_rows + row_counts[end] <= row_budget:
            used_rows += row_counts[end]
            end += 1
        lines = [title, ""]
        for index, item in enumerate(items[offset:end], start=offset):
            marker = "›" if index == selected else " "
            suffix = f" — {item.description}" if item.description else ""
            lines.append(f"{marker} {item.label}{suffix}")
        footer = "[↑/↓] Select   [Enter] Open   [Esc] Back"
        rendered = "\n".join([*lines, "", footer])
        if terminal.fullscreen:
            rendered = _render_fullscreen_view("\n".join(lines), footer)
        terminal.update(rendered)
        key = reader()
        if key in {"up", "left"}:
            selected = (selected - 1) % len(items)
        elif key in {"down", "right", "tab"}:
            selected = (selected + 1) % len(items)
        elif key == "enter":
            terminal.clear()
            return items[selected].action
        elif key in {"escape", "ctrl_c"}:
            terminal.clear()
            return None


def read_chat_bar(
    buttons: Sequence[TerminalButton],
    *,
    context: str,
    read_key: KeyReader | None = None,
    write: TextWriter | None = None,
    content: str = "",
    surface: LiveTerminal | None = None,
    header_title: str = "SYS EDEN",
    command_suggestions: Sequence[TerminalCommand] = (),
) -> ChatBarResult:
    """Read chat text while keeping secondary navigation available."""
    if not buttons:
        raise ValueError("at least one terminal button is required")
    reader = read_key or _read_windows_key
    terminal = surface or LiveTerminal(write)
    selected = 0
    selected_suggestion = 0
    focus = "chat"
    window_focused = True
    buffer = ""
    cursor_index = 0
    preferred_column: int | None = None
    palette_open = True
    while True:
        suggestions = (
            _matching_command_suggestions(buffer, command_suggestions) if palette_open else []
        )
        selected_suggestion = min(selected_suggestion, max(len(suggestions) - 1, 0))
        if terminal.fullscreen:
            rendered = _render_fullscreen_chat(
                content,
                buttons,
                selected=selected,
                buttons_focused=focus == "buttons",
                context=context,
                buffer=buffer,
                cursor_index=cursor_index,
                header_title=header_title,
                command_suggestions=suggestions,
                selected_suggestion=selected_suggestion,
                window_focused=window_focused,
            )
        else:
            chat_bar = _render_chat_bar(
                buttons,
                selected=selected,
                buttons_focused=focus == "buttons",
                context=context,
                buffer=buffer,
            )
            rendered = "\n".join(part for part in (content, chat_bar) if part)
        terminal.update(rendered)
        key = reader()
        if key == "focus_in":
            window_focused = True
        elif key == "focus_out":
            window_focused = False
        elif key == "up" and suggestions:
            selected_suggestion = (selected_suggestion - 1) % len(suggestions)
        elif key == "down" and suggestions:
            selected_suggestion = (selected_suggestion + 1) % len(suggestions)
        elif key == "up":
            if focus == "buttons":
                focus = "chat"
            elif cursor_index >= _composer_text_width(_terminal_width()):
                width = _composer_text_width(_terminal_width())
                preferred_column = cursor_index % width if preferred_column is None else preferred_column
                cursor_index = min((cursor_index // width - 1) * width + preferred_column, len(buffer))
        elif key == "down":
            if focus == "chat":
                width = _composer_text_width(_terminal_width())
                target = (cursor_index // width + 1) * width
                if target <= len(buffer):
                    preferred_column = cursor_index % width if preferred_column is None else preferred_column
                    cursor_index = min(target + preferred_column, len(buffer))
                else:
                    focus = "buttons"
                    preferred_column = None
        elif key == "page_up":
            terminal.scroll_activity(max(_terminal_height() // 2, 1), redraw=False)
        elif key == "page_down":
            terminal.scroll_activity(-max(_terminal_height() // 2, 1), redraw=False)
        elif key == "wheel_up":
            terminal.scroll_activity(2, redraw=False)
        elif key == "wheel_down":
            terminal.scroll_activity(-2, redraw=False)
        elif key == "left" and focus == "buttons":
            selected = (selected - 1) % len(buttons)
        elif key == "left":
            cursor_index = max(cursor_index - 1, 0)
            preferred_column = None
        elif key in {"right", "tab"} and focus == "buttons":
            selected = (selected + 1) % len(buttons)
        elif key == "right":
            cursor_index = min(cursor_index + 1, len(buffer))
            preferred_column = None
        elif key == "tab" and suggestions:
            buffer = suggestions[selected_suggestion].completion
            cursor_index = len(buffer)
            preferred_column = None
            selected_suggestion = 0
            palette_open = buffer.endswith(" ")
        elif key == "backspace":
            if focus == "chat" and cursor_index:
                buffer = buffer[:cursor_index - 1] + buffer[cursor_index:]
                cursor_index -= 1
                preferred_column = None
                selected_suggestion = 0
                palette_open = True
        elif key == "delete":
            if focus == "chat" and cursor_index < len(buffer):
                buffer = buffer[:cursor_index] + buffer[cursor_index + 1:]
                preferred_column = None
                selected_suggestion = 0
                palette_open = True
        elif key == "escape":
            if suggestions:
                palette_open = False
            elif not buffer:
                terminal.clear()
                return ChatBarResult(canceled=True, cancel_key="escape")
        elif key == "ctrl_c":
            terminal.clear()
            return ChatBarResult(canceled=True, cancel_key="ctrl_c")
        elif key == "enter":
            if focus == "buttons":
                terminal.clear()
                return ChatBarResult(action=buttons[selected].action)
            if suggestions:
                completion = suggestions[selected_suggestion].completion
                if not completion.endswith(" "):
                    terminal.clear()
                    return ChatBarResult(message=completion)
                buffer = completion
                cursor_index = len(buffer)
                preferred_column = None
                selected_suggestion = 0
                palette_open = True
                continue
            if buffer.strip():
                terminal.clear()
                return ChatBarResult(message=buffer.strip())
        elif key.startswith("text:"):
            focus = "chat"
            value = key.removeprefix("text:")
            buffer = buffer[:cursor_index] + value + buffer[cursor_index:]
            cursor_index += len(value)
            preferred_column = None
            selected_suggestion = 0
            palette_open = True


def show_escape_view(
    content: str,
    *,
    read_key: KeyReader | None = None,
    write: TextWriter | None = None,
    surface: LiveTerminal | None = None,
) -> None:
    """Show a scrollable terminal view where Esc consistently means back."""
    reader = read_key or _read_windows_key
    terminal = surface or LiveTerminal(write)
    offset = 0
    while True:
        lines = _wrap_view_content(content, _terminal_width())
        height = max(_terminal_height() - 5, 5)
        offset = min(offset, max(len(lines) - height, 0))
        page = lines[offset : offset + height]
        footer = "[Esc] Back"
        if len(lines) > height:
            footer += "   [Up/Down] Scroll"
        rendered = "\n".join([*page, "", footer])
        if terminal.fullscreen:
            rendered = _render_fullscreen_view("\n".join(page), footer)
        terminal.update(rendered)
        key = reader()
        if key in {"escape", "ctrl_c", "enter"}:
            terminal.clear()
            return
        if key in {"down", "page_down", "wheel_down"}:
            step = height if key == "page_down" else 3 if key == "wheel_down" else 1
            offset = min(offset + step, len(lines) - 1)
        elif key in {"up", "page_up", "wheel_up"}:
            step = height if key == "page_up" else 3 if key == "wheel_up" else 1
            offset = max(offset - step, 0)


def _render_buttons(buttons: Sequence[TerminalButton], selected: int, *, focused: bool) -> str:
    rendered: list[str] = []
    for index, button in enumerate(buttons):
        label = f"[{button.label}]"
        if focused and index == selected:
            label = f">{label}<"
        rendered.append(label)
    return "  ".join(rendered)


def _render_chat_bar(
    buttons: Sequence[TerminalButton],
    *,
    selected: int,
    buttons_focused: bool,
    context: str,
    buffer: str,
) -> str:
    actions = _render_buttons(buttons, selected, focused=buttons_focused)
    return f"{actions}  |  {context} > {buffer}"


def _render_fullscreen_chat(
    content: str,
    buttons: Sequence[TerminalButton],
    *,
    selected: int,
    buttons_focused: bool,
    context: str,
    buffer: str,
    cursor_index: int,
    header_title: str,
    command_suggestions: Sequence[TerminalCommand],
    selected_suggestion: int,
    window_focused: bool,
) -> str:
    width = _terminal_width()
    height = _terminal_height()
    text_width = _composer_text_width(width)
    visible_text_rows = min(5, max(height - 12, 1), len(buffer) // text_width + 1)
    actions = _render_buttons(buttons, selected, focused=buttons_focused)
    in_thread = header_title != "SYS EDEN"
    if in_thread:
        panel = [
            " " + _MUTED_CONTROLS + line[1:] + "\x1b[0m"
            for line in _render_status_panel(
                header_title, context, content, width,
                max_lines=max(height - 7 - visible_text_rows, 3),
            )
        ]
    else:
        max_panel_lines = max(height - 7 - visible_text_rows, 2)
        panel = (
            _render_home_tree_panel(content, width, max_lines=max_panel_lines)
            if not context else None
        ) or _render_status_panel(
            header_title, context, content, width, max_lines=max_panel_lines,
        )
    composer = _render_composer(
        buffer, width, cursor_index=cursor_index, max_text_rows=visible_text_rows,
        focused=not buttons_focused, window_focused=window_focused
    )
    # The feed owns every row between header and composer. Home's optional
    # Activity outline is part of that region; threads need no spacer borders.
    activity_rows = max(height - len(panel) - len(composer) - 2, 1)
    activity_region: list[str]
    if command_suggestions:
        palette = _render_command_palette(
            command_suggestions,
            selected=selected_suggestion,
            width=width,
            available_rows=activity_rows,
        )
        activity_region = [
            *("" for _ in range(max(activity_rows - len(palette), 0))),
            *palette,
        ]
    elif in_thread:
        activity_region = [_ACTIVITY_MARKER for _ in range(activity_rows)]
    else:
        activity_region = [
            _ACTIVITY_TOP_MARKER,
            *(_ACTIVITY_MARKER for _ in range(max(activity_rows - 2, 1))),
            _ACTIVITY_BOTTOM_MARKER,
        ]
    lines = [
        *panel,
        *activity_region,
        *composer,
        _MUTED_CONTROLS + _screen_line(f"  {actions}", width) + "\x1b[0m",
        _screen_line("  /help for commands", width),
    ]
    # Every row in a full-screen frame must overwrite the row from the previous
    # frame. A bare newline only moves the cursor, so a shrinking command palette
    # would otherwise leave the old box and commands visible behind it.
    return "\n".join(_screen_line("", width) if line == "" else line for line in lines[:height])


def _render_fullscreen_view(content: str, footer: str, *, offset: int = 0) -> str:
    width = _terminal_width()
    height = _terminal_height()
    content_lines = _wrap_view_content(content, width)
    available = max(height - 3, 1)
    visible = content_lines[offset : offset + available]
    visible.extend("" for _ in range(available - len(visible)))
    lines = [
        _screen_line("SYS EDEN", width),
        _smooth_rule(width),
        *(_screen_line(line, width) for line in visible),
        _screen_line(f"  {footer}", width),
    ]
    return "\n".join(lines[:height])


def _wrap_view_content(content: str, width: int) -> list[str]:
    lines = content.splitlines() or [""]
    return [
        part
        for line in lines
        for part in _wrap_activity_line(line, max(width - 2, 1))
    ]


def _terminal_width() -> int:
    return max(shutil.get_terminal_size((100, 30)).columns, 24)


def _terminal_height() -> int:
    return max(shutil.get_terminal_size((100, 30)).lines, 14)


def _screen_line(value: str, width: int) -> str:
    inner = max(width - 2, 1)
    visible = _ANSI_ESCAPE.sub("", value)
    clipped = visible[:inner]
    return f" {clipped.ljust(inner)}"


def _wrap_activity_line(value: str, width: int) -> list[str]:
    """Wrap at word boundaries when possible without dropping source text."""
    clean = _ANSI_ESCAPE.sub("", value)
    if not clean:
        return [""]
    parts: list[str] = []
    remaining = clean
    continuation = "  " if clean.startswith("  ") and width > 2 else ""
    while remaining:
        prefix = continuation if parts else ""
        capacity = max(width - len(prefix), 1)
        if len(remaining) <= capacity:
            parts.append(prefix + remaining)
            break
        boundary = max(
            (index + 1 for index, character in enumerate(remaining[:capacity])
             if character.isspace()),
            default=0,
        )
        leading_space = len(remaining) - len(remaining.lstrip())
        take = boundary if boundary > leading_space else capacity
        parts.append(prefix + remaining[:take])
        remaining = remaining[take:]
    return parts


def _thread_activity_rows(lines: Sequence[str], width: int) -> list[_ActivityRow]:
    """Build user-only outlines from the existing speaker-separated thread feed."""
    rows: list[_ActivityRow] = []
    index = 0
    while index < len(lines):
        if lines[index] == "You":
            end = index + 1
            while end < len(lines) and lines[end].startswith("  "):
                end += 1
            if end > index + 1:
                rows.append(_ActivityRow(kind="user_top"))
                for value in lines[index + 1 : end]:
                    rows.extend(
                        _ActivityRow(part, "user_body")
                        for part in _wrap_activity_line(value[2:], max(width - 6, 1))
                    )
                rows.append(_ActivityRow(kind="user_bottom"))
                index = end
                continue
        rows.extend(
            _ActivityRow(part)
            for part in _wrap_activity_line(lines[index], max(width - 2, 1))
        )
        index += 1
    return rows


def _render_thread_activity_row(row: _ActivityRow, width: int) -> str:
    if row.kind == "plain":
        if row.text.startswith("  WARNING: Upcoming non-stoppable step:"):
            return "\x1b[1m\x1b[93m" + _screen_line(row.text, width) + "\x1b[0m"
        return _screen_line(row.text, width)
    inside = max(width - 4, 1)
    gray = "\x1b[38;5;245m"
    reset = "\x1b[0m"
    if row.kind == "user_top":
        label = "─ You "
        rule = (label + "─" * inside)[:inside]
        return f" {gray}╭{rule}╮{reset}"
    if row.kind == "user_bottom":
        return f" {gray}╰{'─' * inside}╯{reset}"
    content_width = max(width - 6, 1)
    return (
        f" {gray}│{reset} {row.text.ljust(content_width)} "
        f"{gray}│{reset}"
    )


def _smooth_rule(width: int) -> str:
    return " " + ("─" * max(width - 2, 1))


def _render_status_panel(
    title: str,
    context: str,
    content: str,
    width: int,
    *,
    max_lines: int,
) -> list[str]:
    panel_width = max(width - 2, 20)
    inner = panel_width - 2
    values = [
        part
        for line in [*([f"Context: {context}"] if context else []), *content.splitlines()]
        for part in _wrap_activity_line(line, max(inner - 2, 1))
    ][: max(max_lines - 2, 0)]
    return [
        _panel_top(title, width),
        *(_panel_line(value, inner) for value in values),
        _panel_bottom(width),
    ]


def _render_home_tree_panel(
    content: str, width: int, *, max_lines: int
) -> list[str] | None:
    """Use the tree silhouette as the open right edge of the home header."""
    tree = _HOME_TREE
    if not tree or len(tree) > max_lines or width < 72:
        return None
    tree_width = max(map(len, tree))
    tree_left = width - 2 - tree_width
    if min(tree_left + len(line) - len(line.lstrip()) for line in tree) < 24:
        return None

    box_height = max(round(len(tree) * 2 / 3), 6)
    box_top = (len(tree) - box_height) // 2
    box_bottom = box_top + box_height - 1
    narrowest_tree_start = min(
        tree_left + len(line) - len(line.lstrip())
        for line in tree[box_top + 1 : box_bottom]
    )
    values = [
        part
        for line in content.splitlines()
        for part in _wrap_activity_line(line, max(narrowest_tree_start - 5, 1))
    ][: box_height - 2]
    first_value_row = box_top + 1 + max((box_height - 2 - len(values)) // 2, 0)
    rows: list[str] = []
    for index, line in enumerate(tree):
        leading = len(line) - len(line.lstrip())
        tree_start = tree_left + leading
        art = line[leading:]
        if index == box_top:
            left = "╭ SYS EDEN "
            left += "─" * max(tree_start - 2 - len(left), 0)
        elif index == box_bottom:
            left = "╰" + "─" * max(tree_start - 3, 0)
        elif box_top < index < box_bottom:
            value_index = index - first_value_row
            value = values[value_index] if 0 <= value_index < len(values) else ""
            left = ("│  " + value)[: tree_start - 2]
        else:
            left = ""
        if left:
            row = left.ljust(tree_start - 2) + "  " + art
        else:
            row = (" " * tree_start) + art
        rows.append(_screen_line(row, width))
    return rows


def _panel_top(title: str, width: int) -> str:
    inner = max(width - 4, 18)
    label = f" {title} "
    return " ╭" + label + ("─" * max(inner - len(label), 0)) + "╮"


def _panel_bottom(width: int) -> str:
    inner = max(width - 4, 18)
    return " ╰" + ("─" * inner) + "╯"


def _activity_panel_line(value: str, width: int) -> str:
    return _panel_line(value, max(width - 4, 18))


def _panel_line(value: str, inner: int) -> str:
    clipped = value[: max(inner - 2, 1)]
    return f" │ {clipped.ljust(max(inner - 2, 1))} │"


def _matching_command_suggestions(
    buffer: str, commands: Sequence[TerminalCommand]
) -> list[TerminalCommand]:
    if not buffer.startswith("/"):
        return []
    query = buffer.casefold()
    if any(character.isspace() for character in buffer):
        return [
            command for command in commands
            if " " in command.completion
            and not command.completion.endswith(" ")
            and command.completion.casefold().startswith(query)
        ]
    return [
        command for command in commands
        if " " not in command.completion or command.completion.endswith(" ")
        if command.label.casefold().startswith(query)
    ]


def _render_command_palette(
    suggestions: Sequence[TerminalCommand],
    *,
    selected: int,
    width: int,
    available_rows: int,
) -> list[str]:
    if available_rows < 3:
        command = suggestions[selected]
        return [_screen_line(f"  › {command.label}  {command.description}", width)]
    visible_count = min(5, len(suggestions), available_rows - 2)
    offset = min(max(selected - visible_count + 1, 0), len(suggestions) - visible_count)
    visible = suggestions[offset : offset + visible_count]
    inner = max(width - 4, 18)
    lines = [_panel_top("Commands", width)]
    for index, command in enumerate(visible, start=offset):
        marker = "›" if index == selected else " "
        lines.append(_panel_line(f"{marker} {command.label}  {command.description}", inner))
    lines.append(_panel_bottom(width))
    return lines


def _composer_text_width(width: int) -> int:
    return max(width - 7, 1)


def _render_composer(
    buffer: str, width: int, *, cursor_index: int, max_text_rows: int,
    focused: bool, window_focused: bool
) -> list[str]:
    inner = max(width - 4, 16)
    blank = "".ljust(inner)
    text_width = _composer_text_width(width)
    chunks = [buffer[index:index + text_width] for index in range(0, len(buffer), text_width)]
    if not chunks or len(buffer) % text_width == 0:
        chunks.append("")
    cursor_row, cursor_column = divmod(cursor_index, text_width)
    first_row = min(max(cursor_row - max_text_rows + 1, 0), max(len(chunks) - max_text_rows, 0))
    visible = chunks[first_row:first_row + max_text_rows]
    return [
        _composer_line(blank, foreground=255),
        *(
            _composer_message_line(
                "› " if focused and row == 0 else "  ",
                value if buffer else "Ask Eden anything",
                inner=inner,
                foreground=255 if buffer else 245,
                marker_foreground=255 if window_focused else 245,
                focused=focused and row == cursor_row,
                cursor_column=cursor_column if row == cursor_row else None,
                placeholder=not buffer,
            )
            for row, value in enumerate(visible, start=first_row)
        ),
        _composer_line(blank, foreground=255),
    ]


def _composer_line(value: str, *, foreground: int) -> str:
    return f"  \x1b[48;5;236m\x1b[38;5;{foreground}m{value}\x1b[0m"


def _composer_message_line(
    marker: str,
    value: str,
    *,
    inner: int,
    foreground: int,
    marker_foreground: int,
    focused: bool,
    cursor_column: int | None,
    placeholder: bool,
) -> str:
    available = max(inner - len(marker), 0)
    if not focused:
        message = value[:available].ljust(available)
        return f"  \x1b[48;5;236m\x1b[38;5;{marker_foreground}m{marker}\x1b[38;5;{foreground}m{message}\x1b[0m"
    # Save the native cursor at the insertion point, including inside text.
    if placeholder:
        text = value[: max(available - 2, 0)]
        message = "\x1b[s  " + text + " " * max(available - len(text) - 2, 0)
    else:
        column = min(cursor_column or 0, len(value))
        message = (value[:column] + "\x1b[s" + (" " if column == len(value) else "")
                   + value[column:])
        message += " " * max(available - len(value) - (column == len(value)), 0)
    return f"  \x1b[48;5;236m\x1b[38;5;{marker_foreground}m{marker}\x1b[38;5;{foreground}m{message}\x1b[0m"


def _stdout_write(value: str) -> object:
    result = sys.stdout.write(value)
    sys.stdout.flush()
    return result


def _enable_windows_virtual_terminal() -> None:
    """Best-effort ANSI cursor support for legacy Windows console sessions."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except (AttributeError, OSError):
        return


def _enable_windows_virtual_terminal_input() -> int | None:
    """Return the original mode so mouse reporting never leaks into the shell."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) and kernel32.SetConsoleMode(
            handle, mode.value | 0x0200
        ):
            return int(mode.value)
    except (AttributeError, OSError):
        return None
    return None


def _restore_windows_input_mode(original_mode: int | None) -> None:
    if original_mode is None or sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), original_mode)
    except (AttributeError, OSError):
        return


def _display_line_count(value: str) -> int:
    """Include terminal wrapping when returning the live region's screen height."""
    width = max(shutil.get_terminal_size((100, 30)).columns, 1)
    count = 0
    for line in value.split("\n"):
        visible = _ANSI_ESCAPE.sub("", line)
        count += max((len(visible) + width - 1) // width, 1)
    return count


def _read_windows_key() -> str:
    if sys.platform != "win32":
        raise RuntimeError("interactive keyboard navigation currently requires Windows")
    import msvcrt

    size = shutil.get_terminal_size((100, 30))
    while not msvcrt.kbhit():
        if shutil.get_terminal_size((100, 30)) != size:
            return "resize"
        time.sleep(0.05)
    value = msvcrt.getwch()
    if value in {"\x00", "\xe0"}:
        return {
            "K": "left",
            "M": "right",
            "H": "up",
            "P": "down",
            "I": "page_up",
            "Q": "page_down",
            "S": "delete",
        }.get(msvcrt.getwch(), "unknown")
    if value == "\x1b":
        deadline = time.monotonic() + 0.03
        while not msvcrt.kbhit() and time.monotonic() < deadline:
            time.sleep(0.001)
        if not msvcrt.kbhit():
            return "escape"
        if msvcrt.getwch() != "[":
            return "escape"
        sequence = ""
        for _ in range(40):
            deadline = time.monotonic() + 0.03
            while not msvcrt.kbhit() and time.monotonic() < deadline:
                time.sleep(0.001)
            if not msvcrt.kbhit():
                return "unknown"
            character = msvcrt.getwch()
            sequence += character
            if character.isalpha() or character == "~":
                return _decode_csi(sequence)
        return "unknown"
    return {
        "\r": "enter",
        "\x1b": "escape",
        "\x03": "ctrl_c",
        "\t": "tab",
        "\x08": "backspace",
        "\x7f": "backspace",
    }.get(value, f"text:{value}" if value.isprintable() else "unknown")


def _decode_csi(sequence: str) -> str:
    if sequence.startswith("<") and sequence.endswith(("M", "m")):
        fields = sequence[1:-1].split(";")
        if len(fields) != 3 or not all(field.isdigit() for field in fields):
            return "unknown"
        button = int(fields[0])
        if button & 64:
            return {0: "wheel_up", 1: "wheel_down"}.get(button & 3, "unknown")
        return "mouse"
    return {
        "I": "focus_in",
        "O": "focus_out",
        "A": "up",
        "B": "down",
        "C": "right",
        "D": "left",
        "5~": "page_up",
        "6~": "page_down",
        "3~": "delete",
    }.get(sequence, "unknown")
