"""ViewModel for monthly balance tracking and deviation analysis."""

from __future__ import annotations

from datetime import date
import pandas as pd
from app.models.database import get_connection
from app.viewmodels.mcda_vm import ScoringVM


class BalanceVM:
    """Record and analyse monthly balance snapshots."""

    @staticmethod
    def record_balance(platform_id: int, month: date, balance: float) -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO balance_snapshots (platform_id, month, balance)
               VALUES (?, ?, ?)
               ON CONFLICT (platform_id, month)
               DO UPDATE SET balance = excluded.balance""",
            [int(platform_id), month, float(balance)],
        )

    @staticmethod
    def delete_balance(snapshot_id: int) -> None:
        con = get_connection()
        con.execute("DELETE FROM balance_snapshots WHERE id = ?", [int(snapshot_id)])

    @staticmethod
    def get_balances_for_portfolio(portfolio_id: int) -> pd.DataFrame:
        """All balance snapshots for a portfolio, joined with platform info."""
        con = get_connection()
        return con.execute(
            """SELECT bs.id, p.name AS platform, bs.month, bs.balance, p.id AS platform_id
               FROM balance_snapshots bs
               JOIN platforms p ON bs.platform_id = p.id
               WHERE p.portfolio_id = ?
               ORDER BY bs.month DESC, p.name""",
            [portfolio_id],
        ).fetchdf()

    @staticmethod
    def get_latest_balances(portfolio_id: int) -> pd.DataFrame:
        """Get latest balance per platform."""
        con = get_connection()
        return con.execute(
            """SELECT p.id AS platform_id, p.name AS platform, p.status,
                      bs.balance, bs.month
               FROM platforms p
               LEFT JOIN (
                   SELECT platform_id, balance, month
                   FROM balance_snapshots
                   WHERE (platform_id, month) IN (
                       SELECT platform_id, MAX(month)
                       FROM balance_snapshots
                       GROUP BY platform_id
                   )
               ) bs ON p.id = bs.platform_id
               WHERE p.portfolio_id = ?
               ORDER BY p.name""",
            [portfolio_id],
        ).fetchdf()

    @staticmethod
    def compute_deviation(
        portfolio_id: int,
        rebalance_statuses: set[str] | None = None,
    ) -> pd.DataFrame:
        """Compare latest balances against MCDA target allocation.

        Parameters
        ----------
        rebalance_statuses
            Platform statuses that participate in rebalancing.  Platforms
            whose status is **not** in this set have their *entire* balance
            added to off-budget (i.e. excluded from the effective total and
            target calculation).  ``None`` means only ``{"Running"}``.

        Returns DataFrame with:
            platform, status, latest_balance, pct_allocation,
            target_value, deviation, off_budget_total
        """
        if rebalance_statuses is None:
            rebalance_statuses = {"Running"}

        latest = BalanceVM.get_latest_balances(portfolio_id)
        allocation = ScoringVM.compute_allocation(portfolio_id)

        if latest.empty or allocation.empty:
            return pd.DataFrame(
                columns=[
                    "platform", "status", "latest_balance", "pct_allocation",
                    "target_value", "deviation", "off_budget_total",
                ]
            )

        con = get_connection()

        # Total portfolio balance (excluding off-budget)
        total_balance = latest["balance"].fillna(0).sum()

        # Get off-budget totals per platform (from pockets table)
        off_budget = con.execute(
            """SELECT p.id AS platform_id, COALESCE(SUM(ob.amount), 0) AS off_budget_total
               FROM platforms p
               LEFT JOIN off_budget_pockets ob ON p.id = ob.platform_id
               WHERE p.portfolio_id = ?
               GROUP BY p.id""",
            [portfolio_id],
        ).fetchdf()

        # Merge
        merged = latest.merge(
            allocation[["platform_id", "pct_allocation", "status"]],
            on="platform_id",
            how="left",
            suffixes=("", "_alloc"),
        )
        merged = merged.merge(off_budget, on="platform_id", how="left")
        merged["off_budget_total"] = merged["off_budget_total"].fillna(0)

        # Platforms whose status is NOT selected for rebalancing:
        # their full balance is treated as off-budget.
        not_rebal = ~merged["status"].isin(rebalance_statuses)
        merged.loc[not_rebal, "off_budget_total"] = merged.loc[
            not_rebal, "balance"
        ].fillna(0)

        # Effective balance = balance - off_budget
        effective_total = total_balance - merged["off_budget_total"].sum()

        merged["target_value"] = merged["pct_allocation"].fillna(0) * effective_total
        merged["latest_balance"] = merged["balance"].fillna(0)
        merged["deviation"] = merged["latest_balance"] - merged["off_budget_total"] - merged["target_value"]

        return merged[
            ["platform", "status", "latest_balance", "pct_allocation",
             "target_value", "deviation", "off_budget_total"]
        ]


class PocketVM:
    """Manage off-budget pockets."""

    @staticmethod
    def list_pockets(platform_id: int) -> pd.DataFrame:
        con = get_connection()
        return con.execute(
            "SELECT id, name, amount, note FROM off_budget_pockets WHERE platform_id = ? ORDER BY name",
            [int(platform_id)],
        ).fetchdf()

    @staticmethod
    def create_pocket(platform_id: int, name: str, amount: float, note: str = "") -> int:
        con = get_connection()
        con.execute(
            "INSERT INTO off_budget_pockets (platform_id, name, amount, note) VALUES (?, ?, ?, ?)",
            [int(platform_id), name, float(amount), note],
        )
        return con.execute("SELECT currval('seq_pocket')").fetchone()[0]

    @staticmethod
    def update_pocket(pocket_id: int, name: str, amount: float, note: str = "") -> None:
        con = get_connection()
        con.execute(
            "UPDATE off_budget_pockets SET name = ?, amount = ?, note = ? WHERE id = ?",
            [name, float(amount), note, int(pocket_id)],
        )

    @staticmethod
    def delete_pocket(pocket_id: int) -> None:
        con = get_connection()
        con.execute("DELETE FROM off_budget_pockets WHERE id = ?", [int(pocket_id)])


class LoanOriginatorVM:
    """Manage loan originators per platform."""

    @staticmethod
    def list_originators(platform_id: int) -> pd.DataFrame:
        con = get_connection()
        return con.execute(
            """SELECT id, country, originator_name, num_loans, note
               FROM loan_originators WHERE platform_id = ? ORDER BY country""",
            [int(platform_id)],
        ).fetchdf()

    @staticmethod
    def save_originator(
        platform_id: int, country: str, originator_name: str, num_loans: float, note: str = ""
    ) -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO loan_originators (platform_id, country, originator_name, num_loans, note)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (platform_id, country, originator_name)
               DO UPDATE SET num_loans = excluded.num_loans, note = excluded.note""",
            [int(platform_id), country, originator_name, float(num_loans), note],
        )

    @staticmethod
    def delete_originator(originator_id: int) -> None:
        con = get_connection()
        con.execute("DELETE FROM loan_originators WHERE id = ?", [int(originator_id)])


