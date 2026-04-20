"""Token wallet service — balance + ledger + quotas."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pi_ai_cloud.models import TokenLedger, TokenWallet
from app.shared.license.models import License


class InsufficientTokens(Exception):
    def __init__(self, balance: int, requested: int) -> None:
        super().__init__(f"Insufficient tokens: balance={balance}, need={requested}")
        self.balance = balance
        self.requested = requested


class WalletService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create(self, lic: License) -> TokenWallet:
        q = select(TokenWallet).where(TokenWallet.license_id == lic.id)
        result = await self.db.execute(q)
        wallet = result.scalar_one_or_none()
        if wallet is None:
            wallet = TokenWallet(
                license_id=lic.id,
                balance=0,
                lifetime_topup=0,
                lifetime_spend=0,
            )
            # Free tier bonus on first wallet creation
            if lic.tier == "free":
                wallet.balance = 1000
                wallet.lifetime_topup = 1000
            self.db.add(wallet)
            await self.db.flush()
            if wallet.balance > 0:
                self.db.add(
                    TokenLedger(
                        wallet_id=wallet.id,
                        op="bonus",
                        delta=wallet.balance,
                        balance_after=wallet.balance,
                        reference_type="signup_bonus",
                        note="Free tier signup bonus",
                    )
                )
                await self.db.flush()
        return wallet

    async def topup(
        self,
        wallet: TokenWallet,
        amount: int,
        *,
        op: str = "topup",
        reference_type: str = "",
        reference_id: str = "",
        note: str = "",
    ) -> TokenLedger:
        if amount <= 0:
            raise ValueError("Top-up amount must be positive")
        wallet.balance += amount
        wallet.lifetime_topup += amount
        wallet.last_activity_at = datetime.now(timezone.utc)

        entry = TokenLedger(
            wallet_id=wallet.id,
            op=op,
            delta=amount,
            balance_after=wallet.balance,
            reference_type=reference_type,
            reference_id=reference_id,
            note=note,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def spend(
        self,
        wallet: TokenWallet,
        amount: int,
        *,
        reference_type: str = "ai_usage",
        reference_id: str = "",
        note: str = "",
    ) -> TokenLedger:
        if amount <= 0:
            raise ValueError("Spend amount must be positive")
        if wallet.balance < amount:
            raise InsufficientTokens(wallet.balance, amount)

        wallet.balance -= amount
        wallet.lifetime_spend += amount
        wallet.last_activity_at = datetime.now(timezone.utc)

        entry = TokenLedger(
            wallet_id=wallet.id,
            op="spend",
            delta=-amount,
            balance_after=wallet.balance,
            reference_type=reference_type,
            reference_id=reference_id,
            note=note,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_ledger(
        self, wallet: TokenWallet, *, limit: int = 50, offset: int = 0
    ) -> list[TokenLedger]:
        q = (
            select(TokenLedger)
            .where(TokenLedger.wallet_id == wallet.id)
            .order_by(TokenLedger.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())


# Pricing catalog — what each "pack" gives the customer
TOPUP_PACKS: dict[str, tuple[int, int]] = {
    # pack_id → (pi_tokens, price_cents)
    "10k":  (10_000,    100),   # $1.00
    "100k": (100_000,   900),   # $9.00
    "500k": (500_000,   3500),  # $35 — 22% off
    "1m":   (1_000_000, 5900),  # $59 — 34% off
    "5m":   (5_000_000, 24900), # $249 — 44% off
}
