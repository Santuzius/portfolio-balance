"""Data access layer – every SQL query lives here.

ViewModels must NOT import get_connection() or execute SQL directly.
They call repository methods and perform business logic on results.
"""

from __future__ import annotations

from datetime import date
import pandas as pd
from app.models.database import get_connection


# ── Portfolio ───────────────────────────────────────────────────────


class PortfolioRepo:

    @staticmethod
    def list_all() -> pd.DataFrame:
        return get_connection().execute(
            "SELECT id, name, status, created_at FROM portfolios ORDER BY name"
        ).fetchdf()

    @staticmethod
    def get(portfolio_id: int) -> tuple | None:
        return get_connection().execute(
            "SELECT id, name, status FROM portfolios WHERE id = ?",
            [int(portfolio_id)],
        ).fetchone()

    @staticmethod
    def create(name: str, status: str) -> int:
        con = get_connection()
        con.execute(
            "INSERT INTO portfolios (name, status) VALUES (?, ?)", [name, status]
        )
        return con.execute("SELECT currval('seq_portfolio')").fetchone()[0]

    @staticmethod
    def update(portfolio_id: int, name: str, status: str) -> None:
        get_connection().execute(
            "UPDATE portfolios SET name = ?, status = ? WHERE id = ?",
            [name, status, int(portfolio_id)],
        )

    @staticmethod
    def delete_cascade(portfolio_id: int) -> None:
        con = get_connection()
        pid = int(portfolio_id)
        pids = [r[0] for r in con.execute(
            "SELECT id FROM platforms WHERE portfolio_id = ?", [pid]
        ).fetchall()]
        for p in pids:
            PlatformRepo.delete_cascade(p)
        con.execute("DELETE FROM auto_score_equations WHERE portfolio_id = ?", [pid])
        con.execute("DELETE FROM pairwise_comparisons WHERE portfolio_id = ?", [pid])
        con.execute("DELETE FROM criteria WHERE portfolio_id = ?", [pid])
        con.execute("DELETE FROM portfolios WHERE id = ?", [pid])

    @staticmethod
    def copy(source_id: int, new_name: str) -> int:
        """Deep-copy a portfolio. Everything except balance_snapshots."""
        con = get_connection()

        src = con.execute(
            "SELECT status FROM portfolios WHERE id = ?", [source_id]
        ).fetchone()
        if src is None:
            raise ValueError("Source portfolio not found.")
        con.execute(
            "INSERT INTO portfolios (name, status) VALUES (?, ?)", [new_name, src[0]]
        )
        new_pid = con.execute("SELECT currval('seq_portfolio')").fetchone()[0]

        # criteria
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
            crit_map[old_id] = con.execute("SELECT currval('seq_criterion')").fetchone()[0]

        # pairwise comparisons
        for row_cid, col_cid, val in con.execute(
            "SELECT criterion_row, criterion_col, value "
            "FROM pairwise_comparisons WHERE portfolio_id = ?",
            [source_id],
        ).fetchall():
            if row_cid in crit_map and col_cid in crit_map:
                con.execute(
                    "INSERT INTO pairwise_comparisons "
                    "(portfolio_id, criterion_row, criterion_col, value) VALUES (?, ?, ?, ?)",
                    [new_pid, crit_map[row_cid], crit_map[col_cid], val],
                )

        # platforms
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
            plat_map[old_plat_id] = con.execute("SELECT currval('seq_platform')").fetchone()[0]

        # per-platform data
        for old_pid, new_plat_id in plat_map.items():
            # scores
            for cid, score, note in con.execute(
                "SELECT criterion_id, score, note FROM scores WHERE platform_id = ?",
                [old_pid],
            ).fetchall():
                if cid in crit_map:
                    con.execute(
                        "INSERT INTO scores (platform_id, criterion_id, score, note) "
                        "VALUES (?, ?, ?, ?)",
                        [new_plat_id, crit_map[cid], score, note],
                    )
            # interest_rates
            row = con.execute(
                "SELECT estimated_rate FROM interest_rates WHERE platform_id = ?",
                [old_pid],
            ).fetchone()
            if row:
                con.execute(
                    "INSERT INTO interest_rates (platform_id, estimated_rate) "
                    "VALUES (?, ?)",
                    [new_plat_id, row[0]],
                )
            # country_statuses
            for country, status, note in con.execute(
                "SELECT country, status, note FROM country_statuses WHERE platform_id = ?",
                [old_pid],
            ).fetchall():
                con.execute(
                    "INSERT INTO country_statuses (platform_id, country, status, note) "
                    "VALUES (?, ?, ?, ?)",
                    [new_plat_id, country, status, note],
                )
            # country_allocations
            row = con.execute(
                "SELECT allocation_mode, excluded_statuses "
                "FROM country_allocations WHERE platform_id = ?",
                [old_pid],
            ).fetchone()
            if row:
                con.execute(
                    "INSERT INTO country_allocations "
                    "(platform_id, allocation_mode, excluded_statuses) VALUES (?, ?, ?)",
                    [new_plat_id, row[0], row[1]],
                )
            # country_allocation_pcts
            for country, pct, val in con.execute(
                "SELECT country, pct, value FROM country_allocation_pcts "
                "WHERE platform_id = ?",
                [old_pid],
            ).fetchall():
                con.execute(
                    "INSERT INTO country_allocation_pcts "
                    "(platform_id, country, pct, value) VALUES (?, ?, ?, ?)",
                    [new_plat_id, country, pct, val],
                )
            # off_budget_pockets
            for name, amount, note in con.execute(
                "SELECT name, amount, note FROM off_budget_pockets WHERE platform_id = ?",
                [old_pid],
            ).fetchall():
                con.execute(
                    "INSERT INTO off_budget_pockets (platform_id, name, amount, note) "
                    "VALUES (?, ?, ?, ?)",
                    [new_plat_id, name, amount, note],
                )
            # loan_originators
            for country, orig_name, num_loans, note in con.execute(
                "SELECT country, originator_name, num_loans, note "
                "FROM loan_originators WHERE platform_id = ?",
                [old_pid],
            ).fetchall():
                con.execute(
                    "INSERT INTO loan_originators "
                    "(platform_id, country, originator_name, num_loans, note) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [new_plat_id, country, orig_name, num_loans, note],
                )

        # auto_score_equations
        for sp_type, equation, enabled in con.execute(
            "SELECT special_type, equation, enabled "
            "FROM auto_score_equations WHERE portfolio_id = ?",
            [source_id],
        ).fetchall():
            con.execute(
                "INSERT INTO auto_score_equations "
                "(portfolio_id, special_type, equation, enabled) VALUES (?, ?, ?, ?)",
                [new_pid, sp_type, equation, enabled],
            )

        return new_pid


