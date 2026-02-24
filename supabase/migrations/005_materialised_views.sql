-- ============================================
-- ANNAS AI HUB — Materialised Views
-- ============================================
-- Migration 005: Pre-computed views for fast dashboard queries
-- Refreshed after each pipeline run via pipeline_orchestrator
-- ============================================

-- =====================
-- PIPELINE SUMMARY
-- =====================
-- Aggregated deal counts, values, and probabilities by stage

CREATE MATERIALIZED VIEW IF NOT EXISTS v_pipeline_summary AS
SELECT
    d.stage,
    COALESCE(ps.label, d.stage_label, d.stage)  AS stage_label,
    COALESCE(ps.display_order, 0)                AS display_order,
    COUNT(*)                                      AS deal_count,
    COALESCE(SUM(d.amount), 0)                   AS total_value,
    COALESCE(SUM(d.weighted_amount), 0)          AS weighted_value,
    ROUND(AVG(d.amount), 2)                      AS avg_deal_size,
    ROUND(AVG(d.probability), 1)                 AS avg_probability,
    ROUND(AVG(d.days_in_stage), 1)               AS avg_days_in_stage,
    COUNT(*) FILTER (WHERE d.is_closed_won)       AS won_count,
    COUNT(*) FILTER (WHERE d.is_closed AND NOT d.is_closed_won) AS lost_count,
    COUNT(*) FILTER (WHERE NOT d.is_closed)       AS open_count
FROM deals d
LEFT JOIN pipeline_stages ps ON d.stage = ps.id
GROUP BY d.stage, COALESCE(ps.label, d.stage_label, d.stage), COALESCE(ps.display_order, 0)
ORDER BY display_order;

CREATE UNIQUE INDEX IF NOT EXISTS idx_v_pipeline_summary_stage
    ON v_pipeline_summary (stage);


-- =====================
-- ACTIVITY BY REP
-- =====================
-- Activity counts per owner, broken down by type

CREATE MATERIALIZED VIEW IF NOT EXISTS v_activity_by_rep AS
SELECT
    a.owner_id,
    a.owner_name,
    COUNT(*)                                          AS total_activities,
    COUNT(*) FILTER (WHERE a.type = 'call')           AS calls,
    COUNT(*) FILTER (WHERE a.type = 'email')          AS emails,
    COUNT(*) FILTER (WHERE a.type = 'meeting')        AS meetings,
    COUNT(*) FILTER (WHERE a.type = 'task')           AS tasks,
    COUNT(*) FILTER (WHERE a.type = 'note')           AS notes,
    COUNT(*) FILTER (WHERE a.activity_date >= NOW() - INTERVAL '7 days')  AS last_7d,
    COUNT(*) FILTER (WHERE a.activity_date >= NOW() - INTERVAL '30 days') AS last_30d,
    ROUND(AVG(a.duration_ms) FILTER (WHERE a.type = 'call' AND a.duration_ms > 0), 0)
                                                      AS avg_call_duration_ms,
    MIN(a.activity_date)                              AS earliest_activity,
    MAX(a.activity_date)                              AS latest_activity
FROM activities a
WHERE a.owner_id IS NOT NULL
GROUP BY a.owner_id, a.owner_name
ORDER BY total_activities DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_v_activity_by_rep_owner
    ON v_activity_by_rep (owner_id);


-- =====================
-- DEAL VELOCITY
-- =====================
-- Sales cycle speed and conversion metrics by pipeline and owner

