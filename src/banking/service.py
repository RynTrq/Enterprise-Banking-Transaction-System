"""Business operations for accounts and transactions."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union

from banking.domain import (
    Account,
    AccountNotFoundError,
    DuplicateRequestError,
    InsufficientFundsError,
    Money,
    Transaction,
    TransactionType,
    ValidationError,
)
from banking.store import BankState, JsonBankingStore


class BankingService:
    """Coordinates validation, account mutation, ledger recording, and storage."""

    def __init__(self, store: JsonBankingStore) -> None:
        self.store = store

    def create_account(
        self,
        owner_name: str,
        opening_balance: Union[Decimal, int, str] = "0.00",
        currency: str = "USD",
    ) -> Account:
        state = self.store.load()
        account = Account.create(owner_name, opening_balance, currency)
        state.accounts[account.id] = account

        if account.balance > Decimal("0.00"):
            transaction = Transaction.create(
                transaction_type=TransactionType.DEPOSIT,
                amount=account.balance,
                currency=account.currency,
                source_account_id=None,
                destination_account_id=account.id,
                description="Opening balance",
            )
            state.transactions.append(transaction)

        self.store.save(state)
        return account

    def list_accounts(self) -> list[Account]:
        state = self.store.load()
        return sorted(state.accounts.values(), key=lambda account: account.created_at)

    def get_account(self, account_id: str) -> Account:
        return self._get_account(self.store.load(), account_id)

    def close_account(self, account_id: str) -> Account:
        state = self.store.load()
        account = self._get_account(state, account_id)
        closed = account.close()
        state.accounts[closed.id] = closed
        self.store.save(state)
        return closed

    def deposit(
        self,
        account_id: str,
        amount: Union[Decimal, int, str],
        description: str = "",
        idempotency_key: Optional[str] = None,
    ) -> Transaction:
        state = self.store.load()
        account = self._get_account(state, account_id)
        account.ensure_active()
        money = Money.positive(amount)

        transaction = Transaction.create(
            transaction_type=TransactionType.DEPOSIT,
            amount=money.value,
            currency=account.currency,
            source_account_id=None,
            destination_account_id=account.id,
            description=description,
            idempotency_key=idempotency_key,
        )
        existing = self._idempotent_match(state, transaction)
        if existing:
            return existing

        state.accounts[account.id] = account.with_balance(account.balance + money.value)
        state.transactions.append(transaction)
        self.store.save(state)
        return transaction

    def withdraw(
        self,
        account_id: str,
        amount: Union[Decimal, int, str],
        description: str = "",
        idempotency_key: Optional[str] = None,
    ) -> Transaction:
        state = self.store.load()
        account = self._get_account(state, account_id)
        account.ensure_active()
        money = Money.positive(amount)
        if account.balance < money.value:
            raise InsufficientFundsError("Withdrawal exceeds available balance.")

        transaction = Transaction.create(
            transaction_type=TransactionType.WITHDRAWAL,
            amount=money.value,
            currency=account.currency,
            source_account_id=account.id,
            destination_account_id=None,
            description=description,
            idempotency_key=idempotency_key,
        )
        existing = self._idempotent_match(state, transaction)
        if existing:
            return existing

        state.accounts[account.id] = account.with_balance(account.balance - money.value)
        state.transactions.append(transaction)
        self.store.save(state)
        return transaction

    def transfer(
        self,
        source_account_id: str,
        destination_account_id: str,
        amount: Union[Decimal, int, str],
        description: str = "",
        idempotency_key: Optional[str] = None,
    ) -> Transaction:
        if source_account_id == destination_account_id:
            raise ValidationError("Source and destination accounts must differ.")

        state = self.store.load()
        source = self._get_account(state, source_account_id)
        destination = self._get_account(state, destination_account_id)
        source.ensure_active()
        destination.ensure_active()

        if source.currency != destination.currency:
            raise ValidationError("Transfers require matching account currencies.")

        money = Money.positive(amount)
        if source.balance < money.value:
            raise InsufficientFundsError("Transfer exceeds available balance.")

        transaction = Transaction.create(
            transaction_type=TransactionType.TRANSFER,
            amount=money.value,
            currency=source.currency,
            source_account_id=source.id,
            destination_account_id=destination.id,
            description=description,
            idempotency_key=idempotency_key,
        )
        existing = self._idempotent_match(state, transaction)
        if existing:
            return existing

        state.accounts[source.id] = source.with_balance(source.balance - money.value)
        state.accounts[destination.id] = destination.with_balance(
            destination.balance + money.value
        )
        state.transactions.append(transaction)
        self.store.save(state)
        return transaction

    def list_transactions(self, account_id: Optional[str] = None) -> list[Transaction]:
        state = self.store.load()
        transactions = state.transactions
        if account_id is not None:
            transactions = [
                transaction
                for transaction in transactions
                if transaction.source_account_id == account_id
                or transaction.destination_account_id == account_id
            ]
        return transactions

    @staticmethod
    def _get_account(state: BankState, account_id: str) -> Account:
        account = state.accounts.get(account_id)
        if account is None:
            raise AccountNotFoundError(f"Account {account_id} was not found.")
        return account

    @staticmethod
    def _idempotent_match(
        state: BankState, candidate: Transaction
    ) -> Optional[Transaction]:
        if candidate.idempotency_key is None:
            return None

        for transaction in state.transactions:
            if transaction.idempotency_key != candidate.idempotency_key:
                continue
            if transaction.fingerprint() != candidate.fingerprint():
                raise DuplicateRequestError(
                    "Idempotency key was already used for a different transaction."
                )
            return transaction

        return None
