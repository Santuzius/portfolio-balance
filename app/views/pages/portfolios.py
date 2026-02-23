"""Portfolio & Platform management page."""

from __future__ import annotations

import streamlit as st
from app.viewmodels.portfolio_vm import PortfolioVM
from app.views.components.common import (
    PLATFORM_STATUSES,
    status_badge,
)


def render(portfolio_id: int | None) -> None:
    st.header("🗂️ Portfolios & Platforms")

    # ── Create Portfolio ────────────────────────────────────────────
    with st.expander("➕ Create New Portfolio", expanded=portfolio_id is None):
        with st.form("create_portfolio"):
            name = st.text_input("Portfolio Name")
            status = st.selectbox("Status", PLATFORM_STATUSES)
            if st.form_submit_button("Create Portfolio"):
                if name.strip():
                    try:
                        PortfolioVM.create_portfolio(name.strip(), status)
                        st.success(f"Portfolio '{name}' created!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
                else:
                    st.warning("Name cannot be empty.")

    if portfolio_id is None:
        return

    # ── Edit Current Portfolio ──────────────────────────────────────
    portfolio = PortfolioVM.get_portfolio(portfolio_id)
    if portfolio is None:
        st.error("Portfolio not found.")
        return

    st.subheader(f"Portfolio: {portfolio['name']}")
    with st.expander("✏️ Edit Portfolio"):
        with st.form("edit_portfolio"):
            new_name = st.text_input("Name", value=portfolio["name"])
            new_status = st.selectbox(
                "Status",
                PLATFORM_STATUSES,
                index=PLATFORM_STATUSES.index(portfolio["status"]),
            )
            col1, col2 = st.columns(2)
            if col1.form_submit_button("Update"):
                PortfolioVM.update_portfolio(portfolio_id, new_name, new_status)
                st.success("Updated!")
                st.rerun()
            if col2.form_submit_button("🗑️ Delete Portfolio", type="secondary"):
                PortfolioVM.delete_portfolio(portfolio_id)
                st.success("Deleted!")
                st.rerun()

    # ── Platforms ───────────────────────────────────────────────────
    st.subheader("Platforms")

    platforms = PortfolioVM.list_platforms(portfolio_id)

    with st.expander("➕ Add Platform"):
        with st.form("add_platform"):
            p_name = st.text_input("Platform Name")
            p_status = st.selectbox("Status", PLATFORM_STATUSES, key="new_plat_status")
            if st.form_submit_button("Add Platform"):
                if p_name.strip():
                    try:
                        PortfolioVM.create_platform(portfolio_id, p_name.strip(), p_status)
                        st.success(f"Platform '{p_name}' added!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    if platforms.empty:
        st.info("No platforms yet.")
        return

    for _, plat in platforms.iterrows():
        with st.expander(f"{status_badge(plat['status'])} {plat['name']}"):
            with st.form(f"edit_plat_{plat['id']}"):
                ep_name = st.text_input("Name", value=plat["name"], key=f"ep_name_{plat['id']}")
                ep_status = st.selectbox(
                    "Status",
                    PLATFORM_STATUSES,
                    index=PLATFORM_STATUSES.index(plat["status"]),
                    key=f"ep_status_{plat['id']}",
                )
                c1, c2 = st.columns(2)
                if c1.form_submit_button("Update"):
                    PortfolioVM.update_platform(plat["id"], ep_name, ep_status)
                    st.success("Updated!")
                    st.rerun()
                if c2.form_submit_button("🗑️ Delete"):
                    PortfolioVM.delete_platform(plat["id"])
                    st.success("Deleted!")
                    st.rerun()
