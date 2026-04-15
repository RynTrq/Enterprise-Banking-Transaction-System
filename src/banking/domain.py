"""Domain records and validation helpers for banking operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any, Optional, Tuple, Union
from uuid import uuid4

MONEY_QUANT = Decimal("0.01")


class BankingError(Exception):
    """Base exception for expected banking failures."""


class ValidationError(BankingError):
    """Raised when user-supplied data is invalid."""


class AccountNotFoundError(BankingError):
    """Raised when an account cannot be found."""


class AccountClosedError(BankingError):
    """Raised when a mutating operation targets a closed account."""


class InsufficientFundsError(BankingError):
    """Raised when a debit would exceed the account balance."""


class DuplicateRequestError(BankingError):
    """Raised when an idempotency key is reused for a different operation."""


class AccountStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class Money:
    """Validated two-decimal-place money value."""

    def __init__(self, value: Union[Decimal, int, str]) -> None:
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError(f"Invalid monetary amount: {value!r}") from exc

        if not decimal.is_finite():
            raise ValidationError("Monetary amounts must be finite.")

        self.value = decimal.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    @classmethod
    def positive(cls, value: Union[Decimal, int, str]) -> "Money":
        money = cls(value)
        if money.value <= Decimal("0.00"):
            raise ValidationError("Amount must be greater than zero.")
        return money

    def __str__(self) -> str:
        return f"{self.value:.2f}"


@dataclass(frozen=True)
class Account:
    id: str
    owner_name: str
    balance: Decimal
    currency: str
    status: AccountStatus
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        owner_name: str,
        opening_balance: Union[Decimal, int, str] = "0.00",
        currency: str = "USD",
    ) -> "Account":
        owner = owner_name.strip()
        if len(owner) < 2:
            raise ValidationError("Owner name must contain at least two characters.")

        normalized_currency = currency.strip().upper()
        if len(normalized_currency) != 3 or not normalized_currency.isalpha():
            raise ValidationError("Currency must be a three-letter ISO code.")

        balance = Money(opening_balance).value
        if balance < Decimal("0.00"):
            raise ValidationError("Opening balance cannot be negative.")

        timestamp = now_utc()
        return cls(
            id=new_id("acct"),
            owner_name=owner,
            balance=balance,
            currency=normalized_currency,
            status=AccountStatus.ACTIVE,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def ensure_active(self) -> None:
        if self.status is AccountStatus.CLOSED:
            raise AccountClosedError(f"Account {self.id} is closed.")

    def with_balance(self, balance: Decimal) -> "Account":
        return Account(
            id=self.id,
            owner_name=self.owner_name,
            balance=balance.quantize(MONEY_QUANT),
            currency=self.currency,
            status=self.status,
            created_at=self.created_at,
            updated_at=now_utc(),
        )

    def close(self) -> "Account":
        self.ensure_active()
        if self.balance != Decimal("0.00"):
            raise ValidationError("Only zero-balance accounts can be closed.")

        return Account(
            id=self.id,
            owner_name=self.owner_name,
            balance=self.balance,
            currency=self.currency,
            status=AccountStatus.CLOSED,
            created_at=self.created_at,
            updated_at=now_utc(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_name": self.owner_name,
            "balance": str(self.balance),
            "currency": self.currency,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Account":
        return cls(
            id=str(payload["id"]),
            owner_name=str(payload["owner_name"]),
            balance=Money(payload["balance"]).value,
            currency=str(payload["currency"]).upper(),
            status=AccountStatus(payload["status"]),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )


@dataclass(frozen=True)
class Transaction:
    id: str
    type: TransactionType
    amount: Decimal
    currency: str
    source_account_id: Optional[str]
    destination_account_id: Optional[str]
    description: str
    idempotency_key: Optional[str]
    created_at: str

    @classmethod
    def create(
        cls,
        transaction_type: TransactionType,
        amount: Decimal,
        currency: str,
        source_account_id: Optional[str],
        destination_account_id: Optional[str],
        description: str = "",
        idempotency_key: Optional[str] = None,
    ) -> "Transaction":
        return cls(
            id=new_id("txn"),
            type=transaction_type,
            amount=Money.positive(amount).value,
            currency=currency.upper(),
            source_account_id=source_account_id,
            destination_account_id=destination_account_id,
            description=description.strip(),
            idempotency_key=idempotency_key.strip() if idempotency_key else None,
            created_at=now_utc(),
        )

    def fingerprint(self) -> Tuple[Any, ...]:
        return (
            self.type.value,
            str(self.amount),
            self.currency,
            self.source_account_id,
            self.destination_account_id,
            self.description,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "amount": str(self.amount),
            "currency": self.currency,
            "source_account_id": self.source_account_id,
            "destination_account_id": self.destination_account_id,
            "description": self.description,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Transaction":
        return cls(
            id=str(payload["id"]),
            type=TransactionType(payload["type"]),
            amount=Money.positive(payload["amount"]).value,
            currency=str(payload["currency"]).upper(),
            source_account_id=payload.get("source_account_id"),
            destination_account_id=payload.get("destination_account_id"),
            description=str(payload.get("description", "")),
            idempotency_key=payload.get("idempotency_key"),
            created_at=str(payload["created_at"]),
        )
