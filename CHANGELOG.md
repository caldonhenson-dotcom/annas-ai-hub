# Changelog

All notable changes to Annas AI Hub are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `.ai/rules.md` — Engineering standards and project governance rules
- `PROJECT_STATUS.md` — Project health tracking
- `ARCHITECTURE.md` — System diagrams, tech stack, integration map
- `TECH_DEBT.md` — Known shortcuts and technical debt register

## [0.5.0] - 2025-02-23

### Added
- `api/outreach-data.js` — New endpoint fetching live prospects, approvals, AI logs from Supabase
- `OutreachActions` controller — Real approve/reject workflows with visual feedback and toast notifications
- `showToast()` — Global toast notification system replacing all `alert()` calls
- `escHtml()` — HTML escape helper for XSS prevention
- Live data loader — Dashboard tries Supabase on load, falls back to demo data

### Fixed
- 5 innerHTML XSS vulnerabilities in prospect panel (pillar, linkedin_url, company_domain, email, display_name)
- `prospect_id` injection risk — now validated with UUID/integer regex before Supabase URL interpolation
- Added `rel="noopener"` on all external links
- URL scheme validation on linkedin_url (must be https://)

### Removed
- All 10 `alert()` stub calls replaced with real UI

## [0.4.0] - 2025-02-23

### Added
- `api/_helpers.js` — Shared security module (CORS whitelist, rate limiting, error handling, prompt sanitisation)
- Rate limiting on all 5 API endpoints (per-IP sliding window)
- Input validation: sequence_step clamped 1-4, channel enum, question length cap 2000 chars
- `.catch()` error handling on disconnect fetch

### Fixed
- CORS restricted from wildcard `*` to origin whitelist across all 5 serverless functions
- Removed `detail: String(err)` from all error responses (no internal leak)
- Removed `raw_preview` from prospect-research error responses
- Removed hardcoded Supabase URL fallbacks — env vars required

## [0.3.0] - 2025-02-23

### Added
- Chrome extension for single-click LinkedIn cookie capture (Manifest V3)
- Extension auto-detection via content script broadcast
- Quick-connect flow — skips modal if extension detected

## [0.2.0] - 2025-02-23

### Added
- Interactive outreach workspace with 9 sub-tabs
- LinkedIn auth modal with bookmarklet + manual paste
- Prospect detail slide-out panel (research, messages, composer, scoring, notes)
- AI message composer with sequence step and channel selection
- 3 Vercel serverless functions: linkedin-session, prospect-research, draft-message

## [0.1.0] - 2025-02-22

### Added
- Initial dashboard with HubSpot, Monday.com, and AI chat integration
- `api/ai-query.js` — AI-powered data analysis
- Anna AI chat interface with markdown rendering
