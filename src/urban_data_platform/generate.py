"""Deterministic source-data generator for the local demonstration."""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


Record = dict[str, Any]
SYNTHETIC_EPOCH = datetime(2040, 1, 1, 8, 0, tzinfo=timezone.utc)


def _timestamp(*, minutes: int = 0, seconds: int = 0) -> str:
    value = SYNTHETIC_EPOCH + timedelta(minutes=minutes, seconds=seconds)
    return value.isoformat().replace("+00:00", "Z")


def _record(
    record_type: str,
    business_key: str,
    event_time: str,
    recorded_at: str,
    payload: dict[str, Any],
    *,
    version: int = 1,
) -> Record:
    return {
        "business_key": business_key,
        "event_time": event_time,
        "payload": payload,
        "record_type": record_type,
        "recorded_at": recorded_at,
        "version": version,
    }


def _delivery_event(
    delivery_id: str,
    event_key: str,
    event_kind: str,
    minute: int,
    *,
    recorded_minute: int | None = None,
    version: int = 1,
    **extra: Any,
) -> Record:
    payload = {"delivery_id": delivery_id, "event_kind": event_kind, **extra}
    return _record(
        "delivery_event",
        f"event:{delivery_id}:{event_key}",
        _timestamp(minutes=minute),
        _timestamp(minutes=recorded_minute if recorded_minute is not None else minute, seconds=45),
        payload,
        version=version,
    )


def _ledger_entry(
    delivery_id: str,
    entry_key: str,
    entry_type: str,
    amount_minor: int,
    minute: int,
    *,
    recorded_minute: int | None = None,
    version: int = 1,
    reference_entry_key: str | None = None,
) -> Record:
    return _record(
        "ledger_entry",
        f"ledger:{delivery_id}:{entry_key}",
        _timestamp(minutes=minute),
        _timestamp(minutes=recorded_minute if recorded_minute is not None else minute, seconds=50),
        {
            "amount_minor": amount_minor,
            "delivery_id": delivery_id,
            "entry_type": entry_type,
            "reference_entry_key": reference_entry_key,
        },
        version=version,
    )


