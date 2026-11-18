"""Fixed credit top-up packages parsed from ``TOPUP_PACKAGES``.

Format: ``name:credits:price_cents[,name:credits:price_cents]``. Prices are
always in the smallest currency unit (e.g. cents for USD); the server never
accepts a client-supplied amount.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


@dataclass(frozen=True)
class TopUpPackage:
    name: str
    credits: int
    price_cents: int
    currency: str = "usd"


def parse_packages(raw: str) -> list[TopUpPackage]:
    packages: list[TopUpPackage] = []
    seen: set[str] = set()
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3:
            raise ValueError(f"invalid TOPUP_PACKAGES entry: {item!r}")
        name, credits_raw, price_raw = (part.strip() for part in parts)
        if not _NAME_RE.match(name):
            raise ValueError(f"invalid top-up package name: {name!r}")
        if name in seen:
            raise ValueError(f"duplicate top-up package: {name!r}")
        credits, price_cents = int(credits_raw), int(price_raw)
        if credits <= 0 or price_cents <= 0:
            raise ValueError(f"top-up amounts must be positive: {item!r}")
        seen.add(name)
        packages.append(TopUpPackage(name=name, credits=credits, price_cents=price_cents))
    return packages


def find_package(packages: list[TopUpPackage], name: str) -> TopUpPackage | None:
    return next((package for package in packages if package.name == name), None)
