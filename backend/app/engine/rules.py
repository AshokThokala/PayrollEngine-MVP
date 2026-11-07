"""Date-effective statutory rules loaded from JSON config.

Rules are data, not code: a change in law is a new entry with a new
``valid_from`` date. Every calculation records the rule version it used
(``<category>@<valid_from>``) so a past payslip can be explained in an audit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

STATE_FILES = {"TG": "telangana.json"}


class RuleNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Rule:
    category: str
    data: dict

    @property
    def version(self) -> str:
        return f"{self.category}@{self.data['valid_from']}"

    def __getitem__(self, key):
        return self.data[key]


def _covers(entry: dict, on: date) -> bool:
    start = date.fromisoformat(entry["valid_from"])
    end = date.fromisoformat(entry["valid_to"]) if entry.get("valid_to") else None
    return start <= on and (end is None or on <= end)


class RuleBook:
    def __init__(self, central: dict, states: dict[str, dict]):
        self._central = central
        self._states = states

    @classmethod
    def load(cls, rules_dir: Path = RULES_DIR) -> "RuleBook":
        central = json.loads((rules_dir / "central.json").read_text())
        states = {
            code: json.loads((rules_dir / fname).read_text())
            for code, fname in STATE_FILES.items()
        }
        return cls(central, states)

    @property
    def supported_states(self) -> list[str]:
        return sorted(self._states)

    def central(self, category: str, on: date) -> Rule:
        return self._pick(self._central, category, on, scope="central")

    def state(self, state: str, category: str, on: date) -> Rule:
        if state not in self._states:
            raise RuleNotFound(f"State {state!r} not supported yet")
        return self._pick(self._states[state], category, on, scope=state)

    @staticmethod
    def _pick(book: dict, category: str, on: date, scope: str) -> Rule:
        for entry in book.get(category, []):
            if _covers(entry, on):
                return Rule(f"{scope}.{category}", entry)
        raise RuleNotFound(f"No {scope} rule for {category!r} on {on.isoformat()}")
