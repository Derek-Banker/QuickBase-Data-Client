"""Safely preview or run a small Quickbase upsert-records request."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.common import (
    add_common_arguments,
    load_credentials,
    print_dry_run,
    require_real_credentials,
)
from quickbase_data_client import Auth, QuickBaseClient

DEFAULT_RECORD = {"6": {"value": "Example"}, "7": {"value": 1}}


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser)
    parser.add_argument("--table-id", default=os.getenv("QUICKBASE_TEST_TABLE_ID"))
    parser.add_argument(
        "--confirm-upsert",
        action="store_true",
        help="Required with --execute because this writes records.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the upsert-records example."""
    parser = build_parser()
    args = parser.parse_args(argv)
    realm, user_token = load_credentials(args)

    if not args.table_id:
        raise SystemExit("--table-id or QUICKBASE_TEST_TABLE_ID is required.")

    if not args.execute:
        print_dry_run(
            "upsert_records",
            {
                "table_id": args.table_id,
                "records": [DEFAULT_RECORD],
                "execute": False,
            },
        )
        return 0

    if not args.confirm_upsert:
        raise SystemExit("Live upserts require both --execute and --confirm-upsert.")

    realm, user_token = require_real_credentials(realm, user_token)
    table = QuickBaseClient(Auth(realm, user_token)).table(id=args.table_id)
    response = table.upsert_records([DEFAULT_RECORD])
    print(f"status: {response.status_code}")
    print(f"metadata: {response.metadata}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
