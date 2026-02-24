"""ViewModel for monthly balance tracking and deviation analysis."""

from __future__ import annotations

from datetime import date
import pandas as pd
from app.models.repositories import (
    BalanceRepo, PocketRepo, LoanOriginatorRepo,
    InterestRateRepo, CountryStatusRepo, CountryAllocationRepo,
    OriginatorAllocationRepo, AutoScoreRepo,
)
from app.viewmodels.mcda_vm import ScoringVM


class BalanceVM:
    """Record and analyse monthly balance snapshots."""

    @staticmethod
    def record_balance(platform_id: int, month: date, balance: float) -> None:
        BalanceRepo.record(platform_id, month, balance)

    @staticmethod
    def delete_balance(snapshot_id: int) -> None:
        BalanceRepo.delete(snapshot_id)

    @staticmethod
    def get_balances_for_portfolio(portfolio_id: int) -> pd.DataFrame:
        """All balance snapshots for a portfolio, joined with platform info."""
        return BalanceRepo.get_all_for_portfolio(portfolio_id)

    @staticmethod
    def get_latest_balances(portfolio_id: int) -> pd.DataFrame:
        """Get latest balance per platform."""
        return BalanceRepo.get_latest(portfolio_id)

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
            added to off-budget.  ``None`` means only ``{"Running"}``.

        Returns DataFrame with:
            platform, status, latest_balance, pct_allocation,
            target_value, deviation, off_budget_total
        """
        if rebalance_statuses is None:
            rebalance_statuses = {"Running"}

        latest = BalanceRepo.get_latest(portfolio_id)
        allocation = ScoringVM.compute_allocation(portfolio_id)

        if latest.empty or allocation.empty:
            return pd.DataFrame(
                columns=[
                    "platform", "status", "latest_balance", "pct_allocation",
                    "target_value", "deviation", "off_budget_total",
                ],
            )

        total_balance = latest["balance"].fillna(0).sum()

        off_budget = BalanceRepo.get_off_budget_totals(portfolio_id)

        merged = latest.merge(
            allocation[["platform_id", "pct_allocation", "status"]],
            on="platform_id",
            how="left",
            suffixes=("", "_alloc"),
        )
        merged = merged.merge(off_budget, on="platform_id", how="left")
        merged["off_budget_total"] = merged["off_budget_total"].fillna(0)

        # Platforms not selected for rebalancing: full balance is off-budget
        not_rebal = ~merged["status"].isin(rebalance_statuses)
        merged.loc[not_rebal, "off_budget_total"] = merged.loc[
            not_rebal, "balance"
        ].fillna(0)

        effective_total = total_balance - merged["off_budget_total"].sum()

        merged["target_value"] = merged["pct_allocation"].fillna(0) * effective_total
        merged["latest_balance"] = merged["balance"].fillna(0)
        merged["deviation"] = merged["target_value"] - (
            merged["latest_balance"] - merged["off_budget_total"]
        )

        return merged[
            [
                "platform", "status", "latest_balance", "pct_allocation",
                "target_value", "deviation", "off_budget_total",
            ]
        ]


class PocketVM:
    """Manage off-budget pockets."""

    @staticmethod
    def list_pockets(platform_id: int) -> pd.DataFrame:
        return PocketRepo.list_for_platform(platform_id)

    @staticmethod
    def create_pocket(
        platform_id: int, name: str, amount: float, note: str = "",
    ) -> int:
        return PocketRepo.create(platform_id, name, amount, note)

    @staticmethod
    def update_pocket(
        pocket_id: int, name: str, amount: float, note: str = "",
    ) -> None:
        PocketRepo.update(pocket_id, name, amount, note)

    @staticmethod
    def delete_pocket(pocket_id: int) -> None:
        PocketRepo.delete(pocket_id)


class LoanOriginatorVM:
    """Manage loan originators per platform."""

    @staticmethod
    def list_originators(platform_id: int) -> pd.DataFrame:
        return LoanOriginatorRepo.list_for_platform(platform_id)

    @staticmethod
    def list_all_for_portfolio(portfolio_id: int) -> pd.DataFrame:
        return LoanOriginatorRepo.list_all_for_portfolio(portfolio_id)

    @staticmethod
    def save_originator(
        platform_id: int, country: str, originator_name: str,
        num_loans: float, status: str = "Running", note: str = "",
    ) -> None:
        LoanOriginatorRepo.save(platform_id, country, originator_name, num_loans, status, note)

    @staticmethod
    def update_originator(
        originator_id: int, country: str, originator_name: str,
        num_loans: float, status: str = "Running", note: str = "",
    ) -> None:
        LoanOriginatorRepo.update(originator_id, country, originator_name, num_loans, status, note)

    @staticmethod
    def delete_originator(originator_id: int) -> None:
        LoanOriginatorRepo.delete(originator_id)

    @staticmethod
    def ensure_default(platform_id: int, platform_name: str) -> None:
        """Ensure the platform has at least one originator (itself at 100%)."""
        LoanOriginatorRepo.ensure_default(platform_id, platform_name)


class InterestRateVM:
    """Manage interest rate data per platform."""

    @staticmethod
    def get_rates(portfolio_id: int) -> pd.DataFrame:
        return InterestRateRepo.get_rates(portfolio_id)

    @staticmethod
    def save_rate(platform_id: int, estimated_rate: float) -> None:
        InterestRateRepo.save_rate(platform_id, estimated_rate)


class CountryStatusVM:
    """Manage country statuses."""

    @staticmethod
    def list_statuses(platform_id: int | None = None) -> pd.DataFrame:
        return CountryStatusRepo.list_statuses(platform_id)

    @staticmethod
    def save_status(
        platform_id: int | None, country: str, status: str, note: str = "",
    ) -> None:
        CountryStatusRepo.save(platform_id, country, status, note)

    @staticmethod
    def update_status(
        status_id: int, new_status: str, note: str | None = None,
    ) -> None:
        CountryStatusRepo.update(status_id, new_status, note)

    @staticmethod
    def delete_status(status_id: int) -> None:
        CountryStatusRepo.delete(status_id)


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
        mode = CountryAllocationRepo.get_mode_raw(platform_id)
        if mode is None:
            return "equal"
        # Migrate legacy 'status' rows transparently
        return "equal" if mode == "status" else mode

    @staticmethod
    def set_mode(platform_id: int, mode: str) -> None:
        CountryAllocationRepo.set_mode(platform_id, mode)

    @staticmethod
    def get_excluded_statuses(platform_id: int) -> list[str] | None:
        """Return list of excluded country statuses, or None if never configured."""
        raw = CountryAllocationRepo.get_excluded_statuses_raw(platform_id)
        if raw is None:
            return None          # no row → never configured
        if raw:
            return [s.strip() for s in raw.split(",") if s.strip()]
        return []                # row exists, empty → explicitly include all

    @staticmethod
    def set_excluded_statuses(platform_id: int, excluded: list[str]) -> None:
        CountryAllocationRepo.set_excluded_statuses(platform_id, ",".join(excluded))

    @staticmethod
    def get_pcts(platform_id: int) -> pd.DataFrame:
        return CountryAllocationRepo.get_pcts(platform_id)

    @staticmethod
    def save_pct(
        platform_id: int, country: str, pct: float, value: float = 0.0,
    ) -> None:
        CountryAllocationRepo.save_pct(platform_id, country, pct, value)

    @staticmethod
    def included_countries(platform_id: int) -> pd.DataFrame:
        """Return only countries whose status is NOT excluded.

        Running is always included regardless of the exclusion list.
        """
        countries = CountryStatusRepo.list_statuses(platform_id)
        if countries.empty:
            return countries
        excluded_list = CountryAllocationVM.get_excluded_statuses(platform_id)
        if excluded_list is None:
            non_running = set(countries[countries["status"] != "Running"]["status"])
            excluded = non_running
        else:
            excluded = set(excluded_list)
        excluded.discard("Running")
        return countries[~countries["status"].isin(excluded)]

    @staticmethod
    def compute_allocation(platform_id: int) -> pd.DataFrame:
        """Compute country allocation for a platform.

        1. If mode == 'inherit', derive from originator data.
        2. Otherwise filter countries by excluded statuses.
        3. Apply equal or manual allocation to the remaining ones.

        Returns DataFrame with columns: country, pct
        """
        mode = CountryAllocationVM.get_mode(platform_id)

        # ── Inherit from originators ─────────────────────────────
        if mode == "inherit":
            origs = LoanOriginatorRepo.list_for_platform(platform_id)
            if origs.empty:
                return pd.DataFrame(columns=["country", "pct"])

            # Use originator allocation pcts to weight countries
            orig_alloc = OriginatorAllocationVM.compute_allocation(platform_id)
            country_pct: dict[str, float] = {}
            for _, row in orig_alloc.iterrows():
                c = row["country"].strip() if row["country"] else "Unknown"
                if not c:
                    c = "Unknown"
                country_pct[c] = country_pct.get(c, 0) + float(row["pct"])
            return pd.DataFrame([
                {"country": c, "pct": p} for c, p in country_pct.items()
            ])

        # ── Normal mode (equal / manual) ─────────────────────────
        all_countries = CountryStatusRepo.list_statuses(platform_id)
        if all_countries.empty:
            return pd.DataFrame(columns=["country", "pct"])

        excluded_list = CountryAllocationVM.get_excluded_statuses(platform_id)
        if excluded_list is None:
            # Never configured → default: exclude all non-Running
            non_running = set(all_countries[all_countries["status"] != "Running"]["status"])
            excluded = non_running
        else:
            excluded = set(excluded_list)
        excluded.discard("Running")
        included = all_countries[~all_countries["status"].isin(excluded)]
        mode = CountryAllocationVM.get_mode(platform_id)

        result = []

        if mode == "manual" and not included.empty:
            manual = CountryAllocationRepo.get_pcts(platform_id)
            pct_map = (
                dict(zip(manual["country"], manual["pct"]))
                if not manual.empty
                else {}
            )
            included_set = set(included["country"].tolist())
            for _, row in all_countries.iterrows():
                c = row["country"]
                result.append({
                    "country": c,
                    "pct": float(pct_map.get(c, 0)) if c in included_set else 0.0,
                })
        else:
            included_set = set(included["country"].tolist())
            n = len(included)
            eq_pct = 100.0 / n if n > 0 else 0.0
            for _, row in all_countries.iterrows():
                result.append({
                    "country": row["country"],
                    "pct": eq_pct if row["country"] in included_set else 0.0,
                })

        return pd.DataFrame(result)


def _orig_key(name: str, country: str) -> str:
    """Composite key for an originator (name + country).

    Two originators may share the same name but differ by country,
    so the allocation key must incorporate both.
    """
    return f"{name}|{country}"


class OriginatorAllocationVM:
    """Manage per-platform originator allocation mode and percentages.

    Mirrors CountryAllocationVM but for loan originators.
    """

    @staticmethod
    def get_mode(platform_id: int) -> str:
        mode = OriginatorAllocationRepo.get_mode_raw(platform_id)
        return "equal" if mode is None else mode

    @staticmethod
    def set_mode(platform_id: int, mode: str) -> None:
        OriginatorAllocationRepo.set_mode(platform_id, mode)

    @staticmethod
    def get_excluded_statuses(platform_id: int) -> list[str] | None:
        """Return excluded statuses, or None if never configured."""
        raw = OriginatorAllocationRepo.get_excluded_statuses_raw(platform_id)
        if raw is None:
            return None
        if raw:
            return [s.strip() for s in raw.split(",") if s.strip()]
        return []

    @staticmethod
    def set_excluded_statuses(platform_id: int, excluded: list[str]) -> None:
        OriginatorAllocationRepo.set_excluded_statuses(platform_id, ",".join(excluded))

    @staticmethod
    def get_pcts(platform_id: int) -> pd.DataFrame:
        return OriginatorAllocationRepo.get_pcts(platform_id)

    @staticmethod
    def save_pct(
        platform_id: int, originator_key: str, pct: float, value: float = 0.0,
    ) -> None:
        OriginatorAllocationRepo.save_pct(platform_id, originator_key, pct, value)

    @staticmethod
    def included_originators(platform_id: int) -> pd.DataFrame:
        """Return only originators whose status is NOT excluded."""
        origs = LoanOriginatorRepo.list_for_platform(platform_id)
        if origs.empty:
            return origs
        excluded_list = OriginatorAllocationVM.get_excluded_statuses(platform_id)
        if excluded_list is None:
            non_running = set(origs[origs["status"] != "Running"]["status"])
            excluded = non_running
        else:
            excluded = set(excluded_list)
        excluded.discard("Running")
        return origs[~origs["status"].isin(excluded)]

    @staticmethod
    def compute_allocation(platform_id: int) -> pd.DataFrame:
        """Compute originator allocation for a platform.

        Returns DataFrame with columns: originator_name, country, originator_key, pct
        """
        all_origs = LoanOriginatorRepo.list_for_platform(platform_id)
        if all_origs.empty:
            return pd.DataFrame(columns=["originator_name", "country", "originator_key", "pct"])

        excluded_list = OriginatorAllocationVM.get_excluded_statuses(platform_id)
        if excluded_list is None:
            non_running = set(all_origs[all_origs["status"] != "Running"]["status"])
            excluded = non_running
        else:
            excluded = set(excluded_list)
        excluded.discard("Running")
        included = all_origs[~all_origs["status"].isin(excluded)]
        mode = OriginatorAllocationVM.get_mode(platform_id)

        # Build included set using composite key
        included_keys = set(
            _orig_key(r["originator_name"], r["country"])
            for _, r in included.iterrows()
        )

        result = []

        if mode == "manual" and not included.empty:
            manual = OriginatorAllocationRepo.get_pcts(platform_id)
            pct_map = (
                dict(zip(manual["originator_key"], manual["pct"]))
                if not manual.empty
                else {}
            )
            for _, row in all_origs.iterrows():
                key = _orig_key(row["originator_name"], row["country"])
                result.append({
                    "originator_name": row["originator_name"],
                    "country": row["country"],
                    "originator_key": key,
                    "pct": float(pct_map.get(key, 0)) if key in included_keys else 0.0,
                })
        else:
            n = len(included)
            eq_pct = 100.0 / n if n > 0 else 0.0
            for _, row in all_origs.iterrows():
                key = _orig_key(row["originator_name"], row["country"])
                result.append({
                    "originator_name": row["originator_name"],
                    "country": row["country"],
                    "originator_key": key,
                    "pct": eq_pct if key in included_keys else 0.0,
                })

        return pd.DataFrame(result)


class AutoScoreVM:
    """Manage and compute auto-score equations for special criteria."""

    DEFAULT_EQUATIONS = {
        "interest_rate": "max(0, min(10, 5 + (10 / (max_rate - min_rate)) * (rate - avg_rate)))",
        "country": "min(10, count * 1.5)",
        "loan_originator": "min(10, count * 2.0)",
    }

    @staticmethod
    def get_equation(portfolio_id: int, special_type: str) -> tuple[str, bool]:
        """Return (equation_str, enabled)."""
        row = AutoScoreRepo.get_equation(portfolio_id, special_type)
        if row:
            eq = row[0] if row[0] else AutoScoreVM.DEFAULT_EQUATIONS.get(special_type, "")
            return eq, bool(row[1])
        return AutoScoreVM.DEFAULT_EQUATIONS.get(special_type, ""), False

    @staticmethod
    def save_equation(
        portfolio_id: int, special_type: str, equation: str, enabled: bool,
    ) -> None:
        AutoScoreRepo.save_equation(portfolio_id, special_type, equation, enabled)

    @staticmethod
    def compute_interest_rate_scores(
        portfolio_id: int, equation: str,
    ) -> dict[int, float]:
        """Compute interest rate scores for all Running platforms.

        Returns {platform_id: score}.
        Available variables in equation: rate, min_rate, max_rate, avg_rate.
        """
        from app.viewmodels.portfolio_vm import PortfolioVM

        platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=False)
        rates_df = InterestRateRepo.get_rates(portfolio_id)
        running_ids = set(
            int(x)
            for x in platforms[platforms["status"] == "Running"]["id"].tolist()
        )
        rates_df = rates_df[
            rates_df["platform_id"].apply(lambda x: int(x) in running_ids)
        ]
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
    def compute_country_scores(
        portfolio_id: int, equation: str,
    ) -> dict[int, float]:
        """Compute country count scores for all Running platforms.

        Returns {platform_id: score}.
        Available variables in equation: count (number of included countries).
        """
        from app.viewmodels.portfolio_vm import PortfolioVM

        platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=False)
        running = platforms[platforms["status"] == "Running"]

        results = {}
        for _, plat in running.iterrows():
            pid = int(plat["id"])
            included = CountryAllocationVM.included_countries(pid)
            # Always exclude "Defaulted" from count
            count = len(included[included["status"] != "Defaulted"])
            try:
                score = eval(equation, {"__builtins__": {}}, {
                    "count": count, "min": min, "max": max, "abs": abs,
                })
                results[pid] = float(max(0, min(10, score)))
            except Exception:
                results[pid] = 0.0
        return results

    @staticmethod
    def compute_originator_scores(
        portfolio_id: int, equation: str,
    ) -> dict[int, float]:
        """Compute originator count scores for all Running platforms.

        Returns {platform_id: score}.
        Available variables: count (number of included originators).
        """
        from app.viewmodels.portfolio_vm import PortfolioVM

        platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=False)
        running = platforms[platforms["status"] == "Running"]

        results = {}
        for _, plat in running.iterrows():
            pid = int(plat["id"])
            included = OriginatorAllocationVM.included_originators(pid)
            # Always exclude "Defaulted" from count
            count = len(included[included["status"] != "Defaulted"])
            try:
                score = eval(equation, {"__builtins__": {}}, {
                    "count": count, "min": min, "max": max, "abs": abs,
                })
                results[pid] = float(max(0, min(10, score)))
            except Exception:
                results[pid] = 0.0
        return results
