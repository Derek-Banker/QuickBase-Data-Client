"""Shared helpers for safe Quickbase example scripts."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Dict

PLACEHOLDER_VALUES = {
    "",
    "example.quickbase.com",
    "qb-user-token",
    "your-token",
    "your-user-token",
}


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs from an explicit environment file."""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared authentication and safety arguments to an example parser."""
    parser.add_argument("--env-file", type=Path, help="Optional environment file to load.")
    parser.add_argument("--realm", help="Quickbase realm hostname.")
    parser.add_argument("--user-token", help="Quickbase user token.")
    parser.add_argument("--execute", action="store_true", help="Run the live Quickbase request.")


def load_credentials(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Load credentials from explicit arguments or environment variables."""
    if args.env_file is not None:
        load_env_file(args.env_file)
    realm = args.realm or os.getenv("QUICKBASE_REALM")
    user_token = args.user_token or os.getenv("QUICKBASE_USER_TOKEN")
    return realm, user_token


def require_real_credentials(realm: str | None, user_token: str | None) -> tuple[str, str]:
    """Return credentials after rejecting missing or placeholder values."""
    normalized_realm = (realm or "").strip()
    normalized_token = (user_token or "").strip()
    if normalized_realm in PLACEHOLDER_VALUES or normalized_token in PLACEHOLDER_VALUES:
        raise SystemExit(
            "Live execution requires real QUICKBASE_REALM and QUICKBASE_USER_TOKEN values."
        )
    return normalized_realm, normalized_token


def parse_select(value: str | None) -> list[int] | None:
    """Parse a comma-separated Quickbase field-id list."""
    if not value:
        return None
    return [int(segment.strip()) for segment in value.split(",") if segment.strip()]


def print_dry_run(title: str, payload: Dict[str, object]) -> None:
    """Print a consistent dry-run summary."""
    print(f"{title} dry run")
    for key, value in payload.items():
        print(f"{key}: {value}")
