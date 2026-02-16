# HubSpot Sales Intelligence Dashboard

## Overview

A comprehensive, self-contained sales intelligence dashboard that pulls data from HubSpot CRM API v3, analyzes it across 6 dimensions, and generates an interactive HTML dashboard with time-period filtering and YoY comparisons.

Built for a 4-10 person sales team running a mixed inbound + outbound motion.

---

## Architecture

```mermaid
flowchart TD
    subgraph External
        HS[("HubSpot CRM<br/>API v3")]
    end

    subgraph "Data Layer"
        FH["fetch_hubspot.py<br/><i>API client + pagination</i>"]
        RAW[("data/raw/<br/>12 JSON files ~95MB")]
    end

    subgraph "Analysis Layer"
        SA["hubspot_sales_analyzer.py"]
        LA["LeadAnalyzer"]
        PA["PipelineAnalyzer"]
        AA["ActivityAnalyzer"]
        CA["ContactAnalyzer"]
        WA["WebSignalsAnalyzer"]
        IA["InsightsAnalyzer"]
        RE["ReverseEngineeringModel"]
        TS["TimeSeriesCollector"]
        YOY["YoY Summary"]
        PROC[("data/processed/<br/>hubspot_sales_metrics.json")]
    end

    subgraph "Presentation Layer"
        GD["generate_hubspot_dashboard.py"]
        HTML[("dashboard-v2.html<br/>336KB self-contained")]
        FAPI["FastAPI Server<br/>main.py"]
    end

    subgraph "Deployment"
        LOCAL["localhost:8001"]
        GHP["GitHub Pages"]
    end

    HS -->|"Bearer pat-eu1-*"| FH
    FH -->|"Pagination + Rate Limiting<br/>100 req/10s"| RAW

    RAW --> SA
    SA --> LA & PA & AA & CA & WA & IA & RE & TS
    TS --> YOY
    LA & PA & AA & CA & WA & IA & RE & YOY --> PROC

    PROC --> GD
    GD -->|"Inline CSS/JS/SVG<br/>No CDN dependencies"| HTML

    HTML --> FAPI --> LOCAL
    HTML --> GHP

    style HS fill:#ff7a59,stroke:#ff5c35,color:#fff
    style HTML fill:#fb923c,stroke:#ea580c,color:#fff
    style PROC fill:#38bdf8,stroke:#0284c7,color:#fff
    style RAW fill:#334155,stroke:#475569,color:#e2e8f0
```

---

## Pipeline Flow

```mermaid
sequenceDiagram
    participant H as HubSpot API
    participant F as fetch_hubspot.py
    participant R as data/raw/
    participant A as hubspot_sales_analyzer.py
    participant P as data/processed/
    participant G as generate_hubspot_dashboard.py
    participant D as dashboard-v2.html

    F->>H: GET /crm/v3/objects/contacts (paginated)
    H-->>F: 44,602 contacts
    F->>H: GET /crm/v3/objects/companies
    H-->>F: 17,781 companies
    F->>H: GET /crm/v3/objects/deals
    H-->>F: 75 deals
    F->>H: GET /crm/v3/objects/{calls,meetings,tasks,notes}
    H-->>F: 11,787 activities
    F->>H: GET /crm/v3/owners, pipelines, associations
    H-->>F: 9 owners, 1 pipeline, associations
    F->>R: Write 12 JSON files

    A->>R: Load all raw JSON
    A->>A: Run 6 analyzers + TimeSeriesCollector
    A->>A: Compute YoY summary
    A->>P: Write hubspot_sales_metrics.json

    G->>P: Load metrics JSON
    G->>G: Build 8 dashboard sections
    G->>G: Embed time_series as JS const
    G->>G: Generate filter bar + chart rendering JS
    G->>D: Write 336KB self-contained HTML
```

---

## Dashboard Sections

| # | Section | Key Metrics | Interactive |
|---|---------|-------------|-------------|
| 1 | Executive Summary | Pipeline value, win rate, open deals, activities, contacts, avg deal size | KPIs update on filter |
| 2 | Leads & Sources | Leads by source, MQL/SQL counts, lead status, source effectiveness | Filtered bar charts |
| 3 | Qualified Leads & Funnel | Conversion funnel: Lead > MQL > SQL > Opp > Customer | Static (long-term) |
| 4 | Target Setting | Revenue targets, reverse-engineering model, what-if scenarios | Static (configurable) |
| 5 | Pipeline View | Stage breakdown, velocity, stale deals, pipeline by owner | Static (snapshot) |
| 6 | Activity Tracking | Calls/emails/meetings/tasks by rep, daily trends | Filtered breakdown |
| 7 | Contacts & Companies | Lifecycle stages, top engaged contacts, company summary | KPI updates |
| 8 | Insights & Forecast | Win/loss analysis, sales cycle trends, revenue forecast, cohort analysis | Static (analytical) |

---

## Time Filtering

The dashboard includes an interactive filter bar with 6 time periods:

| Filter | Date Range | Description |
|--------|-----------|-------------|
| This Week | Mon-Sun of current week | Current week performance |
| Last Week | Previous Mon-Sun | Last week's results |
| MTD | 1st of month to today | Month-to-date |
| **YTD** (default) | Jan 1 to today | Year-to-date |
| Last Year | Jan 1 - Dec 31 of prev year | Full previous year |
| All Time | No filter | Everything |

**YoY Badges**: When YTD or All Time is selected, KPI cards show Year-over-Year comparison badges (e.g., "+12.2% YoY").