class InterestRateVM:
    """Manage interest rate data per platform."""

    @staticmethod
    def get_rates(portfolio_id: int) -> pd.DataFrame:
        con = get_connection()
        return con.execute(
            """SELECT p.id AS platform_id, p.name AS platform,
                      COALESCE(ir.estimated_rate, 0) AS estimated_rate
               FROM platforms p
               LEFT JOIN interest_rates ir ON p.id = ir.platform_id
               WHERE p.portfolio_id = ?
               ORDER BY p.name""",
            [portfolio_id],
        ).fetchdf()

    @staticmethod
    def save_rate(platform_id: int, estimated_rate: float) -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO interest_rates (platform_id, estimated_rate)
               VALUES (?, ?)
               ON CONFLICT (platform_id)
               DO UPDATE SET estimated_rate = excluded.estimated_rate""",
            [int(platform_id), float(estimated_rate)],
        )


class CountryStatusVM:
    """Manage country statuses."""

    @staticmethod
    def list_statuses(platform_id: int | None = None) -> pd.DataFrame:
        con = get_connection()
        if platform_id is not None:
            return con.execute(
                """SELECT cs.id, p.name AS platform, cs.country, cs.status, cs.note
                   FROM country_statuses cs
                   LEFT JOIN platforms p ON cs.platform_id = p.id
                   WHERE cs.platform_id = ?
                   ORDER BY cs.country""",
                [int(platform_id)],
            ).fetchdf()
        return con.execute(
            """SELECT cs.id, p.name AS platform, cs.country, cs.status, cs.note
               FROM country_statuses cs
               LEFT JOIN platforms p ON cs.platform_id = p.id
               ORDER BY cs.country, p.name"""
        ).fetchdf()

    @staticmethod
    def save_status(platform_id: int | None, country: str, status: str, note: str = "") -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO country_statuses (platform_id, country, status, note)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (platform_id, country)
               DO UPDATE SET status = excluded.status, note = excluded.note""",
            [int(platform_id) if platform_id is not None else None, country, status, note],
        )

    @staticmethod
    def update_status(status_id: int, new_status: str, note: str | None = None) -> None:
        """Update just the status (and optionally note) of an existing entry."""
        con = get_connection()
        if note is not None:
            con.execute(
                "UPDATE country_statuses SET status = ?, note = ? WHERE id = ?",
                [new_status, note, int(status_id)],
            )
        else:
            con.execute(
                "UPDATE country_statuses SET status = ? WHERE id = ?",
                [new_status, int(status_id)],
            )

    @staticmethod
    def delete_status(status_id: int) -> None:
        con = get_connection()
        con.execute("DELETE FROM country_statuses WHERE id = ?", [int(status_id)])


