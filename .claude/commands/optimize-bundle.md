---
description: Analyse and optimise frontend asset loading and performance
user-invocable: true
---

Analyse the Vanilla JS SPA frontend for optimisation opportunities:

## 1. Script Loading Analysis
- Check `index.html` for script loading order and `defer`/`async` attributes
- Verify `js/router.js` lazy-loads page scripts on demand (not all upfront)
- Check if Chart.js is loaded via CDN with proper caching headers
- Identify any scripts loaded globally that are only needed by specific pages

## 2. CSS Analysis
- Check `css/tokens.css` and `css/pipeline.css` for unused CSS rules
- Identify duplicate or redundant style declarations
- Check if CSS custom properties are used consistently (no hardcoded colours)
- Verify responsive breakpoints work (test at 900px, 768px, 480px)

## 3. Asset Size Audit
- Measure total page weight: HTML + CSS + JS + images
- Check for unoptimised images (should use WebP/AVIF where possible)
- Check if `js/data.js` could be split or lazy-loaded (it contains all TS/STATIC/YOY data)
- Identify any inline styles that should be moved to CSS classes

## 4. Runtime Performance
- Check for unnecessary DOM re-renders in page renderers
- Verify Chart.js instances are properly destroyed before recreation
- Check for memory leaks (event listeners not cleaned up on page navigation)
- Verify `ensureCanvas()` cleanup pattern is used consistently

## 5. Network Optimisation
- Check if static assets have proper cache headers (via Vercel config or HTML meta)
- Verify CDN resources use `crossorigin` and `integrity` attributes
- Check if the daily data refresh (`data.js`) could be fetched incrementally

## 6. Python Backend Performance
- Check FastAPI routes for N+1 query patterns against Supabase
- Verify database queries use proper indexes
- Check if materialised views are refreshed efficiently
- Identify any synchronous blocking calls that should be async

Output a prioritised list of optimisations with effort vs impact ratings (Quick Win / Medium / Large).
