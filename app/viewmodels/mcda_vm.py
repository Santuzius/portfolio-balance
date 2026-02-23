"""ViewModel for MCDA: criteria, weighting matrix, scoring matrix, and allocation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from app.models.database import get_connection


class CriteriaVM:
    """Manage criteria and pairwise weighting."""

    # ── Criteria CRUD ───────────────────────────────────────────────

    @staticmethod
    def list_criteria(portfolio_id: int) -> pd.DataFrame:
        con = get_connection()
        return con.execute(
            """SELECT id, name, display_order, is_special, special_type
               FROM criteria
               WHERE portfolio_id = ?
               ORDER BY display_order""",
            [portfolio_id],
        ).fetchdf()

    @staticmethod
    def create_criterion(
        portfolio_id: int,
        name: str,
        display_order: int = 0,
        is_special: bool = False,
        special_type: str | None = None,
    ) -> int:
        con = get_connection()
        con.execute(
            """INSERT INTO criteria (portfolio_id, name, display_order, is_special, special_type)
               VALUES (?, ?, ?, ?, ?)""",
            [portfolio_id, name, display_order, is_special, special_type],
        )
        return con.execute("SELECT currval('seq_criterion')").fetchone()[0]

    @staticmethod
    def update_criterion(
        criterion_id: int,
        name: str,
        display_order: int,
        is_special: bool,
        special_type: str | None,
    ) -> None:
        con = get_connection()
        cid = int(criterion_id)
        # DuckDB UPDATE = internal DELETE+INSERT, which triggers FK checks.
        # Workaround: detach dependent rows, update, re-attach.
        pw_rows = con.execute(
            "SELECT portfolio_id, criterion_row, criterion_col, value "
            "FROM pairwise_comparisons WHERE criterion_row = ? OR criterion_col = ?",
            [cid, cid],
        ).fetchall()
        sc_rows = con.execute(
            "SELECT platform_id, criterion_id, score, note "
            "FROM scores WHERE criterion_id = ?",
            [cid],
        ).fetchall()
        con.execute(
            "DELETE FROM pairwise_comparisons WHERE criterion_row = ? OR criterion_col = ?",
            [cid, cid],
        )
        con.execute("DELETE FROM scores WHERE criterion_id = ?", [cid])
        con.execute(
            """UPDATE criteria
               SET name = ?, display_order = ?, is_special = ?, special_type = ?
               WHERE id = ?""",
            [name, display_order, is_special, special_type, cid],
        )
        for r in pw_rows:
            con.execute(
                "INSERT INTO pairwise_comparisons (portfolio_id, criterion_row, criterion_col, value) "
                "VALUES (?, ?, ?, ?)",
                [int(r[0]), int(r[1]), int(r[2]), int(r[3])],
            )
        for r in sc_rows:
            con.execute(
                "INSERT INTO scores (platform_id, criterion_id, score, note) "
                "VALUES (?, ?, ?, ?)",
                [int(r[0]), int(r[1]), float(r[2]), str(r[3])],
            )

    @staticmethod
    def delete_criterion(criterion_id: int) -> None:
        con = get_connection()
        con.execute(
            "DELETE FROM pairwise_comparisons WHERE criterion_row = ? OR criterion_col = ?",
            [criterion_id, criterion_id],
        )
        con.execute("DELETE FROM scores WHERE criterion_id = ?", [criterion_id])
        con.execute("DELETE FROM criteria WHERE id = ?", [criterion_id])

    # ── Pairwise Comparison (Weighting Matrix) ─────────────────────

    @staticmethod
    def get_pairwise_matrix(portfolio_id: int) -> pd.DataFrame:
        """Return a square DataFrame with criterion names as index & columns.

        Values: 2 = row more important, 1 = equal, 0 = row less important.
        Diagonal is always empty (NaN).
        """
        con = get_connection()
        criteria = con.execute(
            "SELECT id, name FROM criteria WHERE portfolio_id = ? ORDER BY display_order",
            [portfolio_id],
        ).fetchdf()
        if criteria.empty:
            return pd.DataFrame()

        n = len(criteria)
        names = criteria["name"].tolist()
        ids = criteria["id"].tolist()

        matrix = pd.DataFrame(np.nan, index=names, columns=names)

        rows = con.execute(
            """SELECT cr.name AS row_name, cc.name AS col_name, pc.value
               FROM pairwise_comparisons pc
               JOIN criteria cr ON pc.criterion_row = cr.id
               JOIN criteria cc ON pc.criterion_col = cc.id
               WHERE pc.portfolio_id = ?""",
            [portfolio_id],
        ).fetchdf()

        for _, r in rows.iterrows():
            matrix.at[r["row_name"], r["col_name"]] = r["value"]

        return matrix

    @staticmethod
    def save_pairwise_value(
        portfolio_id: int, row_criterion_id: int, col_criterion_id: int, value: int
    ) -> None:
        con = get_connection()
        pid = int(portfolio_id)
        rid = int(row_criterion_id)
        cid = int(col_criterion_id)
        val = int(value)
        # Upsert
        con.execute(
            """INSERT INTO pairwise_comparisons (portfolio_id, criterion_row, criterion_col, value)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (portfolio_id, criterion_row, criterion_col)
               DO UPDATE SET value = excluded.value""",
            [pid, rid, cid, val],
        )
        # Mirror: if row>col gets 2, col>row gets 0
        mirror = 2 - val  # 2→0, 1→1, 0→2
        con.execute(
            """INSERT INTO pairwise_comparisons (portfolio_id, criterion_row, criterion_col, value)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (portfolio_id, criterion_row, criterion_col)
               DO UPDATE SET value = excluded.value""",
            [pid, cid, rid, mirror],
        )

    @staticmethod
    def compute_weights(portfolio_id: int) -> pd.DataFrame:
        """Compute normalised weighting factors from pairwise matrix.

        Returns DataFrame with columns: criterion_id, name, raw_sum, weight_factor.
        Weight factor is normalised so minimum = 1.
        """
        con = get_connection()
        criteria = con.execute(
            "SELECT id, name FROM criteria WHERE portfolio_id = ? ORDER BY display_order",
            [portfolio_id],
        ).fetchdf()
        if criteria.empty:
            return pd.DataFrame(columns=["criterion_id", "name", "raw_sum", "weight_factor"])

        ids = criteria["id"].tolist()
        names = criteria["name"].tolist()

        # Sum of pairwise values for each row criterion
        raw_sums = []
        for cid in ids:
            result = con.execute(
                "SELECT COALESCE(SUM(value), 0) FROM pairwise_comparisons WHERE portfolio_id = ? AND criterion_row = ?",
                [portfolio_id, cid],
            ).fetchone()
            raw_sums.append(result[0])

        # Normalise: add 1 to each (shift so min becomes 1 if all zeros)
        raw_arr = np.array(raw_sums, dtype=float)
        weight_factors = raw_arr + 1  # +1 so that even a score of 0 gets weight 1

        return pd.DataFrame(
            {
                "criterion_id": ids,
                "name": names,
                "raw_sum": raw_sums,
                "weight_factor": weight_factors,
            }
        )


class ScoringVM:
    """Manage platform scores and compute weighted MCDA allocation."""

    @staticmethod
    def get_scores_matrix(portfolio_id: int) -> pd.DataFrame:
        """Return a pivoted DataFrame: rows = platforms, columns = criteria, values = scores."""
        con = get_connection()
        df = con.execute(
            """SELECT p.name AS platform, c.name AS criterion, s.score, s.note
               FROM scores s
               JOIN platforms p ON s.platform_id = p.id
               JOIN criteria c ON s.criterion_id = c.id
               WHERE p.portfolio_id = ?
               ORDER BY p.name, c.display_order""",
            [portfolio_id],
        ).fetchdf()
        if df.empty:
            return pd.DataFrame()
        return df.pivot_table(index="platform", columns="criterion", values="score", aggfunc="first").fillna(0)

    @staticmethod
    def get_scores_for_platform(platform_id: int) -> pd.DataFrame:
        con = get_connection()
        pid = int(platform_id)
        return con.execute(
            """SELECT c.id AS criterion_id, c.name, COALESCE(s.score, 0) AS score,
                      COALESCE(s.note, '') AS note
               FROM criteria c
               LEFT JOIN scores s ON s.criterion_id = c.id AND s.platform_id = ?
               WHERE c.portfolio_id = (SELECT portfolio_id FROM platforms WHERE id = ?)
               ORDER BY c.display_order""",
            [pid, pid],
        ).fetchdf()

    @staticmethod
    def save_score(platform_id: int, criterion_id: int, score: float, note: str = "") -> None:
        con = get_connection()
        con.execute(
            """INSERT INTO scores (platform_id, criterion_id, score, note)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (platform_id, criterion_id)
               DO UPDATE SET score = excluded.score, note = excluded.note""",
            [int(platform_id), int(criterion_id), float(score), note],
        )

    @staticmethod
    def compute_allocation(portfolio_id: int) -> pd.DataFrame:
        """Run the full MCDA and return allocation percentages.

        Returns DataFrame with columns:
            platform_id, platform, total_weighted_score, pct_allocation, status
        """
        con = get_connection()
        weights_df = CriteriaVM.compute_weights(portfolio_id)
        if weights_df.empty:
            return pd.DataFrame(
                columns=["platform_id", "platform", "total_weighted_score", "pct_allocation", "status"]
            )

        platforms = con.execute(
            "SELECT id, name, status FROM platforms WHERE portfolio_id = ? ORDER BY name",
            [portfolio_id],
        ).fetchdf()
        if platforms.empty:
            return pd.DataFrame(
                columns=["platform_id", "platform", "total_weighted_score", "pct_allocation", "status"]
            )

        # Build weight dict  criterion_id -> weight_factor
        weight_map = dict(zip(weights_df["criterion_id"], weights_df["weight_factor"]))

        results = []
        for _, plat in platforms.iterrows():
            # Only Running platforms get MCDA allocation;
            # Dissaving, Closed, Defaulted all get 0%.
            if plat["status"] != "Running":
                results.append(
                    {
                        "platform_id": plat["id"],
                        "platform": plat["name"],
                        "total_weighted_score": 0.0,
                        "pct_allocation": 0.0,
                        "status": plat["status"],
                    }
                )
                continue

            scores = con.execute(
                "SELECT criterion_id, score FROM scores WHERE platform_id = ?",
                [int(plat["id"])],
            ).fetchdf()
            total = 0.0
            for _, s in scores.iterrows():
                w = weight_map.get(s["criterion_id"], 1)
                total += s["score"] * w
            results.append(
                {
                    "platform_id": plat["id"],
                    "platform": plat["name"],
                    "total_weighted_score": total,
                    "pct_allocation": total,  # will normalise below
                    "status": plat["status"],
                }
            )

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
