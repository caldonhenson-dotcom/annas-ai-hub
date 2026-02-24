-- ============================================
-- ANNAS AI HUB — Metric Definitions
-- ============================================
-- Migration 006: Queryable metric registry
-- Used by the AI engine to understand available metrics,
-- their formulas, and how to compute them from the schema.
-- ============================================

CREATE TABLE IF NOT EXISTS metric_definitions (
    name            TEXT PRIMARY KEY,
    formula_sql     TEXT NOT NULL,           -- SQL snippet or full query
    description     TEXT NOT NULL,
    category        TEXT NOT NULL,           -- pipeline | activity | lead | forecast | ma | company
    unit            TEXT NOT NULL,           -- currency | percent | count | days | ratio
    display_name    TEXT,                    -- human-friendly label
    source_table    TEXT,                    -- primary table this metric queries
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metric_defs_category ON metric_definitions (category);

ALTER TABLE metric_definitions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read metric_definitions"
    ON metric_definitions FOR SELECT USING (true);
CREATE POLICY "Allow service write metric_definitions"
    ON metric_definitions FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow service update metric_definitions"
    ON metric_definitions FOR UPDATE USING (true);

-- =====================
-- PIPELINE METRICS
-- =====================

INSERT INTO metric_definitions (name, formula_sql, description, category, unit, display_name, source_table) VALUES

('total_pipeline_value',
 'SELECT COALESCE(SUM(amount), 0) AS value FROM deals WHERE NOT is_closed',
 'Total value of all open (non-closed) deals in the pipeline',
 'pipeline', 'currency', 'Total Pipeline Value', 'deals'),

('weighted_pipeline_value',
 'SELECT COALESCE(SUM(weighted_amount), 0) AS value FROM deals WHERE NOT is_closed',
 'Sum of deal amounts weighted by stage probability',
 'pipeline', 'currency', 'Weighted Pipeline', 'deals'),

('open_deals_count',
 'SELECT COUNT(*) AS value FROM deals WHERE NOT is_closed',
 'Number of deals currently open in the pipeline',
 'pipeline', 'count', 'Open Deals', 'deals'),

('won_deals_count',
 'SELECT COUNT(*) AS value FROM deals WHERE is_closed_won',
 'Total number of closed-won deals',
 'pipeline', 'count', 'Won Deals', 'deals'),

('lost_deals_count',
 'SELECT COUNT(*) AS value FROM deals WHERE is_closed AND NOT is_closed_won',
 'Total number of closed-lost deals',
 'pipeline', 'count', 'Lost Deals', 'deals'),

('win_rate',
 'SELECT ROUND(COUNT(*) FILTER (WHERE is_closed_won)::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE is_closed), 0), 4) AS value FROM deals',
 'Ratio of won deals to total closed deals (won + lost)',
 'pipeline', 'percent', 'Win Rate', 'deals'),

('avg_deal_size',
 'SELECT ROUND(AVG(amount), 2) AS value FROM deals WHERE is_closed_won',
 'Average monetary value of closed-won deals',
 'pipeline', 'currency', 'Avg Deal Size', 'deals'),

('avg_sales_cycle_days',
 'SELECT ROUND(AVG(EXTRACT(EPOCH FROM (last_modified - create_date)) / 86400), 1) AS value FROM deals WHERE is_closed_won AND create_date IS NOT NULL',
 'Average number of days from deal creation to close-won',
 'pipeline', 'days', 'Avg Sales Cycle', 'deals'),

('pipeline_velocity',
 'SELECT ROUND((COUNT(*) FILTER (WHERE NOT is_closed) * COALESCE(AVG(amount) FILTER (WHERE is_closed_won), 0) * COALESCE(COUNT(*) FILTER (WHERE is_closed_won)::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE is_closed), 0), 0)) / NULLIF(AVG(EXTRACT(EPOCH FROM (last_modified - create_date)) / 86400) FILTER (WHERE is_closed_won AND create_date IS NOT NULL), 0), 2) AS value FROM deals',
 'Pipeline velocity = (open deals x avg deal size x win rate) / avg cycle days',
 'pipeline', 'currency', 'Pipeline Velocity', 'deals'),

('pipeline_coverage',
 'SELECT ROUND(COALESCE(SUM(weighted_amount) FILTER (WHERE NOT is_closed), 0) / NULLIF(SUM(amount) FILTER (WHERE is_closed_won AND last_modified >= NOW() - INTERVAL ''90 days''), 1), 2) AS value FROM deals',
 'Ratio of weighted pipeline to recent revenue — indicates forecast confidence',
 'pipeline', 'ratio', 'Pipeline Coverage', 'deals'),

('deals_by_stage',
 'SELECT stage, COALESCE(stage_label, stage) AS label, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total_value FROM deals WHERE NOT is_closed GROUP BY stage, stage_label ORDER BY COUNT(*) DESC',
 'Breakdown of open deals grouped by pipeline stage',
 'pipeline', 'count', 'Deals by Stage', 'deals'),

('deals_won_30d',
 'SELECT COUNT(*) AS value FROM deals WHERE is_closed_won AND last_modified >= NOW() - INTERVAL ''30 days''',
 'Number of deals closed-won in the last 30 days',
 'pipeline', 'count', 'Won Last 30d', 'deals'),

('revenue_won_30d',
 'SELECT COALESCE(SUM(amount), 0) AS value FROM deals WHERE is_closed_won AND last_modified >= NOW() - INTERVAL ''30 days''',
 'Revenue from deals closed-won in the last 30 days',
 'pipeline', 'currency', 'Revenue Won 30d', 'deals')

ON CONFLICT (name) DO UPDATE SET
    formula_sql = EXCLUDED.formula_sql,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    unit = EXCLUDED.unit,
    display_name = EXCLUDED.display_name,
    source_table = EXCLUDED.source_table;


-- =====================
-- ACTIVITY METRICS
-- =====================

INSERT INTO metric_definitions (name, formula_sql, description, category, unit, display_name, source_table) VALUES

('total_activities',
 'SELECT COUNT(*) AS value FROM activities',
 'Total number of logged activities (calls, emails, meetings, tasks, notes)',
 'activity', 'count', 'Total Activities', 'activities'),

('activities_by_type',
 'SELECT type, COUNT(*) AS count FROM activities GROUP BY type ORDER BY count DESC',
 'Activity counts broken down by type (call, email, meeting, task, note)',
 'activity', 'count', 'Activities by Type', 'activities'),

('activities_7d',
 'SELECT COUNT(*) AS value FROM activities WHERE activity_date >= NOW() - INTERVAL ''7 days''',
 'Number of activities logged in the last 7 days',
 'activity', 'count', 'Activities Last 7d', 'activities'),

('activities_30d',
 'SELECT COUNT(*) AS value FROM activities WHERE activity_date >= NOW() - INTERVAL ''30 days''',
 'Number of activities logged in the last 30 days',
 'activity', 'count', 'Activities Last 30d', 'activities'),

('activities_by_rep',
 'SELECT owner_name, total_activities, calls, emails, meetings, tasks, notes FROM v_activity_by_rep ORDER BY total_activities DESC',
 'Per-rep breakdown of all activity types with totals',
 'activity', 'count', 'Activity by Rep', 'v_activity_by_rep'),

('avg_call_duration',
 'SELECT ROUND(AVG(duration_ms) / 1000, 0) AS value_seconds FROM activities WHERE type = ''call'' AND duration_ms > 0',
 'Average call duration in seconds',
 'activity', 'count', 'Avg Call Duration', 'activities')

ON CONFLICT (name) DO UPDATE SET
    formula_sql = EXCLUDED.formula_sql,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    unit = EXCLUDED.unit,
    display_name = EXCLUDED.display_name,
    source_table = EXCLUDED.source_table;


-- =====================
-- LEAD METRICS
-- =====================

INSERT INTO metric_definitions (name, formula_sql, description, category, unit, display_name, source_table) VALUES

('total_contacts',
 'SELECT COUNT(*) AS value FROM contacts',
 'Total number of contacts in the CRM',
 'lead', 'count', 'Total Contacts', 'contacts'),

('new_contacts_30d',
 'SELECT COUNT(*) AS value FROM contacts WHERE create_date >= NOW() - INTERVAL ''30 days''',
 'Contacts created in the last 30 days',
 'lead', 'count', 'New Contacts 30d', 'contacts'),

('contacts_by_lifecycle',
 'SELECT lifecycle_stage, COUNT(*) AS count FROM contacts WHERE lifecycle_stage IS NOT NULL GROUP BY lifecycle_stage ORDER BY count DESC',
 'Contact counts grouped by lifecycle stage (subscriber, lead, MQL, SQL, opportunity, customer)',
 'lead', 'count', 'Contacts by Lifecycle', 'contacts'),

('mql_count',
 'SELECT COUNT(*) AS value FROM contacts WHERE lifecycle_stage = ''marketingqualifiedlead''',
 'Number of contacts at the Marketing Qualified Lead stage',
 'lead', 'count', 'MQLs', 'contacts'),

('sql_count',
 'SELECT COUNT(*) AS value FROM contacts WHERE lifecycle_stage = ''salesqualifiedlead''',
 'Number of contacts at the Sales Qualified Lead stage',
 'lead', 'count', 'SQLs', 'contacts'),

('lead_to_mql_rate',
 'SELECT ROUND(COUNT(*) FILTER (WHERE lifecycle_stage = ''marketingqualifiedlead'')::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE lifecycle_stage = ''lead''), 0), 4) AS value FROM contacts',
 'Conversion rate from Lead to Marketing Qualified Lead',
 'lead', 'percent', 'Lead→MQL Rate', 'contacts'),

('contacts_by_source',
 'SELECT source, COUNT(*) AS count FROM contacts WHERE source IS NOT NULL GROUP BY source ORDER BY count DESC',
 'Contact counts grouped by original traffic source',
 'lead', 'count', 'Contacts by Source', 'contacts'),

('new_mqls_30d',
 'SELECT COUNT(*) AS value FROM contacts WHERE mql_date >= NOW() - INTERVAL ''30 days''',
 'Contacts who reached MQL stage in the last 30 days',
 'lead', 'count', 'New MQLs 30d', 'contacts'),

('new_sqls_30d',
 'SELECT COUNT(*) AS value FROM contacts WHERE sql_date >= NOW() - INTERVAL ''30 days''',
 'Contacts who reached SQL stage in the last 30 days',
 'lead', 'count', 'New SQLs 30d', 'contacts')

ON CONFLICT (name) DO UPDATE SET
    formula_sql = EXCLUDED.formula_sql,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    unit = EXCLUDED.unit,
    display_name = EXCLUDED.display_name,
    source_table = EXCLUDED.source_table;


-- =====================
-- FORECAST METRICS
-- =====================

INSERT INTO metric_definitions (name, formula_sql, description, category, unit, display_name, source_table) VALUES

('forecast_by_close_month',
 'SELECT TO_CHAR(close_date, ''YYYY-MM'') AS month, COUNT(*) AS deal_count, COALESCE(SUM(amount), 0) AS total_value, COALESCE(SUM(weighted_amount), 0) AS weighted_value FROM deals WHERE NOT is_closed AND close_date IS NOT NULL GROUP BY TO_CHAR(close_date, ''YYYY-MM'') ORDER BY month',
 'Open deals grouped by expected close month with total and weighted values',
 'forecast', 'currency', 'Forecast by Month', 'deals'),

('revenue_won_by_month',
 'SELECT TO_CHAR(last_modified, ''YYYY-MM'') AS month, COALESCE(SUM(amount), 0) AS value FROM deals WHERE is_closed_won GROUP BY TO_CHAR(last_modified, ''YYYY-MM'') ORDER BY month',
 'Monthly revenue from closed-won deals',
 'forecast', 'currency', 'Revenue by Month', 'deals'),

('rep_performance',
 'SELECT owner_id, owner_name, won_deals, lost_deals, open_deals, win_rate, avg_won_deal_size, avg_cycle_days, total_won_revenue, total_open_pipeline FROM v_deal_velocity ORDER BY total_won_revenue DESC',
 'Per-rep sales performance: wins, losses, win rate, deal size, cycle time, revenue',
 'forecast', 'currency', 'Rep Performance', 'v_deal_velocity')

ON CONFLICT (name) DO UPDATE SET
    formula_sql = EXCLUDED.formula_sql,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    unit = EXCLUDED.unit,
    display_name = EXCLUDED.display_name,
    source_table = EXCLUDED.source_table;


-- =====================
-- M&A METRICS
-- =====================

INSERT INTO metric_definitions (name, formula_sql, description, category, unit, display_name, source_table) VALUES

('active_ma_projects',
 'SELECT COUNT(*) AS value FROM monday_projects WHERE is_active',
 'Number of active M&A projects tracked in Monday.com',
 'ma', 'count', 'Active M&A Projects', 'monday_projects'),

('total_ma_value',
 'SELECT COALESCE(SUM(value), 0) AS value FROM monday_projects WHERE is_active',
 'Total deal value of active M&A projects',
 'ma', 'currency', 'Active M&A Value', 'monday_projects'),

('ma_by_stage',
 'SELECT stage, COUNT(*) AS count, COALESCE(SUM(value), 0) AS total_value FROM monday_projects WHERE is_active GROUP BY stage ORDER BY total_value DESC',
 'Active M&A projects grouped by pipeline stage with values',
 'ma', 'count', 'M&A by Stage', 'monday_projects'),

('ma_by_owner',
 'SELECT owner, COUNT(*) AS count, COALESCE(SUM(value), 0) AS total_value FROM monday_projects WHERE is_active GROUP BY owner ORDER BY total_value DESC',
 'Active M&A projects grouped by owner with values',
 'ma', 'count', 'M&A by Owner', 'monday_projects'),

('avg_ic_score',
 'SELECT ROUND(AVG(total_score), 2) AS value FROM monday_ic_scores WHERE total_score IS NOT NULL',
 'Average Investment Committee score across all scored items',
 'ma', 'count', 'Avg IC Score', 'monday_ic_scores')

ON CONFLICT (name) DO UPDATE SET
    formula_sql = EXCLUDED.formula_sql,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    unit = EXCLUDED.unit,
    display_name = EXCLUDED.display_name,
    source_table = EXCLUDED.source_table;


-- =====================
-- COMPANY METRICS
-- =====================

INSERT INTO metric_definitions (name, formula_sql, description, category, unit, display_name, source_table) VALUES

('total_companies',
 'SELECT COUNT(*) AS value FROM companies',
 'Total number of companies in the CRM',
 'company', 'count', 'Total Companies', 'companies'),

('companies_by_industry',
 'SELECT industry, COUNT(*) AS count FROM companies WHERE industry IS NOT NULL GROUP BY industry ORDER BY count DESC',
 'Companies grouped by industry vertical',
 'company', 'count', 'Companies by Industry', 'companies'),

('companies_with_revenue',
 'SELECT COUNT(*) AS value FROM companies WHERE total_revenue > 0',
 'Number of companies with recorded revenue',
 'company', 'count', 'Companies with Revenue', 'companies')

ON CONFLICT (name) DO UPDATE SET
    formula_sql = EXCLUDED.formula_sql,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    unit = EXCLUDED.unit,
    display_name = EXCLUDED.display_name,
    source_table = EXCLUDED.source_table;
