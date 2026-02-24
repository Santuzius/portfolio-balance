"""
Database layer – DuckDB-backed persistence for Portfolio Balance.

All tables are created idempotently (CREATE TABLE IF NOT EXISTS).
"""

from __future__ import annotations

import duckdb
import streamlit as st
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "pb-data" / "portfolio_balance.duckdb"


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a cached persistent DuckDB connection (singleton)."""
    con = duckdb.connect(str(DB_PATH))
    _bootstrap(con)
    return con


def _bootstrap(con: duckdb.DuckDBPyConnection) -> None:
    """Create schema if it doesn't exist yet."""

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_portfolio START 1;
        CREATE TABLE IF NOT EXISTS portfolios (
            id              INTEGER DEFAULT nextval('seq_portfolio') PRIMARY KEY,
            name            TEXT NOT NULL UNIQUE,
            status          TEXT NOT NULL DEFAULT 'Running'
                            CHECK (status IN ('Running','Dissaving','Defaulted','Closed')),
            created_at      TIMESTAMP DEFAULT current_timestamp
        );
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_platform START 1;
        CREATE TABLE IF NOT EXISTS platforms (
            id              INTEGER DEFAULT nextval('seq_platform') PRIMARY KEY,
            portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id),
            name            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'Running'
                            CHECK (status IN ('Running','Dissaving','Defaulted','Closed')),
            UNIQUE (portfolio_id, name)
        );
    """)

    # ----- MCDA criteria (per portfolio) -----
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_criterion START 1;
        CREATE TABLE IF NOT EXISTS criteria (
            id              INTEGER DEFAULT nextval('seq_criterion') PRIMARY KEY,
            portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id),
            name            TEXT NOT NULL,
            display_order   INTEGER NOT NULL DEFAULT 0,
            is_special      BOOLEAN NOT NULL DEFAULT FALSE,
            special_type    TEXT DEFAULT NULL,
            UNIQUE (portfolio_id, name)
        );
    """)

    # ----- Pairwise comparison (weighting matrix) -----
    con.execute("""
        CREATE TABLE IF NOT EXISTS pairwise_comparisons (
            portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id),
            criterion_row   INTEGER NOT NULL REFERENCES criteria(id),
            criterion_col   INTEGER NOT NULL REFERENCES criteria(id),
            value           INTEGER NOT NULL CHECK (value IN (0,1,2)),
            PRIMARY KEY (portfolio_id, criterion_row, criterion_col)
        );
    """)

    # ----- Evaluation / Scoring of each platform per criterion -----
    con.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            platform_id     INTEGER NOT NULL REFERENCES platforms(id),
            criterion_id    INTEGER NOT NULL REFERENCES criteria(id),
            score           DOUBLE NOT NULL DEFAULT 0,
            note            TEXT DEFAULT '',
            PRIMARY KEY (platform_id, criterion_id)
        );
    """)

    # ----- Monthly balance snapshots -----
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_snapshot START 1;
        CREATE TABLE IF NOT EXISTS balance_snapshots (
            id              INTEGER DEFAULT nextval('seq_snapshot') PRIMARY KEY,
            platform_id     INTEGER NOT NULL REFERENCES platforms(id),
            month           DATE NOT NULL,
            balance         DOUBLE NOT NULL DEFAULT 0,
            UNIQUE (platform_id, month)
        );
    """)

    # ----- Loan originators (per platform) -----
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_originator START 1;
        CREATE TABLE IF NOT EXISTS loan_originators (
            id              INTEGER DEFAULT nextval('seq_originator') PRIMARY KEY,
            platform_id     INTEGER NOT NULL REFERENCES platforms(id),
            country         TEXT NOT NULL DEFAULT '',
            originator_name TEXT NOT NULL DEFAULT '',
            num_loans       DOUBLE NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'Running'
                            CHECK (status IN (
                                'Separated','Running','Being Relocated','To Relocate',
                                'High Supply','Possible','To Be Tested',
                                'Low Supply Active','Low Supply Inactive',
                                'Risky','Defaulted','Filtered Out')),
            note            TEXT DEFAULT '',
            UNIQUE (platform_id, country, originator_name)
        );
    """)

    # ----- Off-budget pockets -----
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_pocket START 1;
        CREATE TABLE IF NOT EXISTS off_budget_pockets (
            id              INTEGER DEFAULT nextval('seq_pocket') PRIMARY KEY,
            platform_id     INTEGER NOT NULL REFERENCES platforms(id),
            name            TEXT NOT NULL,
            amount          DOUBLE NOT NULL DEFAULT 0,
            note            TEXT DEFAULT ''
        );
    """)

    # ----- Interest rates (special criterion data) -----
    con.execute("""
        CREATE TABLE IF NOT EXISTS interest_rates (
            platform_id     INTEGER NOT NULL REFERENCES platforms(id) PRIMARY KEY,
            estimated_rate  DOUBLE NOT NULL DEFAULT 0
        );
    """)

    # ----- Country status (special criterion data) -----
    # Statuses ordered by priority (best first):
    #   Separated, Running, Being Relocated, To Relocate, High Supply,
    #   Possible, To Be Tested, Low Supply Active, Low Supply Inactive,
    #   Risky, Filtered Out
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_country_status START 1;
        CREATE TABLE IF NOT EXISTS country_statuses (
            id              INTEGER DEFAULT nextval('seq_country_status') PRIMARY KEY,
            platform_id     INTEGER REFERENCES platforms(id),
            country         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'Possible'
                            CHECK (status IN (
                                'Separated','Running','Being Relocated','To Relocate',
                                'High Supply','Possible','To Be Tested',
                                'Low Supply Active','Low Supply Inactive',
                                'Risky','Defaulted','Filtered Out')),
            note            TEXT DEFAULT '',
            UNIQUE (platform_id, country)
        );
    """)

    # ----- Country allocation per platform -----
    con.execute("""
        CREATE TABLE IF NOT EXISTS country_allocations (
            platform_id     INTEGER NOT NULL REFERENCES platforms(id),
            allocation_mode TEXT NOT NULL DEFAULT 'equal',
            excluded_statuses TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (platform_id)
        );
    """)

    # Per-country manual allocation percentage (and optional absolute value)
    con.execute("""
        CREATE TABLE IF NOT EXISTS country_allocation_pcts (
            platform_id     INTEGER NOT NULL REFERENCES platforms(id),
            country         TEXT NOT NULL,
            pct             DOUBLE NOT NULL DEFAULT 0,
            value           DOUBLE NOT NULL DEFAULT 0,
            PRIMARY KEY (platform_id, country)
        );
    """)

    # ----- Auto-score equations for special criteria -----
    con.execute("""
        CREATE TABLE IF NOT EXISTS auto_score_equations (
            portfolio_id    INTEGER NOT NULL REFERENCES portfolios(id),
            special_type    TEXT NOT NULL,
            equation        TEXT NOT NULL DEFAULT '',
            enabled         BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (portfolio_id, special_type)
        );
    """)

    # ----- Originator allocation per platform -----
    con.execute("""
        CREATE TABLE IF NOT EXISTS originator_allocations (
            platform_id     INTEGER NOT NULL REFERENCES platforms(id),
            allocation_mode TEXT NOT NULL DEFAULT 'equal',
            excluded_statuses TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (platform_id)
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS originator_allocation_pcts (
            platform_id     INTEGER NOT NULL REFERENCES platforms(id),
            originator_key  TEXT NOT NULL,
            pct             DOUBLE NOT NULL DEFAULT 0,
            value           DOUBLE NOT NULL DEFAULT 0,
            PRIMARY KEY (platform_id, originator_key)
        );
    """)

    # ----- Schema migrations for existing databases -----
    _migrate(con)


def _migrate(con: duckdb.DuckDBPyConnection) -> None:
    """Idempotent schema migrations for existing databases."""

    # loan_originators: add 'status' column if missing (pre-v2 databases)
    cols = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'loan_originators'"
        ).fetchall()
    }
    if cols and "status" not in cols:
        con.execute(
            "ALTER TABLE loan_originators ADD COLUMN status TEXT NOT NULL DEFAULT 'Running'"
        )