CREATE MATERIALIZED VIEW IF NOT EXISTS v_deal_velocity AS
SELECT
    d.pipeline,
    d.owner_id,
    d.owner_name,
    COUNT(*) FILTER (WHERE d.is_closed_won)     AS won_deals,
    COUNT(*) FILTER (WHERE d.is_closed AND NOT d.is_closed_won) AS lost_deals,
    COUNT(*) FILTER (WHERE NOT d.is_closed)     AS open_deals,
    CASE
        WHEN COUNT(*) FILTER (WHERE d.is_closed) > 0
        THEN ROUND(
            COUNT(*) FILTER (WHERE d.is_closed_won)::NUMERIC /
            COUNT(*) FILTER (WHERE d.is_closed)::NUMERIC, 4
        )
        ELSE NULL
    END                                          AS win_rate,
    ROUND(AVG(d.amount) FILTER (WHERE d.is_closed_won), 2)
                                                 AS avg_won_deal_size,
    ROUND(AVG(
        EXTRACT(EPOCH FROM (d.last_modified - d.create_date)) / 86400
    ) FILTER (WHERE d.is_closed_won AND d.create_date IS NOT NULL), 1)
                                                 AS avg_cycle_days,
    COALESCE(SUM(d.amount) FILTER (WHERE d.is_closed_won), 0)
                                                 AS total_won_revenue,
    COALESCE(SUM(d.amount) FILTER (WHERE NOT d.is_closed), 0)
                                                 AS total_open_pipeline,
    COALESCE(SUM(d.weighted_amount) FILTER (WHERE NOT d.is_closed), 0)
                                                 AS weighted_open_pipeline,
    -- Pipeline velocity = (deals * avg_value * win_rate) / avg_cycle_days
    CASE
        WHEN AVG(
            EXTRACT(EPOCH FROM (d.last_modified - d.create_date)) / 86400
        ) FILTER (WHERE d.is_closed_won AND d.create_date IS NOT NULL) > 0
        THEN ROUND(
            (COUNT(*) FILTER (WHERE NOT d.is_closed)
             * COALESCE(AVG(d.amount) FILTER (WHERE d.is_closed_won), 0)
             * COALESCE(
                COUNT(*) FILTER (WHERE d.is_closed_won)::NUMERIC /
                NULLIF(COUNT(*) FILTER (WHERE d.is_closed), 0), 0
               )
            ) / AVG(
                EXTRACT(EPOCH FROM (d.last_modified - d.create_date)) / 86400
            ) FILTER (WHERE d.is_closed_won AND d.create_date IS NOT NULL),
        2)
        ELSE 0
    END                                          AS pipeline_velocity
FROM deals d
GROUP BY d.pipeline, d.owner_id, d.owner_name
ORDER BY total_won_revenue DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_v_deal_velocity_owner_pipeline
    ON v_deal_velocity (pipeline, owner_id);


-- =====================
-- WEEKLY KPIs
-- =====================
-- Rolling KPIs for the last 7 and 30 days, plus current pipeline state

CREATE MATERIALIZED VIEW IF NOT EXISTS v_weekly_kpis AS
SELECT
    NOW()                                            AS computed_at,

    -- Lead metrics
    (SELECT COUNT(*) FROM contacts
     WHERE create_date >= NOW() - INTERVAL '7 days')  AS new_contacts_7d,
    (SELECT COUNT(*) FROM contacts
     WHERE create_date >= NOW() - INTERVAL '30 days') AS new_contacts_30d,
    (SELECT COUNT(*) FROM contacts
     WHERE lifecycle_stage = 'marketingqualifiedlead'
       AND mql_date >= NOW() - INTERVAL '30 days')    AS new_mqls_30d,
    (SELECT COUNT(*) FROM contacts
     WHERE lifecycle_stage = 'salesqualifiedlead'
       AND sql_date >= NOW() - INTERVAL '30 days')    AS new_sqls_30d,

    -- Deal metrics
    (SELECT COUNT(*) FROM deals
     WHERE create_date >= NOW() - INTERVAL '7 days')  AS deals_created_7d,
    (SELECT COUNT(*) FROM deals
     WHERE create_date >= NOW() - INTERVAL '30 days') AS deals_created_30d,
    (SELECT COUNT(*) FROM deals
     WHERE is_closed_won
       AND last_modified >= NOW() - INTERVAL '7 days') AS deals_won_7d,
    (SELECT COUNT(*) FROM deals
     WHERE is_closed_won
       AND last_modified >= NOW() - INTERVAL '30 days') AS deals_won_30d,
    (SELECT COALESCE(SUM(amount), 0) FROM deals
     WHERE is_closed_won
       AND last_modified >= NOW() - INTERVAL '30 days') AS revenue_won_30d,

    -- Pipeline state
    (SELECT COUNT(*) FROM deals WHERE NOT is_closed)   AS open_deals,
    (SELECT COALESCE(SUM(amount), 0) FROM deals
     WHERE NOT is_closed)                              AS total_pipeline_value,
    (SELECT COALESCE(SUM(weighted_amount), 0) FROM deals
     WHERE NOT is_closed)                              AS weighted_pipeline_value,

    -- Activity metrics
    (SELECT COUNT(*) FROM activities
     WHERE activity_date >= NOW() - INTERVAL '7 days')  AS activities_7d,
    (SELECT COUNT(*) FROM activities
     WHERE activity_date >= NOW() - INTERVAL '30 days') AS activities_30d,

    -- Win rate (last 90 days closed deals)
    (SELECT CASE
        WHEN COUNT(*) FILTER (WHERE is_closed) > 0
        THEN ROUND(
            COUNT(*) FILTER (WHERE is_closed_won)::NUMERIC /
            COUNT(*) FILTER (WHERE is_closed)::NUMERIC, 4)
        ELSE NULL
     END
     FROM deals
     WHERE is_closed AND last_modified >= NOW() - INTERVAL '90 days')
                                                        AS win_rate_90d,

    -- Average deal size (closed won last 90d)
    (SELECT ROUND(AVG(amount), 2) FROM deals
     WHERE is_closed_won
       AND last_modified >= NOW() - INTERVAL '90 days') AS avg_deal_size_90d,

    -- Average sales cycle (closed won last 90d)
    (SELECT ROUND(AVG(
        EXTRACT(EPOCH FROM (last_modified - create_date)) / 86400
     ), 1) FROM deals
     WHERE is_closed_won
       AND create_date IS NOT NULL
       AND last_modified >= NOW() - INTERVAL '90 days') AS avg_cycle_days_90d,

    -- Monday M&A
    (SELECT COUNT(*) FROM monday_projects
     WHERE is_active)                                   AS active_ma_projects,
    (SELECT COALESCE(SUM(value), 0) FROM monday_projects
     WHERE is_active)                                   AS active_ma_value;

