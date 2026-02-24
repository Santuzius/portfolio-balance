"""ViewModel for MCDA: criteria, weighting matrix, scoring matrix, and allocation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from app.models.repositories import (
    CriteriaRepo, PlatformRepo, ScoreRepo,
)


class CriteriaVM:
    """Manage criteria and pairwise weighting."""

    # ── Criteria CRUD ───────────────────────────────────────────────

    @staticmethod
    def list_criteria(portfolio_id: int) -> pd.DataFrame:
        return CriteriaRepo.list_for_portfolio(portfolio_id)

    @staticmethod
    def create_criterion(
        portfolio_id: int,
        name: str,
        display_order: int = 0,
        is_special: bool = False,
        special_type: str | None = None,
    ) -> int:
        return CriteriaRepo.create(
            portfolio_id, name, display_order, is_special, special_type,
        )

    @staticmethod
    def update_criterion(
        criterion_id: int,
        name: str,
        display_order: int,
        is_special: bool,
        special_type: str | None,
    ) -> None:
        CriteriaRepo.update(criterion_id, name, display_order, is_special, special_type)

    @staticmethod
    def delete_criterion(criterion_id: int) -> None:
        CriteriaRepo.delete(criterion_id)

    # ── Pairwise Comparison (Weighting Matrix) ─────────────────────

    @staticmethod
    def get_pairwise_matrix(portfolio_id: int) -> pd.DataFrame:
        """Return a square DataFrame with criterion names as index & columns.

        Values: 2 = row more important, 1 = equal, 0 = row less important.
        Diagonal is always empty (NaN).
        """
        criteria = CriteriaRepo.list_for_portfolio(portfolio_id)
        if criteria.empty:
            return pd.DataFrame()

        names = criteria["name"].tolist()
        matrix = pd.DataFrame(np.nan, index=names, columns=names)

        pw = CriteriaRepo.get_pairwise_named(portfolio_id)
        for _, r in pw.iterrows():
            matrix.at[r["row_name"], r["col_name"]] = r["value"]

        return matrix

    @staticmethod
    def get_pairwise_values_dict(portfolio_id: int) -> dict[tuple[int, int], int]:
        """Return {(row_criterion_id, col_criterion_id): value} dict."""
        df = CriteriaRepo.get_pairwise_values(portfolio_id)
        if df.empty:
            return {}
        return {
            (int(r["criterion_row"]), int(r["criterion_col"])): int(r["value"])
            for _, r in df.iterrows()
        }

    @staticmethod
    def save_pairwise_value(
        portfolio_id: int, row_criterion_id: int, col_criterion_id: int, value: int,
    ) -> None:
        CriteriaRepo.save_pairwise_value(
            portfolio_id, row_criterion_id, col_criterion_id, value,
        )

    @staticmethod
    def compute_weights(portfolio_id: int) -> pd.DataFrame:
        """Compute normalised weighting factors from pairwise matrix.

        Returns DataFrame with columns: criterion_id, name, raw_sum, weight_factor.
        Weight factor is normalised so minimum = 1.
        """
        rows = CriteriaRepo.get_pairwise_row_sums(portfolio_id)
        if not rows:
            return pd.DataFrame(
                columns=["criterion_id", "name", "raw_sum", "weight_factor"],
            )

        ids = [r[0] for r in rows]
        names = [r[1] for r in rows]
        raw_sums = [r[2] for r in rows]

        # Normalise: add 1 so that even a score of 0 gets weight 1
        raw_arr = np.array(raw_sums, dtype=float)
        weight_factors = raw_arr + 1

        return pd.DataFrame({
            "criterion_id": ids,
            "name": names,
            "raw_sum": raw_sums,
            "weight_factor": weight_factors,
        })


class ScoringVM:
    """Manage platform scores and compute weighted MCDA allocation."""

    @staticmethod
    def get_scores_matrix(portfolio_id: int) -> pd.DataFrame:
        """Pivoted DataFrame: rows = platforms, columns = criteria, values = scores."""
        return ScoreRepo.get_matrix(portfolio_id)

    @staticmethod
    def get_scores_for_platform(platform_id: int) -> pd.DataFrame:
        return ScoreRepo.get_for_platform(platform_id)

    @staticmethod
    def save_score(
        platform_id: int, criterion_id: int, score: float, note: str = "",
    ) -> None:
        ScoreRepo.save(platform_id, criterion_id, score, note)

    @staticmethod
    def compute_allocation(portfolio_id: int) -> pd.DataFrame:
        """Run the full MCDA and return allocation percentages.

        Returns DataFrame with columns:
            platform_id, platform, total_weighted_score, pct_allocation, status
        """
        weights_df = CriteriaVM.compute_weights(portfolio_id)
        if weights_df.empty:
            return pd.DataFrame(
                columns=[
                    "platform_id", "platform",
                    "total_weighted_score", "pct_allocation", "status",
                ],
            )

        platforms = PlatformRepo.list_simple(portfolio_id)
        if platforms.empty:
            return pd.DataFrame(
                columns=[
                    "platform_id", "platform",
                    "total_weighted_score", "pct_allocation", "status",
                ],
            )

        weight_map = dict(
            zip(weights_df["criterion_id"], weights_df["weight_factor"]),
        )

        results = []
        for _, plat in platforms.iterrows():
            if plat["status"] != "Running":
                results.append({
                    "platform_id": plat["id"],
                    "platform": plat["name"],
                    "total_weighted_score": 0.0,
                    "pct_allocation": 0.0,
                    "status": plat["status"],
                })
                continue

            scores = ScoreRepo.get_raw_scores(int(plat["id"]))
            total = 0.0
            for _, s in scores.iterrows():
                w = weight_map.get(s["criterion_id"], 1)
                total += s["score"] * w
            results.append({
                "platform_id": plat["id"],
                "platform": plat["name"],
                "total_weighted_score": total,
                "pct_allocation": total,  # normalised below
                "status": plat["status"],
            })

        df = pd.DataFrame(results)
        grand_total = df["total_weighted_score"].sum()
        if grand_total > 0:
            df["pct_allocation"] = df["total_weighted_score"] / grand_total
        else:
            df["pct_allocation"] = 0.0

        # Compute optimal score for reference
        optimal_score = sum(10 * w for w in weight_map.values())
        df["optimal_score"] = optimal_score

        return df
