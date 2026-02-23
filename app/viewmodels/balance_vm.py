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
        merged["deviation"] = merged["target_value"] - (merged["latest_balance"] - merged["off_budget_total"])

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
    """Manage per-platform country allocation mode and percentages.

    Each platform has:
      * excluded_statuses – comma-separated status names whose countries get 0%.
        "Running" is *always* included (never excluded).
      * allocation_mode – 'equal' or 'manual'  (applied to *included* countries).
    """

    @staticmethod
    def get_mode(platform_id: int) -> str:
        """Return 'manual' or 'equal'."""
        con = get_connection()
        row = con.execute(
            "SELECT allocation_mode FROM country_allocations WHERE platform_id = ?",
            [int(platform_id)],
        ).fetchone()
        mode = row[0] if row else "equal"
        # Migrate legacy 'status' rows transparently
        return "equal" if mode == "status" else mode

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
    def get_excluded_statuses(platform_id: int) -> list[str]:
        """Return list of excluded country statuses."""
        con = get_connection()
        row = con.execute(
            "SELECT excluded_statuses FROM country_allocations WHERE platform_id = ?",
            [int(platform_id)],
        ).fetchone()
        if row and row[0]:
            return [s.strip() for s in row[0].split(",") if s.strip()]
        return []

    @staticmethod
    def set_excluded_statuses(platform_id: int, excluded: list[str]) -> None:
        con = get_connection()
        val = ",".join(excluded)
        con.execute(
            """INSERT INTO country_allocations (platform_id, excluded_statuses)
               VALUES (?, ?)
               ON CONFLICT (platform_id)
               DO UPDATE SET excluded_statuses = excluded.excluded_statuses""",
            [int(platform_id), val],
        )

    @staticmethod
    def get_pcts(platform_id: int) -> pd.DataFrame:
        """Return manual allocation pcts and values for a platform."""
        con = get_connection()
        return con.execute(
            "SELECT country, pct, value FROM country_allocation_pcts WHERE platform_id = ? ORDER BY country",
            [int(platform_id)],
        ).fetchdf()

    @staticmethod
    def save_pct(platform_id: int, country: str, pct: float, value: float = 0.0) -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO country_allocation_pcts (platform_id, country, pct, value)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (platform_id, country)
               DO UPDATE SET pct = excluded.pct, value = excluded.value""",
            [int(platform_id), country, float(pct), float(value)],
        )

    @staticmethod
    def included_countries(platform_id: int) -> pd.DataFrame:
        """Return only countries whose status is NOT excluded.

        Running is always included regardless of the exclusion list.
        """
        from app.viewmodels.balance_vm import CountryStatusVM

        countries = CountryStatusVM.list_statuses(platform_id)
        if countries.empty:
            return countries
        excluded = set(CountryAllocationVM.get_excluded_statuses(platform_id))
        excluded.discard("Running")
        return countries[~countries["status"].isin(excluded)]

    @staticmethod
    def compute_allocation(platform_id: int) -> pd.DataFrame:
        """Compute country allocation for a platform.

        1. Filter countries by excluded statuses.
        2. Apply equal or manual allocation to the remaining ones.

        Returns DataFrame with columns: country, pct
        """
        from app.viewmodels.balance_vm import CountryStatusVM

        all_countries = CountryStatusVM.list_statuses(platform_id)
        if all_countries.empty:
            return pd.DataFrame(columns=["country", "pct"])

        excluded = set(CountryAllocationVM.get_excluded_statuses(platform_id))
        excluded.discard("Running")
        included = all_countries[~all_countries["status"].isin(excluded)]
        mode = CountryAllocationVM.get_mode(platform_id)

        # Build result – excluded countries always get 0%
        result = []

        if mode == "manual" and not included.empty:
            manual = CountryAllocationVM.get_pcts(platform_id)
            pct_map = dict(zip(manual["country"], manual["pct"])) if not manual.empty else {}
            included_set = set(included["country"].tolist())
            for _, row in all_countries.iterrows():
                c = row["country"]
                result.append({
                    "country": c,
                    "pct": float(pct_map.get(c, 0)) if c in included_set else 0.0,
                })
        else:
            # Equal allocation among included countries
            included_set = set(included["country"].tolist())
            n = len(included)
            eq_pct = 100.0 / n if n > 0 else 0.0
            for _, row in all_countries.iterrows():
                result.append({
                    "country": row["country"],
                    "pct": eq_pct if row["country"] in included_set else 0.0,
                })

        return pd.DataFrame(result)


class AutoScoreVM:
    """Manage and compute auto-score equations for special criteria."""

    DEFAULT_EQUATIONS = {
        "interest_rate": "max(0, min(10, 5 + (10 / (max_rate - min_rate)) * (rate - avg_rate)))",
        "country": "min(10, count * 1.5)",
    }

    @staticmethod
    def get_equation(portfolio_id: int, special_type: str) -> tuple[str, bool]:
        """Return (equation_str, enabled)."""
        con = get_connection()
        row = con.execute(
            "SELECT equation, enabled FROM auto_score_equations WHERE portfolio_id = ? AND special_type = ?",
            [int(portfolio_id), special_type],
        ).fetchone()
        if row:
            eq = row[0] if row[0] else AutoScoreVM.DEFAULT_EQUATIONS.get(special_type, "")
            return eq, bool(row[1])
        return AutoScoreVM.DEFAULT_EQUATIONS.get(special_type, ""), False

    @staticmethod
    def save_equation(portfolio_id: int, special_type: str, equation: str, enabled: bool) -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO auto_score_equations (portfolio_id, special_type, equation, enabled)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (portfolio_id, special_type)
               DO UPDATE SET equation = excluded.equation, enabled = excluded.enabled""",
            [int(portfolio_id), special_type, equation, enabled],
        )

    @staticmethod
    def compute_interest_rate_scores(portfolio_id: int, equation: str) -> dict[int, float]:
        """Compute interest rate scores for all Running platforms.

        Returns {platform_id: score}.
        Available variables in equation: rate, min_rate, max_rate, avg_rate.
        """
        from app.viewmodels.balance_vm import InterestRateVM
        from app.viewmodels.portfolio_vm import PortfolioVM

        platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=False)
        rates_df = InterestRateVM.get_rates(portfolio_id)
        # Only Running platforms
        running_ids = set(int(x) for x in platforms[platforms["status"] == "Running"]["id"].tolist())
        rates_df = rates_df[rates_df["platform_id"].apply(lambda x: int(x) in running_ids)]
        active_rates = rates_df[rates_df["estimated_rate"] > 0]["estimated_rate"]

        if active_rates.empty:
            return {}

        min_rate = float(active_rates.min())
        max_rate = float(active_rates.max())
        avg_rate = float(active_rates.mean())

        results = {}
        for _, r in rates_df.iterrows():
            pid = int(r["platform_id"])
            rate = float(r["estimated_rate"])
            try:
                score = eval(equation, {"__builtins__": {}}, {
                    "rate": rate, "min_rate": min_rate, "max_rate": max_rate,
                    "avg_rate": avg_rate, "min": min, "max": max, "abs": abs,
                })
                results[pid] = float(max(0, min(10, score)))
            except Exception:
                results[pid] = 0.0
        return results

    @staticmethod
    def compute_country_scores(portfolio_id: int, equation: str) -> dict[int, float]:
        """Compute country count scores for all Running platforms.

        Only countries whose status is *not* excluded are counted.

        Returns {platform_id: score}.
        Available variables in equation: count (number of included countries).
        """
        from app.viewmodels.balance_vm import CountryAllocationVM
        from app.viewmodels.portfolio_vm import PortfolioVM

        platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=False)
        running = platforms[platforms["status"] == "Running"]

        results = {}
        for _, plat in running.iterrows():
            pid = int(plat["id"])
            included = CountryAllocationVM.included_countries(pid)
            count = len(included)
            try:
                score = eval(equation, {"__builtins__": {}}, {
                    "count": count, "min": min, "max": max, "abs": abs,
                })
                results[pid] = float(max(0, min(10, score)))
            except Exception:
                results[pid] = 0.0
        return results
