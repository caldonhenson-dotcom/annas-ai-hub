-- ============================================
-- ANNAS AI HUB — Normalised Data Schema
-- ============================================
-- Migration 004: Entity tables for live queries
-- Replaces JSONB blobs with queryable, indexed tables
-- ============================================

-- =====================
-- HUBSPOT TABLES
-- =====================

-- Owners (sales reps)
CREATE TABLE IF NOT EXISTS owners (
    id              TEXT PRIMARY KEY,           -- HubSpot owner ID
    name            TEXT,
    email           TEXT,
    source          TEXT DEFAULT 'hubspot',     -- hubspot | monday
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Pipeline stages
CREATE TABLE IF NOT EXISTS pipeline_stages (
    id              TEXT PRIMARY KEY,           -- stage ID
    pipeline_id     TEXT NOT NULL,
    label           TEXT NOT NULL,
    display_order   INT,
    probability     NUMERIC,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Deals
CREATE TABLE IF NOT EXISTS deals (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    stage           TEXT,
    stage_label     TEXT,
    pipeline        TEXT,
    amount          NUMERIC,
    weighted_amount NUMERIC,
    probability     INT,
    owner_id        TEXT,
    owner_name      TEXT,
    close_date      DATE,
    create_date     TIMESTAMPTZ,
    last_modified   TIMESTAMPTZ,
    is_closed_won   BOOLEAN DEFAULT FALSE,
    is_closed       BOOLEAN DEFAULT FALSE,
    source          TEXT,                       -- analytics source
    deal_type       TEXT,
    days_in_stage   INT,
    closed_won_reason  TEXT,
    closed_lost_reason TEXT,
    forecast_amount    NUMERIC,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deals_stage ON deals (stage);
CREATE INDEX IF NOT EXISTS idx_deals_owner ON deals (owner_id);
CREATE INDEX IF NOT EXISTS idx_deals_close_date ON deals (close_date);
CREATE INDEX IF NOT EXISTS idx_deals_created ON deals (create_date DESC);

-- Contacts
CREATE TABLE IF NOT EXISTS contacts (
    id              TEXT PRIMARY KEY,
    email           TEXT,
    first_name      TEXT,
    last_name       TEXT,
    company         TEXT,
    phone           TEXT,
    lifecycle_stage TEXT,
    lead_status     TEXT,
    source          TEXT,                       -- analytics source
    owner_id        TEXT,
    owner_name      TEXT,
    create_date     TIMESTAMPTZ,
    last_modified   TIMESTAMPTZ,
    page_views      INT,
    visits          INT,
    first_conversion TEXT,
    recent_conversion TEXT,
    num_deals       INT,
    lead_date       TIMESTAMPTZ,
    mql_date        TIMESTAMPTZ,
    sql_date        TIMESTAMPTZ,
    opportunity_date TIMESTAMPTZ,
    customer_date   TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contacts_lifecycle ON contacts (lifecycle_stage);
CREATE INDEX IF NOT EXISTS idx_contacts_owner ON contacts (owner_id);
CREATE INDEX IF NOT EXISTS idx_contacts_source ON contacts (source);
CREATE INDEX IF NOT EXISTS idx_contacts_created ON contacts (create_date DESC);

-- Companies
CREATE TABLE IF NOT EXISTS companies (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    domain          TEXT,
    industry        TEXT,
    annual_revenue  NUMERIC,
    num_employees   INT,
    lifecycle_stage TEXT,
    owner_id        TEXT,
    create_date     TIMESTAMPTZ,
    num_contacts    INT,
    num_deals       INT,
    source          TEXT,
    total_revenue   NUMERIC,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_companies_industry ON companies (industry);

-- Activities (unified: calls, emails, meetings, tasks, notes)
CREATE TABLE IF NOT EXISTS activities (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,              -- call | email | meeting | task | note
    owner_id        TEXT,
    owner_name      TEXT,
    subject         TEXT,
    direction       TEXT,                       -- inbound | outbound (calls/emails)
    status          TEXT,                       -- disposition, email status, task status
    duration_ms     INT,                        -- call duration
    activity_date   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activities_type ON activities (type);
CREATE INDEX IF NOT EXISTS idx_activities_owner ON activities (owner_id);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities (activity_date DESC);

-- Associations (contact↔deal, contact↔company, deal↔company)
CREATE TABLE IF NOT EXISTS associations (
    id              BIGSERIAL PRIMARY KEY,
    from_type       TEXT NOT NULL,              -- contact | deal | company
    from_id         TEXT NOT NULL,
    to_type         TEXT NOT NULL,
    to_id           TEXT NOT NULL,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(from_type, from_id, to_type, to_id)
);

CREATE INDEX IF NOT EXISTS idx_assoc_from ON associations (from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_assoc_to ON associations (to_type, to_id);

-- =====================
-- MONDAY.COM TABLES
-- =====================

-- Monday boards
CREATE TABLE IF NOT EXISTS monday_boards (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    workspace_id    TEXT,
    workspace_name  TEXT,
    state           TEXT,
    board_kind      TEXT,
    item_count      INT,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Monday M&A projects
CREATE TABLE IF NOT EXISTS monday_projects (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    board_id        TEXT,
    board_name      TEXT,
    workspace       TEXT,
    stage           TEXT,
    status          TEXT,
    owner           TEXT,
    value           NUMERIC,
    target_close    DATE,
    is_active       BOOLEAN DEFAULT TRUE,
    group_name      TEXT,
    subitems_count  INT DEFAULT 0,
    subitems_complete INT DEFAULT 0,
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_monday_projects_stage ON monday_projects (stage);
CREATE INDEX IF NOT EXISTS idx_monday_projects_owner ON monday_projects (owner);
CREATE INDEX IF NOT EXISTS idx_monday_projects_active ON monday_projects (is_active);

-- Monday IC scores
CREATE TABLE IF NOT EXISTS monday_ic_scores (
    id              TEXT PRIMARY KEY,
    item_name       TEXT,
    board_name      TEXT,
    workspace       TEXT,
    total_score     NUMERIC,
    avg_score       NUMERIC,
    status          TEXT,
    owner           TEXT,
    scores          JSONB DEFAULT '{}'::jsonb,   -- {category: score}
    decisions       JSONB DEFAULT '{}'::jsonb,   -- {category: decision}
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ic_scores_score ON monday_ic_scores (total_score DESC);

-- =====================
-- SNAPSHOT DIFFS
-- =====================

CREATE TABLE IF NOT EXISTS snapshot_diffs (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    previous_id     BIGINT,
    current_id      BIGINT,
    changes         JSONB NOT NULL,             -- {metric_name: {old, new, change_pct}}
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshot_diffs_source ON snapshot_diffs (source, generated_at DESC);

-- =====================
-- RLS POLICIES
-- =====================

ALTER TABLE owners ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE associations ENABLE ROW LEVEL SECURITY;
ALTER TABLE monday_boards ENABLE ROW LEVEL SECURITY;
ALTER TABLE monday_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE monday_ic_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE snapshot_diffs ENABLE ROW LEVEL SECURITY;

-- Public read for all entity tables (will be tightened in Phase 7 with user auth)
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN SELECT unnest(ARRAY[
        'owners', 'pipeline_stages', 'deals', 'contacts', 'companies',
        'activities', 'associations', 'monday_boards', 'monday_projects',
        'monday_ic_scores', 'snapshot_diffs'
    ])
    LOOP
        EXECUTE format('CREATE POLICY "Allow public read %I" ON %I FOR SELECT USING (true)', tbl, tbl);
        EXECUTE format('CREATE POLICY "Allow service write %I" ON %I FOR INSERT WITH CHECK (true)', tbl, tbl);
        EXECUTE format('CREATE POLICY "Allow service update %I" ON %I FOR UPDATE USING (true)', tbl, tbl);
        EXECUTE format('CREATE POLICY "Allow service delete %I" ON %I FOR DELETE USING (true)', tbl, tbl);
    END LOOP;
END $$;