def build_records(seed: int = 734_021) -> tuple[list[Record], list[Record]]:
    """Return the initial and late-arriving deterministic record batches."""

    rng = random.Random(seed)
    initial: list[Record] = []
    late: list[Record] = []

    cells = {
        "cell-amber": (0.0, 100.0, 0.0, 100.0),
        "cell-cobalt": (100.0, 200.0, 0.0, 100.0),
        "cell-jade": (0.0, 100.0, 100.0, 200.0),
    }
    for zone_id, (x_min, x_max, y_min, y_max) in cells.items():
        initial.append(
            _record(
                "zone",
                f"zone:{zone_id}",
                _timestamp(minutes=-120),
                _timestamp(minutes=-119),
                {
                    "max_distance_squared": 3_600.0,
                    "x_max": x_max,
                    "x_min": x_min,
                    "y_max": y_max,
                    "y_min": y_min,
                    "zone_id": zone_id,
                },
            )
        )

    switch_plan = {
        "cell-amber": [(-60, "control"), (75, "treatment")],
        "cell-cobalt": [(-60, "treatment"), (75, "control")],
        "cell-jade": [(-60, "control"), (45, "treatment")],
    }
    for zone_id, states in switch_plan.items():
        for position, (minute, arm) in enumerate(states):
            effective_at = _timestamp(minutes=minute)
            initial.append(
                _record(
                    "switch_state",
                    f"state:{zone_id}:{position}",
                    effective_at,
                    _timestamp(minutes=minute, seconds=20),
                    {
                        "arm": arm,
                        "effective_at": effective_at,
                        "zone_id": zone_id,
                    },
                )
            )

    zone_ids = tuple(cells)
    first_request: Record | None = None
    terminal_plan = {
        1: ("completed", 28, True),
        2: ("cancelled", 25, False),
        3: ("completed", 31, False),
        4: ("cancelled", 27, True),
        5: ("completed", 30, True),
        6: ("cancelled", 24, False),
        7: ("cancelled", 33, True),
        8: ("completed", 29, False),
    }

    for number in range(1, 13):
        delivery_id = f"delivery-{number:03d}"
        request_minute = (number - 1) * 15
        zone_id = zone_ids[(number - 1) % len(zone_ids)]
        x_min, x_max, y_min, y_max = cells[zone_id]
        pickup_x = x_min + 18.0 + rng.randint(0, 42)
        pickup_y = y_min + 18.0 + rng.randint(0, 42)
        dropoff_x = min(x_max - 4.0, pickup_x + rng.randint(8, 28))
        dropoff_y = min(y_max - 4.0, pickup_y + rng.randint(8, 28))

        if number == 6:
            pickup_x = x_max + 8.0
        if number == 8:
            pickup_x, pickup_y = x_min + 12.0, y_min + 12.0
            dropoff_x, dropoff_y = x_max - 3.0, y_max - 3.0

        request = _delivery_event(
            delivery_id,
            "request",
            "requested",
            request_minute,
            zone_id=zone_id,
            pickup_x=pickup_x,
            pickup_y=pickup_y,
            dropoff_x=dropoff_x,
            dropoff_y=dropoff_y,
        )
        initial.append(request)
        if first_request is None:
            first_request = request

        initial.append(
            _delivery_event(
                delivery_id,
                "attempt-1",
                "dispatch_attempt",
                request_minute + 1,
            )
        )
        initial.append(
            _delivery_event(
                delivery_id,
                "accept-1",
                "dispatch_accepted",
                request_minute + 3,
            )
        )

        if number == 3:
            initial.append(
                _delivery_event(
                    delivery_id,
                    "revoke-1",
                    "dispatch_revoked",
                    request_minute + 4,
                )
            )
            initial.append(
                _delivery_event(
                    delivery_id,
                    "accept-2",
                    "dispatch_accepted",
                    request_minute + 6,
                )
            )
        if number == 5:
            initial.append(
                _delivery_event(
                    delivery_id,
                    "accept-2",
                    "dispatch_accepted",
                    request_minute + 5,
                )
            )

        if number in terminal_plan:
            kind, offset, is_batched = terminal_plan[number]
            initial.append(
                _delivery_event(
                    delivery_id,
                    "terminal",
                    kind,
                    request_minute + offset,
                    is_batched=is_batched,
                )
            )

    if first_request is not None:
        initial.append(dict(first_request))

    initial_ledger = {
        1: [("base", "base", 1_000), ("adjustment", "adjustment", 100)],
        2: [("base", "base", 900), ("reversal", "reversal", -900)],
        3: [("base", "base", 1_200)],
        4: [("base", "base", 800), ("reversal", "reversal", -800)],
        5: [("base", "base", 1_100), ("adjustment", "adjustment", -50)],
        6: [("base", "base", 950), ("reversal", "reversal", -950)],
        7: [("base", "base", 1_000), ("reversal", "reversal", -875)],
        8: [("base", "base", 1_050)],
    }
    for number, entries in initial_ledger.items():
        delivery_id = f"delivery-{number:03d}"
        minute = (number - 1) * 15 + 34
        for position, (entry_key, entry_type, amount) in enumerate(entries):
            reference = f"ledger:{delivery_id}:base" if entry_type == "reversal" else None
            initial.append(
                _ledger_entry(
                    delivery_id,
                    entry_key,
                    entry_type,
                    amount,
                    minute + position,
                    reference_entry_key=reference,
                )
            )

    late.extend(
        [
            _delivery_event(
                "delivery-004",
                "terminal",
                "completed",
                72,
                recorded_minute=230,
                version=2,
                is_batched=True,
            ),
            _ledger_entry(
                "delivery-004",
                "reversal",
                "adjustment",
                0,
                76,
                recorded_minute=231,
                version=2,
            ),
            _delivery_event(
                "delivery-009",
                "terminal",
                "completed",
                149,
                recorded_minute=310,
                is_batched=True,
            ),
            _ledger_entry("delivery-009", "base", "base", 1_150, 151, recorded_minute=311),
            _delivery_event(
                "delivery-010",
                "terminal",
                "cancelled",
                163,
                recorded_minute=325,
                is_batched=False,
            ),
            _ledger_entry("delivery-010", "base", "base", 980, 165, recorded_minute=326),
            _ledger_entry(
                "delivery-010",
                "reversal",
                "reversal",
                -980,
                166,
                recorded_minute=327,
                reference_entry_key="ledger:delivery-010:base",
            ),
            _delivery_event(
                "delivery-011",
                "terminal",
                "completed",
                178,
                recorded_minute=340,
                is_batched=False,
            ),
            _ledger_entry("delivery-011", "base", "base", 1_020, 180, recorded_minute=341),
        ]
    )

    rng.shuffle(initial)
    rng.shuffle(late)
    return initial, late


def _write_jsonl(path: Path, records: list[Record]) -> None:
    body = "".join(
        json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        for record in records
    )
    path.write_text(body, encoding="utf-8")


def generate_batches(output_dir: str | Path, seed: int = 734_021) -> dict[str, Path]:
    """Write two stable JSONL batches and return their paths."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    initial, late = build_records(seed)
    paths = {
        "initial": destination / "batch_initial.jsonl",
        "late": destination / "batch_late.jsonl",
    }
    _write_jsonl(paths["initial"], initial)
    _write_jsonl(paths["late"], late)
    return paths
