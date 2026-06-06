from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


EXPIRY_HOURS = 50
WARNING_THRESHOLDS = {
    "24h": timedelta(hours=24),
    "6h": timedelta(hours=6),
    "2h": timedelta(hours=2),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def dt_to_str(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass
class Stockpile:
    id: str
    guild_id: int
    channel_id: int
    message_id: int | None
    name: str
    location: str
    type: str
    created_by_user_id: int
    last_refreshed_at: str
    expires_at: str
    last_refreshed_by_user_id: int
    warned_24h: bool
    warned_6h: bool
    warned_2h: bool
    expired_notified: bool
    created_at: str
    updated_at: str

    @property
    def expires_datetime(self) -> datetime:
        return parse_dt(self.expires_at)

    @property
    def last_refreshed_datetime(self) -> datetime:
        return parse_dt(self.last_refreshed_at)


class StockpileStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def all(self) -> list[Stockpile]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        return [Stockpile(**item) for item in raw.get("stockpiles", [])]

    def save_all(self, stockpiles: Iterable[Stockpile]) -> None:
        payload = {"stockpiles": [asdict(item) for item in stockpiles]}
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        tmp_path.replace(self.path)

    def get(self, stockpile_id: str) -> Stockpile | None:
        return next((item for item in self.all() if item.id == stockpile_id), None)

    def create(
        self,
        *,
        guild_id: int,
        channel_id: int,
        name: str,
        location: str,
        stockpile_type: str,
        user_id: int,
        now: datetime | None = None,
    ) -> Stockpile:
        current = now or utc_now()
        current_str = dt_to_str(current)
        stockpile = Stockpile(
            id=uuid.uuid4().hex[:8],
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=None,
            name=name.strip(),
            location=location.strip(),
            type=stockpile_type,
            created_by_user_id=user_id,
            last_refreshed_at=current_str,
            expires_at=dt_to_str(current + timedelta(hours=EXPIRY_HOURS)),
            last_refreshed_by_user_id=user_id,
            warned_24h=False,
            warned_6h=False,
            warned_2h=False,
            expired_notified=False,
            created_at=current_str,
            updated_at=current_str,
        )
        stockpiles = self.all()
        stockpiles.append(stockpile)
        self.save_all(stockpiles)
        return stockpile

    def update(self, updated: Stockpile) -> Stockpile:
        stockpiles = self.all()
        for index, stockpile in enumerate(stockpiles):
            if stockpile.id == updated.id:
                updated.updated_at = dt_to_str(utc_now())
                stockpiles[index] = updated
                self.save_all(stockpiles)
                return updated
        raise KeyError(f"Unknown stockpile id: {updated.id}")

    def set_message_id(self, stockpile_id: str, message_id: int) -> Stockpile:
        stockpile = self.get(stockpile_id)
        if stockpile is None:
            raise KeyError(f"Unknown stockpile id: {stockpile_id}")
        stockpile.message_id = message_id
        return self.update(stockpile)

    def refresh(
        self,
        stockpile_id: str,
        *,
        user_id: int,
        now: datetime | None = None,
    ) -> Stockpile:
        stockpile = self.get(stockpile_id)
        if stockpile is None:
            raise KeyError(f"Unknown stockpile id: {stockpile_id}")

        current = now or utc_now()
        stockpile.last_refreshed_at = dt_to_str(current)
        stockpile.expires_at = dt_to_str(current + timedelta(hours=EXPIRY_HOURS))
        stockpile.last_refreshed_by_user_id = user_id
        stockpile.warned_24h = False
        stockpile.warned_6h = False
        stockpile.warned_2h = False
        stockpile.expired_notified = False
        return self.update(stockpile)

    def delete(self, stockpile_id: str) -> bool:
        stockpiles = self.all()
        kept = [item for item in stockpiles if item.id != stockpile_id]
        if len(kept) == len(stockpiles):
            return False
        self.save_all(kept)
        return True


def remaining_time(stockpile: Stockpile, now: datetime | None = None) -> timedelta:
    return stockpile.expires_datetime - (now or utc_now())


def warning_due(stockpile: Stockpile, now: datetime | None = None) -> str | None:
    remaining = remaining_time(stockpile, now)
    if remaining <= timedelta(seconds=0):
        return "expired" if not stockpile.expired_notified else None
    if remaining <= WARNING_THRESHOLDS["2h"] and not stockpile.warned_2h:
        return "2h"
    if remaining <= WARNING_THRESHOLDS["6h"] and not stockpile.warned_6h:
        return "6h"
    if remaining <= WARNING_THRESHOLDS["24h"] and not stockpile.warned_24h:
        return "24h"
    return None


def mark_warning_sent(stockpile: Stockpile, warning: str) -> Stockpile:
    if warning == "24h":
        stockpile.warned_24h = True
    elif warning == "6h":
        stockpile.warned_6h = True
    elif warning == "2h":
        stockpile.warned_2h = True
    elif warning == "expired":
        stockpile.expired_notified = True
    else:
        raise ValueError(f"Unknown warning: {warning}")
    return stockpile


def format_remaining(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "expired"

    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
