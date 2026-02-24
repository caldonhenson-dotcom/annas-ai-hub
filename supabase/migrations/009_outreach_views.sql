-- ============================================================================
-- Annas AI Hub — Migration 009: Outreach Analytics Views
-- ============================================================================
-- Materialised views for outreach dashboard metrics.
--
-- Views:
--   mv_outreach_summary       — Per-pillar outreach metrics
--   mv_approval_metrics       — Approval queue health metrics
--   mv_outreach_funnel        — Conversion funnel by pillar
--   mv_ai_usage_summary       — AI provider usage and cost
-- ============================================================================

-- ─── Per-Pillar Outreach Summary ────────────────────────────────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_outreach_summary AS
SELECT
    p.id                                       AS pillar_id,
    p.name                                     AS pillar_name,
    COUNT(DISTINCT pr.id)                      AS total_prospects,
    COUNT(DISTINCT pr.id) FILTER (WHERE pr.research_status = 'complete')
                                               AS researched_prospects,
    COUNT(DISTINCT e.id)                       AS total_enrollments,
    COUNT(DISTINCT e.id) FILTER (WHERE e.status = 'active')
                                               AS active_enrollments,
    COUNT(DISTINCT e.id) FILTER (WHERE e.status = 'completed')
                                               AS completed_enrollments,
    COUNT(DISTINCT e.id) FILTER (WHERE e.status = 'replied')
                                               AS replied_enrollments,
    COUNT(m.id) FILTER (WHERE m.direction = 'outbound' AND m.status = 'sent')
                                               AS messages_sent,
    COUNT(m.id) FILTER (WHERE m.direction = 'inbound')
                                               AS messages_received,
    ROUND(
        CASE
            WHEN COUNT(m.id) FILTER (WHERE m.direction = 'outbound' AND m.status = 'sent') > 0
            THEN COUNT(m.id) FILTER (WHERE m.direction = 'inbound')::numeric
                 / COUNT(m.id) FILTER (WHERE m.direction = 'outbound' AND m.status = 'sent')
            ELSE 0
        END, 3
    )                                          AS reply_rate,
    COUNT(DISTINCT pr.id) FILTER (WHERE pr.status = 'interested')
                                               AS interested_count,
    ROUND(
        CASE
            WHEN COUNT(DISTINCT pr.id) > 0
            THEN COUNT(DISTINCT pr.id) FILTER (WHERE pr.status = 'interested')::numeric
                 / COUNT(DISTINCT pr.id)
            ELSE 0
        END, 3
    )                                          AS conversion_rate,
    ROUND(AVG(pr.lead_score), 1)               AS avg_lead_score,
    ROUND(AVG(pr.fit_score), 1)                AS avg_fit_score,
    ROUND(AVG(pr.engagement_score), 1)         AS avg_engagement_score,
    NOW()                                      AS refreshed_at
FROM outreach_pillars p
LEFT JOIN outreach_prospects pr ON pr.pillar_id = p.id
LEFT JOIN outreach_enrollments e ON e.prospect_id = pr.id
LEFT JOIN outreach_messages m ON m.prospect_id = pr.id
GROUP BY p.id, p.name
ORDER BY p.name;

-- Unique index for REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_outreach_summary_pillar
    ON mv_outreach_summary (pillar_id);


