"""Reusable UI helper components."""

from __future__ import annotations
import streamlit as st


STATUS_COLORS = {
    "Running": "🟢",
    "Dissaving": "🟡",
    "Defaulted": "🔴",
    "Closed": "⚪",
}

PLATFORM_STATUSES = ["Running", "Dissaving", "Defaulted", "Closed"]

# Country statuses ordered by priority (best→worst), with hex colour codes
# from the original spreadsheet (J6:K16).
COUNTRY_STATUSES = [
    "Separated",
    "Running",
    "Being Relocated",
    "To Relocate",
    "High Supply",
    "Possible",
    "To Be Tested",
    "Low Supply Active",
    "Low Supply Inactive",
    "Risky",
    "Filtered Out",
]

COUNTRY_STATUS_COLORS: dict[str, str] = {
    "Separated":          "#548135",
    "Running":            "#00b050",
    "Being Relocated":    "#92d050",
    "To Relocate":        "#7030a0",
    "High Supply":        "#0070c0",
    "Possible":           "#000000",
    "To Be Tested":       "#ff3399",
    "Low Supply Active":  "#ffc000",
    "Low Supply Inactive":"#ffd965",
    "Risky":              "#ff0000",
    "Filtered Out":       "#a5a5a5",
}

# Mapping from ISO 3166-1 country names to flag emojis
COUNTRY_FLAGS: dict[str, str] = {
    "Albania": "🇦🇱", "Armenia": "🇦🇲", "Botswana": "🇧🇼", "Brazil": "🇧🇷",
    "Bulgaria": "🇧🇬", "Colombia": "🇨🇴", "Czech Republic": "🇨🇿", "Denmark": "🇩🇰",
    "Estonia": "🇪🇪", "Finland": "🇫🇮", "Georgia": "🇬🇪", "Germany": "🇩🇪",
    "Great Britain": "🇬🇧", "Iceland": "🇮🇸", "India": "🇮🇳", "Indonesia": "🇮🇩",
    "Jordan": "🇯🇴", "Kazakhstan": "🇰🇿", "Kenya": "🇰🇪", "Kosovo": "🇽🇰",
    "Latvia": "🇱🇻", "Lithuania": "🇱🇹", "Mexico": "🇲🇽", "Moldova": "🇲🇩",
    "Netherlands": "🇳🇱", "Nigeria": "🇳🇬", "North Macedonia": "🇲🇰",
    "Peru": "🇵🇪", "Philippines": "🇵🇭", "Poland": "🇵🇱", "Romania": "🇷🇴",
    "Russia": "🇷🇺", "Singapore": "🇸🇬", "South Africa": "🇿🇦", "Spain": "🇪🇸",
    "Sri Lanka": "🇱🇰", "Sweden": "🇸🇪", "Uganda": "🇺🇬", "Ukraine": "🇺🇦",
    "Uzbekistan": "🇺🇿", "Vietnam": "🇻🇳", "Belarus": "🇧🇾", "Cyprus": "🇨🇾",
}


def country_flag(country: str) -> str:
    """Return flag emoji + country name."""
    flag = COUNTRY_FLAGS.get(country, "🏳️")
    return f"{flag} {country}"


def country_status_badge(status: str) -> str:
    """Return a coloured dot + status label as HTML."""
    color = COUNTRY_STATUS_COLORS.get(status, "#888")
    return f'<span style="color:{color}">●</span> {status}'


def country_status_priority(status: str) -> int:
    """Return sort priority (lower = better)."""
    try:
        return COUNTRY_STATUSES.index(status)
    except ValueError:
        return 999


def status_badge(status: str) -> str:
    """Return an emoji + status label."""
    icon = STATUS_COLORS.get(status, "❓")
    return f"{icon} {status}"


def portfolio_selector(key: str = "portfolio_select") -> int | None:
    """Render a portfolio selector in the sidebar and return selected id."""
    from app.viewmodels.portfolio_vm import PortfolioVM

    portfolios = PortfolioVM.list_portfolios()
    if portfolios.empty:
        st.sidebar.warning("No portfolios yet. Create one first.")
        return None

    options = {f"{row['name']} ({STATUS_COLORS.get(row['status'], '')})": row["id"] for _, row in portfolios.iterrows()}
    selected_label = st.sidebar.selectbox("Portfolio", list(options.keys()), key=key)
    return options[selected_label] if selected_label else None


def platform_selector(portfolio_id: int, key: str = "platform_select", include_all: bool = False) -> int | None:
    """Render a platform selector and return selected id."""
    from app.viewmodels.portfolio_vm import PortfolioVM

    platforms = PortfolioVM.list_platforms(portfolio_id)
    if platforms.empty:
        st.warning("No platforms in this portfolio.")
        return None

    options = {}
    if include_all:
        options["All Platforms"] = None
    for _, row in platforms.iterrows():
        options[f"{row['name']} ({STATUS_COLORS.get(row['status'], '')})"] = row["id"]

    selected_label = st.selectbox("Platform", list(options.keys()), key=key)
    return options[selected_label] if selected_label else None
