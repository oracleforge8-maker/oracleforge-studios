/* ============================================================
   OracleForge — main.js
   Shared site behavior: mobile nav toggle + waitlist form handler
   ============================================================ */

(function () {
    'use strict';

    // ---------- Mobile nav toggle ----------
    const navToggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');

    if (navToggle && navLinks) {
        navToggle.addEventListener('click', function () {
            navLinks.classList.toggle('open');
        });
    }

    // ---------- Shared waitlist form handler ----------
    // Handles any form with id="waitlistForm" (home + waitlist pages).
    const waitlistForm = document.getElementById('waitlistForm');
    if (waitlistForm) {
        waitlistForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            const email = encodeURIComponent(waitlistForm.email.value.trim());
            const name = encodeURIComponent(
                (waitlistForm.name ? waitlistForm.name.value : '') || ''
            );
            const referredBy = encodeURIComponent(
                (waitlistForm.referred_by ? waitlistForm.referred_by.value : '') || ''
            );

            const msg = document.getElementById('formMessage');
            const refBox = document.getElementById('referralCode');

            try {
                const res = await fetch('/api/waitlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'email=' + email + '&name=' + name + '&referred_by=' + referredBy
                });
                const data = await res.json();

                if (data.success) {
                    if (msg) {
                        msg.innerHTML = '<div class="form-success">✅ You are on the list, anon! Welcome to the cult.</div>';
                    }
                    if (refBox && data.referral_code) {
                        refBox.textContent = 'Your referral code: ' + data.referral_code;
                    }
                    waitlistForm.reset();
                } else {
                    if (msg) {
                        msg.innerHTML = '<div class="form-error" style="display:block;">⚠️ ' +
                            (data.error || 'Something went wrong') + '</div>';
                    }
                }
            } catch (err) {
                if (msg) {
                    msg.innerHTML = '<div class="form-error" style="display:block;">⚠️ Network error: ' +
                        String(err) + '</div>';
                }
            }
        });
    }

    // ---------- Market ticker ----------
    // Homepage auto-scrolling market ticker (BTC / ETH / SOL + top-3 gainers).
    // Polls /api/ticker every 60s. Hovering pauses the scroll (via CSS). The
    // track is duplicated so the marquee loops seamlessly, and on refresh we
    // only swap each item's text via DOM APIs (XSS-safe) — the running CSS
    // animation on the track is never reset, so scrolling stays smooth.
    const tickerTrack = document.getElementById('tickerTrack');

    if (tickerTrack) {
        const POLL_MS = 60000;
        const MAJOR_KEYS = ['btc', 'eth', 'sol'];
        const MEDALS = {1: '🥇', 2: '🥈', 3: '🥉'};

        function fmtPrice(price) {
            if (price === null || price === undefined || isNaN(Number(price))) return '—';
            const n = Number(price);
            if (!n) return '$0.00';
            const opts = Math.abs(n) >= 100
                ? {minimumFractionDigits: 2, maximumFractionDigits: 2}
                : Math.abs(n) >= 1
                ? {minimumFractionDigits: 2, maximumFractionDigits: 4}
                : {minimumFractionDigits: 4, maximumFractionDigits: 8};
            return '$' + n.toLocaleString('en-US', opts);
        }

        function fmtChange(c) {
            if (c === null || c === undefined || isNaN(Number(c))) return '—';
            const n = Number(c);
            return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
        }

        function changeClass(c) {
            if (c === null || c === undefined || isNaN(Number(c))) return '';
            return (Number(c) || 0) >= 0 ? 'up' : 'down';
        }

        function buildItem(key, symbol, price, change, medal) {
            const item = document.createElement('div');
            item.className = 'ticker-item';
            item.dataset.key = key;
            if (medal) {
                const m = document.createElement('span');
                m.className = 'ticker-medal';
                m.textContent = medal;
                item.appendChild(m);
            }
            const s = document.createElement('span');
            s.className = 'ticker-symbol';
            s.textContent = symbol;
            item.appendChild(s);
            const p = document.createElement('span');
            p.className = 'ticker-price';
            p.textContent = fmtPrice(price);
            item.appendChild(p);
            const c = document.createElement('span');
            c.className = 'ticker-change ' + changeClass(change);
            c.textContent = fmtChange(change);
            item.appendChild(c);
            return item;
        }

        // Replace an existing item with a freshly built one (XSS-safe DOM
        // APIs only). The track's CSS animation keeps running through the swap.
        function swapItem(item, key, symbol, price, change, medal) {
            const next = buildItem(key, symbol, price, change, medal);
            if (item.parentNode) {
                item.parentNode.replaceChild(next, item);
            }
        }

        function initTicker(data) {
            tickerTrack.innerHTML = '';
            const frag = document.createDocumentFragment();
            MAJOR_KEYS.forEach(function (k) {
                const coin = (data && data[k]) || {price: null, change_24h: null};
                frag.appendChild(buildItem(k, k.toUpperCase(), coin.price, coin.change_24h, null));
            });
            const gainers = (data && data.top_gainers) || [];
            for (let i = 1; i <= 3; i++) {
                const g = gainers[i - 1] || {symbol: '—', price: null, change_30m: null};
                frag.appendChild(buildItem('gainer-' + i, (g.symbol || '?').toUpperCase(), g.price, g.change_30m, MEDALS[i]));
            }
            tickerTrack.appendChild(frag);
            // Duplicate the set so the marquee (translateX 0 -> -50%) loops seamlessly.
            tickerTrack.innerHTML += tickerTrack.innerHTML;
        }

        function refreshTicker(data) {
            // Update every matching node (both duplicated copies) in place so
            // the track's running CSS animation is never interrupted.
            MAJOR_KEYS.forEach(function (k) {
                const coin = (data[k] || {price: 0, change_24h: 0});
                tickerTrack.querySelectorAll('.ticker-item[data-key="' + k + '"]').forEach(function (item) {
                    swapItem(item, k, k.toUpperCase(), coin.price, coin.change_24h, null);
                });
            });
            const gainers = data.top_gainers || [];
            for (let i = 1; i <= 3; i++) {
                const key = 'gainer-' + i;
                const g = gainers[i - 1] || {symbol: '—', price: 0, change_30m: 0};
                tickerTrack.querySelectorAll('.ticker-item[data-key="' + key + '"]').forEach(function (item) {
                    swapItem(item, key, (g.symbol || '?').toUpperCase(), g.price, g.change_30m, MEDALS[i]);
                });
            }
        }

        async function loadTicker() {
            try {
                const res = await fetch('/api/ticker', {cache: 'no-store'});
                if (!res.ok) throw new Error('Ticker API returned ' + res.status);
                const data = await res.json();
                refreshTicker(data);
            } catch (err) {
                console.warn('Market ticker fetch failed:', err);
            }
        }

        // Show + scroll immediately (placeholders), then hydrate with data.
        initTicker();
        loadTicker();
        setInterval(loadTicker, POLL_MS);
    }

    // ---------- Top 10 Gainers table ----------
    // Homepage table of the top 10 coins by 30-minute price momentum.
    // Polls /api/top-gainers every 60s, renders medals for the top 3, and
    // colours each change green (up) / red (down). All DOM updates use
    // textContent so the table stays XSS-safe.
    const gainersBody = document.getElementById('topGainersBody');
    const gainersTable = document.getElementById('topGainersTable');

    if (gainersBody) {
        const POLL_MS = 60000;
        const MEDALS = {1: '🥇', 2: '🥈', 3: '🥉'};
        const MEDAL_CLASS = {1: 'gold', 2: 'silver', 3: 'bronze'};

        function fmtPriceG(price) {
            if (price === null || price === undefined || isNaN(Number(price))) return '—';
            const n = Number(price);
            if (!n) return '$0.00';
            const opts = Math.abs(n) >= 100
                ? {minimumFractionDigits: 2, maximumFractionDigits: 2}
                : Math.abs(n) >= 1
                ? {minimumFractionDigits: 2, maximumFractionDigits: 4}
                : {minimumFractionDigits: 4, maximumFractionDigits: 8};
            return '$' + n.toLocaleString('en-US', opts);
        }

        function fmtChangeG(c) {
            if (c === null || c === undefined || isNaN(Number(c))) return '—';
            const n = Number(c);
            return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
        }

        function changeClassG(c) {
            if (c === null || c === undefined || isNaN(Number(c))) return 'change-neutral';
            return (Number(c) || 0) >= 0 ? 'change-up' : 'change-down';
        }

        function medalCell(rank) {
            const cls = MEDAL_CLASS[rank];
            const icon = MEDALS[rank] || '';
            if (!icon) return '';
            const span = document.createElement('span');
            span.className = 'gainers-medal ' + (cls || '');
            span.innerHTML = icon; // emoji glyph is safe
            return span;
        }

        function renderGainers(coins) {
            gainersBody.innerHTML = '';
            const frag = document.createDocumentFragment();

            (coins || []).forEach(function (coin) {
                const tr = document.createElement('tr');

                // Rank (with medal for top 3)
                const tdRank = document.createElement('td');
                tdRank.className = 'gainers-rank';
                tdRank.textContent = coin.rank;
                if (coin.rank <= 3) {
                    tdRank.appendChild(medalCell(coin.rank));
                }

                // Coin symbol
                const tdSym = document.createElement('td');
                tdSym.className = 'gainers-symbol';
                tdSym.textContent = (coin.symbol || '—').toUpperCase();

                // Price
                const tdPrice = document.createElement('td');
                tdPrice.className = 'gainers-price';
                tdPrice.textContent = fmtPriceG(coin.price);

                // 30m change
                const tdChange30 = document.createElement('td');
                tdChange30.className = 'num-col';
                const span30 = document.createElement('span');
                span30.className = changeClassG(coin.change_30m);
                span30.textContent = fmtChangeG(coin.change_30m);
                tdChange30.appendChild(span30);

                // 24h change
                const tdChange24 = document.createElement('td');
                tdChange24.className = 'num-col';
                const span24 = document.createElement('span');
                span24.className = changeClassG(coin.change_24h);
                span24.textContent = fmtChangeG(coin.change_24h);
                tdChange24.appendChild(span24);

                tr.append(tdRank, tdSym, tdPrice, tdChange30, tdChange24);
                frag.appendChild(tr);
            });

            gainersBody.appendChild(frag);

            // Show a last-updated timestamp footer.
            removeUpdatedRow();
            const updated = document.createElement('tr');
            updated.className = 'gainers-updated-row';
            const td = document.createElement('td');
            td.colSpan = 5;
            td.className = 'gainers-updated';
            td.textContent = 'Updated ' + new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) + ' · auto-refreshes every 60s';
            updated.appendChild(td);
            gainersBody.parentNode.appendChild(updated);
        }

        function removeUpdatedRow() {
            const old = gainersBody.parentNode.querySelector('.gainers-updated-row');
            if (old) old.remove();
        }

        function showError(msg) {
            removeUpdatedRow();
            gainersBody.innerHTML = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 5;
            td.className = 'gainers-loading';
            td.textContent = msg;
            tr.appendChild(td);
            gainersBody.appendChild(tr);
        }

        async function loadGainers() {
            try {
                const res = await fetch('/api/top-gainers', {cache: 'no-store'});
                if (!res.ok) throw new Error('Top gainers API returned ' + res.status);
                const coins = await res.json();
                if (!Array.isArray(coins) || coins.length === 0) {
                    showError('No gainers data available right now.');
                    return;
                }
                renderGainers(coins);
            } catch (err) {
                console.warn('Top gainers fetch failed:', err);
                // Keep the last rendered state (or a hint) on error.
            }
        }

        // Hydrate on load, then refresh every 60 seconds.
        loadGainers();
        setInterval(loadGainers, POLL_MS);
    }
})();
