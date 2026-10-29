from .models import InputType, NormalizedInputEvent, TargetRule
try:
    from .keyboard_state import KeyboardStateManager
except ImportError:
    KeyboardStateManager = None
from .strategies import (
    CommandSequenceStrategy,
    InputMatchStrategy,
    KeyCombinationStrategy,
    SingleKeyStrategy,
    TargetRuleFactory,
)
from .identity import DynamicPathResolver, FlexibleIdentityParser, StudentIdentityWatcher

__all__ = [
    "InputType",
    "NormalizedInputEvent",
    "TargetRule",
    "KeyboardStateManager",
    "InputMatchStrategy",
    "SingleKeyStrategy",
    "KeyCombinationStrategy",
    "CommandSequenceStrategy",
    "TargetRuleFactory",
    "DynamicPathResolver",
    "FlexibleIdentityParser",
    "StudentIdentityWatcher",
]
