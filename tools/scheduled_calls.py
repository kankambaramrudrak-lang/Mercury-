"""Persist and dispatch one-time phone calls approved in advance by the user."""

from __future__ import annotations

import queue
import sqlite3
import threading
import time
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Protocol


@dataclass(frozen=True)
class ScheduledCall:
    id: int
    recipient: str
    announcement: str
    due_at: float


class ScheduledCallClient(Protocol):
    def call_contact_preapproved(self, recipient: str, announcement: str) -> str: ...


class ScheduledCallStore:
    def __init__(self, database_path: str | Path, clock: Callable[[], float] = time.time) -> None:
        self.database_path = Path(database_path)
        self._clock = clock
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS scheduled_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient TEXT NOT NULL,
                    announcement TEXT NOT NULL,
                    due_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'queued', 'completed', 'failed'))
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

    def add(self, recipient: str, announcement: str, delay_seconds: int) -> ScheduledCall:
        recipient = " ".join(recipient.split())
        announcement = " ".join(announcement.split())
        if not recipient or len(recipient) > 100:
            raise ValueError("A contact name is required")
        if not announcement or len(announcement) > 1000:
            raise ValueError("Call message must contain 1 to 1000 characters")
        if type(delay_seconds) is not int or not 5 <= delay_seconds <= 31_536_000:
            raise ValueError("Scheduled call must be at least five seconds from now and within 365 days")
        due_at = self._clock() + delay_seconds
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO scheduled_calls(recipient, announcement, due_at) VALUES (?, ?, ?)",
                (recipient, announcement, due_at),
            )
            call_id = int(cursor.lastrowid)
        return ScheduledCall(call_id, recipient, announcement, due_at)

    def claim_due(self, now: float | None = None) -> list[ScheduledCall]:
        current_time = self._clock() if now is None else now
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT id, recipient, announcement, due_at FROM scheduled_calls "
                "WHERE status='pending' AND due_at <= ? ORDER BY due_at, id",
                (current_time,),
            ).fetchall()
            if rows:
                connection.executemany(
                    "UPDATE scheduled_calls SET status='queued' WHERE id=? AND status='pending'",
                    [(row["id"],) for row in rows],
                )
            connection.commit()
        return [
            ScheduledCall(int(row["id"]), row["recipient"], row["announcement"], float(row["due_at"]))
            for row in rows
        ]

    def pending(self) -> list[ScheduledCall]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, recipient, announcement, due_at FROM scheduled_calls "
                "WHERE status='pending' ORDER BY due_at, id"
            ).fetchall()
        return [
            ScheduledCall(int(row["id"]), row["recipient"], row["announcement"], float(row["due_at"]))
            for row in rows
        ]

    def cancel(self, call_id: int) -> bool:
        """Remove a future call only while it is still pending."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM scheduled_calls WHERE id=? AND status='pending'", (call_id,)
            )
            return cursor.rowcount == 1

    def finish(self, call_id: int, succeeded: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE scheduled_calls SET status=? WHERE id=? AND status='queued'",
                ("completed" if succeeded else "failed", call_id),
            )


class ScheduledCallScheduler:
    def __init__(
        self,
        store: ScheduledCallStore,
        interval_seconds: float = 0.5,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("Scheduler interval must be positive")
        self.store = store
        self.interval_seconds = interval_seconds
        self._clock = clock
        self._due: queue.Queue[ScheduledCall] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="hercules-scheduled-calls", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def poll_once(self) -> None:
        for scheduled_call in self.store.claim_due(self._clock()):
            self._due.put(scheduled_call)

    def drain(self) -> list[ScheduledCall]:
        ready: list[ScheduledCall] = []
        while True:
            try:
                ready.append(self._due.get_nowait())
            except queue.Empty:
                return ready

    def finish(self, scheduled_call: ScheduledCall, succeeded: bool) -> None:
        self.store.finish(scheduled_call.id, succeeded)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except (sqlite3.Error, OSError):
                pass
            self._stop.wait(self.interval_seconds)


def describe_call_time(due_at: float) -> str:
    """Format a local wall-clock time for an approval prompt."""
    return datetime.fromtimestamp(due_at).astimezone().strftime("%A, %B %d at %I:%M %p %Z")


def dispatch_due_calls(
    scheduler: ScheduledCallScheduler,
    client: ScheduledCallClient,
    notify: Callable[[str], None],
) -> None:
    """Execute calls approved at scheduling time and report only the result."""
    for scheduled_call in scheduler.drain():
        try:
            result = client.call_contact_preapproved(scheduled_call.recipient, scheduled_call.announcement)
            succeeded = result.startswith("Phone call started")
        except Exception:
            result = "The scheduled phone call could not be completed. No retry was made."
            succeeded = False
        scheduler.finish(scheduled_call, succeeded)
        notify(result)