-- v_weekly_kpis is a single-row view, unique on computed_at
CREATE UNIQUE INDEX IF NOT EXISTS idx_v_weekly_kpis_computed
    ON v_weekly_kpis (computed_at);


-- =====================
-- LEAD FUNNEL
-- =====================
-- Lifecycle stage progression counts

CREATE MATERIALIZED VIEW IF NOT EXISTS v_lead_funnel AS
SELECT
    lifecycle_stage,
    COUNT(*)                                           AS total_count,
    COUNT(*) FILTER (WHERE create_date >= NOW() - INTERVAL '30 days')
                                                       AS new_30d,
    COUNT(*) FILTER (WHERE create_date >= NOW() - INTERVAL '7 days')
                                                       AS new_7d
FROM contacts
WHERE lifecycle_stage IS NOT NULL
GROUP BY lifecycle_stage
ORDER BY
    CASE lifecycle_stage
        WHEN 'subscriber'              THEN 1
        WHEN 'lead'                    THEN 2
        WHEN 'marketingqualifiedlead'  THEN 3
        WHEN 'salesqualifiedlead'      THEN 4
        WHEN 'opportunity'             THEN 5
        WHEN 'customer'                THEN 6
        WHEN 'evangelist'              THEN 7
        ELSE 99
    END;

CREATE UNIQUE INDEX IF NOT EXISTS idx_v_lead_funnel_stage
    ON v_lead_funnel (lifecycle_stage);


-- =====================
-- M&A PIPELINE
-- =====================
-- Monday.com M&A project summary by stage

CREATE MATERIALIZED VIEW IF NOT EXISTS v_ma_pipeline AS
SELECT
    mp.stage,
    COUNT(*)                                           AS project_count,
    COUNT(*) FILTER (WHERE mp.is_active)               AS active_count,
    COALESCE(SUM(mp.value), 0)                        AS total_value,
    COALESCE(SUM(mp.value) FILTER (WHERE mp.is_active), 0)
                                                       AS active_value,
    ROUND(AVG(mp.subitems_count), 1)                  AS avg_subitems,
    ROUND(AVG(
        CASE WHEN mp.subitems_count > 0
        THEN mp.subitems_complete::NUMERIC / mp.subitems_count * 100
        ELSE 0 END
    ), 1)                                              AS avg_completion_pct
FROM monday_projects mp
GROUP BY mp.stage
ORDER BY total_value DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_v_ma_pipeline_stage
    ON v_ma_pipeline (stage);


-- =====================
-- HELPER: Refresh all views
-- =====================
-- Called by pipeline_orchestrator after analysis phase

CREATE OR REPLACE FUNCTION refresh_all_views()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_pipeline_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_activity_by_rep;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_deal_velocity;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_weekly_kpis;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_lead_funnel;
    REFRESH MATERIALIZED VIEW CONCURRENTLY v_ma_pipeline;
END;
$$ LANGUAGE plpgsql;
