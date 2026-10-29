"""Persistent local reminders and timers with a queue-based scheduler."""

from __future__ import annotations

import queue
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator


@dataclass(frozen=True)
class Reminder:
    id: int
    message: str
    due_at: float
    kind: str


class ReminderStore:
    """Store reminder text and UTC timestamps in the existing local database."""

    def __init__(self, database_path: str | Path, clock: Callable[[], float] = time.time) -> None:
        self.database_path = Path(database_path)
        self._clock = clock
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY,
                    message TEXT NOT NULL,
                    due_at REAL NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('reminder', 'timer')),
                    notified_at REAL
                )"""
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def add(self, message: str, delay_seconds: int, kind: str = "reminder") -> Reminder:
        clean_message = " ".join(message.split())
        if not clean_message or len(clean_message) > 500:
            raise ValueError("Reminder text must contain 1 to 500 characters")
        if type(delay_seconds) is not int or not 1 <= delay_seconds <= 31_536_000:
            raise ValueError("Delay must be between 1 second and 365 days")
        if kind not in {"reminder", "timer"}:
            raise ValueError("Unknown scheduled item type")
        due_at = self._clock() + delay_seconds
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO reminders(message, due_at, kind) VALUES (?, ?, ?)",
                (clean_message, due_at, kind),
            )
            item_id = int(cursor.lastrowid)
        return Reminder(item_id, clean_message, due_at, kind)

    def due(self, now: float | None = None) -> list[Reminder]:
        """Return due entries; the UI marks each delivered only after presenting it."""
        current_time = self._clock() if now is None else now
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, message, due_at, kind FROM reminders "
                "WHERE notified_at IS NULL AND due_at <= ? ORDER BY due_at, id",
                (current_time,),
            ).fetchall()
        return [Reminder(int(row["id"]), row["message"], float(row["due_at"]), row["kind"]) for row in rows]

    def mark_notified(self, reminder_id: int, now: float | None = None) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE reminders SET notified_at = ? WHERE id = ? AND notified_at IS NULL",
                (self._clock() if now is None else now, reminder_id),
            )
        return cursor.rowcount == 1

    def pending(self) -> list[Reminder]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, message, due_at, kind FROM reminders "
                "WHERE notified_at IS NULL ORDER BY due_at, id"
            ).fetchall()
        return [Reminder(int(row["id"]), row["message"], float(row["due_at"]), row["kind"]) for row in rows]


class ReminderScheduler:
    """Check persisted reminders on a worker and queue due messages for the UI thread."""

    def __init__(
        self,
        store: ReminderStore,
        interval_seconds: float = 0.5,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("Scheduler interval must be positive")
        self.store = store
        self.interval_seconds = interval_seconds
        self._clock = clock
        self._due: queue.Queue[Reminder] = queue.Queue()
        self._queued_ids: set[int] = set()
        self._queued_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hercules-reminders", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def poll_once(self) -> None:
        for reminder in self.store.due(self._clock()):
            with self._queued_lock:
                if reminder.id in self._queued_ids:
                    continue
                self._queued_ids.add(reminder.id)
            self._due.put(reminder)

    def drain(self) -> list[Reminder]:
        ready: list[Reminder] = []
        while True:
            try:
                ready.append(self._due.get_nowait())
            except queue.Empty:
                return ready

    def acknowledge(self, reminder: Reminder) -> bool:
        """Mark an alert delivered after its main-thread speech/notification returns."""
        try:
            return self.store.mark_notified(reminder.id, self._clock())
        finally:
            self.release(reminder)

    def release(self, reminder: Reminder) -> None:
        """Allow a failed presentation to be queued again on the next tick."""
        with self._queued_lock:
            self._queued_ids.discard(reminder.id)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except (sqlite3.Error, OSError):
                # Leave entries pending so the next tick can retry safely.
                pass
            self._stop.wait(self.interval_seconds)
