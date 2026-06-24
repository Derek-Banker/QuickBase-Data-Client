"""Safely preview or run a Quickbase query-records request."""

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
    parse_select,
    print_dry_run,
    require_real_credentials,
)
from quickbase_data_client import Auth, QuickBaseClient


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser)
    parser.add_argument("--table-id", default=os.getenv("QUICKBASE_TEST_TABLE_ID"))
    parser.add_argument("--where", default=os.getenv("QUICKBASE_TEST_QUERY", "{3.GT.0}"))
    parser.add_argument("--select", default=os.getenv("QUICKBASE_TEST_SELECT"))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the query-records example."""
    parser = build_parser()
    args = parser.parse_args(argv)
    realm, user_token = load_credentials(args)
    select = parse_select(args.select)

    if not args.table_id:
        raise SystemExit("--table-id or QUICKBASE_TEST_TABLE_ID is required.")

    if not args.execute:
        print_dry_run(
            "query_records",
            {
                "table_id": args.table_id,
                "where": args.where,
                "select": select,
                "execute": False,
            },
        )
        return 0

    realm, user_token = require_real_credentials(realm, user_token)
    table = QuickBaseClient(Auth(realm, user_token)).table(id=args.table_id)
    response = table.query_records(args.where, select=select)
    print(f"status: {response.status_code}")
    print(f"records: {len(response.data)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