# ── Platform ────────────────────────────────────────────────────────


class PlatformRepo:

    @staticmethod
    def list_for_portfolio(portfolio_id: int) -> pd.DataFrame:
        """Return all platforms with latest balance, ordered by status then balance."""
        return get_connection().execute(
            """SELECT p.id, p.name, p.status,
                      COALESCE(bs.balance, 0) AS latest_balance
               FROM platforms p
               LEFT JOIN (
                   SELECT platform_id, balance
                   FROM balance_snapshots
                   WHERE (platform_id, month) IN (
                       SELECT platform_id, MAX(month)
                       FROM balance_snapshots GROUP BY platform_id
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

    @staticmethod
    def list_simple(portfolio_id: int) -> pd.DataFrame:
        """Lightweight platform list (no balance join)."""
        return get_connection().execute(
            "SELECT id, name, status FROM platforms WHERE portfolio_id = ? ORDER BY name",
            [int(portfolio_id)],
        ).fetchdf()

    @staticmethod
    def create(portfolio_id: int, name: str, status: str) -> int:
        con = get_connection()
        con.execute(
            "INSERT INTO platforms (portfolio_id, name, status) VALUES (?, ?, ?)",
            [int(portfolio_id), name, status],
        )
        return con.execute("SELECT currval('seq_platform')").fetchone()[0]

    @staticmethod
    def update(platform_id: int, name: str, status: str) -> None:
        """FK-safe update (DuckDB UPDATE = internal DELETE+INSERT)."""
        con = get_connection()
        pid = int(platform_id)
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
    def delete_cascade(platform_id: int) -> None:
        con = get_connection()
        pid = int(platform_id)
        for tbl in [
            "country_allocation_pcts", "country_allocations",
            "balance_snapshots", "loan_originators", "off_budget_pockets",
            "interest_rates", "country_statuses", "scores",
        ]:
            con.execute(f"DELETE FROM {tbl} WHERE platform_id = ?", [pid])
        con.execute("DELETE FROM platforms WHERE id = ?", [pid])


# ── Criteria & Pairwise ─────────────────────────────────────────────


class CriteriaRepo:

    @staticmethod
    def list_for_portfolio(portfolio_id: int) -> pd.DataFrame:
        return get_connection().execute(
            """SELECT id, name, display_order, is_special, special_type
               FROM criteria WHERE portfolio_id = ? ORDER BY display_order""",
            [int(portfolio_id)],
        ).fetchdf()

    @staticmethod
    def create(
        portfolio_id: int, name: str, display_order: int,
        is_special: bool, special_type: str | None,
    ) -> int:
        con = get_connection()
        con.execute(
            "INSERT INTO criteria "
            "(portfolio_id, name, display_order, is_special, special_type) "
            "VALUES (?, ?, ?, ?, ?)",
            [int(portfolio_id), name, display_order, is_special, special_type],
        )
        return con.execute("SELECT currval('seq_criterion')").fetchone()[0]

    @staticmethod
    def update(
        criterion_id: int, name: str, display_order: int,
        is_special: bool, special_type: str | None,
    ) -> None:
        """FK-safe update (DuckDB UPDATE = internal DELETE+INSERT)."""
        con = get_connection()
        cid = int(criterion_id)
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
            "DELETE FROM pairwise_comparisons "
            "WHERE criterion_row = ? OR criterion_col = ?",
            [cid, cid],
        )
        con.execute("DELETE FROM scores WHERE criterion_id = ?", [cid])
        con.execute(
            "UPDATE criteria "
            "SET name = ?, display_order = ?, is_special = ?, special_type = ? "
            "WHERE id = ?",
            [name, display_order, is_special, special_type, cid],
        )
        for r in pw_rows:
            con.execute(
                "INSERT INTO pairwise_comparisons "
                "(portfolio_id, criterion_row, criterion_col, value) VALUES (?, ?, ?, ?)",
                list(r),
            )
        for r in sc_rows:
            con.execute(
                "INSERT INTO scores (platform_id, criterion_id, score, note) "
                "VALUES (?, ?, ?, ?)",
                list(r),
            )

    @staticmethod
    def delete(criterion_id: int) -> None:
        con = get_connection()
        cid = int(criterion_id)
        con.execute(
            "DELETE FROM pairwise_comparisons "
            "WHERE criterion_row = ? OR criterion_col = ?",
            [cid, cid],
        )
        con.execute("DELETE FROM scores WHERE criterion_id = ?", [cid])
        con.execute("DELETE FROM criteria WHERE id = ?", [cid])

    @staticmethod
    def get_pairwise_values(portfolio_id: int) -> pd.DataFrame:
        """Raw pairwise comparison values (criterion_row, criterion_col, value)."""
        return get_connection().execute(
            "SELECT criterion_row, criterion_col, value "
            "FROM pairwise_comparisons WHERE portfolio_id = ?",
            [int(portfolio_id)],
        ).fetchdf()

    @staticmethod
    def get_pairwise_named(portfolio_id: int) -> pd.DataFrame:
        """Pairwise values with criterion names."""
        return get_connection().execute(
            """SELECT cr.name AS row_name, cc.name AS col_name, pc.value
               FROM pairwise_comparisons pc
               JOIN criteria cr ON pc.criterion_row = cr.id
               JOIN criteria cc ON pc.criterion_col = cc.id
               WHERE pc.portfolio_id = ?""",
            [int(portfolio_id)],
        ).fetchdf()

    @staticmethod
    def save_pairwise_value(
        portfolio_id: int, row_id: int, col_id: int, value: int,
    ) -> None:
        """Save a pairwise value and its mirror."""
        con = get_connection()
        pid, rid, cid, val = (
            int(portfolio_id), int(row_id), int(col_id), int(value),
        )
        con.execute(
            """INSERT INTO pairwise_comparisons
               (portfolio_id, criterion_row, criterion_col, value)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (portfolio_id, criterion_row, criterion_col)
               DO UPDATE SET value = excluded.value""",
            [pid, rid, cid, val],
        )
        mirror = 2 - val
        con.execute(
            """INSERT INTO pairwise_comparisons
               (portfolio_id, criterion_row, criterion_col, value)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (portfolio_id, criterion_row, criterion_col)
               DO UPDATE SET value = excluded.value""",
            [pid, cid, rid, mirror],
        )

    @staticmethod
    def get_pairwise_row_sums(
        portfolio_id: int,
    ) -> list[tuple[int, str, float]]:
        """Return [(criterion_id, name, raw_sum), …] ordered by display_order."""
        con = get_connection()
        criteria = con.execute(
            "SELECT id, name FROM criteria "
            "WHERE portfolio_id = ? ORDER BY display_order",
            [int(portfolio_id)],
        ).fetchall()
        result: list[tuple[int, str, float]] = []
        for cid, name in criteria:
            row = con.execute(
                "SELECT COALESCE(SUM(value), 0) FROM pairwise_comparisons "
                "WHERE portfolio_id = ? AND criterion_row = ?",
                [int(portfolio_id), int(cid)],
            ).fetchone()
            result.append((int(cid), name, float(row[0])))
        return result


# ── Scores ──────────────────────────────────────────────────────────


class ScoreRepo:

    @staticmethod
    def get_matrix(portfolio_id: int) -> pd.DataFrame:
        """Pivoted score matrix: rows=platforms, columns=criteria."""
        df = get_connection().execute(
            """SELECT p.name AS platform, c.name AS criterion, s.score
               FROM scores s
               JOIN platforms p ON s.platform_id = p.id
               JOIN criteria c ON s.criterion_id = c.id
               WHERE p.portfolio_id = ?
               ORDER BY p.name, c.display_order""",
            [int(portfolio_id)],
        ).fetchdf()
        if df.empty:
            return pd.DataFrame()
        return df.pivot_table(
            index="platform", columns="criterion",
            values="score", aggfunc="first",
        ).fillna(0)

    @staticmethod
    def get_for_platform(platform_id: int) -> pd.DataFrame:
        """All criteria for a platform with current scores."""
        pid = int(platform_id)
        return get_connection().execute(
            """SELECT c.id AS criterion_id, c.name,
                      COALESCE(s.score, 0) AS score,
                      COALESCE(s.note, '') AS note
               FROM criteria c
               LEFT JOIN scores s ON s.criterion_id = c.id AND s.platform_id = ?
               WHERE c.portfolio_id = (
                   SELECT portfolio_id FROM platforms WHERE id = ?
               )
               ORDER BY c.display_order""",
            [pid, pid],
        ).fetchdf()

    @staticmethod
    def get_raw_scores(platform_id: int) -> pd.DataFrame:
        """criterion_id + score only (for allocation computation)."""
        return get_connection().execute(
            "SELECT criterion_id, score FROM scores WHERE platform_id = ?",
            [int(platform_id)],
        ).fetchdf()

    @staticmethod
    def save(
        platform_id: int, criterion_id: int, score: float, note: str = "",
    ) -> None:
        get_connection().execute(
            """INSERT INTO scores (platform_id, criterion_id, score, note)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (platform_id, criterion_id)
               DO UPDATE SET score = excluded.score, note = excluded.note""",
            [int(platform_id), int(criterion_id), float(score), note],
        )


# ── Balance Snapshots ───────────────────────────────────────────────


class BalanceRepo:

    @staticmethod
    def record(platform_id: int, month: date, balance: float) -> None:
        get_connection().execute(
            """INSERT INTO balance_snapshots (platform_id, month, balance)
               VALUES (?, ?, ?)
               ON CONFLICT (platform_id, month)
               DO UPDATE SET balance = excluded.balance""",
            [int(platform_id), month, float(balance)],
        )

    @staticmethod
    def delete(snapshot_id: int) -> None:
        get_connection().execute(
            "DELETE FROM balance_snapshots WHERE id = ?", [int(snapshot_id)]
        )

    @staticmethod
    def get_all_for_portfolio(portfolio_id: int) -> pd.DataFrame:
        return get_connection().execute(
            """SELECT bs.id, p.name AS platform, bs.month, bs.balance,
                      p.id AS platform_id
               FROM balance_snapshots bs
               JOIN platforms p ON bs.platform_id = p.id
               WHERE p.portfolio_id = ?
               ORDER BY bs.month DESC, p.name""",
            [int(portfolio_id)],
        ).fetchdf()

    @staticmethod
    def get_latest(portfolio_id: int) -> pd.DataFrame:
        return get_connection().execute(
            """SELECT p.id AS platform_id, p.name AS platform, p.status,
                      bs.balance, bs.month
               FROM platforms p
               LEFT JOIN (
                   SELECT platform_id, balance, month
                   FROM balance_snapshots
                   WHERE (platform_id, month) IN (
                       SELECT platform_id, MAX(month)
                       FROM balance_snapshots GROUP BY platform_id
                   )
               ) bs ON p.id = bs.platform_id
               WHERE p.portfolio_id = ?
               ORDER BY p.name""",
            [int(portfolio_id)],
        ).fetchdf()

    @staticmethod
    def get_off_budget_totals(portfolio_id: int) -> pd.DataFrame:
        return get_connection().execute(
            """SELECT p.id AS platform_id,
                      COALESCE(SUM(ob.amount), 0) AS off_budget_total
               FROM platforms p
               LEFT JOIN off_budget_pockets ob ON p.id = ob.platform_id
               WHERE p.portfolio_id = ?
               GROUP BY p.id""",
            [int(portfolio_id)],
        ).fetchdf()


# ── Off-Budget Pockets ──────────────────────────────────────────────


class PocketRepo:

    @staticmethod
    def list_for_platform(platform_id: int) -> pd.DataFrame:
        return get_connection().execute(
            "SELECT id, name, amount, note "
            "FROM off_budget_pockets WHERE platform_id = ? ORDER BY name",
            [int(platform_id)],
        ).fetchdf()

    @staticmethod
    def create(
        platform_id: int, name: str, amount: float, note: str = "",
    ) -> int:
        con = get_connection()
        con.execute(
            "INSERT INTO off_budget_pockets (platform_id, name, amount, note) "
            "VALUES (?, ?, ?, ?)",
            [int(platform_id), name, float(amount), note],
        )
        return con.execute("SELECT currval('seq_pocket')").fetchone()[0]

    @staticmethod
    def update(
        pocket_id: int, name: str, amount: float, note: str = "",
    ) -> None:
        get_connection().execute(
            "UPDATE off_budget_pockets SET name = ?, amount = ?, note = ? "
            "WHERE id = ?",
            [name, float(amount), note, int(pocket_id)],
        )

    @staticmethod
    def delete(pocket_id: int) -> None:
        get_connection().execute(
            "DELETE FROM off_budget_pockets WHERE id = ?", [int(pocket_id)]
        )


# ── Loan Originators ───────────────────────────────────────────────


class LoanOriginatorRepo:

    @staticmethod
    def list_for_platform(platform_id: int) -> pd.DataFrame:
        return get_connection().execute(
            """SELECT id, country, originator_name, num_loans, note
               FROM loan_originators WHERE platform_id = ? ORDER BY country""",
            [int(platform_id)],
        ).fetchdf()

    @staticmethod
    def save(
        platform_id: int, country: str, originator_name: str,
        num_loans: float, note: str = "",
    ) -> None:
        get_connection().execute(
            """INSERT INTO loan_originators
               (platform_id, country, originator_name, num_loans, note)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (platform_id, country, originator_name)
               DO UPDATE SET num_loans = excluded.num_loans,
                            note = excluded.note""",
            [int(platform_id), country, originator_name, float(num_loans), note],
        )

    @staticmethod
    def delete(originator_id: int) -> None:
        get_connection().execute(
            "DELETE FROM loan_originators WHERE id = ?", [int(originator_id)]
        )


# ── Interest Rates ──────────────────────────────────────────────────


class InterestRateRepo:

    @staticmethod
    def get_rates(portfolio_id: int) -> pd.DataFrame:
        return get_connection().execute(
            """SELECT p.id AS platform_id, p.name AS platform,
                      COALESCE(ir.estimated_rate, 0) AS estimated_rate
               FROM platforms p
               LEFT JOIN interest_rates ir ON p.id = ir.platform_id
               WHERE p.portfolio_id = ?
               ORDER BY p.name""",
            [int(portfolio_id)],
        ).fetchdf()

    @staticmethod
    def save_rate(platform_id: int, estimated_rate: float) -> None:
        get_connection().execute(
            """INSERT INTO interest_rates (platform_id, estimated_rate)
               VALUES (?, ?)
               ON CONFLICT (platform_id)
               DO UPDATE SET estimated_rate = excluded.estimated_rate""",
            [int(platform_id), float(estimated_rate)],
        )


# ── Country Statuses ────────────────────────────────────────────────


class CountryStatusRepo:

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
    def save(
        platform_id: int | None, country: str, status: str, note: str = "",
    ) -> None:
        get_connection().execute(
            """INSERT INTO country_statuses (platform_id, country, status, note)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (platform_id, country)
               DO UPDATE SET status = excluded.status, note = excluded.note""",
            [
                int(platform_id) if platform_id is not None else None,
                country, status, note,
            ],
        )

    @staticmethod
    def update(
        status_id: int, new_status: str, note: str | None = None,
    ) -> None:
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
    def delete(status_id: int) -> None:
        get_connection().execute(
            "DELETE FROM country_statuses WHERE id = ?", [int(status_id)]
        )


# ── Country Allocation ──────────────────────────────────────────────


class CountryAllocationRepo:

    @staticmethod
    def get_mode_raw(platform_id: int) -> str | None:
        row = get_connection().execute(
            "SELECT allocation_mode FROM country_allocations WHERE platform_id = ?",
            [int(platform_id)],
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def set_mode(platform_id: int, mode: str) -> None:
        get_connection().execute(
            """INSERT INTO country_allocations (platform_id, allocation_mode)
               VALUES (?, ?)
               ON CONFLICT (platform_id)
               DO UPDATE SET allocation_mode = excluded.allocation_mode""",
            [int(platform_id), mode],
        )

    @staticmethod
    def get_excluded_statuses_raw(platform_id: int) -> str:
        row = get_connection().execute(
            "SELECT excluded_statuses FROM country_allocations WHERE platform_id = ?",
            [int(platform_id)],
        ).fetchone()
        return row[0] if row and row[0] else ""

    @staticmethod
    def set_excluded_statuses(platform_id: int, excluded_csv: str) -> None:
        get_connection().execute(
            """INSERT INTO country_allocations (platform_id, excluded_statuses)
               VALUES (?, ?)
               ON CONFLICT (platform_id)
               DO UPDATE SET excluded_statuses = excluded.excluded_statuses""",
            [int(platform_id), excluded_csv],
        )

    @staticmethod
    def get_pcts(platform_id: int) -> pd.DataFrame:
        return get_connection().execute(
            "SELECT country, pct, value FROM country_allocation_pcts "
            "WHERE platform_id = ? ORDER BY country",
            [int(platform_id)],
        ).fetchdf()

    @staticmethod
    def save_pct(
        platform_id: int, country: str, pct: float, value: float = 0.0,
    ) -> None:
        get_connection().execute(
            """INSERT INTO country_allocation_pcts (platform_id, country, pct, value)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (platform_id, country)
               DO UPDATE SET pct = excluded.pct, value = excluded.value""",
            [int(platform_id), country, float(pct), float(value)],
        )


# ── Auto-Score Equations ────────────────────────────────────────────


class AutoScoreRepo:

    @staticmethod
    def get_equation(
        portfolio_id: int, special_type: str,
    ) -> tuple | None:
        """Return (equation, enabled) or None."""
        return get_connection().execute(
            "SELECT equation, enabled FROM auto_score_equations "
            "WHERE portfolio_id = ? AND special_type = ?",
            [int(portfolio_id), special_type],
        ).fetchone()

    @staticmethod
    def save_equation(
        portfolio_id: int, special_type: str,
        equation: str, enabled: bool,
    ) -> None:
        get_connection().execute(
            """INSERT INTO auto_score_equations
               (portfolio_id, special_type, equation, enabled)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (portfolio_id, special_type)
               DO UPDATE SET equation = excluded.equation,
                            enabled = excluded.enabled""",
            [int(portfolio_id), special_type, equation, enabled],
        )
