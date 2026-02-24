"""
Portfolio Balance – Multi-Criteria Decision Analysis for Investment Portfolios.

Entry point for the Streamlit application.
Run with:  streamlit run app/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add workspace root to path so 'app' module can be imported
workspace_root = Path(__file__).parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

import streamlit as st

# Force DB initialisation on import
from app.models.database import get_connection
get_connection()

from app.views.components.common import portfolio_selector
from app.viewmodels.mcda_vm import CriteriaVM
from app.views.pages import (
    dashboard, portfolios, criteria, scoring, balances,
    interest_rates, countries, loan_originators,
)


st.set_page_config(
    page_title="Portfolio Balance",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar Header ──────────────────────────────────────────────────
st.sidebar.title("Portfolio Balance")
st.sidebar.markdown("*Multi-Criteria Decision Analysis*")
st.sidebar.divider()

# Portfolio selector (also stores in st.session_state["portfolio_id"])
portfolio_id = portfolio_selector()

st.sidebar.divider()

# ── Build page list ─────────────────────────────────────────────────
pages: list[st.Page] = [
    st.Page(dashboard.page, title="Rebalancing", icon="⚖️", url_path="rebalancing"),
    st.Page(portfolios.page, title="Portfolios & Platforms", icon="🗂️", url_path="portfolios"),
    st.Page(criteria.page, title="Criteria", icon="💎", url_path="criteria"),
    st.Page(criteria.page_weighting, title="Weighting Matrix", icon="📐", url_path="weighting"),
    st.Page(scoring.page, title="Scoring Matrix", icon="🏆", url_path="scoring"),
    st.Page(balances.page, title="Balance Tracking", icon="💰", url_path="balances"),
]

# Conditionally show special-criteria pages
if portfolio_id is not None:
    _crit_df = CriteriaVM.list_criteria(portfolio_id)
    if not _crit_df.empty:
        _special = _crit_df[_crit_df["is_special"] == True]  # noqa: E712
        if not _special[_special["special_type"] == "interest_rate"].empty:
            pages.append(
                st.Page(interest_rates.page, title="Interest Rates", icon="📈", url_path="interest-rates"),
            )
        if not _special[_special["special_type"] == "loan_originator"].empty:
            pages.append(
                st.Page(loan_originators.page, title="Loan Originators", icon="🏦", url_path="loan-originators"),
            )
        if not _special[_special["special_type"] == "country"].empty:
            pages.append(
                st.Page(countries.page, title="Countries", icon="🌍", url_path="countries"),
            )

nav = st.navigation(pages)
nav.run()

st.sidebar.divider()
st.sidebar.caption("Built with Streamlit + DuckDB")
