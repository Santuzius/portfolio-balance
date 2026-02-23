"""Balance Tracking page – record and monitor portfolio balance snapshots."""

from __future__ import annotations

from datetime import datetime
import streamlit as st
import pandas as pd

from app.viewmodels.balance_vm import BalanceVM
from app.viewmodels.portfolio_vm import PortfolioVM


def render(portfolio_id: int) -> None:
    st.header("💰 Balance Tracking")

    portfolio = PortfolioVM.get_portfolio(portfolio_id)
    if portfolio is None:
        st.error("Portfolio not found.")
        return

    # ── Get active platforms (exclude €0 Closed/Defaulted) ──────────
    platforms = PortfolioVM.list_platforms(portfolio_id, include_inactive=False)
    all_platforms = PortfolioVM.list_platforms(portfolio_id)
    if all_platforms.empty:
        st.warning("No platforms configured. Add platforms to your portfolio first.")
        return

    # ── 1. Current Balances (first) ─────────────────────────────────
    st.subheader("💡 Current Balances")

    latest_df = BalanceVM.get_latest_balances(portfolio_id)

    if latest_df.empty:
        st.info("No balance data available yet.")
    else:
        # Filter out €0 Closed/Defaulted
        display_latest = latest_df.copy()
        display_latest = display_latest[
            ~(
                (display_latest["status"].isin(["Closed", "Defaulted"]))
                & (display_latest["balance"].fillna(0) == 0)
            )
        ]
        if display_latest.empty:
            st.info("No active balances.")
        else:
            display_latest = display_latest.sort_values("balance", ascending=False, na_position="last")
            display_latest["balance"] = display_latest["balance"].fillna(0).apply(lambda x: f"€{x:,.2f}")
            display_latest["month"] = pd.to_datetime(display_latest["month"]).dt.strftime("%Y-%m-%d")

            st.dataframe(
                display_latest[["platform", "status", "balance", "month"]].rename(
                    columns={"platform": "Platform", "status": "Status", "balance": "Balance", "month": "Date"}
                ),
                use_container_width=True,
                hide_index=True,
            )

    # ── 2. Record New Balance ───────────────────────────────────────
    st.subheader("📝 Record Balance Snapshot")

    if all_platforms.empty:
        st.warning("No platforms to record balances for.")
    else:
        with st.form("record_balance_form"):
            col1, col2, col3 = st.columns(3)

            with col1:
                platform_name = st.selectbox(
                    "Platform",
                    options=all_platforms["name"].tolist(),
                    key="balance_platform",
                )

            with col2:
                month = st.date_input(
                    "Date",
                    value=datetime.now().date().replace(day=1),
                    key="balance_month",
                )

            with col3:
                balance = st.number_input(
                    "Balance Amount",
                    min_value=0.0,
                    step=100.0,
                    key="balance_amount",
                )

            if st.form_submit_button("Record Balance"):
                platform_id = int(all_platforms[all_platforms["name"] == platform_name]["id"].values[0])
                try:
                    BalanceVM.record_balance(platform_id, month, balance)
                    st.success(f"Balance recorded for {platform_name} on {month}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error recording balance: {str(e)}")

    # ── 3. Balance History (last, all records, with delete) ─────────
    st.subheader("📊 Balance History")

    balances_df = BalanceVM.get_balances_for_portfolio(portfolio_id)

    if balances_df.empty:
        st.info("No balance snapshots recorded yet.")
    else:
        display_df = balances_df.copy()
        display_df["month"] = pd.to_datetime(display_df["month"]).dt.strftime("%Y-%m-%d")
        display_df["balance_fmt"] = display_df["balance"].apply(lambda x: f"€{x:,.2f}")

        st.dataframe(
            display_df[["month", "platform", "balance_fmt"]].rename(
                columns={"month": "Date", "platform": "Platform", "balance_fmt": "Balance"}
            ),
            use_container_width=True,
            hide_index=True,
        )

        # Delete individual records
        st.markdown("**Delete a record:**")
        options = {
            f"{row['platform']} — €{row['balance']:,.2f} ({pd.to_datetime(row['month']).strftime('%Y-%m-%d')})": int(row["id"])
            for _, row in balances_df.iterrows()
        }
        del_label = st.selectbox("Select record to delete", list(options.keys()), key="del_balance")
        if st.button("🗑️ Delete Record", key="del_balance_btn"):
            BalanceVM.delete_balance(options[del_label])
            st.success("Record deleted!")
            st.rerun()
