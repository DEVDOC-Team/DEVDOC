"""Concurrency-safe, conservative process-lifetime LLM budget guard."""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path


class BudgetExceededError(Exception):
    """Raised before a provider request would exceed the configured spend ceiling."""


@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: uuid.UUID
    reserved_cost_usd: float
    input_tokens: int
    output_tokens: int


class LLMBudgetGuard:
    """Reserves worst-case cost before each attempt, optionally persisting spend.

    A SQLite ledger shares reservations across service instances and process restarts
    on the same filesystem. Unsettled reservations remain charged after a crash.
    """

    def __init__(
        self,
        *,
        budget_usd: float,
        input_cost_per_million_usd: float,
        output_cost_per_million_usd: float,
        ledger_path: str | Path | None = None,
    ) -> None:
        if budget_usd <= 0 or budget_usd > 25:
            raise ValueError("budget_usd must be greater than zero and no more than $25")
        if input_cost_per_million_usd <= 0 or output_cost_per_million_usd <= 0:
            raise ValueError("Positive input and output token prices are required")
        self._budget_usd = budget_usd
        self._input_rate = input_cost_per_million_usd
        self._output_rate = output_cost_per_million_usd
        self._ledger_path = Path(ledger_path) if ledger_path is not None else None
        self._spent_usd = 0.0
        self._pending_usd = 0.0
        self._reservations: dict[uuid.UUID, BudgetReservation] = {}
        self._lock = asyncio.Lock()
        if self._ledger_path is not None:
            self._initialize_ledger()

    def _initialize_ledger(self) -> None:
        assert self._ledger_path is not None
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._ledger_path, timeout=30)
        try:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_budget_state (
                        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                        budget_usd REAL NOT NULL,
                        input_rate REAL NOT NULL,
                        output_rate REAL NOT NULL,
                        spent_usd REAL NOT NULL DEFAULT 0
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_budget_reservations (
                        reservation_id TEXT PRIMARY KEY,
                        reserved_cost_usd REAL NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO llm_budget_state
                        (singleton, budget_usd, input_rate, output_rate)
                    VALUES (1, ?, ?, ?)
                    """,
                    (self._budget_usd, self._input_rate, self._output_rate),
                )
                config = connection.execute(
                    """
                    SELECT budget_usd, input_rate, output_rate
                    FROM llm_budget_state WHERE singleton = 1
                    """
                ).fetchone()
        finally:
            connection.close()
        expected = (self._budget_usd, self._input_rate, self._output_rate)
        if config != expected:
            raise ValueError(
                "LLM budget ledger already exists with different budget or token prices"
            )

    async def reserve(self, *, input_tokens: int, output_tokens: int) -> BudgetReservation:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Token estimates must be non-negative")
        cost = self.estimate_cost(input_tokens, output_tokens)
        async with self._lock:
            reservation = BudgetReservation(
                reservation_id=uuid.uuid4(),
                reserved_cost_usd=cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            if self._ledger_path is None:
                if self._spent_usd + self._pending_usd + cost > self._budget_usd:
                    raise BudgetExceededError("LLM request would exceed the configured budget")
                self._reservations[reservation.reservation_id] = reservation
                self._pending_usd += cost
            else:
                connection = sqlite3.connect(self._ledger_path, timeout=30)
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    state = connection.execute(
                        """
                        SELECT spent_usd FROM llm_budget_state WHERE singleton = 1
                        """
                    ).fetchone()
                    pending = connection.execute(
                        "SELECT COALESCE(SUM(reserved_cost_usd), 0) FROM llm_budget_reservations"
                    ).fetchone()[0]
                    if state is None or state[0] + pending + cost > self._budget_usd:
                        raise BudgetExceededError("LLM request would exceed the configured budget")
                    connection.execute(
                        """
                        INSERT INTO llm_budget_reservations
                            (reservation_id, reserved_cost_usd)
                        VALUES (?, ?)
                        """,
                        (str(reservation.reservation_id), cost),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.close()
            return reservation

    async def settle(
        self,
        reservation: BudgetReservation,
        *,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        failed: bool = False,
    ) -> float:
        async with self._lock:
            connection: sqlite3.Connection | None = None
            if self._ledger_path is None:
                current = self._reservations.get(reservation.reservation_id)
                if current is None:
                    raise ValueError("Budget reservation is unknown or already settled")
                reserved_cost = current.reserved_cost_usd
            else:
                connection = sqlite3.connect(self._ledger_path, timeout=30)
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    current = connection.execute(
                        """
                        SELECT reserved_cost_usd FROM llm_budget_reservations
                        WHERE reservation_id = ?
                        """,
                        (str(reservation.reservation_id),),
                    ).fetchone()
                    if current is None:
                        raise ValueError("Budget reservation is unknown or already settled")
                    reserved_cost = current[0]
                except Exception:
                    connection.rollback()
                    connection.close()
                    raise

            if failed:
                charged = reserved_cost
            else:
                input_used = reservation.input_tokens if prompt_tokens is None else prompt_tokens
                output_used = (
                    reservation.output_tokens if completion_tokens is None else completion_tokens
                )
                charged = min(reserved_cost, self.estimate_cost(input_used, output_used))
            if self._ledger_path is None:
                del self._reservations[reservation.reservation_id]
                self._pending_usd -= current.reserved_cost_usd
                self._spent_usd += charged
            else:
                assert connection is not None
                try:
                    connection.execute(
                        "DELETE FROM llm_budget_reservations WHERE reservation_id = ?",
                        (str(reservation.reservation_id),),
                    )
                    connection.execute(
                        """
                        UPDATE llm_budget_state
                        SET spent_usd = spent_usd + ?
                        WHERE singleton = 1
                        """,
                        (charged,),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.close()
            return charged

    async def remaining_usd(self) -> float:
        async with self._lock:
            if self._ledger_path is not None:
                connection = sqlite3.connect(self._ledger_path, timeout=30)
                try:
                    spent = connection.execute(
                        "SELECT spent_usd FROM llm_budget_state WHERE singleton = 1"
                    ).fetchone()[0]
                    pending = connection.execute(
                        "SELECT COALESCE(SUM(reserved_cost_usd), 0) FROM llm_budget_reservations"
                    ).fetchone()[0]
                finally:
                    connection.close()
                return max(0.0, self._budget_usd - spent - pending)
            return max(0.0, self._budget_usd - self._spent_usd - self._pending_usd)

    async def spent_usd(self) -> float:
        async with self._lock:
            if self._ledger_path is not None:
                connection = sqlite3.connect(self._ledger_path, timeout=30)
                try:
                    return connection.execute(
                        "SELECT spent_usd FROM llm_budget_state WHERE singleton = 1"
                    ).fetchone()[0]
                finally:
                    connection.close()
            return self._spent_usd

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self._input_rate + output_tokens * self._output_rate) / 1_000_000
