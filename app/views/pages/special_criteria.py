"""Special criterion pages: Interest Rates comparison and Country Status overview."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from app.viewmodels.portfolio_vm import PortfolioVM
from app.viewmodels.balance_vm import (
    InterestRateVM, CountryStatusVM, CountryAllocationVM, BalanceVM,
    AutoScoreVM,
)
from app.viewmodels.mcda_vm import CriteriaVM, ScoringVM
from app.views.components.common import (
    COUNTRY_STATUSES, COUNTRY_STATUS_COLORS, country_flag,
    country_status_priority,
)


# ---------------------------------------------------------------------------
# Page wrappers for st.navigation
# ---------------------------------------------------------------------------

def page_interest_rates() -> None:
    """st.navigation entry-point."""
    portfolio_id = st.session_state.get("portfolio_id")
    if portfolio_id is None:
        st.info("👈 Select or create a portfolio to get started.")
        return
    render_interest_rates(portfolio_id)


def page_countries() -> None:
    """st.navigation entry-point."""
    portfolio_id = st.session_state.get("portfolio_id")
    if portfolio_id is None:
        st.info("👈 Select or create a portfolio to get started.")
        return
    render_country_status(portfolio_id)


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
# Country Status
# ---------------------------------------------------------------------------

def _status_color_html(status: str) -> str:
    """Coloured dot + status name as HTML."""
    color = COUNTRY_STATUS_COLORS.get(status, "#888")
    return f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{color};margin-right:4px"></span>{status}'


def render_country_status(portfolio_id: int) -> None:
    st.header("🌍 Countries Overview")

    platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=True)
    if platforms.empty:
        st.warning("Add platforms first.")
        return

    tab_stats, tab_alloc, tab_platform, tab_details = st.tabs(
        ["Distribution", "Country Allocation", "Country Status", "Details"]
    )

    # ── Tab 1: Distribution statistics ─────────────────────────────
    with tab_stats:
        _render_distribution_stats(portfolio_id, platforms)

    # ── Tab 2: Country Allocation ─────────────────────────────────
    with tab_alloc:
        _render_country_allocation(portfolio_id, platforms)

    # ── Tab 3: Per-platform editable country status ─────────────
    with tab_platform:
        selected = st.selectbox("Select Platform", platforms["name"].tolist(), key="cs_plat")
        plat_row = platforms[platforms["name"] == selected].iloc[0]
        platform_id = int(plat_row["id"])

        statuses = CountryStatusVM.list_statuses(platform_id)

        # Add new country
        with st.expander("➕ Add Country"):
            with st.form(f"add_cs_{platform_id}"):
                country = st.text_input("Country")
                status_val = st.selectbox("Status", COUNTRY_STATUSES, key=f"add_cs_status_{platform_id}")
                note = st.text_input("Note")
                if st.form_submit_button("Add"):
                    if country.strip():
                        CountryStatusVM.save_status(int(platform_id), country.strip(), status_val, note)
                        st.success("Added!")
                        st.rerun()

        if not statuses.empty:
            # Sort by status priority
            statuses = statuses.copy()
            statuses["_prio"] = statuses["status"].apply(country_status_priority)
            statuses = statuses.sort_values("_prio")

            # Status legend
            with st.expander("🎨 Status Legend"):
                legend_html = " &nbsp; ".join(
                    _status_color_html(s) for s in COUNTRY_STATUSES
                )
                st.markdown(legend_html, unsafe_allow_html=True)

            # Editable table: inline status change via form
            st.markdown("**Edit country statuses** (change status in-place):")
            with st.form(f"edit_cs_{platform_id}"):
                edit_entries = []
                for _, row in statuses.iterrows():
                    c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
                    c1.markdown(country_flag(row["country"]))
                    new_status = c2.selectbox(
                        "Status",
                        COUNTRY_STATUSES,
                        index=COUNTRY_STATUSES.index(row["status"]) if row["status"] in COUNTRY_STATUSES else 5,
                        key=f"cs_edit_{row['id']}",
                        label_visibility="collapsed",
                    )
                    new_note = c3.text_input(
                        "Note",
                        value=str(row["note"] or ""),
                        key=f"cs_note_{row['id']}",
                        label_visibility="collapsed",
                    )
                    edit_entries.append((int(row["id"]), new_status, new_note))

                if st.form_submit_button("💾 Save Changes"):
                    for sid, ns, nn in edit_entries:
                        CountryStatusVM.update_status(sid, ns, nn)
                    st.success("Statuses updated!")
                    st.rerun()

            # Delete
            del_id = st.selectbox(
                "Delete Entry",
                statuses["id"].tolist(),
                format_func=lambda x: statuses[statuses["id"] == x].iloc[0]["country"],
                key="del_cs",
            )
            if st.button("🗑️ Delete", key="del_cs_btn"):
                CountryStatusVM.delete_status(int(del_id))
                st.success("Deleted!")
                st.rerun()
        else:
            st.info("No country statuses for this platform.")

    # ── Tab 4: Details matrix ─────────────────────────────────────
    with tab_details:
        _render_overview(portfolio_id)

    # ── Auto-Score Equation ─────────────────────────────────────────
    _render_auto_country(portfolio_id, platforms)


def _render_country_allocation(portfolio_id: int, platforms: pd.DataFrame) -> None:
    """Per-platform country allocation: status filter → equal/manual mode."""
    st.subheader("Country Allocation")

    sel = st.selectbox("Platform", platforms["name"].tolist(), key="ca_plat")
    plat_row = platforms[platforms["name"] == sel].iloc[0]
    pid = int(plat_row["id"])

    countries = CountryStatusVM.list_statuses(pid)
    if countries.empty:
        st.info("No countries for this platform.")
        return

    countries = countries.copy()
    countries["_prio"] = countries["status"].apply(country_status_priority)
    countries = countries.sort_values("_prio")

    # ── Step 1: Status filter ──────────────────────────────────────
    st.markdown("#### 1. Include / Exclude Statuses")
    st.caption("Running is always included. All other statuses are excluded by default.")

    present_statuses = sorted(
        set(countries["status"].tolist()), key=country_status_priority
    )
    non_running = [s for s in present_statuses if s != "Running"]
    excluded = set(CountryAllocationVM.get_excluded_statuses(pid))

    # On first visit (no saved exclusions yet) default to excluding everything
    # except Running.
    if not excluded and non_running:
        excluded = set(non_running)

    with st.form(f"ca_status_filter_{pid}"):
        new_included: list[str] = []
        for s in non_running:
            color = COUNTRY_STATUS_COLORS.get(s, "#888")
            cnt = int((countries["status"] == s).sum())
            if st.checkbox(
                f"Include **{s}** ({cnt} {'country' if cnt == 1 else 'countries'})",
                value=(s not in excluded),
                key=f"ca_inc_{pid}_{s}",
            ):
                new_included.append(s)

        if st.form_submit_button("💾 Save Status Filter"):
            new_excluded = [s for s in non_running if s not in new_included]
            CountryAllocationVM.set_excluded_statuses(pid, new_excluded)
            st.success("Status filter saved!")
            st.rerun()

    # Determine included countries for the remainder of the UI
    excluded_now = set(CountryAllocationVM.get_excluded_statuses(pid))
    if not excluded_now and non_running:
        excluded_now = set(non_running)
    excluded_now.discard("Running")
    included = countries[~countries["status"].isin(excluded_now)]
    excluded_df = countries[countries["status"].isin(excluded_now)]

    n_inc = len(included)
    st.markdown(
        f"**{n_inc}** included / **{len(excluded_df)}** excluded countries"
    )

    if n_inc == 0:
        st.warning("No countries included — adjust the status filter above.")
        return

    # ── Step 2: Allocation mode ────────────────────────────────────
    st.markdown("#### 2. Allocation Mode")

    current_mode = CountryAllocationVM.get_mode(pid)
    MODES = ["equal", "manual"]
    mode = st.radio(
        "Mode",
        MODES,
        index=MODES.index(current_mode) if current_mode in MODES else 0,
        horizontal=True,
        key=f"ca_mode_{pid}",
    )
    if mode != current_mode:
        CountryAllocationVM.set_mode(pid, mode)

    if mode == "manual":
        _render_manual_mode(pid, portfolio_id, included, excluded_df)
    else:
        _render_equal_mode(included, excluded_df)


def _render_manual_mode(
    pid: int,
    portfolio_id: int,
    included: pd.DataFrame,
    excluded: pd.DataFrame,
) -> None:
    """Manual allocation: user sets % or absolute value per included country."""
    manual_pcts = CountryAllocationVM.get_pcts(pid)
    pct_map: dict[str, float] = {}
    val_map: dict[str, float] = {}
    if not manual_pcts.empty:
        pct_map = dict(zip(manual_pcts["country"], manual_pcts["pct"]))
        if "value" in manual_pcts.columns:
            val_map = dict(zip(manual_pcts["country"], manual_pcts["value"]))

    # Get platform's current balance for value-validation
    latest_bal = BalanceVM.get_latest_balances(portfolio_id)
    plat_bal_row = latest_bal[latest_bal["platform_id"] == pid]
    current_balance = float(plat_bal_row.iloc[0]["balance"] or 0) if not plat_bal_row.empty else 0.0

    input_type = st.radio(
        "Input type",
        ["Percentage (%)", "Value (€)"],
        horizontal=True,
        key=f"ca_input_type_{pid}",
    )

    with st.form(f"ca_manual_{pid}"):
        pct_entries: list[tuple[str, float, float]] = []
        for _, row in included.iterrows():
            c1, c2 = st.columns([3, 2])
            c1.markdown(
                f"{country_flag(row['country'])} "
                f"(<span style='color:{COUNTRY_STATUS_COLORS.get(row['status'], '#888')}'>●</span> {row['status']})",
                unsafe_allow_html=True,
            )
            if input_type == "Percentage (%)":
                pct = c2.number_input(
                    "%",
                    value=float(pct_map.get(row["country"], 0)),
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    key=f"ca_pct_{pid}_{row['country']}",
                    label_visibility="collapsed",
                )
                pct_entries.append((row["country"], pct, 0.0))
            else:
                val = c2.number_input(
                    "€",
                    value=float(val_map.get(row["country"], 0)),
                    min_value=0.0,
                    step=10.0,
                    key=f"ca_val_{pid}_{row['country']}",
                    label_visibility="collapsed",
                )
                pct_entries.append((row["country"], 0.0, val))

        # Totals & validation
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
            # Auto-calculate percentages from values
            if total_val > 0:
                pct_entries = [(c, v / total_val * 100, v) for c, _, v in pct_entries]

        if st.form_submit_button("💾 Save Allocation"):
            for country, pct, val in pct_entries:
                CountryAllocationVM.save_pct(pid, country, pct, val)
            st.success("Manual allocation saved!")
            st.rerun()

    # Show excluded countries as 0%
    if not excluded.empty:
        st.markdown("**Excluded countries** (0% allocation):")
        exc_rows = [
            {"Country": country_flag(r["country"]), "Status": r["status"], "Allocation": "0%"}
            for _, r in excluded.iterrows()
        ]
        st.dataframe(pd.DataFrame(exc_rows), width="stretch", hide_index=True)


def _render_equal_mode(included: pd.DataFrame, excluded: pd.DataFrame) -> None:
    """Equal allocation display using native Streamlit dataframe."""
    n = len(included)
    eq_pct = 100.0 / n if n > 0 else 0.0
    rows = []
    for _, row in included.iterrows():
        rows.append({
            "Country": country_flag(row["country"]),
            "Status": row["status"],
            "Allocation %": f"{eq_pct:.1f}%",
        })
    for _, row in excluded.iterrows():
        rows.append({
            "Country": country_flag(row["country"]),
            "Status": row["status"],
            "Allocation %": "0.0% (excluded)",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_distribution_stats(portfolio_id: int, platforms: pd.DataFrame) -> None:
    """Show distribution of funds among countries across the portfolio."""
    st.subheader("Country Fund Distribution")

    # Get latest balances and country allocations
    latest = BalanceVM.get_latest_balances(portfolio_id)
    if latest.empty:
        st.info("No balance data yet.")
        return

    country_funds: dict[str, float] = {}

    for _, plat in platforms.iterrows():
        pid = int(plat["id"])
        bal_row = latest[latest["platform_id"] == pid]
        if bal_row.empty:
            continue
        balance = float(bal_row.iloc[0]["balance"] or 0)
        if balance <= 0:
            continue

        alloc = CountryAllocationVM.compute_allocation(pid)
        if alloc.empty:
            continue

        for _, a in alloc.iterrows():
            country = a["country"]
            pct = float(a["pct"])
            amount = balance * pct / 100.0
            country_funds[country] = country_funds.get(country, 0) + amount

    if not country_funds:
        st.info("No allocation data available.")
        return

    fund_df = pd.DataFrame([
        {"Country": country_flag(c), "country_raw": c, "Amount": amt}
        for c, amt in country_funds.items()
    ]).sort_values("Amount", ascending=False)

    total = fund_df["Amount"].sum()
    fund_df["Pct"] = (fund_df["Amount"] / total * 100).round(2) if total > 0 else 0
    fund_df["Amount €"] = fund_df["Amount"].apply(lambda x: f"€{x:,.2f}")

    # Pie chart
    fig = px.pie(
        fund_df, values="Amount", names="Country",
        title="Portfolio-wide Country Distribution",
        hole=0.3,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig, width="stretch")

    # Table
    st.dataframe(
        fund_df[["Country", "Amount €", "Pct"]].rename(columns={"Pct": "%"}),
        width="stretch",
        hide_index=True,
    )


def _render_overview(portfolio_id: int) -> None:
    """Global overview: all country statuses across all platforms."""
    all_statuses = CountryStatusVM.list_statuses()
    if all_statuses.empty:
        st.info("No country statuses recorded yet.")
        return

    # Add colour-coded HTML for status display
    all_statuses = all_statuses.copy()
    all_statuses["_prio"] = all_statuses["status"].apply(country_status_priority)
    all_statuses = all_statuses.sort_values(["_prio", "country"])
    all_statuses["Country"] = all_statuses["country"].apply(country_flag)
    all_statuses["Status"] = all_statuses["status"]

    st.dataframe(
        all_statuses[["Country", "platform", "Status", "note"]].rename(
            columns={"platform": "Platform", "note": "Note"}
        ),
        width="stretch",
        hide_index=True,
    )

    # Pivot: country × platform → status
    pivot = all_statuses.pivot_table(
        index="Country",
        columns="platform",
        values="status",
        aggfunc="first",
    ).fillna("—")
    st.subheader("Country × Platform Matrix")
    st.dataframe(pivot, width="stretch")


# ---------------------------------------------------------------------------
# Auto-Score helpers (moved from Scoring page)
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


def _render_auto_country(
    portfolio_id: int, platforms: pd.DataFrame
) -> None:
    """Auto-score section for country count criterion."""
    criteria = CriteriaVM.list_criteria(portfolio_id)
    special = criteria[(criteria["is_special"] == True) & (criteria["special_type"] == "country")]  # noqa: E712
    if special.empty:
        return

    st.divider()
    st.subheader("Auto-Score Equation")
    st.markdown(
        "Variables: `count` (number of countries for the platform). "
        "Builtins: `min()`, `max()`, `abs()`."
    )

    eq, enabled = AutoScoreVM.get_equation(portfolio_id, "country")

    col_eq, col_toggle = st.columns([4, 1])
    new_eq = col_eq.text_input(
        "Equation",
        value=eq,
        key="auto_eq_country",
        help="Python expression. Result clamped to [0, 10].",
    )
    new_enabled = col_toggle.checkbox("Enabled", value=enabled, key="auto_en_country")

    c1, c2 = st.columns(2)
    if c1.button("💾 Save Equation", key="save_eq_country"):
        AutoScoreVM.save_equation(portfolio_id, "country", new_eq, new_enabled)
        st.success("Country score equation saved!")

    if c2.button("🔄 Apply & Write Scores", key="apply_country", disabled=not new_enabled):
        crit_row = special.iloc[0]
        crit_id = int(crit_row["id"])
        scores = AutoScoreVM.compute_country_scores(portfolio_id, new_eq)
        if not scores:
            st.warning("No country data found for Running platforms.")
        else:
            for pid, score in scores.items():
                ScoringVM.save_score(pid, crit_id, score)
            st.success(f"Applied country scores to {len(scores)} platforms.")
            preview_rows = []
            plat_map = dict(zip(platforms["id"].astype(int), platforms["name"]))
            for pid, score in sorted(scores.items(), key=lambda x: -x[1]):
                preview_rows.append({"Platform": plat_map.get(pid, str(pid)), "Score": round(score, 2)})
            st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)
