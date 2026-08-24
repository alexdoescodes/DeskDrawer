"""Deadline arithmetic and the sweep that removes expired links.

This module never receives or constructs an origin path in a form it could
delete. It selects names and hands them to Store.remove, which unlinks a path
inside items/.
"""

from .store import Item, Store


def deadline(item: Item, lifetime_seconds: float) -> float:
    return item.last_activity + lifetime_seconds


def expired_names(items: dict[str, Item], now: float, lifetime_seconds: float) -> list[str]:
    return [
        name
        for name, item in sorted(items.items())
        if now > deadline(item, lifetime_seconds)
    ]


def sweep(store: Store, now: float, lifetime_seconds: float) -> list[str]:
    removed = []
    for name in expired_names(store.load(), now, lifetime_seconds):
        if store.remove(name):
            removed.append(name)
    return removed
