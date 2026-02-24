-- ============================================
-- ANNAS AI HUB — Outreach Engine Schema
-- ============================================
-- Migration 008: Intelligent outreach engine
-- LinkedIn DM integration, pillar-based sequences,
-- AI research/drafting, approval queue, lead scoring
-- ============================================

-- =============================================
-- LINKEDIN TABLES (ported from AI Clawdon)
-- =============================================

-- Encrypted LinkedIn session credentials
CREATE TABLE IF NOT EXISTS linkedin_sessions (
    id              BIGSERIAL PRIMARY KEY,
    li_at           TEXT NOT NULL,               -- Fernet-encrypted li_at cookie
    csrf_token      TEXT NOT NULL,               -- Fernet-encrypted CSRF token
    profile_id      TEXT,                        -- LinkedIn profile URN
    display_name    TEXT,
    is_valid        BOOLEAN DEFAULT TRUE,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_validated  TIMESTAMPTZ DEFAULT NOW()
);

-- LinkedIn conversation threads
CREATE TABLE IF NOT EXISTS linkedin_threads (
    id              TEXT PRIMARY KEY,            -- thread URN
    participants    JSONB DEFAULT '[]'::jsonb,   -- [{id, name, profile_url, photo_url}]
    last_message_at TIMESTAMPTZ,
    last_message_preview TEXT,
    unread_count    INT DEFAULT 0,
    is_archived     BOOLEAN DEFAULT FALSE,
    is_muted        BOOLEAN DEFAULT FALSE,
    is_starred      BOOLEAN DEFAULT FALSE,
    total_messages  INT DEFAULT 0,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_linkedin_threads_last_msg ON linkedin_threads (last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_linkedin_threads_unread ON linkedin_threads (unread_count) WHERE unread_count > 0;

-- LinkedIn individual messages
CREATE TABLE IF NOT EXISTS linkedin_messages (
    id              TEXT PRIMARY KEY,            -- message URN
    thread_id       TEXT NOT NULL REFERENCES linkedin_threads(id) ON DELETE CASCADE,
    sender_id       TEXT,
    sender_name     TEXT,
    body            TEXT,
    attachments     JSONB DEFAULT '[]'::jsonb,
    is_inbound      BOOLEAN DEFAULT TRUE,
    sent_at         TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_linkedin_messages_thread ON linkedin_messages (thread_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_linkedin_messages_sent ON linkedin_messages (sent_at DESC);

-- LinkedIn contact profiles (cache)
CREATE TABLE IF NOT EXISTS linkedin_contacts (
    id              TEXT PRIMARY KEY,            -- profile URN
    first_name      TEXT,
    last_name       TEXT,
    headline        TEXT,
    company         TEXT,
    location        TEXT,
    profile_url     TEXT,
    photo_url       TEXT,
    connection_degree INT,
    industry        TEXT,
    prospect_id     BIGINT,                     -- link to outreach_prospects
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_linkedin_contacts_prospect ON linkedin_contacts (prospect_id) WHERE prospect_id IS NOT NULL;

-- Labels for thread organisation
CREATE TABLE IF NOT EXISTS linkedin_labels (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    color           TEXT DEFAULT '#6366f1',
    sort_order      INT DEFAULT 0,
    is_pinned       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Thread-label junction
CREATE TABLE IF NOT EXISTS linkedin_thread_labels (
    id              BIGSERIAL PRIMARY KEY,
    thread_id       TEXT NOT NULL REFERENCES linkedin_threads(id) ON DELETE CASCADE,
    label_id        BIGINT NOT NULL REFERENCES linkedin_labels(id) ON DELETE CASCADE,
    assigned_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(thread_id, label_id)
);

CREATE INDEX IF NOT EXISTS idx_thread_labels_thread ON linkedin_thread_labels (thread_id);
CREATE INDEX IF NOT EXISTS idx_thread_labels_label ON linkedin_thread_labels (label_id);

-- Snooze timers on threads
CREATE TABLE IF NOT EXISTS linkedin_snoozes (
    id              BIGSERIAL PRIMARY KEY,
    thread_id       TEXT NOT NULL REFERENCES linkedin_threads(id) ON DELETE CASCADE UNIQUE,
    snooze_until    TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Follow-up reminders
CREATE TABLE IF NOT EXISTS linkedin_followups (
    id              BIGSERIAL PRIMARY KEY,
    thread_id       TEXT NOT NULL REFERENCES linkedin_threads(id) ON DELETE CASCADE,
    remind_at       TIMESTAMPTZ NOT NULL,
    note            TEXT,
    is_completed    BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_followups_remind ON linkedin_followups (remind_at) WHERE is_completed = FALSE;

-- Reusable message snippets/templates
CREATE TABLE IF NOT EXISTS linkedin_snippets (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    trigger         TEXT,                        -- shortcode e.g. "/intro"
    variables       JSONB DEFAULT '[]'::jsonb,   -- ["first_name", "company"]
    use_count       INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Private notes on contacts
CREATE TABLE IF NOT EXISTS linkedin_contact_notes (
    id              BIGSERIAL PRIMARY KEY,
    contact_id      TEXT NOT NULL REFERENCES linkedin_contacts(id) ON DELETE CASCADE,
    note            TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contact_notes_contact ON linkedin_contact_notes (contact_id);


-- =============================================
-- OUTREACH ENGINE TABLES
-- =============================================

-- Service pillar definitions
CREATE TABLE IF NOT EXISTS outreach_pillars (
    id              BIGSERIAL PRIMARY KEY,
    slug            TEXT UNIQUE NOT NULL,         -- e.g. "supply-chain", "commercial-dd"
    name            TEXT NOT NULL,                -- e.g. "Supply Chain Optimisation"
    description     TEXT,
    icp_criteria    JSONB DEFAULT '{}'::jsonb,    -- {titles, industries, company_size, revenue_range, signals}
    messaging_angles JSONB DEFAULT '[]'::jsonb,   -- ["pain point 1", "value prop 2"]
    research_prompts JSONB DEFAULT '[]'::jsonb,   -- AI prompts for researching prospects
    objection_handlers JSONB DEFAULT '{}'::jsonb, -- {objection: response_guidance}
    is_active       BOOLEAN DEFAULT TRUE,
    sort_order      INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Multi-step outreach sequences per pillar
CREATE TABLE IF NOT EXISTS outreach_sequences (
    id              BIGSERIAL PRIMARY KEY,
    pillar_id       BIGINT NOT NULL REFERENCES outreach_pillars(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,                -- e.g. "Supply Chain - Cold Outreach"
    description     TEXT,
    channel         TEXT DEFAULT 'linkedin',      -- linkedin | email | multi
    total_steps     INT DEFAULT 1,
    delay_days      INT[] DEFAULT '{3,5,7}'::int[], -- delay between steps
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sequences_pillar ON outreach_sequences (pillar_id);

-- Message templates per sequence step
CREATE TABLE IF NOT EXISTS outreach_templates (
    id              BIGSERIAL PRIMARY KEY,
    sequence_id     BIGINT NOT NULL REFERENCES outreach_sequences(id) ON DELETE CASCADE,
    step_number     INT NOT NULL,                 -- 1, 2, 3...
    name            TEXT,                          -- e.g. "Initial Connection Request"
    channel         TEXT DEFAULT 'linkedin',       -- linkedin | email
    subject         TEXT,                          -- email subject (null for LinkedIn DMs)
    body_template   TEXT NOT NULL,                 -- template with {{variables}}
    ai_system_prompt TEXT,                         -- override system prompt for AI drafting
    variables       JSONB DEFAULT '[]'::jsonb,     -- ["first_name", "company", "pain_point"]
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sequence_id, step_number)
);

CREATE INDEX IF NOT EXISTS idx_templates_sequence ON outreach_templates (sequence_id, step_number);

-- Unified prospects
CREATE TABLE IF NOT EXISTS outreach_prospects (
    id              BIGSERIAL PRIMARY KEY,
    -- Identity
    first_name      TEXT,
    last_name       TEXT,
    email           TEXT,
    linkedin_url    TEXT,
    linkedin_id     TEXT,                         -- LinkedIn profile URN
    phone           TEXT,
    -- Company
    company_name    TEXT,
    company_domain  TEXT,
    company_size    TEXT,                          -- e.g. "50-200"
    industry        TEXT,
    job_title       TEXT,
    -- Source linkage
    hubspot_contact_id TEXT,                      -- link to HubSpot contacts.id
    linkedin_contact_id TEXT,                     -- link to linkedin_contacts.id
    source          TEXT DEFAULT 'manual',         -- hubspot | linkedin | csv | manual
    -- Pillar assignment
    pillar_id       BIGINT REFERENCES outreach_pillars(id),
    -- AI research
    research_brief  JSONB,                        -- AI-generated research output
    research_status TEXT DEFAULT 'pending',        -- pending | in_progress | complete | failed
    researched_at   TIMESTAMPTZ,
    -- Scoring
    fit_score       INT DEFAULT 0,                -- 0-50 (ICP match)
    engagement_score INT DEFAULT 0,               -- 0-50 (response signals)
    lead_score      INT DEFAULT 0,                -- fit + engagement (0-100)
    -- Status
    status          TEXT DEFAULT 'new',            -- new | researched | enrolled | active | replied | won | lost | disqualified
    last_contacted  TIMESTAMPTZ,
    last_replied    TIMESTAMPTZ,
    total_messages_sent INT DEFAULT 0,
    total_messages_received INT DEFAULT 0,
    -- Timestamps
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prospects_pillar ON outreach_prospects (pillar_id);
CREATE INDEX IF NOT EXISTS idx_prospects_status ON outreach_prospects (status);
CREATE INDEX IF NOT EXISTS idx_prospects_score ON outreach_prospects (lead_score DESC);
CREATE INDEX IF NOT EXISTS idx_prospects_hubspot ON outreach_prospects (hubspot_contact_id) WHERE hubspot_contact_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_prospects_linkedin ON outreach_prospects (linkedin_id) WHERE linkedin_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_prospects_email ON outreach_prospects (email) WHERE email IS NOT NULL;

-- Add FK from linkedin_contacts to outreach_prospects
ALTER TABLE linkedin_contacts
    ADD CONSTRAINT fk_linkedin_contacts_prospect
    FOREIGN KEY (prospect_id) REFERENCES outreach_prospects(id) ON DELETE SET NULL;

-- Prospect-in-sequence tracking
CREATE TABLE IF NOT EXISTS outreach_enrollments (
    id              BIGSERIAL PRIMARY KEY,
    prospect_id     BIGINT NOT NULL REFERENCES outreach_prospects(id) ON DELETE CASCADE,
    sequence_id     BIGINT NOT NULL REFERENCES outreach_sequences(id) ON DELETE CASCADE,
    -- Progress
    current_step    INT DEFAULT 1,
    status          TEXT DEFAULT 'active',         -- active | paused | completed | cancelled | replied
    -- Timing
    enrolled_at     TIMESTAMPTZ DEFAULT NOW(),
    next_step_at    TIMESTAMPTZ,                   -- when to execute next step
    completed_at    TIMESTAMPTZ,
    paused_at       TIMESTAMPTZ,
    -- Metadata
    total_sent      INT DEFAULT 0,
    total_replies   INT DEFAULT 0,
    UNIQUE(prospect_id, sequence_id)
);

CREATE INDEX IF NOT EXISTS idx_enrollments_prospect ON outreach_enrollments (prospect_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_sequence ON outreach_enrollments (sequence_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_next_step ON outreach_enrollments (next_step_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_enrollments_status ON outreach_enrollments (status);

-- All outreach messages (sent + received)
CREATE TABLE IF NOT EXISTS outreach_messages (
    id              BIGSERIAL PRIMARY KEY,
    prospect_id     BIGINT NOT NULL REFERENCES outreach_prospects(id) ON DELETE CASCADE,
    enrollment_id   BIGINT REFERENCES outreach_enrollments(id) ON DELETE SET NULL,
    -- Message content
    channel         TEXT DEFAULT 'linkedin',       -- linkedin | email
    direction       TEXT NOT NULL,                  -- outbound | inbound
    subject         TEXT,
    body            TEXT NOT NULL,
    -- Status tracking
    status          TEXT DEFAULT 'draft',           -- draft | pending_approval | approved | sent | delivered | failed | received
    -- AI metadata
    ai_drafted      BOOLEAN DEFAULT FALSE,
    ai_model        TEXT,
    template_id     BIGINT REFERENCES outreach_templates(id),
    -- Intent classification (for inbound)
    intent          TEXT,                           -- interested | not_now | question | referral | objection | unsubscribe | unknown
    intent_confidence NUMERIC,
    intent_signals  JSONB,                         -- extracted intent signals
    -- Linkage
    linkedin_message_id TEXT,                      -- link to linkedin_messages.id
    -- Timestamps
    drafted_at      TIMESTAMPTZ DEFAULT NOW(),
    approved_at     TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    received_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outreach_msgs_prospect ON outreach_messages (prospect_id, drafted_at DESC);
CREATE INDEX IF NOT EXISTS idx_outreach_msgs_enrollment ON outreach_messages (enrollment_id) WHERE enrollment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_outreach_msgs_status ON outreach_messages (status);
CREATE INDEX IF NOT EXISTS idx_outreach_msgs_intent ON outreach_messages (intent) WHERE direction = 'inbound';

-- Human-in-the-loop approval queue
CREATE TABLE IF NOT EXISTS outreach_approvals (
    id              BIGSERIAL PRIMARY KEY,
    message_id      BIGINT NOT NULL REFERENCES outreach_messages(id) ON DELETE CASCADE UNIQUE,
    prospect_id     BIGINT NOT NULL REFERENCES outreach_prospects(id) ON DELETE CASCADE,
    -- Context snapshot (frozen at time of submission)
    prospect_snapshot JSONB NOT NULL,              -- prospect data at time of draft
    pillar_name     TEXT,
    sequence_name   TEXT,
    step_number     INT,
    -- Review
    status          TEXT DEFAULT 'pending',         -- pending | approved | rejected | edited
    reviewer_notes  TEXT,
    edited_body     TEXT,                           -- if reviewer edits the message
    -- Timestamps
    submitted_at    TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_approvals_status ON outreach_approvals (status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_approvals_prospect ON outreach_approvals (prospect_id);

-- Lead score audit trail
CREATE TABLE IF NOT EXISTS outreach_score_history (
    id              BIGSERIAL PRIMARY KEY,
    prospect_id     BIGINT NOT NULL REFERENCES outreach_prospects(id) ON DELETE CASCADE,
    fit_score       INT,
    engagement_score INT,
    lead_score      INT,
    reason          TEXT,                           -- what triggered the recalculation
    scored_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_score_history_prospect ON outreach_score_history (prospect_id, scored_at DESC);

-- AI call audit log
CREATE TABLE IF NOT EXISTS outreach_ai_logs (
    id              BIGSERIAL PRIMARY KEY,
    task            TEXT NOT NULL,                  -- research | draft_message | classify_intent | draft_reply
    provider        TEXT NOT NULL,                  -- groq | claude
    model           TEXT NOT NULL,                  -- llama-3.3-70b-versatile | claude-sonnet-4-5-20250929
    input_tokens    INT,
    output_tokens   INT,
    latency_ms      INT,
    prospect_id     BIGINT REFERENCES outreach_prospects(id) ON DELETE SET NULL,
    success         BOOLEAN DEFAULT TRUE,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_logs_task ON outreach_ai_logs (task, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_logs_prospect ON outreach_ai_logs (prospect_id) WHERE prospect_id IS NOT NULL;


-- =============================================
-- ROW LEVEL SECURITY
-- =============================================

ALTER TABLE linkedin_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_thread_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_snoozes ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_followups ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_snippets ENABLE ROW LEVEL SECURITY;
ALTER TABLE linkedin_contact_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_pillars ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_sequences ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_prospects ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_score_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_ai_logs ENABLE ROW LEVEL SECURITY;

-- Service role full access on all outreach tables
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN SELECT unnest(ARRAY[
        'linkedin_sessions', 'linkedin_threads', 'linkedin_messages',
        'linkedin_contacts', 'linkedin_labels', 'linkedin_thread_labels',
        'linkedin_snoozes', 'linkedin_followups', 'linkedin_snippets',
        'linkedin_contact_notes',
        'outreach_pillars', 'outreach_sequences', 'outreach_templates',
        'outreach_prospects', 'outreach_enrollments', 'outreach_messages',
        'outreach_approvals', 'outreach_score_history', 'outreach_ai_logs'
    ])
    LOOP
        EXECUTE format('CREATE POLICY "Allow read %I" ON %I FOR SELECT USING (true)', tbl, tbl);
        EXECUTE format('CREATE POLICY "Allow insert %I" ON %I FOR INSERT WITH CHECK (true)', tbl, tbl);
        EXECUTE format('CREATE POLICY "Allow update %I" ON %I FOR UPDATE USING (true)', tbl, tbl);
        EXECUTE format('CREATE POLICY "Allow delete %I" ON %I FOR DELETE USING (true)', tbl, tbl);
    END LOOP;
END $$;
