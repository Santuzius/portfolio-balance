"""Criteria definition and pairwise weighting matrix page."""

from __future__ import annotations

import streamlit as st
import pandas as pd
from app.viewmodels.mcda_vm import CriteriaVM


SPECIAL_TYPES = [None, "interest_rate", "country", "loan_originator"]
SPECIAL_LABELS = {
    "interest_rate": "Interest Rate",
    "country": "Country",
    "loan_originator": "Loan Originator",
    None: "None",
}


def page() -> None:
    """st.navigation entry-point."""
    portfolio_id = st.session_state.get("portfolio_id")
    if portfolio_id is None:
        st.info("👈 Select or create a portfolio to get started.")
        return
    render(portfolio_id)


def page_weighting() -> None:
    """st.navigation entry-point for weighting matrix."""
    portfolio_id = st.session_state.get("portfolio_id")
    if portfolio_id is None:
        st.info("👈 Select or create a portfolio to get started.")
        return
    render_weighting(portfolio_id)


def render(portfolio_id: int) -> None:
    st.header("⚖️ Criteria")
    _render_criteria(portfolio_id)


def render_weighting(portfolio_id: int) -> None:
    st.header("📐 Weighting Matrix (Gewichtungsmatrix)")
    _render_weighting(portfolio_id)


def _render_criteria(portfolio_id: int) -> None:
    st.subheader("Define Criteria")
    criteria = CriteriaVM.list_criteria(portfolio_id)

    with st.expander("➕ Add Criterion", expanded=criteria.empty):
        with st.form("add_criterion"):
            name = st.text_input("Criterion Name")
            order = st.number_input("Display Order", value=len(criteria) + 1, min_value=1)
            sp_type = st.selectbox(
                "Special Type",
                SPECIAL_TYPES,
                format_func=lambda x: SPECIAL_LABELS.get(x, "None"),
            )
            if st.form_submit_button("Add"):
                if name.strip():
                    is_special = sp_type is not None
                    try:
                        CriteriaVM.create_criterion(
                            portfolio_id, name.strip(), order, is_special, sp_type
                        )
                        st.success(f"Criterion '{name}' added!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    if criteria.empty:
        st.info("No criteria defined yet.")
        return

    for _, c in criteria.iterrows():
        sp_label = SPECIAL_LABELS.get(c.get("special_type"), "None")
        label = f"{'⭐ ' if c['is_special'] else '⚫ '}{c['name']} (order: {c['display_order']}, special: {sp_label})"
        with st.expander(label):
            with st.form(f"edit_crit_{c['id']}"):
                ec_name = st.text_input("Name", value=c["name"], key=f"ec_name_{c['id']}")
                ec_order = st.number_input("Order", value=int(c["display_order"]), key=f"ec_order_{c['id']}")
                ec_type = st.selectbox(
                    "Type",
                    SPECIAL_TYPES,
                    index=SPECIAL_TYPES.index(c.get("special_type")) if c.get("special_type") in SPECIAL_TYPES else 0,
                    format_func=lambda x: SPECIAL_LABELS.get(x, "None"),
                    key=f"ec_type_{c['id']}",
                )
                col1, col2 = st.columns(2)
                if col1.form_submit_button("Update"):
                    ec_special = ec_type is not None
                    CriteriaVM.update_criterion(
                        c["id"], ec_name, ec_order, ec_special, ec_type
                    )
                    st.success("Updated!")
                    st.rerun()
                if col2.form_submit_button("🗑️ Delete"):
                    CriteriaVM.delete_criterion(c["id"])
                    st.success("Deleted!")
                    st.rerun()


def _render_weighting(portfolio_id: int) -> None:
    st.subheader("Pairwise Comparison Matrix")
    st.caption(
        "Compare criteria pairwise: **2** = row is more important, "
        "**1** = equal, **0** = row is less important. "
        "The mirror cell is filled automatically."
    )

    criteria = CriteriaVM.list_criteria(portfolio_id)

    if len(criteria) < 2:
        st.info("Need at least 2 criteria to build a weighting matrix.")
        return

    ids = criteria["id"].tolist()
    names = criteria["name"].tolist()
    n = len(ids)

    # Load existing comparisons
    existing = CriteriaVM.get_pairwise_values_dict(portfolio_id)

    # Build the upper-triangle form
    with st.form("pairwise_form"):
        st.markdown("Fill the **upper triangle** (row vs column):")

        # Create header
        header_cols = st.columns(n + 1)
        header_cols[0].write("**↓ Row / Col →**")
        for j, name in enumerate(names):
            header_cols[j + 1].write(f"**{name}**")

        values_to_save = []
        for i in range(n):
            row_cols = st.columns(n + 1)
            row_cols[0].write(f"**{names[i]}**")
            for j in range(n):
                if i == j:
                    row_cols[j + 1].write("—")
                elif i < j:
                    # Upper triangle: editable
                    current = existing.get((ids[i], ids[j]), 1)
                    val = row_cols[j + 1].selectbox(
                        f"{names[i]} vs {names[j]}",
                        [0, 1, 2],
                        index=current,
                        key=f"pw_{ids[i]}_{ids[j]}",
                        label_visibility="collapsed",
                    )
                    values_to_save.append((ids[i], ids[j], val))
                else:
                    # Lower triangle: show mirror (read-only)
                    mirror_val = existing.get((ids[i], ids[j]), 1)
                    row_cols[j + 1].write(str(mirror_val))

        if st.form_submit_button("💾 Save Weighting Matrix"):
            for row_id, col_id, val in values_to_save:
                CriteriaVM.save_pairwise_value(portfolio_id, row_id, col_id, val)
            st.success("Weighting matrix saved!")
            st.rerun()

    # Show computed weights
    st.subheader("Computed Weights")
    weights = CriteriaVM.compute_weights(portfolio_id)
    if not weights.empty:
        display = weights[["name", "raw_sum", "weight_factor"]].rename(
            columns={"name": "Criterion", "raw_sum": "Raw Sum", "weight_factor": "Weight Factor"}
        )
        st.dataframe(display, width="stretch", hide_index=True)
