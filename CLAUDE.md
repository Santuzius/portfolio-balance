# CLAUDE.md – AI Development Guidelines

## Project Overview
P2P lending portfolio management app using **Streamlit + DuckDB**.
MVVM architecture with clean data-access separation.

## Quick Start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/main.py
```

## Architecture
```
pb-data/                         # DuckDB file (separate folder for cloud sync)
app/
├── models/
│   ├── database.py              # DuckDB connection (@st.cache_resource) + schema bootstrap
│   └── repositories.py          # ALL SQL queries (data access layer)
├── viewmodels/
│   ├── portfolio_vm.py          # Portfolio & platform CRUD (delegates to repos)
│   ├── mcda_vm.py               # Criteria, weighting, scoring, allocation computation
│   └── balance_vm.py            # Balances, pockets, interest rates, countries, originators, auto-score
├── views/
│   ├── components/common.py     # Shared UI helpers (selectors, badges, constants)
│   └── pages/                   # Streamlit page modules (each has a page() entry-point)
│       ├── interest_rates.py    # Interest rate comparison
│       ├── countries.py         # Country status & allocation (can inherit from originators)
│       └── loan_originators.py  # Loan originator management & allocation
└── main.py                      # App entry-point with st.navigation
```

## Key Rules
- **No DB queries in viewmodels or views.** All SQL lives in `repositories.py`.
- **Connection is cached** via `@st.cache_resource` in `database.py`.
- **Page routing** uses `st.navigation` (Streamlit ≥1.37). Each page module exposes a `page()` function.
- **No temporary tables** in DuckDB. All state is either persistent or in `st.session_state`.
- DuckDB UPDATE = internal DELETE+INSERT → FK-safe workaround (detach/re-attach) required for updates with dependants.
- **No CHECK constraints on `special_type`** columns — app-level validation only (avoids DuckDB migration pain).

## Conventions
- Static methods on classes (no instances).
- `pd.DataFrame` as the primary data exchange format.
- `int()` cast on all IDs before passing to SQL (DuckDB is strict with int64 vs Python int).
- Pairwise matrix uses 0/1/2 values (less/equal/more important); mirror is `2 - val`.
- Allocation: `weight_factor = raw_pairwise_sum + 1` (so every criterion gets at least weight 1).
- Originator composite key: `_orig_key(name, country)` → `"name|country"` (same name can exist in different countries).
- Special criteria types: `interest_rate`, `country`, `loan_originator`. Each gets a conditional sidebar page.

## Testing
No test suite yet. Manual testing via the Streamlit UI.
The DuckDB file is at `pb-data/portfolio_balance.duckdb`.

## Common Tasks
- **Add a new table**: Update `database.py` `_bootstrap()`, add repo class in `repositories.py`, add VM methods, add UI.
- **Add a new page**: Create view in `pages/`, add `page()` wrapper, register in `main.py` `pages` list.
- **Add a new special criterion type**: Add type string to `SPECIAL_TYPES` in `criteria.py`, create page module, wire in `main.py`.
- **Fix FK violations on UPDATE**: Use the detach/re-attach pattern (see `PlatformRepo.update()`).
- **DB migrations**: Use `_migrate()` in `database.py`. Avoid ALTER on tables with FK dependants (use export/import instead).
