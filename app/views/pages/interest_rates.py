"""Interest Rates comparison page."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from app.viewmodels.portfolio_vm import PortfolioVM
from app.viewmodels.balance_vm import InterestRateVM, AutoScoreVM
from app.viewmodels.mcda_vm import CriteriaVM, ScoringVM


# ---------------------------------------------------------------------------
# Page wrapper for st.navigation
# ---------------------------------------------------------------------------

def page() -> None:
    """st.navigation entry-point."""
    portfolio_id = st.session_state.get("portfolio_id")
    if portfolio_id is None:
        st.info("👈 Select or create a portfolio to get started.")
        return
    render_interest_rates(portfolio_id)


# ---------------------------------------------------------------------------
# Interest Rates
# ---------------------------------------------------------------------------

def render_interest_rates(portfolio_id: int) -> None:
    st.header("📈 Interest Rate Comparison")

    # Defaulted, Closed, Dissaving are always inactive
    INACTIVE_STATUSES = {"Defaulted", "Closed", "Dissaving"}
    show_inactive = st.checkbox("Show inactive platforms", value=False, key="ir_show_inactive")
    all_plats = PortfolioVM.list_platforms(portfolio_id, include_inactive=True)
    if show_inactive:
        platforms = all_plats
    else:
        platforms = all_plats[~all_plats["status"].isin(INACTIVE_STATUSES)]
    if platforms.empty:
        st.warning("Add platforms first.")
        return

    rates = InterestRateVM.get_rates(portfolio_id)
    # Filter rates to shown platforms only
    shown_ids = set(int(x) for x in platforms["id"].tolist())
    rates = rates[rates["platform_id"].apply(lambda x: int(x) in shown_ids)]

    # ── Edit rates ──────────────────────────────────────────────────
    with st.form("interest_rates_form"):
        entries = []
        for _, r in rates.iterrows():
            st.markdown(f"**{r['platform']}**")
            est = st.number_input(
                "Estimated Rate (%)",
                value=float(r["estimated_rate"]) * 100,
                step=0.1,
                format="%.2f",
                key=f"ir_est_{r['platform_id']}",
            )
            entries.append((int(r["platform_id"]), est / 100))

        if st.form_submit_button("💾 Save Rates"):
            for pid, est in entries:
                InterestRateVM.save_rate(int(pid), est)
            st.success("Interest rates saved!")
            st.rerun()

    # ── Comparison chart ────────────────────────────────────────────
    rates = InterestRateVM.get_rates(portfolio_id)  # refresh
    rates = rates[rates["platform_id"].apply(lambda x: int(x) in shown_ids)]
    if not rates.empty and rates["estimated_rate"].sum() > 0:
        chart_df = rates[rates["estimated_rate"] > 0].copy()
        chart_df["est_pct"] = chart_df["estimated_rate"] * 100

        fig = px.bar(
            chart_df,
            x="platform",
            y="est_pct",
            title="Estimated Interest Rates by Platform",
            labels={"platform": "Platform", "est_pct": "Rate (%)"},
            text="est_pct",
        )
        fig.update_traces(texttemplate="%{text:.2f}%", textposition="auto")
        st.plotly_chart(fig, width="stretch")

        # Summary stats
        col1, col2, col3 = st.columns(3)
        active_rates = chart_df["est_pct"]
        col1.metric("Min Rate", f"{active_rates.min():.2f}%")
        col2.metric("Avg Rate", f"{active_rates.mean():.2f}%")
        col3.metric("Max Rate", f"{active_rates.max():.2f}%")

    # ── Auto-Score Equation ─────────────────────────────────────────
    _render_auto_interest_rate(portfolio_id, platforms)


# ---------------------------------------------------------------------------
# Auto-Score helper
# ---------------------------------------------------------------------------

def _render_auto_interest_rate(
    portfolio_id: int, platforms: pd.DataFrame
) -> None:
    """Auto-score section for interest rate criterion."""
    criteria = CriteriaVM.list_criteria(portfolio_id)
    special = criteria[(criteria["is_special"] == True) & (criteria["special_type"] == "interest_rate")]  # noqa: E712
    if special.empty:
        return

    st.divider()
    st.subheader("Auto-Score Equation")
    st.markdown(
        "Variables: `rate` (platform rate), `min_rate`, `max_rate`, `avg_rate` (across active platforms). "
        "Builtins: `min()`, `max()`, `abs()`."
    )

    eq, enabled = AutoScoreVM.get_equation(portfolio_id, "interest_rate")

    col_eq, col_toggle = st.columns([4, 1])
    new_eq = col_eq.text_input(
        "Equation",
        value=eq,
        key="auto_eq_interest",
        help="Python expression. Result clamped to [0, 10].",
    )
    new_enabled = col_toggle.checkbox("Enabled", value=enabled, key="auto_en_interest")

    c1, c2 = st.columns(2)
    if c1.button("💾 Save Equation", key="save_eq_interest"):
        AutoScoreVM.save_equation(portfolio_id, "interest_rate", new_eq, new_enabled)
        st.success("Interest rate equation saved!")

    if c2.button("🔄 Apply & Write Scores", key="apply_interest", disabled=not new_enabled):
        crit_row = special.iloc[0]
        crit_id = int(crit_row["id"])
        scores = AutoScoreVM.compute_interest_rate_scores(portfolio_id, new_eq)
        if not scores:
            st.warning("No interest rate data found for Running platforms.")
        else:
            for pid, score in scores.items():
                ScoringVM.save_score(pid, crit_id, score)
            st.success(f"Applied interest rate scores to {len(scores)} platforms.")
            preview_rows = []
            plat_map = dict(zip(platforms["id"].astype(int), platforms["name"]))
            for pid, score in sorted(scores.items(), key=lambda x: -x[1]):
                preview_rows.append({"Platform": plat_map.get(pid, str(pid)), "Score": round(score, 2)})
            st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)
