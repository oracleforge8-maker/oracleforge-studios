/* ============================================================
   OracleForge Studios — dashboard.js
   Shared dashboard behavior: SSE real-time health + helpers
   ============================================================ */

(function () {
    'use strict';

    // ---------- Real-time health via Server-Sent Events ----------
    // Connects to /dashboard/stream and updates the status dot on
    // the overview + health pages every 30 seconds.
    function initHealthStream() {
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        if (!dot || !text) return; // only on pages with the health hero

        try {
            const es = new EventSource('/dashboard/stream');
            es.onmessage = function (event) {
                try {
                    const data = JSON.parse(event.data);
                    const overall = data.overall || 'unknown';
                    dot.className = 'status-dot ' + overall;
                    text.textContent = 'System: ' + overall.toUpperCase();
                } catch (e) {
                    // ignore malformed events
                }
            };
            es.onerror = function () {
                // EventSource auto-reconnects; just log silently
                text.textContent = 'System: reconnecting…';
            };
        } catch (e) {
            // SSE not supported — fall back to polling (handled per-page)
        }
    }

    // ---------- Generic fetch helper ----------
    async function api(url, options) {
        const res = await fetch(url, options);
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    }

    // ---------- Init ----------
    document.addEventListener('DOMContentLoaded', function () {
        initHealthStream();
    });

    // Expose helpers for page scripts
    window.Observatory = { api: api };
})();