-- ─── Approval Queue Metrics ────────────────────────────────────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_approval_metrics AS
SELECT
    COUNT(*) FILTER (WHERE a.status = 'pending')   AS pending_count,
    COUNT(*) FILTER (WHERE a.status = 'approved')  AS approved_count,
    COUNT(*) FILTER (WHERE a.status = 'rejected')  AS rejected_count,
    COUNT(*) FILTER (WHERE a.status = 'edited')    AS edited_count,
    COUNT(*) FILTER (WHERE a.status != 'pending')  AS total_reviewed,
    ROUND(
        AVG(
            CASE
                WHEN a.status != 'pending' AND a.reviewed_at IS NOT NULL AND a.submitted_at IS NOT NULL
                THEN EXTRACT(EPOCH FROM (a.reviewed_at - a.submitted_at)) / 60.0
            END
        ), 1
    )                                               AS avg_review_minutes,
    ROUND(
        CASE
            WHEN COUNT(*) > 0
            THEN COUNT(*) FILTER (WHERE a.status IN ('approved', 'edited'))::numeric / COUNT(*)
            ELSE 0
        END, 3
    )                                               AS approval_rate,
    -- Daily breakdown (last 30 days)
    COUNT(*) FILTER (
        WHERE a.submitted_at >= NOW() - INTERVAL '1 day'
    )                                               AS submitted_today,
    COUNT(*) FILTER (
        WHERE a.reviewed_at >= NOW() - INTERVAL '1 day'
        AND a.status != 'pending'
    )                                               AS reviewed_today,
    COUNT(*) FILTER (
        WHERE a.submitted_at >= NOW() - INTERVAL '7 days'
    )                                               AS submitted_7d,
    COUNT(*) FILTER (
        WHERE a.reviewed_at >= NOW() - INTERVAL '7 days'
        AND a.status != 'pending'
    )                                               AS reviewed_7d,
    NOW()                                           AS refreshed_at
FROM outreach_approvals a;

-- Single-row view, use constant index
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_approval_metrics
    ON mv_approval_metrics (refreshed_at);


-- ─── Outreach Funnel by Pillar ─────────────────────────────────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_outreach_funnel AS
SELECT
    p.id                                           AS pillar_id,
    p.name                                         AS pillar_name,
    COUNT(DISTINCT pr.id)                          AS total_prospects,
    COUNT(DISTINCT pr.id) FILTER (WHERE pr.research_status = 'complete')
                                                   AS researched,
    COUNT(DISTINCT e.prospect_id)                  AS enrolled,
    COUNT(DISTINCT m.prospect_id) FILTER (WHERE m.direction = 'outbound' AND m.status = 'sent')
                                                   AS contacted,
    COUNT(DISTINCT m.prospect_id) FILTER (WHERE m.direction = 'inbound')
                                                   AS replied,
    COUNT(DISTINCT pr.id) FILTER (WHERE pr.status = 'interested')
                                                   AS interested,
    COUNT(DISTINCT pr.id) FILTER (WHERE pr.status = 'converted')
                                                   AS converted,
    NOW()                                          AS refreshed_at
FROM outreach_pillars p
LEFT JOIN outreach_prospects pr ON pr.pillar_id = p.id
LEFT JOIN outreach_enrollments e ON e.prospect_id = pr.id
LEFT JOIN outreach_messages m ON m.prospect_id = pr.id
GROUP BY p.id, p.name
ORDER BY p.name;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_outreach_funnel_pillar
    ON mv_outreach_funnel (pillar_id);


-- ─── AI Usage Summary ──────────────────────────────────────────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_ai_usage_summary AS
SELECT
    l.provider,
    l.task,
    COUNT(*)                                       AS total_calls,
    COUNT(*) FILTER (WHERE l.success = true)       AS successful_calls,
    COUNT(*) FILTER (WHERE l.success = false)      AS failed_calls,
    ROUND(
        CASE WHEN COUNT(*) > 0
            THEN COUNT(*) FILTER (WHERE l.success = true)::numeric / COUNT(*)
            ELSE 0
        END, 3
    )                                              AS success_rate,
    SUM(COALESCE(l.input_tokens, 0))              AS total_input_tokens,
    SUM(COALESCE(l.output_tokens, 0))             AS total_output_tokens,
    SUM(COALESCE(l.input_tokens, 0) + COALESCE(l.output_tokens, 0))
                                                   AS total_tokens,
    ROUND(AVG(l.latency_ms), 0)                   AS avg_latency_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY l.latency_ms), 0)
                                                   AS p95_latency_ms,
    NOW()                                          AS refreshed_at
FROM outreach_ai_logs l
GROUP BY l.provider, l.task
ORDER BY l.provider, l.task;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_ai_usage_provider_task
    ON mv_ai_usage_summary (provider, task);


-- ─── Refresh function ──────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION refresh_outreach_views()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_outreach_summary;
    REFRESH MATERIALIZED VIEW mv_approval_metrics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_outreach_funnel;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_ai_usage_summary;
END;
$$;
