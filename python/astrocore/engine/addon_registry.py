from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple


@dataclass(frozen=True)
class AddonDeclaration(object):
    name: str
    lifecycle_events: Tuple[str, ...]
    handler: Callable


class AddonRegistry(object):
    def __init__(self):
        self._declarations = []

    def register(self, declaration):
        self._declarations.append(declaration)

    def handlers_for_event(self, event_name):
        return [row for row in self._declarations if str(event_name) in tuple(row.lifecycle_events)]
