"""Special criterion pages: Interest Rates comparison and Country Status overview."""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

from app.viewmodels.portfolio_vm import PortfolioVM
from app.viewmodels.balance_vm import (
    InterestRateVM, CountryStatusVM, CountryAllocationVM, BalanceVM,
)
from app.views.components.common import (
    COUNTRY_STATUSES, COUNTRY_STATUS_COLORS, country_flag,
    country_status_priority,
)


# ---------------------------------------------------------------------------
# Interest Rates
# ---------------------------------------------------------------------------

def render_interest_rates(portfolio_id: int) -> None:
    st.header("📈 Interest Rate Comparison")

    show_inactive = st.checkbox("Show inactive platforms", value=False, key="ir_show_inactive")
    platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=show_inactive)
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
        st.plotly_chart(fig, use_container_width=True)

        # Summary stats
        col1, col2, col3 = st.columns(3)
        active_rates = chart_df["est_pct"]
        col1.metric("Min Rate", f"{active_rates.min():.2f}%")
        col2.metric("Avg Rate", f"{active_rates.mean():.2f}%")
        col3.metric("Max Rate", f"{active_rates.max():.2f}%")


# ---------------------------------------------------------------------------
# Country Status
# ---------------------------------------------------------------------------

def _status_color_html(status: str) -> str:
    """Coloured dot + status name as HTML."""
    color = COUNTRY_STATUS_COLORS.get(status, "#888")
    return f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{color};margin-right:4px"></span>{status}'


def render_country_status(portfolio_id: int) -> None:
    st.header("🌍 Country Status Overview")

    platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=False)
    if platforms.empty:
        st.warning("Add platforms first.")
        return

    tab_stats, tab_alloc, tab_platform, tab_details = st.tabs(
        ["Distribution", "Country Allocation", "By Platform", "Details"]
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


def _render_country_allocation(portfolio_id: int, platforms: pd.DataFrame) -> None:
    """Per-platform country allocation mode and percentages."""
    st.subheader("Country Allocation")

    sel = st.selectbox("Platform", platforms["name"].tolist(), key="ca_plat")
    plat_row = platforms[platforms["name"] == sel].iloc[0]
    pid = int(plat_row["id"])

    current_mode = CountryAllocationVM.get_mode(pid)

    mode = st.radio(
        "Allocation mode",
        ["equal", "manual"],
        index=0 if current_mode == "equal" else 1,
        horizontal=True,
        key=f"ca_mode_{pid}",
    )
    if mode != current_mode:
        CountryAllocationVM.set_mode(pid, mode)

    countries = CountryStatusVM.list_statuses(pid)
    if countries.empty:
        st.info("No countries for this platform.")
        return

    # Sort by status priority
    countries = countries.copy()
    countries["_prio"] = countries["status"].apply(country_status_priority)
    countries = countries.sort_values("_prio")

    if mode == "manual":
        manual_pcts = CountryAllocationVM.get_pcts(pid)
        pct_map = dict(zip(manual_pcts["country"], manual_pcts["pct"])) if not manual_pcts.empty else {}

        with st.form(f"ca_manual_{pid}"):
            pct_entries = []
            for _, row in countries.iterrows():
                c1, c2 = st.columns([3, 2])
                c1.markdown(
                    f"{country_flag(row['country'])} "
                    f"(<span style='color:{COUNTRY_STATUS_COLORS.get(row['status'], '#888')}'>\u25cf</span> {row['status']})",
                    unsafe_allow_html=True,
                )
                pct = c2.number_input(
                    "%",
                    value=float(pct_map.get(row["country"], 0)),
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    key=f"ca_pct_{pid}_{row['country']}",
                    label_visibility="collapsed",
                )
                pct_entries.append((row["country"], pct))

            total = sum(p for _, p in pct_entries)
            st.markdown(f"**Total: {total:.1f}%** {'✅' if abs(total - 100) < 0.1 else '⚠️ Should be 100%'}")

            if st.form_submit_button("💾 Save Allocation"):
                for country, pct in pct_entries:
                    CountryAllocationVM.save_pct(pid, country, pct)
                st.success("Manual allocation saved!")
                st.rerun()
    else:
        # Equal allocation display with colored statuses
        n = len(countries)
        eq_pct = 100.0 / n if n > 0 else 0
        html_rows = []
        for _, row in countries.iterrows():
            flag = country_flag(row["country"])
            color = COUNTRY_STATUS_COLORS.get(row["status"], "#888")
            html_rows.append(
                f"<tr><td style='padding:4px'>{flag}</td>"
                f"<td style='padding:4px'><span style='color:{color}'>&bull;</span> {row['status']}</td>"
                f"<td style='padding:4px'>{eq_pct:.1f}%</td></tr>"
            )
        html = (
            "<table style='width:100%;border-collapse:collapse'>"
            "<tr style='border-bottom:2px solid #ddd'>"
            "<th style='text-align:left;padding:4px'>Country</th>"
            "<th style='text-align:left;padding:4px'>Status</th>"
            "<th style='text-align:left;padding:4px'>Allocation %</th></tr>"
            + "".join(html_rows) + "</table>"
        )
        st.markdown(html, unsafe_allow_html=True)


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
    st.plotly_chart(fig, use_container_width=True)

    # Table
    st.dataframe(
        fund_df[["Country", "Amount €", "Pct"]].rename(columns={"Pct": "%"}),
        use_container_width=True,
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
        use_container_width=True,
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
    st.dataframe(pivot, use_container_width=True)
