"""Portfolio & Platform management page."""

from __future__ import annotations

import streamlit as st
from app.viewmodels.portfolio_vm import PortfolioVM
from app.viewmodels.balance_vm import PocketVM
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

    # ── Copy Existing Portfolio ─────────────────────────────────────
    all_portfolios = PortfolioVM.list_portfolios()
    if not all_portfolios.empty:
        with st.expander("📋 Copy Existing Portfolio"):
            with st.form("copy_portfolio"):
                source = st.selectbox(
                    "Source Portfolio",
                    all_portfolios["name"].tolist(),
                    key="copy_src",
                )
                copy_name = st.text_input("New Portfolio Name", key="copy_name")
                if st.form_submit_button("📋 Copy"):
                    if copy_name.strip():
                        src_row = all_portfolios[all_portfolios["name"] == source].iloc[0]
                        try:
                            PortfolioVM.copy_portfolio(int(src_row["id"]), copy_name.strip())
                            st.success(f"Portfolio '{copy_name}' created as copy of '{source}'!")
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

            # ── Off-Budget Pockets ──────────────────────────────────
            _render_off_budget(int(plat["id"]), plat["name"])


def _render_off_budget(platform_id: int, platform_name: str) -> None:
    """Manage off-budget pockets for a platform."""
    st.markdown("**Off-Budget Pockets**")
    pockets = PocketVM.list_pockets(platform_id)

    if not pockets.empty:
        for _, pk in pockets.iterrows():
            col1, col2, col3, col4 = st.columns([2, 1, 2, 1])
            col1.text(pk["name"])
            col2.text(f"€{pk['amount']:,.2f}")
            col3.text(pk["note"] or "")
            if col4.button("🗑️", key=f"del_pocket_{pk['id']}"):
                PocketVM.delete_pocket(int(pk["id"]))
                st.rerun()
        total = pockets["amount"].sum()
        st.caption(f"Total off-budget: **€{total:,.2f}**")

    # Add new pocket
    with st.form(f"add_pocket_{platform_id}"):
        c1, c2, c3 = st.columns([2, 1, 2])
        pk_name = c1.text_input("Pocket Name", key=f"pk_name_{platform_id}")
        pk_amount = c2.number_input("Amount (€)", min_value=0.0, step=10.0, key=f"pk_amt_{platform_id}")
        pk_note = c3.text_input("Note", key=f"pk_note_{platform_id}")
        if st.form_submit_button("➕ Add Pocket"):
            if pk_name.strip():
                PocketVM.create_pocket(platform_id, pk_name.strip(), pk_amount, pk_note)
                st.success(f"Pocket '{pk_name}' added!")
                st.rerun()
            else:
                st.warning("Pocket name cannot be empty.")

    # Edit existing pockets
    if not pockets.empty:
        with st.form(f"edit_pockets_{platform_id}"):
            edit_entries = []
            for _, pk in pockets.iterrows():
                st.markdown(f"*{pk['name']}*")
                ec1, ec2, ec3 = st.columns([2, 1, 2])
                new_name = ec1.text_input(
                    "Name", value=pk["name"], key=f"epk_name_{pk['id']}"
                )
                new_amt = ec2.number_input(
                    "Amount (€)",
                    value=float(pk["amount"]),
                    min_value=0.0,
                    step=10.0,
                    key=f"epk_amt_{pk['id']}",
                )
                new_note = ec3.text_input(
                    "Note",
                    value=str(pk["note"] or ""),
                    key=f"epk_note_{pk['id']}",
                )
                edit_entries.append((int(pk["id"]), new_name, new_amt, new_note))
            if st.form_submit_button("💾 Save Pockets"):
                for pid, n, a, nt in edit_entries:
                    PocketVM.update_pocket(pid, n, a, nt)
                st.success("Pockets updated!")
                st.rerun()
