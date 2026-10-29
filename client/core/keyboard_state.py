from __future__ import annotations

import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from pynput import keyboard

from .models import InputType, NormalizedInputEvent

ALLOWED_COMMAND_PREFIXES: Tuple[str, ...] = (
    "git", "gh", "cd", "ls", "dir", "pwd", "mkdir", "touch",
    "echo", "cat", "clear", "cls", "code", "python", "py",
    "pip", "pytest", "node", "npm"
)

def sanitize_and_validate_command(line: str) -> Optional[str]:

    trimmed = line.strip()
    if not trimmed:
        return None
    words = trimmed.split()
    if not words:
        return None
    first_word = words[0].lower()
    if first_word.endswith(".exe"):
        first_word = first_word[:-4]
    if first_word in ALLOWED_COMMAND_PREFIXES:
        return trimmed
    return None

WINDOWS_CTRL_CHAR_MAP: Dict[str, str] = {
    "\x01": "a", "\x02": "b", "\x03": "c", "\x04": "d", "\x05": "e",
    "\x06": "f", "\x07": "g", "\x08": "h", "\t": "i",   "\n": "j",
    "\x0b": "k", "\x0c": "l", "\r": "m", "\x0e": "n", "\x0f": "o",
    "\x10": "p", "\x11": "q", "\x12": "r", "\x13": "s", "\x14": "t",
    "\x15": "u", "\x16": "v", "\x17": "w", "\x18": "x", "\x19": "y",
    "\x1a": "z"
}

SPECIAL_KEYS_MAP: Dict[keyboard.Key, str] = {
    keyboard.Key.enter: "enter",
    keyboard.Key.tab: "tab",
    keyboard.Key.space: "space",
    keyboard.Key.backspace: "backspace",
    keyboard.Key.esc: "esc",
    keyboard.Key.delete: "delete",
    keyboard.Key.up: "up",
    keyboard.Key.down: "down",
    keyboard.Key.left: "left",
    keyboard.Key.right: "right",
    keyboard.Key.f1: "f1",
    keyboard.Key.f2: "f2",
    keyboard.Key.f3: "f3",
    keyboard.Key.f4: "f4",
    keyboard.Key.f5: "f5",
    keyboard.Key.f6: "f6",
    keyboard.Key.f7: "f7",
    keyboard.Key.f8: "f8",
    keyboard.Key.f9: "f9",
    keyboard.Key.f10: "f10",
    keyboard.Key.f11: "f11",
    keyboard.Key.f12: "f12",
}

MODIFIER_KEYS: Set[keyboard.Key] = {
    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr,
    keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
}

SPANISH_VK_SYMBOLS: Dict[int, str] = {
    192: "ñ",
    189: "-",
    190: ".",
    188: ",",
    219: "'",
    220: "|",
    221: "¿",
}

SPANISH_VK_SHIFT_SYMBOLS: Dict[int, str] = {
    49: "!",
    50: '"',
    51: "·",
    52: "$",
    53: "%",
    54: "&",
    55: "/",
    56: "(",
    57: ")",
    48: "=",
    189: "_",
    190: ":",
    188: ";",
    219: "?",
    221: "¡",
}

