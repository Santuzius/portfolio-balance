"""Scoring Matrix page – evaluate platforms against criteria."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from app.viewmodels.portfolio_vm import PortfolioVM
from app.viewmodels.mcda_vm import CriteriaVM, ScoringVM
from app.views.components.common import status_badge


def page() -> None:
    """st.navigation entry-point."""
    portfolio_id = st.session_state.get("portfolio_id")
    if portfolio_id is None:
        st.info("👈 Select or create a portfolio to get started.")
        return
    render(portfolio_id)


def render(portfolio_id: int) -> None:
    st.header("🏆 Scoring Matrix")
    st.caption(
        "Rate each platform on each criterion from **0** (worst) to **10** (best). "
        "Scores are multiplied by the weight factor to compute the MCDA allocation."
    )

    criteria = CriteriaVM.list_criteria(portfolio_id)

    if criteria.empty:
        st.warning("Define criteria first (⚖️ Criteria & Weighting page).")
        return

    # ── Tabs: Quick Entries | Detailed Entries | Results ────────────
    tab_quick, tab_detail, tab_results = st.tabs(
        ["Quick Entries", "Detailed Entries", "Results"]
    )

    with tab_quick:
        _render_quick_entries(portfolio_id, criteria)

    with tab_detail:
        platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=False)
        if platforms.empty:
            st.warning("Add platforms first (🗂️ Portfolios page).")
        else:
            _render_detail(portfolio_id, criteria, platforms)

    with tab_results:
        _render_results(portfolio_id)


def _render_quick_entries(
    portfolio_id: int, criteria: pd.DataFrame
) -> None:
    """Compact matrix view for scoring with optional all-platforms toggle."""
    crit_ids = criteria["id"].tolist()
    crit_names = criteria["name"].tolist()

    # Checkbox: show all platforms (including inactive)
    show_all = st.checkbox(
        "Show all platforms (including inactive)", value=False, key="qe_show_all"
    )
    platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=show_all)

    if platforms.empty:
        st.warning("Add platforms first (🗂️ Portfolios page).")
        return

    st.subheader("Quick Score Entry")

    with st.form("score_matrix_form"):
        # Header row
        cols = st.columns(len(crit_names) + 1)
        cols[0].write("**Platform**")
        for j, cn in enumerate(crit_names):
            cols[j + 1].write(f"**{cn}**")

        all_scores = []
        for _, plat in platforms.iterrows():
            scores = ScoringVM.get_scores_for_platform(plat["id"])
            score_map = dict(zip(scores["criterion_id"], scores["score"]))

            row_cols = st.columns(len(crit_names) + 1)
            row_cols[0].write(f"{status_badge(plat['status'])} {plat['name']}")

            for j, cid in enumerate(crit_ids):
                current = float(score_map.get(cid, 0))
                val = row_cols[j + 1].number_input(
                    f"{plat['name']}-{crit_names[j]}",
                    min_value=0.0,
                    max_value=10.0,
                    value=current,
                    step=0.5,
                    key=f"sm_{plat['id']}_{cid}",
                    label_visibility="collapsed",
                )
                all_scores.append((plat["id"], cid, val))

        if st.form_submit_button("💾 Save All Scores"):
            for pid, cid, val in all_scores:
                ScoringVM.save_score(int(pid), int(cid), float(val))
            st.success("All scores saved!")
            st.rerun()


def _render_detail(
    portfolio_id: int, criteria: pd.DataFrame, platforms: pd.DataFrame
) -> None:
    """Per-platform detailed scoring with notes."""
    selected_plat = st.selectbox(
        "Select Platform",
        platforms["name"].tolist(),
        key="detail_plat_select",
    )
    plat_row = platforms[platforms["name"] == selected_plat].iloc[0]
    platform_id = plat_row["id"]

    scores = ScoringVM.get_scores_for_platform(platform_id)

    with st.form(f"detail_scores_{platform_id}"):
        st.subheader(f"Scoring: {selected_plat}")

        entries = []
        for _, s in scores.iterrows():
            st.markdown(f"**{s['name']}**")
            col1, col2 = st.columns([1, 2])
            val = col1.number_input(
                "Score (0-10)",
                min_value=0.0,
                max_value=10.0,
                value=float(s["score"]),
                step=0.5,
                key=f"ds_{platform_id}_{s['criterion_id']}",
            )
            note = col2.text_input(
                "Note",
                value=str(s["note"]),
                key=f"dn_{platform_id}_{s['criterion_id']}",
            )
            entries.append((s["criterion_id"], val, note))

        if st.form_submit_button("💾 Save"):
            for cid, val, note in entries:
                ScoringVM.save_score(int(platform_id), int(cid), float(val), note)
            st.success(f"Scores for {selected_plat} saved!")
            st.rerun()


def _render_results(portfolio_id: int) -> None:
    """Display computed MCDA results."""
    st.subheader("MCDA Results")
    allocation = ScoringVM.compute_allocation(portfolio_id)
    if allocation.empty:
        st.info("No scores computed yet.")
        return

    display = allocation[[
        "platform", "status", "total_weighted_score", "pct_allocation"
    ]].copy()
    # Filter out empty Closed/Defaulted
    display = display[
        ~((display["status"].isin(["Closed", "Defaulted"])) & (display["total_weighted_score"] == 0))
    ]
    display["Status"] = display["status"].apply(status_badge)
    display["Weighted Score"] = display["total_weighted_score"].round(2)
    display["Allocation %"] = (display["pct_allocation"] * 100).round(2)
    display = display.sort_values("Weighted Score", ascending=False)

    st.dataframe(
        display[["platform", "Status", "Weighted Score", "Allocation %"]].rename(
            columns={"platform": "Platform"}
        ),
        width="stretch",
        hide_index=True,
    )
