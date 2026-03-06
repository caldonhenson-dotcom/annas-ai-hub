/**
 * HubSpot sync configuration — property lists and column mappings.
 * Ported from Python fetch_hubspot.py CONTACT_PROPS, DEAL_PROPS, COMPANY_PROPS.
 */

export const HUBSPOT_BASE = "https://api.hubspot.com";
export const PAGE_LIMIT = 100;

export const CONTACT_PROPS = [
  "firstname", "lastname", "email", "phone", "company",
  "lifecyclestage", "hs_lead_status", "hubspot_owner_id",
  "createdate", "lastmodifieddate",
  "hs_analytics_source", "hs_analytics_num_page_views",
  "hs_analytics_num_visits", "num_associated_deals",
  "hs_lifecyclestage_lead_date",
  "hs_lifecyclestage_marketingqualifiedlead_date",
  "hs_lifecyclestage_salesqualifiedlead_date",
  "hs_lifecyclestage_opportunity_date",
  "hs_lifecyclestage_customer_date",
];

export const DEAL_PROPS = [
  "dealname", "dealstage", "pipeline", "amount",
  "closedate", "createdate", "hubspot_owner_id",
  "hs_deal_stage_probability", "hs_is_closed_won",
  "hs_is_closed", "hs_analytics_source", "dealtype",
  "hs_forecast_amount", "notes_last_updated",
  "closed_lost_reason", "closed_won_reason",
];

export const COMPANY_PROPS = [
  "name", "domain", "industry", "annualrevenue",
  "numberofemployees", "lifecyclestage", "hubspot_owner_id",
  "createdate", "num_associated_contacts", "num_associated_deals",
  "hs_analytics_source", "total_revenue",
];

/** Map a HubSpot contact record to the contacts table row. */
export function mapContact(r: Record<string, unknown>): Record<string, unknown> {
  const p = (r.properties ?? {}) as Record<string, string | null>;
  return {
    id: String(r.id),
    email: p.email,
    first_name: p.firstname,
    last_name: p.lastname,
    company: p.company,
    phone: p.phone,
    lifecycle_stage: p.lifecyclestage,
    lead_status: p.hs_lead_status,
    source: p.hs_analytics_source,
    owner_id: p.hubspot_owner_id,
    page_views: p.hs_analytics_num_page_views ? Number(p.hs_analytics_num_page_views) : null,
    visits: p.hs_analytics_num_visits ? Number(p.hs_analytics_num_visits) : null,
    num_deals: p.num_associated_deals ? Number(p.num_associated_deals) : null,
    create_date: p.createdate,
    last_modified: p.lastmodifieddate,
    lead_date: p.hs_lifecyclestage_lead_date,
    mql_date: p.hs_lifecyclestage_marketingqualifiedlead_date,
    sql_date: p.hs_lifecyclestage_salesqualifiedlead_date,
    opportunity_date: p.hs_lifecyclestage_opportunity_date,
    customer_date: p.hs_lifecyclestage_customer_date,
    fetched_at: new Date().toISOString(),
  };
}

/** Map a HubSpot deal record to the deals table row. */
export function mapDeal(r: Record<string, unknown>): Record<string, unknown> {
  const p = (r.properties ?? {}) as Record<string, string | null>;
  const amount = p.amount ? Number(p.amount) : null;
  const prob = p.hs_deal_stage_probability ? Number(p.hs_deal_stage_probability) : null;
  return {
    id: String(r.id),
    name: p.dealname,
    stage: p.dealstage,
    pipeline: p.pipeline,
    amount,
    weighted_amount: amount && prob ? amount * prob / 100 : null,
    probability: prob,
    owner_id: p.hubspot_owner_id,
    close_date: p.closedate?.substring(0, 10) ?? null,
    create_date: p.createdate,
    last_modified: p.lastmodifieddate ?? p.createdate,
    is_closed_won: p.hs_is_closed_won === "true",
    is_closed: p.hs_is_closed === "true",
    source: p.hs_analytics_source,
    deal_type: p.dealtype,
    forecast_amount: p.hs_forecast_amount ? Number(p.hs_forecast_amount) : null,
    closed_won_reason: p.closed_won_reason,
    closed_lost_reason: p.closed_lost_reason,
    fetched_at: new Date().toISOString(),
  };
}

/** Map a HubSpot company record to the companies table row. */
export function mapCompany(r: Record<string, unknown>): Record<string, unknown> {
  const p = (r.properties ?? {}) as Record<string, string | null>;
  return {
    id: String(r.id),
    name: p.name,
    domain: p.domain,
    industry: p.industry,
    annual_revenue: p.annualrevenue ? Number(p.annualrevenue) : null,
    num_employees: p.numberofemployees ? Number(p.numberofemployees) : null,
    lifecycle_stage: p.lifecyclestage,
    owner_id: p.hubspot_owner_id,
    create_date: p.createdate,
    num_contacts: p.num_associated_contacts ? Number(p.num_associated_contacts) : null,
    num_deals: p.num_associated_deals ? Number(p.num_associated_deals) : null,
    source: p.hs_analytics_source,
    total_revenue: p.total_revenue ? Number(p.total_revenue) : null,
    fetched_at: new Date().toISOString(),
  };
}
