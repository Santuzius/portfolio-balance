"""ViewModel for portfolio-level CRUD operations."""

from __future__ import annotations

import pandas as pd
from app.models.repositories import PortfolioRepo, PlatformRepo


class PortfolioVM:
    """Manage portfolios and their platforms."""

    # ── Portfolio CRUD ──────────────────────────────────────────────

    @staticmethod
    def list_portfolios() -> pd.DataFrame:
        return PortfolioRepo.list_all()

    @staticmethod
    def get_portfolio(portfolio_id: int) -> dict | None:
        row = PortfolioRepo.get(portfolio_id)
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "status": row[2]}

    @staticmethod
    def create_portfolio(name: str, status: str = "Running") -> int:
        return PortfolioRepo.create(name, status)

    @staticmethod
    def update_portfolio(portfolio_id: int, name: str, status: str) -> None:
        PortfolioRepo.update(portfolio_id, name, status)

    @staticmethod
    def delete_portfolio(portfolio_id: int) -> None:
        PortfolioRepo.delete_cascade(portfolio_id)

    @staticmethod
    def copy_portfolio(source_id: int, new_name: str) -> int:
        return PortfolioRepo.copy(source_id, new_name)

    # ── Platform CRUD ───────────────────────────────────────────────

    @staticmethod
    def list_platforms(portfolio_id: int, include_inactive: bool = True) -> pd.DataFrame:
        """List platforms sorted by status then by latest balance descending.

        If include_inactive is False, platforms with status Closed/Defaulted
        AND 0 balance are excluded.
        """
        df = PlatformRepo.list_for_portfolio(portfolio_id)
        if not include_inactive:
            df = df[
                ~(
                    (df["status"].isin(["Closed", "Defaulted"]))
                    & (df["latest_balance"] == 0)
                )
            ]
        return df

    @staticmethod
    def create_platform(
        portfolio_id: int, name: str, status: str = "Running",
    ) -> int:
        return PlatformRepo.create(portfolio_id, name, status)

    @staticmethod
    def update_platform(platform_id: int, name: str, status: str) -> None:
        PlatformRepo.update(platform_id, name, status)

    @staticmethod
    def delete_platform(platform_id: int) -> None:
        PlatformRepo.delete_cascade(platform_id)