class KeyboardStateManager:

    def __init__(
        self,
        command_buffer_timeout: float = 12.0,
        enforce_whitelist: bool = False,
    ) -> None:
        self._pressed_modifiers: Set[str] = set()
        self._command_buffer: List[str] = []
        self._last_char_time: float = 0.0
        self._command_timeout: float = command_buffer_timeout
        self._max_buffer_len: int = 300
        self._enforce_whitelist: bool = enforce_whitelist

    def _clean_buffer_if_timed_out(self) -> None:
        if self._command_buffer and (time.time() - self._last_char_time > self._command_timeout):
            self._command_buffer.clear()

    def _sync_physical_modifiers_if_idle(self) -> None:

        if sys.platform == "win32" and self._pressed_modifiers:
            if self._last_char_time > 0 and (time.time() - self._last_char_time > 4.0):
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    if "ctrl" in self._pressed_modifiers and not (user32.GetAsyncKeyState(0x11) & 0x8000):
                        self._pressed_modifiers.discard("ctrl")
                    if "alt" in self._pressed_modifiers and not (user32.GetAsyncKeyState(0x12) & 0x8000):
                        self._pressed_modifiers.discard("alt")
                    if "shift" in self._pressed_modifiers and not (user32.GetAsyncKeyState(0x10) & 0x8000):
                        self._pressed_modifiers.discard("shift")
                    if "cmd" in self._pressed_modifiers and not ((user32.GetAsyncKeyState(0x5B) | user32.GetAsyncKeyState(0x5C)) & 0x8000):
                        self._pressed_modifiers.discard("cmd")
                except Exception:
                    pass

    def on_key_down(self, key: keyboard.Key | keyboard.KeyCode) -> Optional[NormalizedInputEvent]:
        self._clean_buffer_if_timed_out()
        self._sync_physical_modifiers_if_idle()

        if key in MODIFIER_KEYS:
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                self._pressed_modifiers.add("ctrl")
            elif key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                self._pressed_modifiers.add("shift")
            elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
                self._pressed_modifiers.add("alt")
            elif key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
                self._pressed_modifiers.add("cmd")
            return None

        raw_key_name: Optional[str] = None
        is_printable_char = False

        if isinstance(key, keyboard.Key):
            raw_key_name = SPECIAL_KEYS_MAP.get(key)
        elif hasattr(key, "char") and key.char is not None:
            char_val = key.char
            if "ctrl" in self._pressed_modifiers and char_val in WINDOWS_CTRL_CHAR_MAP:
                raw_key_name = WINDOWS_CTRL_CHAR_MAP[char_val]
            else:
                raw_key_name = char_val
                is_printable_char = len(char_val) == 1 and char_val.isprintable()
        elif hasattr(key, "vk"):
            vk = getattr(key, "vk", None)
            if vk is not None:
                if "shift" in self._pressed_modifiers and vk in SPANISH_VK_SHIFT_SYMBOLS:
                    raw_key_name = SPANISH_VK_SHIFT_SYMBOLS[vk]
                    is_printable_char = True
                elif vk in SPANISH_VK_SYMBOLS:
                    raw_key_name = SPANISH_VK_SYMBOLS[vk]
                    is_printable_char = True

        if not raw_key_name:
            return None

        if raw_key_name == "tab" and "alt" in self._pressed_modifiers:
            self._pressed_modifiers.discard("alt")
            self._command_buffer.clear()
            return NormalizedInputEvent(
                input_type=InputType.COMBINATION,
                canonical_repr="alt+tab",
                raw_key="tab",
                modifiers={"alt"},
            )

        if ("ctrl" in self._pressed_modifiers and raw_key_name in ("c", "u", "z")) or raw_key_name == "esc":
            self._command_buffer.clear()

        if raw_key_name in ("up", "down"):
            self._command_buffer.clear()

        has_primary_modifier = bool(self._pressed_modifiers.intersection({"ctrl", "alt", "cmd"}))
        shift_only = ("shift" in self._pressed_modifiers) and not has_primary_modifier

        if shift_only and is_printable_char:
            self._command_buffer.append(raw_key_name)
            if len(self._command_buffer) > self._max_buffer_len:
                self._command_buffer = self._command_buffer[-self._max_buffer_len:]
            self._last_char_time = time.time()
            return None

        if not self._pressed_modifiers and is_printable_char:
            self._command_buffer.append(raw_key_name)
            if len(self._command_buffer) > self._max_buffer_len:
                self._command_buffer = self._command_buffer[-self._max_buffer_len:]
            self._last_char_time = time.time()
        elif raw_key_name == "backspace" and self._command_buffer:
            self._command_buffer.pop()
            self._last_char_time = time.time()
        elif raw_key_name == "space" and self._command_buffer:
            self._command_buffer.append(" ")
            self._last_char_time = time.time()

        if raw_key_name == "enter" and self._command_buffer:
            full_command = "".join(self._command_buffer).strip()
            self._command_buffer.clear()

            if self._enforce_whitelist:
                valid_cmd = sanitize_and_validate_command(full_command)
                if not valid_cmd:
                    return None
                full_command = valid_cmd

            return NormalizedInputEvent(
                input_type=InputType.COMMAND,
                canonical_repr=full_command,
                raw_key="enter",
                modifiers=set(self._pressed_modifiers),
            )

        if has_primary_modifier or (shift_only and not is_printable_char):
            sorted_modifiers = sorted(list(self._pressed_modifiers))
            combo_repr = "+".join(sorted_modifiers + [raw_key_name.lower()])
            return NormalizedInputEvent(
                input_type=InputType.COMBINATION,
                canonical_repr=combo_repr,
                raw_key=raw_key_name,
                modifiers=set(self._pressed_modifiers),
            )

        return NormalizedInputEvent(
            input_type=InputType.SINGLE,
            canonical_repr=raw_key_name.lower(),
            raw_key=raw_key_name,
            modifiers=set(),
        )

    def on_key_up(self, key: keyboard.Key | keyboard.KeyCode) -> None:

        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self._pressed_modifiers.discard("ctrl")
        elif key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self._pressed_modifiers.discard("shift")
        elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
            self._pressed_modifiers.discard("alt")
        elif key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            self._pressed_modifiers.discard("cmd")