---

## HubSpot API Endpoints

| Data | Endpoint | Records |
|------|----------|---------|
| Contacts | `GET /crm/v3/objects/contacts` | 44,602 |
| Companies | `GET /crm/v3/objects/companies` | 17,781 |
| Deals | `GET /crm/v3/objects/deals` | 75 |
| Calls | `GET /crm/v3/objects/calls` | 86 |
| Meetings | `GET /crm/v3/objects/meetings` | 3,670 |
| Tasks | `GET /crm/v3/objects/tasks` | 7,113 |
| Notes | `GET /crm/v3/objects/notes` | 918 |
| Owners | `GET /crm/v3/owners/` | 9 |
| Pipelines | `GET /crm/v3/pipelines/deals` | 1 |
| Associations | `POST /crm/v4/associations/batch/read` | 3 types |

Authentication: Private App token (`pat-eu1-*`) via Bearer header.

---

## File Structure

```
Annas Ai Hub/
├── .env                              # API keys (gitignored)
├── .env.example                      # Template
├── .gitignore
├── requirements.txt
├── HUBSPOT_DASHBOARD.md              # This file
│
├── scripts/
│   ├── fetch_hubspot.py              # HubSpot API client (392 lines)
│   ├── hubspot_sales_analyzer.py     # 6 analyzers + time series (1560 lines)
│   └── generate_hubspot_dashboard.py # Dashboard HTML generator (2200+ lines)
│
├── data/
│   ├── raw/                          # Raw HubSpot JSON (gitignored, ~95MB)
│   │   ├── hubspot_contacts_YYYY-MM-DD.json
│   │   ├── hubspot_companies_YYYY-MM-DD.json
│   │   ├── hubspot_deals_YYYY-MM-DD.json
│   │   └── ... (12 files total)
│   └── processed/
│       └── hubspot_sales_metrics.json  # Analyzed metrics (~52KB)
│
├── dashboard/
│   ├── api/
│   │   └── main.py                   # FastAPI server
│   └── frontend/
│       ├── dashboard-v2.html         # Generated dashboard (~336KB)
│       └── index.html                # Original AlpineJS frontend
│
└── integrations/
    └── hubspot.py                    # Async HubSpot client
```

---

## Reverse Engineering Model

The target-setting module calculates required top-of-funnel volume:

```mermaid
flowchart LR
    T["Revenue Target<br/>£100K/mo"] --> D["Required Deals<br/>= Target / Avg Deal"]
    D --> O["Required Opps<br/>= Deals / Win Rate"]
    O --> SQL["Required SQLs<br/>= Opps / SQL-to-Opp"]
    SQL --> MQL["Required MQLs<br/>= SQLs / MQL-to-SQL"]
    MQL --> L["Required Leads<br/>= MQLs / Lead-to-MQL"]

    style T fill:#fb923c,stroke:#ea580c,color:#fff
    style L fill:#38bdf8,stroke:#0284c7,color:#fff
```

Current rates from real data:
- Win rate: 27%
- Avg deal size: £15,717
- Avg sales cycle: 105 days

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set HubSpot API key in .env
# HUBSPOT_API_KEY=pat-eu1-your-token-here

# 3. Fetch data from HubSpot
python scripts/fetch_hubspot.py

# 4. Analyze data
python scripts/hubspot_sales_analyzer.py

# 5. Generate dashboard
python scripts/generate_hubspot_dashboard.py

# 6. Serve locally
uvicorn dashboard.api.main:app --port 8001
# Open http://localhost:8001
```

---

## Sales Team (Owners)

| Name | Email |
|------|-------|
| Rose Galbally | rose.galbally@ecomplete.com |
| James Carberry | james.carberry@ecomplete.com |
| Skye Whitton | skylar.whitton@ecomplete.com |
| Josh Elliott | josh.elliott@ecomplete.com |
| Anna Younger | anna.younger@ecomplete.com |
| Caldon Henson | caldon.henson@ecomplete.com |
| Paul Gedman | paul.gedman@ecomplete.com |
| Jake Heath | jake.heath@ecomplete.com |
| Kirill Kopica | kirill.kopica@ecomplete.com |

---

## Pipeline: All New Business

```mermaid
flowchart LR
    IL["Inbound Lead<br/>2%"] --> E["Engaged<br/>1%"]
    E --> FM["First Meeting<br/>5%"]
    FM --> SM["Second Meeting<br/>10%"]
    SM --> PS["Proposal Shared<br/>40%"]
    PS --> DM["Decision Maker<br/>80%"]
    DM --> CS["Contract Sent<br/>90%"]
    CS --> CW["Closed Won<br/>100%"]
    CS --> CL["Closed Lost<br/>0%"]
    IL --> DQ["Disqualified<br/>0%"]

    style CW fill:#22c55e,stroke:#16a34a,color:#fff
    style CL fill:#ef4444,stroke:#dc2626,color:#fff
    style DQ fill:#6b7280,stroke:#4b5563,color:#fff
```

---

## Configuration

Edit `DEFAULT_CONFIG` in `hubspot_sales_analyzer.py`:

```python
DEFAULT_CONFIG = {
    "revenue_target": {
        "monthly": 100_000,
        "quarterly": 300_000,
        "annual": 1_200_000,
    },
    "stale_deal_threshold_days": 30,
    "activity_targets": {
        "calls_per_rep_per_day": 15,
        "emails_per_rep_per_day": 25,
        "meetings_per_rep_per_week": 5,
    },
}
```
