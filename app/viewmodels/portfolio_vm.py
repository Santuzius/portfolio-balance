"""ViewModel for portfolio-level CRUD operations."""

from __future__ import annotations

import pandas as pd
from app.models.database import get_connection


class PortfolioVM:
    """Manage portfolios and their platforms."""

    # ── Portfolio CRUD ──────────────────────────────────────────────

    @staticmethod
    def list_portfolios() -> pd.DataFrame:
        con = get_connection()
        return con.execute(
            "SELECT id, name, status, created_at FROM portfolios ORDER BY name"
        ).fetchdf()

    @staticmethod
    def get_portfolio(portfolio_id: int) -> dict | None:
        con = get_connection()
        row = con.execute(
            "SELECT id, name, status FROM portfolios WHERE id = ?", [portfolio_id]
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "name": row[1], "status": row[2]}

    @staticmethod
    def create_portfolio(name: str, status: str = "Running") -> int:
        con = get_connection()
        con.execute(
            "INSERT INTO portfolios (name, status) VALUES (?, ?)", [name, status]
        )
        return con.execute("SELECT currval('seq_portfolio')").fetchone()[0]

    @staticmethod
    def update_portfolio(portfolio_id: int, name: str, status: str) -> None:
        con = get_connection()
        con.execute(
            "UPDATE portfolios SET name = ?, status = ? WHERE id = ?",
            [name, status, portfolio_id],
        )

    @staticmethod
    def delete_portfolio(portfolio_id: int) -> None:
        con = get_connection()
        # Cascade manually
        platforms = con.execute(
            "SELECT id FROM platforms WHERE portfolio_id = ?", [portfolio_id]
        ).fetchall()
        for (pid,) in platforms:
            con.execute("DELETE FROM balance_snapshots WHERE platform_id = ?", [pid])
            con.execute("DELETE FROM loan_originators WHERE platform_id = ?", [pid])
            con.execute("DELETE FROM off_budget_pockets WHERE platform_id = ?", [pid])
            con.execute("DELETE FROM interest_rates WHERE platform_id = ?", [pid])
            con.execute("DELETE FROM country_statuses WHERE platform_id = ?", [pid])
            con.execute("DELETE FROM scores WHERE platform_id = ?", [pid])
        con.execute("DELETE FROM platforms WHERE portfolio_id = ?", [portfolio_id])
        con.execute(
            "DELETE FROM pairwise_comparisons WHERE portfolio_id = ?", [portfolio_id]
        )
        con.execute("DELETE FROM criteria WHERE portfolio_id = ?", [portfolio_id])
        con.execute("DELETE FROM portfolios WHERE id = ?", [portfolio_id])

    @staticmethod
    def copy_portfolio(source_id: int, new_name: str) -> int:
        """Copy a portfolio with all data except balance_snapshots.

        Copies: platforms, criteria, pairwise_comparisons, scores,
        interest_rates, country_statuses, country_allocations,
        country_allocation_pcts, off_budget_pockets, loan_originators,
        auto_score_equations.
        """
        con = get_connection()

        # 1. Create new portfolio
        src = con.execute(
            "SELECT status FROM portfolios WHERE id = ?", [source_id]
        ).fetchone()
        if src is None:
            raise ValueError("Source portfolio not found.")
        con.execute(
            "INSERT INTO portfolios (name, status) VALUES (?, ?)", [new_name, src[0]]
        )
        new_pid = con.execute("SELECT currval('seq_portfolio')").fetchone()[0]

        # 2. Copy criteria (map old id → new id)
        old_criteria = con.execute(
            "SELECT id, name, display_order, is_special, special_type "
            "FROM criteria WHERE portfolio_id = ? ORDER BY id",
            [source_id],
        ).fetchall()
        crit_map: dict[int, int] = {}
        for old_id, name, order, is_sp, sp_type in old_criteria:
            con.execute(
                "INSERT INTO criteria (portfolio_id, name, display_order, is_special, special_type) "
                "VALUES (?, ?, ?, ?, ?)",
                [new_pid, name, order, is_sp, sp_type],
            )
            new_cid = con.execute("SELECT currval('seq_criterion')").fetchone()[0]
            crit_map[old_id] = new_cid

        # 3. Copy pairwise comparisons
        old_pw = con.execute(
            "SELECT criterion_row, criterion_col, value "
            "FROM pairwise_comparisons WHERE portfolio_id = ?",
            [source_id],
        ).fetchall()
        for row_cid, col_cid, val in old_pw:
            if row_cid in crit_map and col_cid in crit_map:
                con.execute(
                    "INSERT INTO pairwise_comparisons (portfolio_id, criterion_row, criterion_col, value) "
                    "VALUES (?, ?, ?, ?)",
                    [new_pid, crit_map[row_cid], crit_map[col_cid], val],
                )

        # 4. Copy platforms (map old id → new id)
        old_platforms = con.execute(
            "SELECT id, name, status FROM platforms WHERE portfolio_id = ? ORDER BY id",
            [source_id],
        ).fetchall()
        plat_map: dict[int, int] = {}
        for old_plat_id, plat_name, plat_status in old_platforms:
            con.execute(
                "INSERT INTO platforms (portfolio_id, name, status) VALUES (?, ?, ?)",
                [new_pid, plat_name, plat_status],
            )
            new_plat_id = con.execute("SELECT currval('seq_platform')").fetchone()[0]
            plat_map[old_plat_id] = new_plat_id

        # 5. Copy scores
        for old_plat_id, new_plat_id in plat_map.items():
            old_scores = con.execute(
                "SELECT criterion_id, score, note FROM scores WHERE platform_id = ?",
                [old_plat_id],
            ).fetchall()
            for cid, score, note in old_scores:
                if cid in crit_map:
                    con.execute(
                        "INSERT INTO scores (platform_id, criterion_id, score, note) VALUES (?, ?, ?, ?)",
                        [new_plat_id, crit_map[cid], score, note],
                    )

        # 6. Copy interest_rates
        for old_plat_id, new_plat_id in plat_map.items():
            row = con.execute(
                "SELECT estimated_rate FROM interest_rates WHERE platform_id = ?",
                [old_plat_id],
            ).fetchone()
            if row:
                con.execute(
                    "INSERT INTO interest_rates (platform_id, estimated_rate) VALUES (?, ?)",
                    [new_plat_id, row[0]],
                )

        # 7. Copy country_statuses
        for old_plat_id, new_plat_id in plat_map.items():
            rows = con.execute(
                "SELECT country, status, note FROM country_statuses WHERE platform_id = ?",
                [old_plat_id],
            ).fetchall()
            for country, status, note in rows:
                con.execute(
                    "INSERT INTO country_statuses (platform_id, country, status, note) VALUES (?, ?, ?, ?)",
                    [new_plat_id, country, status, note],
                )

        # 8. Copy country_allocations
        for old_plat_id, new_plat_id in plat_map.items():
            row = con.execute(
                "SELECT allocation_mode, excluded_statuses FROM country_allocations WHERE platform_id = ?",
                [old_plat_id],
            ).fetchone()
            if row:
                con.execute(
                    "INSERT INTO country_allocations (platform_id, allocation_mode, excluded_statuses) VALUES (?, ?, ?)",
                    [new_plat_id, row[0], row[1]],
                )

        # 9. Copy country_allocation_pcts
        for old_plat_id, new_plat_id in plat_map.items():
            rows = con.execute(
                "SELECT country, pct, value FROM country_allocation_pcts WHERE platform_id = ?",
                [old_plat_id],
            ).fetchall()
            for country, pct, val in rows:
                con.execute(
                    "INSERT INTO country_allocation_pcts (platform_id, country, pct, value) VALUES (?, ?, ?, ?)",
                    [new_plat_id, country, pct, val],
                )

        # 10. Copy off_budget_pockets
        for old_plat_id, new_plat_id in plat_map.items():
            rows = con.execute(
                "SELECT name, amount, note FROM off_budget_pockets WHERE platform_id = ?",
                [old_plat_id],
            ).fetchall()
            for name, amount, note in rows:
                con.execute(
                    "INSERT INTO off_budget_pockets (platform_id, name, amount, note) VALUES (?, ?, ?, ?)",
                    [new_plat_id, name, amount, note],
                )

        # 11. Copy loan_originators
        for old_plat_id, new_plat_id in plat_map.items():
            rows = con.execute(
                "SELECT country, originator_name, num_loans, note FROM loan_originators WHERE platform_id = ?",
                [old_plat_id],
            ).fetchall()
            for country, orig_name, num_loans, note in rows:
                con.execute(
                    "INSERT INTO loan_originators (platform_id, country, originator_name, num_loans, note) VALUES (?, ?, ?, ?, ?)",
                    [new_plat_id, country, orig_name, num_loans, note],
                )

        # 12. Copy auto_score_equations
        rows = con.execute(
            "SELECT special_type, equation, enabled FROM auto_score_equations WHERE portfolio_id = ?",
            [source_id],
        ).fetchall()
        for sp_type, equation, enabled in rows:
            con.execute(
                "INSERT INTO auto_score_equations (portfolio_id, special_type, equation, enabled) VALUES (?, ?, ?, ?)",
                [new_pid, sp_type, equation, enabled],
            )

        return new_pid

    # ── Platform CRUD ───────────────────────────────────────────────

    @staticmethod
    def list_platforms(portfolio_id: int, include_inactive: bool = True) -> pd.DataFrame:
        """List platforms sorted by status (Running first) then by latest balance descending.

        If include_inactive is False, platforms with status Closed/Defaulted AND 0 balance are excluded.
        """
        con = get_connection()
        df = con.execute(
            """SELECT p.id, p.name, p.status,
                      COALESCE(bs.balance, 0) AS latest_balance
               FROM platforms p
               LEFT JOIN (
                   SELECT platform_id, balance
                   FROM balance_snapshots
                   WHERE (platform_id, month) IN (
                       SELECT platform_id, MAX(month) FROM balance_snapshots GROUP BY platform_id
                   )
               ) bs ON p.id = bs.platform_id
               WHERE p.portfolio_id = ?
               ORDER BY
                   CASE p.status
                       WHEN 'Running' THEN 1
                       WHEN 'Dissaving' THEN 2
                       WHEN 'Defaulted' THEN 3
                       WHEN 'Closed' THEN 4
                       ELSE 5
                   END,
                   COALESCE(bs.balance, 0) DESC,
                   p.name""",
            [int(portfolio_id)],
        ).fetchdf()
        if not include_inactive:
            df = df[~((df["status"].isin(["Closed", "Defaulted"])) & (df["latest_balance"] == 0))]
        return df

    @staticmethod
    def create_platform(portfolio_id: int, name: str, status: str = "Running") -> int:
        con = get_connection()
        con.execute(
            "INSERT INTO platforms (portfolio_id, name, status) VALUES (?, ?, ?)",
            [portfolio_id, name, status],
        )
        return con.execute("SELECT currval('seq_platform')").fetchone()[0]

    @staticmethod
    def update_platform(platform_id: int, name: str, status: str) -> None:
        con = get_connection()
        pid = int(platform_id)
        # DuckDB UPDATE = internal DELETE+INSERT, which triggers FK checks.
        # Workaround: detach dependent rows, update, re-attach.
        dep_tables = [
            "country_allocation_pcts", "country_allocations",
            "scores", "country_statuses", "interest_rates",
            "off_budget_pockets", "loan_originators", "balance_snapshots",
        ]
        saved: dict[str, list] = {}
        for tbl in dep_tables:
            saved[tbl] = con.execute(
                f"SELECT * FROM {tbl} WHERE platform_id = ?", [pid]
            ).fetchall()
            con.execute(f"DELETE FROM {tbl} WHERE platform_id = ?", [pid])
        con.execute(
            "UPDATE platforms SET name = ?, status = ? WHERE id = ?",
            [name, status, pid],
        )
        for tbl in reversed(dep_tables):
            for row in saved[tbl]:
                ph = ", ".join(["?"] * len(row))
                con.execute(f"INSERT INTO {tbl} VALUES ({ph})", list(row))

    @staticmethod
    def delete_platform(platform_id: int) -> None:
        con = get_connection()
        con.execute("DELETE FROM balance_snapshots WHERE platform_id = ?", [platform_id])
        con.execute("DELETE FROM loan_originators WHERE platform_id = ?", [platform_id])
        con.execute("DELETE FROM off_budget_pockets WHERE platform_id = ?", [platform_id])
        con.execute("DELETE FROM interest_rates WHERE platform_id = ?", [platform_id])
        con.execute("DELETE FROM country_statuses WHERE platform_id = ?", [platform_id])
        con.execute("DELETE FROM scores WHERE platform_id = ?", [platform_id])
        con.execute("DELETE FROM platforms WHERE id = ?", [platform_id])
