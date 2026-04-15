"""Atomic JSON persistence for accounts and ledger entries."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from banking.domain import Account, Transaction


@dataclass
class BankState:
    accounts: dict[str, Account] = field(default_factory=dict)
    transactions: list[Transaction] = field(default_factory=list)


class JsonBankingStore:
    """Small durable store with atomic writes.

    This store is intentionally local and simple. It gives the project a
    deterministic persistence boundary without pretending to replace a database.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    def load(self) -> BankState:
        if not self.path.exists():
            return BankState()

        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        accounts = {
            account["id"]: Account.from_dict(account)
            for account in payload.get("accounts", [])
        }
        transactions = [
            Transaction.from_dict(transaction)
            for transaction in payload.get("transactions", [])
        ]
        return BankState(accounts=accounts, transactions=transactions)

    def save(self, state: BankState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "accounts": [
                account.to_dict()
                for account in sorted(state.accounts.values(), key=lambda item: item.id)
            ],
            "transactions": [
                transaction.to_dict() for transaction in state.transactions
            ],
        }

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temp_name, self.path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
