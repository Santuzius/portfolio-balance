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
