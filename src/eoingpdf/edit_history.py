"""Bounded, in-memory document draft history; PDF copies remain immutable."""
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class StampState:
    page: int
    stream: bytes = field(repr=False)
    pixmap: object = field(repr=False, compare=False)
    image_key: bytes = field(repr=False)
    aspect: float
    x: float
    y: float
    width: float
    page_width: float
    page_height: float

    @property
    def image_bytes(self):
        return len(self.stream) + self.pixmap.width() * self.pixmap.height() * 4


@dataclass(frozen=True)
class DraftState:
    path: Path
    password: str = field(repr=False)
    source_count: int
    pages: tuple
    stamps: tuple
    selected_index: int = field(compare=False)
    page: int = field(compare=False)
    dirty: bool = field(compare=False)


@dataclass(frozen=True)
class HistoryEntry:
    label: str
    state: DraftState


class EditHistory:
    def __init__(self, baseline, label, limit=32):
        self.baseline = baseline
        self.limit = max(1, limit)
        self.entries = [HistoryEntry(label, baseline)]
        self.position = 0

    @property
    def current(self):
        return self.entries[self.position].state

    @property
    def can_undo(self):
        return self.position > 0

    @property
    def can_redo(self):
        return self.position + 1 < len(self.entries)

    @property
    def undo_label(self):
        return self.entries[self.position].label if self.can_undo else ''

    @property
    def redo_label(self):
        return self.entries[self.position + 1].label if self.can_redo else ''

    @property
    def retained_states(self):
        return (self.baseline, *(entry.state for entry in self.entries))

    def sync_presentation(self, state):
        """Navigation and object selection do not consume an undo step."""
        if state == self.current:
            entry = self.entries[self.position]
            self.entries[self.position] = replace(entry, state=state)

    def push(self, state, label):
        if state == self.current:
            self.sync_presentation(state)
            return False
        del self.entries[self.position + 1:]
        self.entries.append(HistoryEntry(label, state))
        overflow = len(self.entries) - self.limit - 1
        if overflow > 0:
            del self.entries[:overflow]
        self.position = len(self.entries) - 1
        return True

    def image_bytes(self, extra=()):
        images = {stamp.image_key: stamp.image_bytes
                  for state in self.retained_states for stamp in state.stamps}
        images.update({stamp.image_key: stamp.image_bytes for stamp in extra})
        return sum(images.values())

    def has_image(self, identity):
        return any(stamp.image_key == identity for state in self.retained_states for stamp in state.stamps)

    def find_image(self, identity):
        return next((stamp for state in self.retained_states for stamp in state.stamps
                     if stamp.image_key == identity), None)
