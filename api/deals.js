/**
 * GET /api/deals — HubSpot deals with Supabase cache
 * ==================================================
 * 1. Check Supabase cache (hubspot_deals_cache table, 15 min TTL)
 * 2. If stale, fetch all deals from HubSpot Search API
 * 3. Upsert to Supabase, return fresh data
 * 4. Fallback: return cached data even if stale on HubSpot errors
 */
const { setCors, rateLimit, supabaseUrl, supabaseHeaders, errorResponse } = require('./_helpers');

const HUBSPOT_API = 'https://api.hubapi.com';
const CACHE_TTL_MS = 15 * 60 * 1000; // 15 minutes
const CACHE_TABLE = 'hubspot_deals_cache';

const STAGE_MAP = {
    '2729430207': 'Qualified Lead',
    'qualifiedtobuy': 'Engaged',
    'appointmentscheduled': 'First Meeting Booked',
    '2378307822': 'Second Meeting Booked',
    'presentationscheduled': 'Proposal Shared',
    'decisionmakerboughtin': 'Decision Maker Bought-In',
    'contractsent': 'Contract Sent',
    'closedwon': 'Closed Won',
    'closedlost': 'Closed Lost',
    '2729430208': 'Disqualified',
    '4998113487': 'Re-engage'
};

const OWNER_MAP = {
    '29203010': 'Daniel Arques', '29390276': 'Rose Galbally',
    '29436019': 'James Carberry', '30922676': 'Skye Whitton',
    '75999979': 'Josh Elliott', '76000029': 'Paul Miller',
    '76000036': 'Vanessa Hope', '77510527': 'Anna Younger',
    '77549134': 'Kirill Kopica', '723080656': 'Joseph Gawthrop',
    '723147244': 'Zara Hill', '753930692': 'Caldon Henson',
    '787115722': 'Danny Quinn', '787901637': 'Paul Gedman',
    '787901638': 'Lonya Sherief', '787901639': 'Rory Codd',
    '787901640': 'Kitty Wang', '787901641': 'Carsten Cramer',
    '787901642': 'Sean Addison-Abe', '787901644': 'Alice Oakford',
    '787901645': 'Caspar Waters', '787901646': 'Anna Graham',
    '787901647': 'Les Yates', '787901648': 'Peter Hanly'
};

const DEAL_PROPERTIES = [
    'dealname', 'dealstage', 'amount', 'createdate', 'closedate',
    'hubspot_owner_id', 'product', 'ecomplete_source',
    'closed_lost_reason', 'closed_won_reason',
    'hs_projected_amount', 'hs_is_closed_won', 'hs_is_closed_lost',
    'hs_deal_stage_probability', 'notes_last_contacted', 'notes_last_updated',
    'hs_lastmodifieddate'
];

// ── HubSpot fetch (paginated) ──
async function fetchAllDeals() {
    const token = process.env.HUBSPOT_API_KEY;
    if (!token) throw new Error('HUBSPOT_API_KEY not configured');

    let allDeals = [];
    let after = 0;
    let hasMore = true;

    while (hasMore) {
        const body = {
            properties: DEAL_PROPERTIES,
            sorts: [{ propertyName: 'createdate', direction: 'DESCENDING' }],
            limit: 100,
            after: after
        };

        const resp = await fetch(HUBSPOT_API + '/crm/v3/objects/deals/search', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(body)
        });

        if (!resp.ok) {
            const text = await resp.text();
            throw new Error('HubSpot API ' + resp.status + ': ' + text.slice(0, 200));
        }

        const data = await resp.json();
        allDeals = allDeals.concat(data.results || []);

        if (data.paging && data.paging.next && data.paging.next.after) {
            after = data.paging.next.after;
        } else {
            hasMore = false;
        }
    }

    return allDeals;
}

// ── Transform HubSpot deal to clean format ──
function transformDeal(d) {
    const p = d.properties || {};
    return {
        id: d.id,
        name: p.dealname || '',
        stage: STAGE_MAP[p.dealstage] || p.dealstage || '',
        stageKey: p.dealstage || '',
        amount: parseFloat(p.amount || '0') || 0,
        weighted: parseFloat(p.hs_projected_amount || '0') || 0,
        probability: parseFloat(p.hs_deal_stage_probability || '0') || 0,
        created: p.createdate || '',
        closed: p.closedate || '',
        ownerId: p.hubspot_owner_id || '',
        owner: OWNER_MAP[p.hubspot_owner_id] || 'Unknown',
        product: p.product || '',
        source: p.ecomplete_source || '',
        isWon: p.hs_is_closed_won === 'true',
        isLost: p.hs_is_closed_lost === 'true',
        lostReason: p.closed_lost_reason || '',
        wonReason: p.closed_won_reason || '',
        lastContacted: p.notes_last_contacted || '',
        lastActivity: p.notes_last_updated || '',
        lastModified: p.hs_lastmodifieddate || ''
    };
}

// ── Supabase cache: read ──
async function getCachedDeals() {
    try {
        const resp = await fetch(
            supabaseUrl(CACHE_TABLE + '?select=data,synced_at&id=eq.1'),
            { headers: supabaseHeaders() }
        );
        if (!resp.ok) return null;
        const rows = await resp.json();
        if (!rows.length) return null;

        const row = rows[0];
        const age = Date.now() - new Date(row.synced_at).getTime();
        return { data: row.data, syncedAt: row.synced_at, fresh: age < CACHE_TTL_MS };
    } catch {
        return null;
    }
}

// ── Supabase cache: write ──
async function setCachedDeals(deals) {
    try {
        const payload = {
            id: 1,
            data: deals,
            synced_at: new Date().toISOString(),
            deal_count: deals.length
        };
        await fetch(supabaseUrl(CACHE_TABLE), {
            method: 'POST',
            headers: { ...supabaseHeaders(), Prefer: 'resolution=merge-duplicates' },
            body: JSON.stringify(payload)
        });
    } catch (err) {
        console.error('Cache write failed:', err.message);
    }
}

module.exports = async function handler(req, res) {
    setCors(req, res);
    if (req.method === 'OPTIONS') return res.status(204).end();
    if (req.method !== 'GET') return errorResponse(res, 405, 'Method not allowed');
    if (!rateLimit(req, 30)) return errorResponse(res, 429, 'Rate limited');

    try {
        // 1. Check cache
        const cached = await getCachedDeals();

        if (cached && cached.fresh) {
            return res.status(200).json({
                deals: cached.data,
                meta: { syncedAt: cached.syncedAt, source: 'cache', count: cached.data.length }
            });
        }

        // 2. Fetch from HubSpot
        let deals;
        try {
            const raw = await fetchAllDeals();
            deals = raw.map(transformDeal);
            // 3. Update cache
            await setCachedDeals(deals);
        } catch (hubErr) {
            console.error('HubSpot fetch failed:', hubErr.message);
            // 4. Fallback to stale cache
            if (cached) {
                return res.status(200).json({
                    deals: cached.data,
                    meta: { syncedAt: cached.syncedAt, source: 'stale-cache', count: cached.data.length }
                });
            }
            return errorResponse(res, 502, 'HubSpot API error and no cache available');
        }

        return res.status(200).json({
            deals: deals,
            meta: { syncedAt: new Date().toISOString(), source: 'hubspot', count: deals.length }
        });
    } catch (err) {
        return errorResponse(res, 500, 'Internal error', err);
    }
};
