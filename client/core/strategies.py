from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Dict, Optional, Set

from .models import InputType, NormalizedInputEvent, TargetRule

class InputMatchStrategy(ABC):

    @abstractmethod
    def matches(self, event: NormalizedInputEvent) -> bool:

        pass

    @property
    @abstractmethod
    def target_repr(self) -> str:

        pass

class SingleKeyStrategy(InputMatchStrategy):

    def __init__(self, key_name: str) -> None:
        self.key_name: str = key_name.strip().lower()

    def matches(self, event: NormalizedInputEvent) -> bool:
        if event.input_type != InputType.SINGLE:
            return False
        return event.canonical_repr == self.key_name

    @property
    def target_repr(self) -> str:
        return self.key_name.upper()

class KeyCombinationStrategy(InputMatchStrategy):

    def __init__(self, combination_str: str) -> None:
        parts = [p.strip().lower() for p in combination_str.split("+") if p.strip()]
        self.main_key: str = parts[-1]
        self.required_modifiers: Set[str] = set(parts[:-1])

    def matches(self, event: NormalizedInputEvent) -> bool:
        if event.input_type != InputType.COMBINATION:
            return False

        event_parts = [p.strip().lower() for p in event.canonical_repr.split("+") if p.strip()]
        if not event_parts:
            return False

        event_main_key = event_parts[-1]
        event_modifiers = set(event_parts[:-1])

        return (event_main_key == self.main_key) and (event_modifiers == self.required_modifiers)

    @property
    def target_repr(self) -> str:
        mods = "+".join(sorted(list(self.required_modifiers))).title()
        return f"{mods}+{self.main_key.upper()}" if mods else self.main_key.upper()

class CommandSequenceStrategy(InputMatchStrategy):

    def __init__(self, command_str: str) -> None:
        self.raw_pattern: str = command_str.strip()
        self.normalized_pattern: str = self._normalize_command(self.raw_pattern)

    @staticmethod
    def _normalize_command(cmd: str) -> str:
        cmd = cmd.replace("“", '"').replace("”", '"').replace("'", '"')
        cmd = re.sub(r"\s+", " ", cmd).strip().lower()
        return cmd

    def matches(self, event: NormalizedInputEvent) -> bool:
        if event.input_type != InputType.COMMAND:
            return False

        clean_event = self._normalize_command(event.canonical_repr)
        pattern = self.normalized_pattern

        if clean_event == pattern:
            return True

        if "git commit -m" in pattern:
            return clean_event.startswith("git commit -m")

        if "git switch -c" in pattern:
            return clean_event.startswith("git switch -c")
        if "git checkout -b" in pattern:
            return clean_event.startswith("git checkout -b")

        if pattern in ("git add", "git add .", "git add -a"):
            return clean_event.startswith("git add")

        if clean_event.startswith(pattern + " "):
            return True

        return False

    @property
    def target_repr(self) -> str:
        return self.raw_pattern

class TargetRuleFactory:

    @classmethod
    def create_strategy(cls, pattern: str, input_type: Optional[InputType] = None) -> InputMatchStrategy:
        clean = pattern.strip().lower()

        if input_type == InputType.COMMAND or clean.startswith("git ") or " " in clean:
            return CommandSequenceStrategy(pattern)

        if "+" in clean:
            return KeyCombinationStrategy(clean)

        return SingleKeyStrategy(clean)

    @classmethod
    def create_rule(
        cls,
        rule_id: str,
        label: str,
        pattern: str,
        input_type: Optional[InputType] = None,
        description: str = "",
    ) -> TargetRule:
        clean = pattern.strip()

        if input_type is None:
            if clean.lower().startswith("git ") or " " in clean:
                deduced_type = InputType.COMMAND
            elif "+" in clean:
                deduced_type = InputType.COMBINATION
            else:
                deduced_type = InputType.SINGLE
        else:
            deduced_type = input_type

        return TargetRule(
            id=rule_id,
            label=label,
            input_type=deduced_type,
            pattern=clean,
            description=description,
        )
