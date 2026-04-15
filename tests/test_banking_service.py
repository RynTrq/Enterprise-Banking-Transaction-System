from __future__ import annotations

import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from banking.domain import (  # noqa: E402
    AccountClosedError,
    DuplicateRequestError,
    InsufficientFundsError,
    ValidationError,
)
from banking.service import BankingService  # noqa: E402
from banking.store import JsonBankingStore  # noqa: E402


class BankingServiceTests(unittest.TestCase):
    def make_service(self, directory: str) -> BankingService:
        return BankingService(JsonBankingStore(Path(directory) / "bank.json"))

    def test_create_account_records_opening_balance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bank = self.make_service(directory)

            account = bank.create_account("Ada Lovelace", "125.456", "usd")

            self.assertEqual(account.owner_name, "Ada Lovelace")
            self.assertEqual(account.balance, Decimal("125.46"))
            self.assertEqual(account.currency, "USD")
            transactions = bank.list_transactions(account.id)
            self.assertEqual(len(transactions), 1)
            self.assertEqual(transactions[0].amount, Decimal("125.46"))

    def test_transfer_is_atomic_and_records_single_ledger_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bank = self.make_service(directory)
            source = bank.create_account("Grace Hopper", "100.00")
            destination = bank.create_account("Katherine Johnson", "25.00")

            transaction = bank.transfer(source.id, destination.id, "40.00", "Invoice 100")

            self.assertEqual(transaction.source_account_id, source.id)
            self.assertEqual(transaction.destination_account_id, destination.id)
            self.assertEqual(bank.get_account(source.id).balance, Decimal("60.00"))
            self.assertEqual(bank.get_account(destination.id).balance, Decimal("65.00"))
            self.assertEqual(
                [item.type.value for item in bank.list_transactions()],
                ["deposit", "deposit", "transfer"],
            )

    def test_withdraw_rejects_overdraft_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bank = self.make_service(directory)
            account = bank.create_account("Mary Jackson", "10.00")

            with self.assertRaises(InsufficientFundsError):
                bank.withdraw(account.id, "10.01")

            self.assertEqual(bank.get_account(account.id).balance, Decimal("10.00"))
            self.assertEqual(len(bank.list_transactions(account.id)), 1)

    def test_idempotency_key_returns_original_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bank = self.make_service(directory)
            account = bank.create_account("Dorothy Vaughan")

            first = bank.deposit(account.id, "15", idempotency_key="request-123")
            second = bank.deposit(account.id, "15.00", idempotency_key="request-123")

            self.assertEqual(second.id, first.id)
            self.assertEqual(bank.get_account(account.id).balance, Decimal("15.00"))
            self.assertEqual(len(bank.list_transactions(account.id)), 1)

    def test_idempotency_key_rejects_different_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bank = self.make_service(directory)
            account = bank.create_account("Annie Easley")
            bank.deposit(account.id, "15", idempotency_key="request-123")

            with self.assertRaises(DuplicateRequestError):
                bank.deposit(account.id, "20", idempotency_key="request-123")

            self.assertEqual(bank.get_account(account.id).balance, Decimal("15.00"))

    def test_closed_accounts_cannot_be_mutated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bank = self.make_service(directory)
            account = bank.create_account("Hedy Lamarr")
            closed = bank.close_account(account.id)

            self.assertEqual(closed.status.value, "closed")
            with self.assertRaises(AccountClosedError):
                bank.deposit(account.id, "1")

    def test_rejects_invalid_money_and_self_transfer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bank = self.make_service(directory)
            account = bank.create_account("Barbara Liskov")

            with self.assertRaises(ValidationError):
                bank.deposit(account.id, "0")

            with self.assertRaises(ValidationError):
                bank.transfer(account.id, account.id, "1")


if __name__ == "__main__":
    unittest.main()
