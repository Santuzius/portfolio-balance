# Portfolio Balance

A **Streamlit** web application for managing P2P lending investment portfolios using **Multi-Criteria Decision Analysis (MCDA)**. It helps you determine optimal fund allocation across platforms, track balances, and monitor deviations from your target portfolio.

## Features

### Portfolio & Platform Management
- Create and manage investment portfolios
- Track platforms with statuses: **Running**, **Dissaving**, **Defaulted**, **Closed**
- Platforms sorted by status and latest balance

### MCDA-Based Allocation
- Define custom evaluation criteria (e.g. liquidity, reliability, regulation)
- **Pairwise comparison** weighting matrix to prioritize criteria
- Score each platform (0–10) on every criterion
- Automatically compute weighted allocation percentages

### Dashboard
- **Current vs Target** distribution pie charts
- Deviation analysis table and bar chart (sorted by balance)
- Rebalancing status selector — choose which platform statuses participate in rebalancing; unchecked statuses are treated as off-budget
- KPI metrics: total balance, off-budget, effective balance
- MCDA scores summary

### Balance Tracking
- Record balance snapshots per platform and date
- View current balances (filtered: excludes €0 Closed/Defaulted)
- Full balance history with individual record deletion
- Off-budget pockets per platform

### Interest Rates
- Track estimated interest rates per platform
- Comparison bar chart with min/avg/max stats
- Toggle to show/hide inactive platforms

### Country Status Management
- Track country statuses across all platforms with 11 priority-ordered statuses:
  Separated, Running, Being Relocated, To Relocate, High Supply, Possible, To Be Tested, Low Supply Active, Low Supply Inactive, Risky, Filtered Out
- **Color-coded** status indicators (hex colors from the original spreadsheet)
- **Country flags** 🇩🇪🇵🇱🇱🇻 auto-displayed alongside country names
- Per-platform **country allocation** (manual percentages or equal distribution)
- Portfolio-wide **country fund distribution** pie chart
- Country × Platform status matrix

## Architecture

```
app/
├── main.py                          # Streamlit entry point + page router
├── models/
│   └── database.py                  # DuckDB schema (idempotent bootstrap)
├── viewmodels/
│   ├── portfolio_vm.py              # Portfolio & Platform CRUD
│   ├── mcda_vm.py                   # Criteria, weighting, scoring, allocation
│   └── balance_vm.py                # Balances, pockets, interest rates, countries
└── views/
    ├── components/
    │   └── common.py                # Shared helpers (badges, selectors, flags)
    └── pages/
        ├── dashboard.py             # Main overview with deviation analysis
        ├── portfolios.py            # Portfolio & platform management
        ├── criteria.py              # Criteria definition + weighting matrix
        ├── scoring.py               # Score matrix + MCDA results
        ├── balances.py              # Balance recording and history
        └── special_criteria.py      # Interest rates + country status
```

**MVVM pattern**: Models (DuckDB) → ViewModels (business logic) → Views (Streamlit UI)

## Tech Stack

- **[Streamlit](https://streamlit.io/)** — Web UI framework
- **[DuckDB](https://duckdb.org/)** — Embedded analytical database (persistent, single-file)
- **[Pandas](https://pandas.pydata.org/)** — Data manipulation
- **[Plotly](https://plotly.com/python/)** — Interactive charts
- **[NumPy](https://numpy.org/)** — Numerical operations

## Getting Started

### Prerequisites

- Python 3.11+

### Installation

```bash
git clone https://github.com/Santuzius/portfolio-balance.git
cd portfolio-balance
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Seed Data (Optional)

To populate the database with sample data from the included FODS spreadsheet:

```bash
python -m app.seed
```

### Run

```bash
streamlit run app/main.py
```

The app opens at [http://localhost:8501](http://localhost:8501).

## Quick Start Guide

1. **Create a portfolio** on the Portfolios page
2. **Add platforms** (e.g. Mintos, PeerBerry, Bondora G&G)
3. **Define criteria** on the Criteria page (e.g. Liquidity, Reliability)
4. **Fill the weighting matrix** — pairwise compare criteria importance
5. **Score platforms** on the Scoring page (0–10 per criterion)
6. **Record balances** on the Balance Tracking page
7. **View the Dashboard** to see current vs target allocation and deviation

## License

[MIT](LICENSE)
