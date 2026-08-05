/* ============================================================
   OracleForge — live.js
   Home page live trend widget. Polls /api/trends and renders
   rows via DOM APIs (XSS-safe, no HTML string escaping).
   ============================================================ */

(function () {
    'use strict';

    const feed = document.getElementById('trendFeed');
    if (!feed) return;

    function buildRow(symbol, source, change) {
        const div = document.createElement('div');
        div.className = 'trend-row';

        const left = document.createElement('div');
        const sym = document.createElement('span');
        sym.className = 'trend-symbol';
        sym.textContent = '$' + symbol;

        const src = document.createElement('span');
        src.style.cssText = 'font-size:0.8rem;opacity:0.7;margin-left:0.5rem;';
        src.textContent = source;

        left.appendChild(sym);
        left.appendChild(src);

        const badge = document.createElement('span');
        const cls = change >= 0 ? 'up' : 'down';
        badge.className = 'trend-change ' + cls;
        badge.textContent = (change >= 0 ? '+' : '') + change.toFixed(1) + '%';

        div.appendChild(left);
        div.appendChild(badge);
        return div;
    }

    async function load() {
        try {
            const res = await fetch('/api/trends?limit=6');
            if (!res.ok) throw new Error('API error');
            const data = await res.json();

            feed.innerHTML = '';
            feed.className = '';

            if (!data.trends || !data.trends.length) {
                feed.className = 'live-widget-empty';
                feed.textContent = 'No trends captured yet. The Scout is standing by... 📡';
                return;
            }

            data.trends.forEach(function (t) {
                const chg = Number(t.price_change_pct) || 0;
                feed.appendChild(buildRow(t.token_symbol, t.source, chg));
            });
        } catch (err) {
            feed.className = 'live-widget-empty';
            feed.textContent = '⚠️ Could not reach the feed: ' + String(err);
        }
    }

    // Initial load + refresh every 30s
    load();
    setInterval(load, 30000);
})();