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
from app.views.pages import dashboard, portfolios, criteria, scoring, balances, special_criteria


st.set_page_config(
    page_title="Portfolio Balance",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar Navigation ─────────────────────────────────────────────
st.sidebar.title("Portfolio Balance")
st.sidebar.markdown("*Multi-Criteria Decision Analysis*")
st.sidebar.divider()

# Portfolio selector
portfolio_id = portfolio_selector()

st.sidebar.divider()

PAGES = {
    "📊 Dashboard": "dashboard",
    "🗂️ Portfolios & Platforms": "portfolios",
    "⚖️ Criteria": "criteria",
    "📐 Weighting Matrix": "weighting",
    "🏆 Scoring Matrix": "scoring",
    "💰 Balance Tracking": "balances",
    "📈 Interest Rates": "interest_rates",
    "🌍 Country Status": "country_status",
}

page = st.sidebar.radio("Navigation", list(PAGES.keys()), label_visibility="collapsed")
selected_page = PAGES[page]

st.sidebar.divider()
st.sidebar.caption("Built with Streamlit + DuckDB")

# ── Page Router ─────────────────────────────────────────────────────

if selected_page == "portfolios":
    portfolios.render(portfolio_id)
elif portfolio_id is None:
    st.info("👈 Select or create a portfolio in the sidebar to get started.")
elif selected_page == "dashboard":
    dashboard.render(portfolio_id)
elif selected_page == "criteria":
    criteria.render(portfolio_id)
elif selected_page == "weighting":
    criteria.render_weighting(portfolio_id)
elif selected_page == "scoring":
    scoring.render(portfolio_id)
elif selected_page == "balances":
    balances.render(portfolio_id)
elif selected_page == "interest_rates":
    special_criteria.render_interest_rates(portfolio_id)
elif selected_page == "country_status":
    special_criteria.render_country_status(portfolio_id)
