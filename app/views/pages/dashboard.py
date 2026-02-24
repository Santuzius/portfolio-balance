"""Rebalancing page – main overview with deviation analysis."""

from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from app.viewmodels.balance_vm import BalanceVM
from app.viewmodels.mcda_vm import ScoringVM
from app.views.components.common import status_badge, PLATFORM_STATUSES


def page() -> None:
    """st.navigation entry-point."""
    portfolio_id = st.session_state.get("portfolio_id")
    if portfolio_id is None:
        st.info("👈 Select or create a portfolio to get started.")
        return
    render(portfolio_id)


def render(portfolio_id: int) -> None:
    st.header("⚖️ Rebalancing")

    allocation = ScoringVM.compute_allocation(portfolio_id)

    if allocation.empty:
        st.info("No allocation data yet. Set up criteria, scores, and record balances first.")
        return

    # ── Rebalancing status selector ─────────────────────────────────
    # "Running" is always included; user can opt-in other statuses.
    other_statuses = [s for s in PLATFORM_STATUSES if s != "Running"]
    selected_others = st.multiselect(
        "Include in rebalancing (Running is always included)",
        other_statuses,
        default=[],
        key="rebal_statuses",
    )
    rebalance_statuses: set[str] = {"Running"} | set(selected_others)

    deviation = BalanceVM.compute_deviation(portfolio_id, rebalance_statuses)
    # Filter out empty Closed/Defaulted/Dissaving from display
    allocation = allocation[
        ~((allocation["status"].isin(["Closed", "Defaulted", "Dissaving"])) & (allocation["total_weighted_score"] == 0))
    ]
    if not deviation.empty:
        deviation = deviation[
            ~((deviation["status"].isin(["Closed", "Defaulted", "Dissaving"])) & (deviation["latest_balance"] == 0))
        ]
    # ── KPI Row ─────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    active_platforms = allocation[allocation["status"] == "Running"]
    total_balance = deviation["latest_balance"].sum() if not deviation.empty else 0
    total_off_budget = deviation["off_budget_total"].sum() if not deviation.empty else 0
    effective_balance = total_balance - total_off_budget

    col1.metric("Active Platforms", len(active_platforms))
    col2.metric("Total Balance", f"€{total_balance:,.2f}")
    col3.metric("Off-Budget", f"€{total_off_budget:,.2f}")
    col4.metric("Effective Balance", f"€{effective_balance:,.2f}")

    # ── Portfolio Distribution ──────────────────────────────────────
    st.subheader("Portfolio Distribution")
    col_pie1, col_pie2 = st.columns(2)

    with col_pie1:
        if not deviation.empty:
            cur = deviation[
                (deviation["latest_balance"] > 0) &
                (deviation["status"].isin(rebalance_statuses))
            ].copy()
            if not cur.empty:
                fig_cur = px.pie(
                    cur, values="latest_balance", names="platform",
                    title="Current", hole=0.3,
                )
                fig_cur.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_cur, width="stretch")
            else:
                st.info("No current balance data.")
        else:
            st.info("No balance data yet.")

    with col_pie2:
        active = allocation[allocation["pct_allocation"] > 0]
        if not active.empty:
            fig_tgt = px.pie(
                active, values="pct_allocation", names="platform",
                title="Target", hole=0.3,
            )
            fig_tgt.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_tgt, width="stretch")
        else:
            st.info("No target allocation computed yet.")

    # ── Deviation Table ─────────────────────────────────────────────
    st.subheader("Current Deviation")
    rebal_dev = deviation[deviation["status"].isin(rebalance_statuses)] if not deviation.empty else deviation
    if not rebal_dev.empty:
        display_df = rebal_dev.copy()
        display_df["Status"] = display_df["status"].apply(status_badge)
        display_df["Balance €"] = display_df["latest_balance"].round(2)
        display_df["Target €"] = display_df["target_value"].round(2)
        display_df["Deviation €"] = display_df["deviation"].round(2)
        display_df["Allocation %"] = (display_df["pct_allocation"] * 100).round(2)
        display_df["Off-Budget €"] = display_df["off_budget_total"].round(2)
        display_df = display_df.sort_values("Balance €", ascending=False)

        st.dataframe(
            display_df[["platform", "Status", "Balance €", "Target €", "Deviation €", "Allocation %", "Off-Budget €"]].rename(
                columns={"platform": "Platform"}
            ),
            width="stretch",
            hide_index=True,
        )

        # Bar chart: deviation
        fig_bar = go.Figure()
        colors = ["green" if d >= 0 else "red" for d in display_df["deviation"]]
        fig_bar.add_trace(
            go.Bar(
                x=display_df["platform"],
                y=display_df["deviation"].round(2),
                marker_color=colors,
                text=display_df["deviation"].round(2),
                textposition="auto",
            )
        )
        fig_bar.update_layout(
            title="Balance Deviation from Target",
            xaxis_title="Platform",
            yaxis_title="Deviation (€)",
            showlegend=False,
        )
        st.plotly_chart(fig_bar, width="stretch")

    # ── Scoring Summary Table ───────────────────────────────────────────────
    st.subheader("MCDA Scores")
    if not allocation.empty:
        score_df = allocation[["platform", "status", "total_weighted_score", "pct_allocation"]].copy()
        score_df["Status"] = score_df["status"].apply(status_badge)
        score_df["Weighted Score"] = score_df["total_weighted_score"].round(2)
        score_df["Allocation %"] = (score_df["pct_allocation"] * 100).round(2)
        score_df = score_df.sort_values("Weighted Score", ascending=False)
        st.dataframe(
            score_df[["platform", "Status", "Weighted Score", "Allocation %"]].rename(
                columns={"platform": "Platform"}
            ),
            width="stretch",
            hide_index=True,
        )
