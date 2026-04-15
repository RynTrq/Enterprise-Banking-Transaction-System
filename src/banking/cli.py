"""Command-line interface for the banking transaction system."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from banking.domain import Account, BankingError, Transaction
from banking.service import BankingService
from banking.store import JsonBankingStore

DEFAULT_STORE_PATH = Path.home() / ".enterprise-banking" / "bank.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ebank",
        description="Manage local bank accounts and ledger transactions.",
    )
    parser.add_argument(
        "--store",
        default=os.environ.get("EBANK_STORE", str(DEFAULT_STORE_PATH)),
        help="Path to the JSON data store. Defaults to EBANK_STORE or ~/.enterprise-banking/bank.json.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text tables.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-account", help="Create an account.")
    create.add_argument("owner_name")
    create.add_argument("--opening-balance", default="0.00")
    create.add_argument("--currency", default="USD")

    subparsers.add_parser("list-accounts", help="List all accounts.")

    show = subparsers.add_parser("show-account", help="Show one account.")
    show.add_argument("account_id")

    close = subparsers.add_parser("close-account", help="Close a zero-balance account.")
    close.add_argument("account_id")

    deposit = subparsers.add_parser("deposit", help="Deposit funds.")
    deposit.add_argument("account_id")
    deposit.add_argument("amount")
    deposit.add_argument("--description", default="")
    deposit.add_argument("--idempotency-key")

    withdraw = subparsers.add_parser("withdraw", help="Withdraw funds.")
    withdraw.add_argument("account_id")
    withdraw.add_argument("amount")
    withdraw.add_argument("--description", default="")
    withdraw.add_argument("--idempotency-key")

    transfer = subparsers.add_parser("transfer", help="Transfer funds between accounts.")
    transfer.add_argument("source_account_id")
    transfer.add_argument("destination_account_id")
    transfer.add_argument("amount")
    transfer.add_argument("--description", default="")
    transfer.add_argument("--idempotency-key")

    ledger = subparsers.add_parser("ledger", help="List ledger transactions.")
    ledger.add_argument("--account-id")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = BankingService(JsonBankingStore(args.store))

    try:
        result = dispatch(args, service)
    except BankingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: failed to read or write store: {exc}", file=sys.stderr)
        return 3

    print(render(result, as_json=args.json))
    return 0


def dispatch(args: argparse.Namespace, service: BankingService) -> Any:
    if args.command == "create-account":
        return service.create_account(
            args.owner_name,
            opening_balance=args.opening_balance,
            currency=args.currency,
        )
    if args.command == "list-accounts":
        return service.list_accounts()
    if args.command == "show-account":
        return service.get_account(args.account_id)
    if args.command == "close-account":
        return service.close_account(args.account_id)
    if args.command == "deposit":
        return service.deposit(
            args.account_id,
            args.amount,
            description=args.description,
            idempotency_key=args.idempotency_key,
        )
    if args.command == "withdraw":
        return service.withdraw(
            args.account_id,
            args.amount,
            description=args.description,
            idempotency_key=args.idempotency_key,
        )
    if args.command == "transfer":
        return service.transfer(
            args.source_account_id,
            args.destination_account_id,
            args.amount,
            description=args.description,
            idempotency_key=args.idempotency_key,
        )
    if args.command == "ledger":
        return service.list_transactions(account_id=args.account_id)

    raise AssertionError(f"Unhandled command: {args.command}")


def render(result: Any, as_json: bool) -> str:
    if as_json:
        return json.dumps(to_jsonable(result), indent=2, sort_keys=True)

    if isinstance(result, Account):
        return account_table([result])
    if isinstance(result, Transaction):
        return transaction_table([result])
    if isinstance(result, list):
        if not result:
            return "No records found."
        if isinstance(result[0], Account):
            return account_table(result)
        if isinstance(result[0], Transaction):
            return transaction_table(result)

    return str(result)


def to_jsonable(result: Any) -> Any:
    if isinstance(result, (Account, Transaction)):
        return result.to_dict()
    if isinstance(result, list):
        return [to_jsonable(item) for item in result]
    return result


def account_table(accounts: list[Account]) -> str:
    rows = [
        ["ID", "OWNER", "BALANCE", "CURRENCY", "STATUS"],
        *[
            [
                account.id,
                account.owner_name,
                f"{account.balance:.2f}",
                account.currency,
                account.status.value,
            ]
            for account in accounts
        ],
    ]
    return format_table(rows)


def transaction_table(transactions: list[Transaction]) -> str:
    rows = [
        ["ID", "TYPE", "AMOUNT", "CURRENCY", "SOURCE", "DESTINATION", "CREATED"],
        *[
            [
                transaction.id,
                transaction.type.value,
                f"{transaction.amount:.2f}",
                transaction.currency,
                transaction.source_account_id or "-",
                transaction.destination_account_id or "-",
                transaction.created_at,
            ]
            for transaction in transactions
        ],
    ]
    return format_table(rows)


def format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    rendered = []
    for row_index, row in enumerate(rows):
        rendered.append(
            "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        )
        if row_index == 0:
            rendered.append("  ".join("-" * width for width in widths))
    return "\n".join(rendered)


if __name__ == "__main__":
    raise SystemExit(main())