class CountryAllocationVM:
    """Manage per-platform country allocation mode and percentages."""

    @staticmethod
    def get_mode(platform_id: int) -> str:
        """Return 'manual' or 'equal'."""
        con = get_connection()
        row = con.execute(
            "SELECT allocation_mode FROM country_allocations WHERE platform_id = ?",
            [int(platform_id)],
        ).fetchone()
        return row[0] if row else "equal"

    @staticmethod
    def set_mode(platform_id: int, mode: str) -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO country_allocations (platform_id, allocation_mode)
               VALUES (?, ?)
               ON CONFLICT (platform_id)
               DO UPDATE SET allocation_mode = excluded.allocation_mode""",
            [int(platform_id), mode],
        )

    @staticmethod
    def get_pcts(platform_id: int) -> pd.DataFrame:
        """Return manual allocation pcts for a platform."""
        con = get_connection()
        return con.execute(
            "SELECT country, pct FROM country_allocation_pcts WHERE platform_id = ? ORDER BY country",
            [int(platform_id)],
        ).fetchdf()

    @staticmethod
    def save_pct(platform_id: int, country: str, pct: float) -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO country_allocation_pcts (platform_id, country, pct)
               VALUES (?, ?, ?)
               ON CONFLICT (platform_id, country)
               DO UPDATE SET pct = excluded.pct""",
            [int(platform_id), country, float(pct)],
        )

    @staticmethod
    def compute_allocation(platform_id: int) -> pd.DataFrame:
        """Compute country allocation for a platform.

        Returns DataFrame with columns: country, pct
        """
        from app.viewmodels.balance_vm import CountryStatusVM

        mode = CountryAllocationVM.get_mode(platform_id)
        countries = CountryStatusVM.list_statuses(platform_id)
        if countries.empty:
            return pd.DataFrame(columns=["country", "pct"])

        if mode == "manual":
            manual = CountryAllocationVM.get_pcts(platform_id)
            if manual.empty:
                # Fall back to equal
                n = len(countries)
                return pd.DataFrame({
                    "country": countries["country"].tolist(),
                    "pct": [100.0 / n] * n,
                })
            # Merge manual pcts with countries
            merged = countries[["country"]].merge(manual, on="country", how="left")
            merged["pct"] = merged["pct"].fillna(0)
            return merged[["country", "pct"]]
        else:
            # Equal allocation
            n = len(countries)
            return pd.DataFrame({
                "country": countries["country"].tolist(),
                "pct": [100.0 / n] * n,
            })
