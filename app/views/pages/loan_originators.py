"""Loan Originators page: originator management, allocation, auto-score."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from app.viewmodels.portfolio_vm import PortfolioVM
from app.viewmodels.balance_vm import (
    LoanOriginatorVM, OriginatorAllocationVM, BalanceVM, AutoScoreVM,
    _orig_key,
)
from app.viewmodels.mcda_vm import CriteriaVM, ScoringVM
from app.views.components.common import (
    COUNTRY_STATUSES, COUNTRY_STATUS_COLORS, country_flag,
    country_status_priority,
)


# ---------------------------------------------------------------------------
# Page wrapper for st.navigation
# ---------------------------------------------------------------------------

def page() -> None:
    """st.navigation entry-point."""
    portfolio_id = st.session_state.get("portfolio_id")
    if portfolio_id is None:
        st.info("👈 Select or create a portfolio to get started.")
        return
    render_loan_originators(portfolio_id)


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def _status_color_html(status: str) -> str:
    color = COUNTRY_STATUS_COLORS.get(status, "#888")
    return (
        f'<span style="display:inline-block;width:12px;height:12px;'
        f'border-radius:50%;background:{color};margin-right:4px"></span>{status}'
    )


def render_loan_originators(portfolio_id: int) -> None:
    st.header("🏦 Loan Originators")

    platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=True)
    if platforms.empty:
        st.warning("Add platforms first.")
        return

    tab_overview, tab_alloc, tab_edit = st.tabs(
        ["Overview", "Originator Allocation", "Edit Originators"]
    )

    # ── Tab 1: Overview / Distribution ─────────────────────────────
    with tab_overview:
        _render_originator_overview(portfolio_id, platforms)

    # ── Tab 2: Originator Allocation ──────────────────────────────
    with tab_alloc:
        _render_originator_allocation(portfolio_id, platforms)

    # ── Tab 3: Edit Originators per platform ──────────────────────
    with tab_edit:
        _render_originator_edit(portfolio_id, platforms)

    # ── Auto-Score Equation ─────────────────────────────────────────
    _render_auto_originator(portfolio_id, platforms)


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def _render_originator_overview(portfolio_id: int, platforms: pd.DataFrame) -> None:
    """Show originator distribution across the portfolio."""
    st.subheader("Originator Distribution")

    latest = BalanceVM.get_latest_balances(portfolio_id)
    if latest.empty:
        st.info("No balance data yet.")
        return

    # ── Status filter (like Rebalancing) ────────────────────────
    other_statuses = [s for s in COUNTRY_STATUSES if s != "Running"]
    selected_others = st.multiselect(
        "Include in distribution (Running is always included)",
        other_statuses,
        default=[],
        key="orig_dist_statuses",
    )
    include_statuses: set[str] = {"Running"} | set(selected_others)

    originator_funds: dict[str, float] = {}  # merged by name
    originator_count: dict[str, int] = {}     # count per name

    for _, plat in platforms.iterrows():
        pid = int(plat["id"])
        # Ensure default originator exists
        LoanOriginatorVM.ensure_default(pid, plat["name"])

        bal_row = latest[latest["platform_id"] == pid]
        if bal_row.empty:
            continue
        balance = float(bal_row.iloc[0]["balance"] or 0)
        if balance <= 0:
            continue

        alloc = OriginatorAllocationVM.compute_allocation(pid)
        if alloc.empty:
            continue

        # Build originator status map for this platform
        origs = LoanOriginatorVM.list_originators(pid)
        orig_status_map: dict[str, str] = {}
        if not origs.empty:
            for _, o in origs.iterrows():
                orig_status_map[_orig_key(o["originator_name"], o["country"])] = o["status"]

        for _, a in alloc.iterrows():
            name = a["originator_name"]
            pct = float(a["pct"])
            if pct <= 0:
                continue
            # Filter by selected statuses
            key = _orig_key(a["originator_name"], a["country"])
            if orig_status_map.get(key, "Running") not in include_statuses:
                continue
            amount = balance * pct / 100.0
            originator_funds[name] = originator_funds.get(name, 0) + amount
            originator_count[name] = originator_count.get(name, 0) + 1

    if not originator_funds:
        st.info("No allocation data available.")
        return

    fund_df = pd.DataFrame([
        {"Originator": name, "Amount": amt, "Count": originator_count.get(name, 1)}
        for name, amt in originator_funds.items()
    ]).sort_values("Amount", ascending=False)

    total = fund_df["Amount"].sum()
    fund_df["Pct"] = (fund_df["Amount"] / total * 100).round(2) if total > 0 else 0
    fund_df["Amount €"] = fund_df["Amount"].apply(lambda x: f"€{x:,.2f}")

    fig = px.pie(
        fund_df, values="Amount", names="Originator",
        title="Portfolio-wide Originator Distribution",
        hole=0.3,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, width="stretch")

    st.dataframe(
        fund_df[["Originator", "Count", "Amount €", "Pct"]].rename(columns={"Pct": "%"}),
        width="stretch",
        hide_index=True,
    )


# ---------------------------------------------------------------------------
# Originator Allocation
# ---------------------------------------------------------------------------

def _render_originator_allocation(portfolio_id: int, platforms: pd.DataFrame) -> None:
    """Per-platform originator allocation: status filter → equal/manual mode."""
    st.subheader("Originator Allocation")

    sel = st.selectbox("Platform", platforms["name"].tolist(), key="oa_plat")
    plat_row = platforms[platforms["name"] == sel].iloc[0]
    pid = int(plat_row["id"])

    # Ensure default originator exists
    LoanOriginatorVM.ensure_default(pid, sel)

    origs = LoanOriginatorVM.list_originators(pid)
    if origs.empty:
        st.info("No originators for this platform.")
        return

    origs = origs.copy()
    origs["_prio"] = origs["status"].apply(country_status_priority)
    origs = origs.sort_values("_prio")

    # ── Step 1: Status filter ──────────────────────────────────────
    st.markdown("#### 1. Include / Exclude Statuses")
    st.caption("Running is always included. Other statuses excluded by default.")

    present_statuses = sorted(
        set(origs["status"].tolist()), key=country_status_priority
    )
    non_running = [s for s in present_statuses if s != "Running"]
    excluded_list = OriginatorAllocationVM.get_excluded_statuses(pid)
    if excluded_list is None:
        # Never configured → default to excluding non-Running
        excluded = set(non_running)
    else:
        excluded = set(excluded_list)

    with st.form(f"oa_status_filter_{pid}"):
        new_included: list[str] = []
        for s in non_running:
            cnt = int((origs["status"] == s).sum())
            if st.checkbox(
                f"Include **{s}** ({cnt} {'originator' if cnt == 1 else 'originators'})",
                value=(s not in excluded),
                key=f"oa_inc_{pid}_{s}",
            ):
                new_included.append(s)

        if st.form_submit_button("💾 Save Status Filter"):
            new_excluded = [s for s in non_running if s not in new_included]
            OriginatorAllocationVM.set_excluded_statuses(pid, new_excluded)
            st.success("Status filter saved!")
            st.rerun()

    excluded_list_now = OriginatorAllocationVM.get_excluded_statuses(pid)
    if excluded_list_now is None:
        excluded_now = set(non_running)
    else:
        excluded_now = set(excluded_list_now)
    excluded_now.discard("Running")
    included = origs[~origs["status"].isin(excluded_now)]
    excluded_df = origs[origs["status"].isin(excluded_now)]

    n_inc = len(included)
    st.markdown(
        f"**{n_inc}** included / **{len(excluded_df)}** excluded originators"
    )

    if n_inc == 0:
        st.warning("No originators included — adjust the status filter above.")
        return

    # ── Step 2: Allocation mode ────────────────────────────────────
    st.markdown("#### 2. Allocation Mode")

    current_mode = OriginatorAllocationVM.get_mode(pid)
    MODES = ["equal", "manual"]
    mode = st.radio(
        "Mode",
        MODES,
        index=MODES.index(current_mode) if current_mode in MODES else 0,
        horizontal=True,
        key=f"oa_mode_{pid}",
    )
    if mode != current_mode:
        OriginatorAllocationVM.set_mode(pid, mode)

    if mode == "manual":
        _render_manual_originator_mode(pid, portfolio_id, included, excluded_df)
    else:
        _render_equal_originator_mode(included, excluded_df)


def _render_manual_originator_mode(
    pid: int,
    portfolio_id: int,
    included: pd.DataFrame,
    excluded: pd.DataFrame,
) -> None:
    """Manual allocation for originators."""
    manual_pcts = OriginatorAllocationVM.get_pcts(pid)
    pct_map: dict[str, float] = {}
    val_map: dict[str, float] = {}
    if not manual_pcts.empty:
        pct_map = dict(zip(manual_pcts["originator_key"], manual_pcts["pct"]))
        if "value" in manual_pcts.columns:
            val_map = dict(zip(manual_pcts["originator_key"], manual_pcts["value"]))

    latest_bal = BalanceVM.get_latest_balances(portfolio_id)
    plat_bal_row = latest_bal[latest_bal["platform_id"] == pid]
    current_balance = float(plat_bal_row.iloc[0]["balance"] or 0) if not plat_bal_row.empty else 0.0

    input_type = st.radio(
        "Input type",
        ["Percentage (%)", "Value (€)"],
        horizontal=True,
        key=f"oa_input_type_{pid}",
    )

    with st.form(f"oa_manual_{pid}"):
        pct_entries: list[tuple[str, float, float]] = []
        for _, row in included.iterrows():
            c1, c2 = st.columns([3, 2])
            country_str = country_flag(row["country"]) if row["country"] else "🏳️ (no country)"
            status_color = COUNTRY_STATUS_COLORS.get(row["status"], "#888")
            c1.markdown(
                f"**{row['originator_name']}** — {country_str} "
                f"(<span style='color:{status_color}'>●</span> {row['status']})",
                unsafe_allow_html=True,
            )
            key_name = _orig_key(row["originator_name"], row["country"])
            widget_key = f"{row['id']}"  # use DB id for unique widget keys
            if input_type == "Percentage (%)":
                pct = c2.number_input(
                    "%",
                    value=float(pct_map.get(key_name, 0)),
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    key=f"oa_pct_{pid}_{widget_key}",
                    label_visibility="collapsed",
                )
                pct_entries.append((key_name, pct, 0.0))
            else:
                val = c2.number_input(
                    "€",
                    value=float(val_map.get(key_name, 0)),
                    min_value=0.0,
                    step=10.0,
                    key=f"oa_val_{pid}_{widget_key}",
                    label_visibility="collapsed",
                )
                pct_entries.append((key_name, 0.0, val))

        if input_type == "Percentage (%)":
            total = sum(p for _, p, _ in pct_entries)
            ok = abs(total - 100) < 0.1
            st.markdown(f"**Total: {total:.1f}%** {'✅' if ok else '⚠️ Should be 100%'}")
        else:
            total_val = sum(v for _, _, v in pct_entries)
            bal_ok = abs(total_val - current_balance) < 0.01 if current_balance > 0 else True
            bal_icon = "✅" if bal_ok else "⚠️"
            st.markdown(
                f"**Total: €{total_val:,.2f}** {bal_icon} "
                f"(platform balance: €{current_balance:,.2f})"
            )
            if total_val > 0:
                pct_entries = [(c, v / total_val * 100, v) for c, _, v in pct_entries]

        if st.form_submit_button("💾 Save Allocation"):
            for orig_key, pct, val in pct_entries:
                OriginatorAllocationVM.save_pct(pid, orig_key, pct, val)
            st.success("Manual allocation saved!")
            st.rerun()

    if not excluded.empty:
        st.markdown("**Excluded originators** (0% allocation):")
        exc_rows = [
            {
                "Originator": r["originator_name"],
                "Country": country_flag(r["country"]) if r["country"] else "—",
                "Status": r["status"],
                "Allocation": "0%",
            }
            for _, r in excluded.iterrows()
        ]
        st.dataframe(pd.DataFrame(exc_rows), width="stretch", hide_index=True)


def _render_equal_originator_mode(included: pd.DataFrame, excluded: pd.DataFrame) -> None:
    """Equal allocation display for originators."""
    n = len(included)
    eq_pct = 100.0 / n if n > 0 else 0.0
    rows = []
    for _, row in included.iterrows():
        rows.append({
            "Originator": row["originator_name"],
            "Country": country_flag(row["country"]) if row["country"] else "—",
            "Status": row["status"],
            "Allocation %": f"{eq_pct:.1f}%",
        })
    for _, row in excluded.iterrows():
        rows.append({
            "Originator": row["originator_name"],
            "Country": country_flag(row["country"]) if row["country"] else "—",
            "Status": row["status"],
            "Allocation %": "0.0% (excluded)",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Edit Originators
# ---------------------------------------------------------------------------

def _render_originator_edit(portfolio_id: int, platforms: pd.DataFrame) -> None:
    """Per-platform editable originator management."""
    st.subheader("Edit Originators")

    selected = st.selectbox("Select Platform", platforms["name"].tolist(), key="lo_plat")
    plat_row = platforms[platforms["name"] == selected].iloc[0]
    platform_id = int(plat_row["id"])

    # Ensure default originator exists
    LoanOriginatorVM.ensure_default(platform_id, selected)

    origs = LoanOriginatorVM.list_originators(platform_id)

    # Add new originator
    with st.expander("➕ Add Originator"):
        with st.form(f"add_lo_{platform_id}"):
            orig_name = st.text_input("Originator Name")
            orig_country = st.text_input("Country", help="Country of the originator")
            orig_status = st.selectbox("Status", COUNTRY_STATUSES, index=1, key=f"add_lo_status_{platform_id}")
            orig_note = st.text_input("Note")
            if st.form_submit_button("Add"):
                if orig_name.strip():
                    LoanOriginatorVM.save_originator(
                        platform_id, orig_country.strip(), orig_name.strip(),
                        0.0, orig_status, orig_note,
                    )
                    st.success("Added!")
                    st.rerun()

    if not origs.empty:
        origs = origs.copy()
        origs["_prio"] = origs["status"].apply(country_status_priority)
        origs = origs.sort_values("_prio")

        # Status legend
        with st.expander("🎨 Status Legend"):
            legend_html = " &nbsp; ".join(
                _status_color_html(s) for s in COUNTRY_STATUSES
            )
            st.markdown(legend_html, unsafe_allow_html=True)

        # Editable table
        st.markdown("**Edit originators** (change status in-place):")
        with st.form(f"edit_lo_{platform_id}"):
            edit_entries = []
            for _, row in origs.iterrows():
                c1, c2, c3, c4 = st.columns([2, 2, 1.5, 2])
                c1.text_input(
                    "Name", value=row["originator_name"],
                    key=f"lo_name_{row['id']}", disabled=True,
                    label_visibility="collapsed",
                )
                new_country = c2.text_input(
                    "Country", value=str(row["country"] or ""),
                    key=f"lo_country_{row['id']}",
                    label_visibility="collapsed",
                )
                new_status = c3.selectbox(
                    "Status", COUNTRY_STATUSES,
                    index=COUNTRY_STATUSES.index(row["status"]) if row["status"] in COUNTRY_STATUSES else 1,
                    key=f"lo_status_{row['id']}",
                    label_visibility="collapsed",
                )
                new_note = c4.text_input(
                    "Note", value=str(row["note"] or ""),
                    key=f"lo_note_{row['id']}",
                    label_visibility="collapsed",
                )
                edit_entries.append((
                    int(row["id"]), new_country, row["originator_name"],
                    float(row["num_loans"]), new_status, new_note,
                ))

            if st.form_submit_button("💾 Save Changes"):
                for oid, country, name, loans, status, note in edit_entries:
                    LoanOriginatorVM.update_originator(oid, country, name, loans, status, note)
                st.success("Originators updated!")
                st.rerun()

        # Delete
        del_id = st.selectbox(
            "Delete Entry",
            origs["id"].tolist(),
            format_func=lambda x: f"{origs[origs['id'] == x].iloc[0]['originator_name']} {origs[origs['id'] == x].iloc[0]['country']}",
            key="del_lo",
        )
        if st.button("🗑️ Delete", key="del_lo_btn"):
            LoanOriginatorVM.delete_originator(int(del_id))
            st.success("Deleted!")
            st.rerun()
    else:
        st.info("No originators for this platform.")


# ---------------------------------------------------------------------------
# Auto-Score helper
# ---------------------------------------------------------------------------

def _render_auto_originator(
    portfolio_id: int, platforms: pd.DataFrame,
) -> None:
    """Auto-score section for loan originator count criterion."""
    criteria = CriteriaVM.list_criteria(portfolio_id)
    special = criteria[
        (criteria["is_special"] == True) & (criteria["special_type"] == "loan_originator")  # noqa: E712
    ]
    if special.empty:
        return

    st.divider()
    st.subheader("Auto-Score Equation")
    st.markdown(
        "Variables: `count` (number of included originators for the platform). "
        "Builtins: `min()`, `max()`, `abs()`."
    )

    eq, enabled = AutoScoreVM.get_equation(portfolio_id, "loan_originator")

    col_eq, col_toggle = st.columns([4, 1])
    new_eq = col_eq.text_input(
        "Equation",
        value=eq,
        key="auto_eq_originator",
        help="Python expression. Result clamped to [0, 10].",
    )
    new_enabled = col_toggle.checkbox("Enabled", value=enabled, key="auto_en_originator")

    c1, c2 = st.columns(2)
    if c1.button("💾 Save Equation", key="save_eq_originator"):
        AutoScoreVM.save_equation(portfolio_id, "loan_originator", new_eq, new_enabled)
        st.success("Loan originator equation saved!")

    if c2.button("🔄 Apply & Write Scores", key="apply_originator", disabled=not new_enabled):
        crit_row = special.iloc[0]
        crit_id = int(crit_row["id"])
        scores = AutoScoreVM.compute_originator_scores(portfolio_id, new_eq)
        if not scores:
            st.warning("No originator data found for Running platforms.")
        else:
            for pid, score in scores.items():
                ScoringVM.save_score(pid, crit_id, score)
            st.success(f"Applied originator scores to {len(scores)} platforms.")
            preview_rows = []
            plat_map = dict(zip(platforms["id"].astype(int), platforms["name"]))
            for pid, score in sorted(scores.items(), key=lambda x: -x[1]):
                preview_rows.append({"Platform": plat_map.get(pid, str(pid)), "Score": round(score, 2)})
            st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)
