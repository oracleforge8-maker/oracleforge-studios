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

    // ---------- Quick Stats ----------
    // Homepage quick stats grid (market cap, volume, dominance).
    // Polls /api/quick-stats every 60s and updates the DOM.
    const statsGrid = document.getElementById('quickStatsGrid');
    const statsUpdated = document.getElementById('statsUpdated');

// Quick Stats — always define the function
const POLL_MS = 60000;

function formatNumber(num) {
    if (num >= 1e12) return (num / 1e12).toFixed(2) + 'T';
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
    return num.toFixed(2);
}

function loadQuickStats() {
    // Only run if the elements exist on this page
    if (!document.getElementById('totalMarketCap')) return;
    
    fetch('/api/quick-stats')
        .then(response => response.json())
        .then(data => {
            document.getElementById('totalMarketCap').textContent = '$' + formatNumber(data.total_market_cap);
            document.getElementById('totalVolume').textContent = '$' + formatNumber(data.total_volume);
            document.getElementById('btcDominance').textContent = data.btc_dominance.toFixed(1) + '%';
            document.getElementById('ethDominance').textContent = data.eth_dominance.toFixed(1) + '%';
            document.getElementById('statsTimestamp').textContent = 'Updated: ' + new Date().toLocaleTimeString();
        })
        .catch(() => {
            // Keep existing values if API fails
        });
}

// Run immediately and then every 60 seconds
loadQuickStats();
setInterval(loadQuickStats, POLL_MS);
    // ---------- Breaking News static list ----------
    // Homepage static list of latest crypto headlines (5 most recent).
    // Polls /api/news every 5 minutes.
    const newsList = document.getElementById('newsList');

    if (newsList) {
        const NEWS_POLL_MS = 300000; // 5 minutes
        const MAX_NEWS_ITEMS = 5;

        function buildNewsItem(title, url, source) {
            const item = document.createElement('div');
            item.className = 'news-article';

            const titleSpan = document.createElement('span');
            titleSpan.className = 'news-title';
            titleSpan.textContent = title;

            const sourceSpan = document.createElement('span');
            sourceSpan.className = 'news-source';
            sourceSpan.textContent = source;

            const readMoreLink = document.createElement('a');
            readMoreLink.className = 'news-readmore';
            readMoreLink.href = url || '#';
            readMoreLink.target = '_blank';
            readMoreLink.rel = 'noopener noreferrer';
            readMoreLink.textContent = 'Read more →';

            item.appendChild(titleSpan);
            item.appendChild(sourceSpan);
            item.appendChild(readMoreLink);

            // Add click handler to open article in new tab
            item.addEventListener('click', function(e) {
                if (url && !e.target.classList.contains('news-readmore')) {
                    window.open(url, '_blank', 'noopener,noreferrer');
                }
            });

            return item;
        }

        function renderNewsList(newsItems) {
            newsList.innerHTML = '';
            const frag = document.createDocumentFragment();

            // Add news items (limit to MAX_NEWS_ITEMS)
            const itemsToShow = newsItems.slice(0, MAX_NEWS_ITEMS);
            itemsToShow.forEach(function(item) {
                frag.appendChild(buildNewsItem(
                    item.title || 'Breaking Crypto News',
                    item.url || '',
                    item.source || 'Source'
                ));
            });

            newsList.appendChild(frag);
        }

        function showLoadingNews() {
            newsList.innerHTML = '<div class="news-loading">Loading latest news...</div>';
        }

        async function loadNews() {
            try {
                const res = await fetch('/api/news', {cache: 'no-store'});
                if (!res.ok) throw new Error('News API returned ' + res.status);
                const data = await res.json();

                if (data.news && Array.isArray(data.news) && data.news.length > 0) {
                    renderNewsList(data.news);
                } else {
                    // Fallback to mock data if API returns empty
                    const mockNews = [
                        {title: 'Bitcoin Surges Past $65K as Institutional Adoption Accelerates', url: 'https://example.com/bitcoin-surge', source: 'CoinDesk'},
                        {title: 'Ethereum ETFs Approved by SEC, ETH Price Jumps 12%', url: 'https://example.com/eth-etf', source: 'CoinTelegraph'},
                        {title: 'Solana Network Outage Resolved After 5-Hour Downtime', url: 'https://example.com/solana-outage', source: 'The Block'},
                        {title: 'MicroStrategy Adds 12,000 More BTC to Treasury, Now Holds 226,331 Bitcoin', url: 'https://example.com/microstrategy-btc', source: 'Decrypt'},
                        {title: 'SEC Delays Decision on Spot Bitcoin ETFs Until October', url: 'https://example.com/sec-delay', source: 'Bloomberg'}
                    ];
                    renderNewsList(mockNews);
                }
            } catch (err) {
                console.warn('News fetch failed:', err);
                // Show mock data on error
                const mockNews = [
                    {title: 'Bitcoin Surges Past $65K as Institutional Adoption Accelerates', url: 'https://example.com/bitcoin-surge', source: 'CoinDesk'},
                    {title: 'Ethereum ETFs Approved by SEC, ETH Price Jumps 12%', url: 'https://example.com/eth-etf', source: 'CoinTelegraph'},
                    {title: 'Solana Network Outage Resolved After 5-Hour Downtime', url: 'https://example.com/solana-outage', source: 'The Block'},
                    {title: 'MicroStrategy Adds 12,000 More BTC to Treasury, Now Holds 226,331 Bitcoin', url: 'https://example.com/microstrategy-btc', source: 'Decrypt'},
                    {title: 'Vitalik Buterin Proposes New EIP to Reduce Ethereum Gas Fees by 30%', url: 'https://example.com/vitalik-eip', source: 'CryptoBriefing'}
                ];
                renderNewsList(mockNews);
            }
        }

        // Show loading state immediately, then hydrate with data
        showLoadingNews();
        loadNews();
        setInterval(loadNews, NEWS_POLL_MS);
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
            if (n >= 100) return '$' + n.toFixed(2);
            if (n >= 1) return '$' + n.toFixed(4);
            if (n >= 0.01) return '$' + n.toFixed(6);
            return '$' + n.toFixed(8);
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

    // ---------- Blog Auto-Refresh ----------
    // Blog page auto-refresh for new posts.
    // Polls /api/blog-posts every 5 minutes to check for new content.
    const blogList = document.querySelector('.blog-list');

    if (blogList) {
        const BLOG_POLL_MS = 300000; // 5 minutes
        let lastPostCount = 0;

        function checkForNewPosts() {
            const currentPosts = blogList.querySelectorAll('.blog-card');
            lastPostCount = currentPosts.length;

            // Show a notification if new posts are available
            const notification = document.createElement('div');
            notification.className = 'blog-notification';
            notification.innerHTML = `
                <div class="blog-notification-content">
                    <span>📢 New posts available!</span>
                    <button class="blog-refresh-btn">Refresh Now</button>
                </div>
            `;
            notification.style.display = 'none';
            document.body.appendChild(notification);

            // Add refresh button handler
            const refreshBtn = notification.querySelector('.blog-refresh-btn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', function() {
                    window.location.reload();
                });
            }

            // Check for new posts by comparing count
            setInterval(async function() {
                try {
                    const response = await fetch('/api/blog-posts?limit=10');
                    if (response.ok) {
                        const data = await response.json();
                        if (data.posts && data.posts.length > lastPostCount) {
                            notification.style.display = 'block';
                            lastPostCount = data.posts.length;
                        }
                    }
                } catch (error) {
                    console.warn('Blog post check failed:', error);
                }
            }, BLOG_POLL_MS);
        }

        // Start checking for new posts
        checkForNewPosts();
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

    // ---------- 1-min Chart with Moving Averages ----------
    // Homepage interactive chart showing price action, moving averages, and trading signals.
    // Auto-loads the top trending Pump.fun coin and updates when the top coin changes.
    const chartContainer = document.getElementById('chartContainer');
    const chartLoading = document.getElementById('chartLoading');
    const chartRefreshBtn = document.getElementById('chartRefreshBtn');
    const currentCoinElement = document.getElementById('currentCoin');

    if (chartContainer) {
        // Load Plotly.js from CDN
        let plotlyLoaded = false;
        let plotlyScript = null;
        let currentTopToken = null;

        function loadPlotly() {
            return new Promise((resolve, reject) => {
                if (plotlyLoaded) {
                    resolve();
                    return;
                }

                plotlyScript = document.createElement('script');
                plotlyScript.src = 'https://cdn.plot.ly/plotly-2.27.0.min.js';
                plotlyScript.onload = () => {
                    plotlyLoaded = true;
                    resolve();
                };
                plotlyScript.onerror = () => {
                    reject(new Error('Failed to load Plotly.js'));
                };
                document.head.appendChild(plotlyScript);
            });
        }

        function showLoading() {
            if (chartLoading) chartLoading.style.display = 'block';
            chartContainer.innerHTML = '';
            if (currentCoinElement) currentCoinElement.textContent = 'Loading...';
        }

        function hideLoading() {
            if (chartLoading) chartLoading.style.display = 'none';
        }

        function updateCurrentCoinInfo(token) {
            if (currentCoinElement) {
                currentCoinElement.textContent = token ?
                    `📊 ${token.symbol.toUpperCase()} - $${token.price.toLocaleString('en-US', {
                        minimumFractionDigits: 4,
                        maximumFractionDigits: 8
                    })} | Momentum: ${token.momentum.toFixed(1)}` :
                    'No data available';
            }
        }


        function updateCoinInfoOverlay(token) {
            const overlay = document.getElementById('coinInfoOverlay');
            if (!overlay) return;

            if (token) {
                overlay.innerHTML = `
                    <h4>🪙 ${token.symbol.toUpperCase()}</h4>
                    <div class="coin-price">$${token.price.toLocaleString('en-US', {
                        minimumFractionDigits: 4,
                        maximumFractionDigits: 8
                    })}</div>
                    <div class="coin-stats">
                        <div>
                            <div class="stat-label">Momentum</div>
                            <div class="stat-value">${token.momentum.toFixed(1)}</div>
                        </div>
                        <div>
                            <div class="stat-label">Market Cap</div>
                            <div class="stat-value">$${formatMarketCap(token.marketCapUsd)}</div>
                        </div>
                        <div>
                            <div class="stat-label">Volume</div>
                            <div class="stat-value">$${formatVolume(token.volumeUsd)}</div>
                        </div>
                        <div>
                            <div class="stat-label">Launched</div>
                            <div class="stat-value">${token.launched}</div>
                        </div>
                    </div>
                `;
                overlay.style.display = 'block';
            } else {
                overlay.style.display = 'none';
            }
        }

        function formatMarketCap(mc) {
            if (mc === null || mc === undefined || isNaN(Number(mc))) return '—';
            const n = Number(mc);
            if (!n) return '$0';
            if (n >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
            if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
            if (n >= 1e3) return '$' + (n / 1e3).toFixed(2) + 'K';
            return '$' + n.toFixed(0);
        }

        function formatVolume(vol) {
            if (vol === null || vol === undefined || isNaN(Number(vol))) return '—';
            const n = Number(vol);
            if (!n) return '$0';
            if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
            if (n >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'K';
            return '$' + n.toFixed(0);
        }

        async function loadChart(symbol) {
            showLoading();

            try {
                // Load Plotly if not already loaded
                await loadPlotly();

                // Fetch chart data from API
                const response = await fetch(`/api/chart/${symbol}`);
                if (!response.ok) {
                    throw new Error(`API returned ${response.status}`);
                }

                const data = await response.json();

                if (!data.price_data || data.price_data.length === 0) {
                    throw new Error('No chart data available');
                }

                // Extract data for Plotly
                const timestamps = data.price_data.map(item => new Date(item[0]));
                const prices = data.price_data.map(item => item[4]); // Close price
                const volumes = data.price_data.map(item => item[5]); // Volume

                // Filter out null values from MAs and align with timestamps
                const ma1m = data.ma_1m.map((value, index) => value !== null ? value : null);
                const ma5m = data.ma_5m.map((value, index) => value !== null ? value : null);

                const signals = data.signals || [];

                // Create traces
                const traces = [
                    {
                        x: timestamps,
                        y: prices,
                        type: 'scatter',
                        mode: 'lines',
                        name: 'Price',
                        line: { color: '#3E6AE1', width: 2 },
                        hovertemplate: '<b>Price</b>: $%{y:.4f}<br><b>Time</b>: %{x|%H:%M}<extra></extra>'
                    }
                ];

                // Add MA traces if data exists
                if (ma1m.some(value => value !== null)) {
                    traces.push({
                        x: timestamps,
                        y: ma1m,
                        type: 'scatter',
                        mode: 'lines',
                        name: '1-min MA',
                        line: { color: '#FF7F0E', dash: 'dash', width: 2 },
                        hovertemplate: '<b>1-min MA</b>: $%{y:.4f}<br><b>Time</b>: %{x|%H:%M}<extra></extra>'
                    });
                }

                if (ma5m.some(value => value !== null)) {
                    traces.push({
                        x: timestamps,
                        y: ma5m,
                        type: 'scatter',
                        mode: 'lines',
                        name: '5-min MA',
                        line: { color: '#2CA02C', dash: 'dot', width: 2 },
                        hovertemplate: '<b>5-min MA</b>: $%{y:.4f}<br><b>Time</b>: %{x|%H:%M}<extra></extra>'
                    });
                }

                // Add volume bars
                traces.push({
                    x: timestamps,
                    y: volumes,
                    type: 'bar',
                    name: 'Volume',
                    marker: { color: 'rgba(148, 103, 189, 0.3)' },
                    yaxis: 'y2',
                    hovertemplate: '<b>Volume</b>: %{y:,}<br><b>Time</b>: %{x|%H:%M}<extra></extra>'
                });

                // Add entry/exit signals
                const entrySignals = signals.filter(s => s.type === 'entry');
                const exitSignals = signals.filter(s => s.type === 'exit');

                if (entrySignals.length > 0) {
                    traces.push({
                        x: entrySignals.map(s => new Date(s.time)),
                        y: entrySignals.map(s => s.price),
                        type: 'scatter',
                        mode: 'markers',
                        name: 'Entry Signal',
                        marker: {
                            symbol: 'triangle-up',
                            size: 12,
                            color: '#2ECC71',
                            line: { color: '#27AE60', width: 2 }
                        },
                        hovertemplate: '<b>Entry Signal</b>: $%{y:.4f}<extra></extra>'
                    });
                }

                if (exitSignals.length > 0) {
                    traces.push({
                        x: exitSignals.map(s => new Date(s.time)),
                        y: exitSignals.map(s => s.price),
                        type: 'scatter',
                        mode: 'markers',
                        name: 'Exit Signal',
                        marker: {
                            symbol: 'triangle-down',
                            size: 12,
                            color: '#E74C3C',
                            line: { color: '#C0392B', width: 2 }
                        },
                        hovertemplate: '<b>Exit Signal</b>: $%{y:.4f}<extra></extra>'
                    });
                }

                // Plot layout with dual y-axis - Modern Dark Theme
                const layout = {
                    title: {
                        text: `${symbol.toUpperCase()} Price Chart (Real-Time)`,
                        font: {
                            family: "'Inter', sans-serif",
                            size: 16,
                            color: '#F0EEE9',
                            weight: 'bold'
                        }
                    },
                    xaxis: {
                        title: 'Time',
                        rangeslider: { visible: false },
                        type: 'date',
                        gridcolor: 'rgba(255, 255, 255, 0.1)',
                        zerolinecolor: 'rgba(255, 255, 255, 0.1)',
                        tickfont: {
                            color: '#A8A6A2',
                            size: 12
                        },
                        titlefont: {
                            color: '#F0EEE9',
                            size: 14
                        }
                    },
                    yaxis: {
                        title: 'Price (USD)',
                        fixedrange: false,
                        gridcolor: 'rgba(255, 255, 255, 0.1)',
                        zerolinecolor: 'rgba(255, 255, 255, 0.1)',
                        tickfont: {
                            color: '#A8A6A2',
                            size: 12
                        },
                        titlefont: {
                            color: '#F0EEE9',
                            size: 14
                        },
                        tickformat: '$.4f'
                    },
                    yaxis2: {
                        title: 'Volume',
                        overlaying: 'y',
                        side: 'right',
                        fixedrange: false,
                        showgrid: false,
                        tickfont: {
                            color: '#A8A6A2',
                            size: 12
                        },
                        titlefont: {
                            color: '#F0EEE9',
                            size: 14
                        }
                    },
                    showlegend: true,
                    legend: {
                        x: 0,
                        y: 1.1,
                        orientation: 'h',
                        bgcolor: 'rgba(26, 26, 25, 0.8)',
                        bordercolor: 'rgba(255, 255, 255, 0.2)',
                        borderwidth: 1,
                        font: {
                            color: '#F0EEE9',
                            size: 12
                        }
                    },
                    margin: { t: 60, r: 60, b: 60, l: 60 },
                    hovermode: 'closest',
                    plot_bgcolor: '#0A0A0A',
                    paper_bgcolor: '#12102A',
                    font: {
                        family: "'Inter', sans-serif",
                        color: '#C0C0C0'
                    },
                    hoverlabel: {
                        bgcolor: 'rgba(26, 26, 25, 0.9)',
                        bordercolor: 'rgba(0, 184, 148, 0.7)',
                        font: {
                            color: '#F0EEE9',
                            family: "'Inter', sans-serif"
                        }
                    }
                };

                // Render chart
                Plotly.newPlot(chartContainer, traces, layout, {
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false,
                    modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d']
                });

                hideLoading();

            } catch (error) {
                console.error('Chart loading failed:', error);
                hideLoading();
                chartContainer.innerHTML = `
                    <div class="chart-error">
                        <h3>⚠️ Chart Loading Error</h3>
                        <p>${error.message}</p>
                        <p>We'll automatically retry on the next refresh.</p>
                        <button id="chartRetryBtn" class="btn btn-secondary" style="margin-top: 1rem;">🔄 Try Again</button>
                    </div>
                `;

                // Add retry button event listener
                const retryBtn = document.getElementById('chartRetryBtn');
                if (retryBtn) {
                    retryBtn.addEventListener('click', () => {
                        loadChartForTopToken();
                    });
                }
            }
        }

        async function loadChartForTopToken() {
            try {
                // Fetch pump trending data to get the top token
                const response = await fetch('/api/pump-trending');
                if (!response.ok) {
                    throw new Error(`Pump trending API returned ${response.status}`);
                }

                const data = await response.json();
                const tokens = data.tokens || [];

                if (tokens.length === 0) {
                    throw new Error('No trending tokens available');
                }

                // Get the top token by momentum
                const topToken = tokens.reduce((prev, current) =>
                    (prev.momentum > current.momentum) ? prev : current
                );

                currentTopToken = topToken;
                updateCurrentCoinInfo(topToken);

                // Load chart for the top token's symbol (lowercase)
                await loadChart(topToken.symbol.toLowerCase());

            } catch (error) {
                console.error('Failed to load top token data:', error);
                showLoading();
                chartContainer.innerHTML = `
                    <div class="chart-error">
                        <h3>⚠️ Failed to Load Top Token</h3>
                        <p>${error.message}</p>
                        <p>We'll automatically retry on the next refresh.</p>
                    </div>
                `;
            }
        }

        // Event listeners
        if (chartRefreshBtn) {
            chartRefreshBtn.addEventListener('click', loadChartForTopToken);
        }

        // Load initial chart with top token
        loadChartForTopToken();

        // Auto-refresh every 60 seconds
        setInterval(loadChartForTopToken, 60000);
    }

    // ---------- Pump.fun Trending ----------
    // Homepage card grid of trending Pump.fun meme coins.
    // Polls /api/pump-trending every 60s, renders each token as a card with
    // a momentum progress bar (0-100). Coins with momentum > 70 get a
    // "high-momentum" highlight class. All DOM updates use textContent so
    // the grid stays XSS-safe.
    const pumpGrid = document.getElementById('pumpTrendingGrid');
    const pumpInfoCard = document.getElementById('pumpInfoCard');
    const pumpChartContainer = document.getElementById('pumpChart');
    let currentTopToken = null;

    if (pumpGrid) {
        const POLL_MS = 60000;
        const HIGH_MOMENTUM = 70;
        let plotlyLoaded = false;
        let plotlyScript = null;

        function fmtPricePump(price) {
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

        function fmtMarketCap(mc) {
            if (mc === null || mc === undefined || isNaN(Number(mc))) return '—';
            const n = Number(mc);
            if (!n) return '$0';
            if (n >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
            if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
            if (n >= 1e3) return '$' + (n / 1e3).toFixed(2) + 'K';
            return '$' + n.toFixed(0);
        }

        function fmtVolume(vol) {
            if (vol === null || vol === undefined || isNaN(Number(vol))) return '—';
            const n = Number(vol);
            if (!n) return '$0';
            if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
            if (n >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'K';
            return '$' + n.toFixed(0);
        }

        function momentumBarClass(m) {
            if (m >= 70) return 'high';
            if (m >= 40) return 'mid';
            return 'low';
        }

        function renderPumpCards(tokens) {
            pumpGrid.innerHTML = '';
            const frag = document.createDocumentFragment();

            (tokens || []).forEach(function (token) {
                const card = document.createElement('div');
                const momentum = Number(token.momentum) || 0;
                card.className = 'pump-card';
                if (momentum > HIGH_MOMENTUM) {
                    card.classList.add('high-momentum');
                }

                // --- Header: symbol + price ---
                const header = document.createElement('div');
                header.className = 'pump-card-header';

                const symCol = document.createElement('div');
                const sym = document.createElement('span');
                sym.className = 'pump-symbol';
                sym.textContent = (token.symbol || '—').toUpperCase();
                symCol.appendChild(sym);
                const name = document.createElement('small');
                name.className = 'pump-name';
                name.textContent = token.name || '';
                symCol.appendChild(name);

                const price = document.createElement('span');
                price.className = 'pump-card-price';
                price.textContent = fmtPricePump(token.price);

                header.appendChild(symCol);
                header.appendChild(price);
                card.appendChild(header);

                // --- Launch time ---
                const launched = document.createElement('div');
                launched.className = 'pump-launched';
                launched.textContent = 'Launched ' + (token.launched || 'Recently');
                card.appendChild(launched);

                // --- Momentum label + value row ---
                const momentumRow = document.createElement('div');
                momentumRow.className = 'momentum-row';

                const ml = document.createElement('span');
                ml.className = 'momentum-label';
                ml.textContent = 'Momentum';
                momentumRow.appendChild(ml);

                const value = document.createElement('span');
                value.className = 'momentum-value';
                value.textContent = momentum.toFixed(1);
                momentumRow.appendChild(value);

                card.appendChild(momentumRow);

                // --- Momentum progress bar ---
                const momentumWrap = document.createElement('div');
                momentumWrap.className = 'momentum-bar-wrap ' + momentumBarClass(momentum);

                const bar = document.createElement('div');
                bar.className = 'momentum-bar ' + momentumBarClass(momentum);
                bar.style.width = Math.max(4, Math.min(100, momentum)) + '%';

                momentumWrap.appendChild(bar);
                card.appendChild(momentumWrap);

                // --- Meta: market cap + volume ---
                const meta = document.createElement('div');
                meta.className = 'pump-card-meta';

                const mcItem = document.createElement('span');
                mcItem.className = 'meta-item';
                mcItem.innerHTML = 'MC: <span>' + fmtMarketCap(token.marketCapUsd) + '</span>';

                const volItem = document.createElement('div');
                volItem.className = 'meta-item';
                volItem.innerHTML = 'Vol: <span>' + fmtVolume(token.volumeUsd) + '</span>';

                meta.appendChild(mcItem);
                meta.appendChild(volItem);
                card.appendChild(meta);

                // --- Pump.fun link ---
                if (token.url) {
                    const link = document.createElement('a');
                    link.href = token.url;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    link.className = 'pump-link';
                    link.textContent = 'View on Pump.fun →';
                    card.appendChild(link);
                }

                frag.appendChild(card);
            });

            pumpGrid.appendChild(frag);

            // Updated timestamp
            const updated = document.getElementById('pumpUpdated');
            if (updated) {
                updated.textContent = 'Updated ' +
                    new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) +
                    ' · auto-refreshes every 60s';
            }
        }

        function loadPlotlyForPump() {
            return new Promise((resolve, reject) => {
                if (plotlyLoaded) {
                    resolve();
                    return;
                }

                plotlyScript = document.createElement('script');
                plotlyScript.src = 'https://cdn.plot.ly/plotly-2.27.0.min.js';
                plotlyScript.onload = () => {
                    plotlyLoaded = true;
                    resolve();
                };
                plotlyScript.onerror = () => {
                    reject(new Error('Failed to load Plotly.js'));
                };
                document.head.appendChild(plotlyScript);
            });
        }

        function renderPumpInfoCard(token) {
            if (!pumpInfoCard) return;

            pumpInfoCard.innerHTML = '';

            // Create token info card structure
            const card = document.createElement('div');
            card.className = 'pump-card';
            const momentum = Number(token.momentum) || 0;
            if (momentum > HIGH_MOMENTUM) {
                card.classList.add('high-momentum');
            }

            // Header: symbol + price
            const header = document.createElement('div');
            header.className = 'pump-card-header';

            const symCol = document.createElement('div');
            const sym = document.createElement('span');
            sym.className = 'pump-symbol';
            sym.textContent = (token.symbol || '—').toUpperCase();
            symCol.appendChild(sym);
            const name = document.createElement('small');
            name.className = 'pump-name';
            name.textContent = token.name || '';
            symCol.appendChild(name);

            const price = document.createElement('span');
            price.className = 'pump-card-price';
            price.textContent = fmtPricePump(token.price);

            header.appendChild(symCol);
            header.appendChild(price);
            card.appendChild(header);

            // Launch time
            const launched = document.createElement('div');
            launched.className = 'pump-launched';
            launched.textContent = 'Launched ' + (token.launched || 'Recently');
            card.appendChild(launched);

            // Momentum label + value row
            const momentumRow = document.createElement('div');
            momentumRow.className = 'momentum-row';

            const ml = document.createElement('span');
            ml.className = 'momentum-label';
            ml.textContent = 'Momentum';
            momentumRow.appendChild(ml);

            const value = document.createElement('span');
            value.className = 'momentum-value';
            value.textContent = momentum.toFixed(1);
            momentumRow.appendChild(value);

            card.appendChild(momentumRow);

            // Momentum progress bar
            const momentumWrap = document.createElement('div');
            momentumWrap.className = 'momentum-bar-wrap ' + momentumBarClass(momentum);

            const bar = document.createElement('div');
            bar.className = 'momentum-bar ' + momentumBarClass(momentum);
            bar.style.width = Math.max(4, Math.min(100, momentum)) + '%';

            momentumWrap.appendChild(bar);
            card.appendChild(momentumWrap);

            // Meta: market cap + volume
            const meta = document.createElement('div');
            meta.className = 'pump-card-meta';

            const mcItem = document.createElement('span');
            mcItem.className = 'meta-item';
            mcItem.innerHTML = 'MC: <span>' + fmtMarketCap(token.marketCapUsd) + '</span>';

            const volItem = document.createElement('div');
            volItem.className = 'meta-item';
            volItem.innerHTML = 'Vol: <span>' + fmtVolume(token.volumeUsd) + '</span>';

            meta.appendChild(mcItem);
            meta.appendChild(volItem);
            card.appendChild(meta);

            // Pump.fun link
            if (token.url) {
                const link = document.createElement('a');
                link.href = token.url;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                link.className = 'pump-link';
                link.textContent = 'View on Pump.fun →';
                card.appendChild(link);
            }

            pumpInfoCard.appendChild(card);
        }

        function showPumpLoading(msg) {
            if (pumpInfoCard) {
                pumpInfoCard.innerHTML = '';
                const div = document.createElement('div');
                div.className = 'pump-loading';
                div.textContent = msg;
                pumpInfoCard.appendChild(div);
            }
            if (pumpChartContainer) {
                pumpChartContainer.innerHTML = '';
            }
            const updated = document.getElementById('pumpUpdated');
            if (updated) updated.textContent = '';
        }

        async function loadPumpChart(symbol) {
            if (!pumpChartContainer) return;

            try {
                // Load Plotly if not already loaded
                await loadPlotlyForPump();

                // Fetch chart data from API
                const response = await fetch(`/api/chart/${symbol}`);
                if (!response.ok) {
                    throw new Error(`API returned ${response.status}`);
                }

                const data = await response.json();

                if (!data.price_data || data.price_data.length === 0) {
                    throw new Error('No chart data available');
                }

                // Extract data for Plotly
                const timestamps = data.price_data.map(item => new Date(item[0]));
                const prices = data.price_data.map(item => item[4]); // Close price
                const ma1m = data.ma_1m.filter(item => item !== null);
                const ma5m = data.ma_5m.filter(item => item !== null);

                // Create traces
                const traces = [
                    {
                        x: timestamps,
                        y: prices,
                        type: 'scatter',
                        mode: 'lines',
                        name: 'Price',
                        line: { color: '#1f77b4' }
                    }
                ];

                // Add MA traces if data exists
                if (ma1m.length > 0) {
                    traces.push({
                        x: timestamps.slice(1), // MA starts after 1 period
                        y: ma1m,
                        type: 'scatter',
                        mode: 'lines',
                        name: '1-min MA',
                        line: { color: '#ff7f0e', dash: 'dash' }
                    });
                }

                if (ma5m.length > 0) {
                    traces.push({
                        x: timestamps.slice(5), // MA starts after 5 periods
                        y: ma5m,
                        type: 'scatter',
                        mode: 'lines',
                        name: '5-min MA',
                        line: { color: '#2ca02c', dash: 'dot' }
                    });
                }

                // Plot layout with dark theme
                const layout = {
                    title: `${symbol.toUpperCase()} Price Chart (3h) with MAs`,
                    xaxis: {
                        title: 'Time',
                        rangeslider: { visible: false },
                        type: 'date',
                        gridcolor: 'rgba(255, 255, 255, 0.1)',
                        zerolinecolor: 'rgba(255, 255, 255, 0.1)'
                    },
                    yaxis: {
                        title: 'Price (USD)',
                        fixedrange: false,
                        gridcolor: 'rgba(255, 255, 255, 0.1)',
                        zerolinecolor: 'rgba(255, 255, 255, 0.1)'
                    },
                    showlegend: true,
                    legend: {
                        x: 0,
                        y: 1.1,
                        orientation: 'h',
                        font: { color: '#ffffff' }
                    },
                    margin: { t: 50, r: 20, b: 50, l: 50 },
                    hovermode: 'closest',
                    plot_bgcolor: '#0A0A0A',
                    paper_bgcolor: '#12102A',
                    font: { color: '#C0C0C0' }
                };

                // Render chart
                Plotly.newPlot(pumpChartContainer, traces, layout, {
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false
                });

            } catch (error) {
                console.error('Pump chart loading failed:', error);
                if (pumpChartContainer) {
                    pumpChartContainer.innerHTML = `
                        <div style="color: #FF4444; padding: 1rem; text-align: center;">
                            <p>⚠️ Failed to load chart: ${error.message}</p>
                            <p style="font-size: 0.8rem; opacity: 0.7;">Chart will auto-retry on next refresh</p>
                        </div>
                    `;
                }
            }
        }

        async function loadPumpTrending() {
            showPumpLoading('Scanning the blockchain for fresh degens… 🔍');
            try {
                const res = await fetch('/api/pump-trending', {cache: 'no-store'});
                if (!res.ok) throw new Error('Pump trending API returned ' + res.status);
                const data = await res.json();
                if (!data.tokens || !data.tokens.length) {
                    showPumpLoading('No trending tokens right now. The memecoins are sleeping… 😴');
                    return;
                }

                // Get the top token (highest momentum)
                const topToken = data.tokens.reduce((prev, current) =>
                    (prev.momentum || 0) > (current.momentum || 0) ? prev : current
                );

                // Check if the top token has changed
                const tokenChanged = !currentTopToken || currentTopToken !== topToken.symbol;

                // Render the top token info card
                renderPumpInfoCard(topToken);

                // Load chart for the top token if we have a symbol
                if (topToken.symbol && pumpChartContainer) {
                    currentTopToken = topToken.symbol;
                    if (tokenChanged) {
                        // Only reload chart if the token changed
                        await loadPumpChart(topToken.symbol);
                    }
                }

                // Updated timestamp with more details
                const updated = document.getElementById('pumpUpdated');
                if (updated) {
                    const now = new Date();
                    updated.textContent = 'Last updated: ' +
                        now.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'}) +
                        ' · Next refresh in 60s · Top token: ' + (topToken.symbol || 'N/A').toUpperCase() +
                        ' (Momentum: ' + (topToken.momentum || 0).toFixed(1) + ')';
                }

            } catch (err) {
                console.warn('Pump trending fetch failed:', err);
                showPumpLoading('⚠️ Could not reach the pump feed: ' + String(err));
            }
        }

        // Hydrate on load, then refresh every 60 seconds.
        loadPumpTrending();
        setInterval(loadPumpTrending, POLL_MS);
    }

    // ---------- DexScreener Top Pairs ----------
    // Homepage table of top trading pairs from DexScreener.
    // Polls /api/dexscreener/top every 60s and renders the results into the
    // DexScreener table body. Each row shows rank, coin info, price, 24h
    // change (green/red), volume, and a Buy button linking to DexScreener.
    function loadDexScreener() {
        const tbody = document.getElementById('dexBody');
        if (!tbody) return;
        fetch('/api/dexscreener/top')
            .then(r => r.json())
            .then(data => {
                tbody.innerHTML = '';
                data.forEach((coin, i) => {
                    const tr = document.createElement('tr');
                    const change = coin.change_24h || 0;
                    const color = change >= 0 ? '#00B894' : '#E17055';
                    const risk = coin.risk_score || { score: 0, risk_level: 'Unknown', emoji: '⚪' };
                    const riskClass = risk.risk_level.toLowerCase();
                    const riskHtml = `<span class="risk-badge risk-${riskClass}">${risk.emoji} ${risk.risk_level}</span>`;
                    tr.innerHTML = `
                        <td>${i+1}</td>
                        <td><strong>${coin.symbol}</strong><br><small>${coin.name}</small></td>
                        <td>$${coin.price.toFixed(6)}</td>
                        <td style="color:${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
                        <td>$${(coin.volume_24h/1e6).toFixed(2)}M</td>
                        <td>${riskHtml}</td>
                        <td><a href="${coin.url}" target="_blank" class="buy-btn">Buy</a></td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(() => {
                tbody.innerHTML = '<tr><td colspan="7">Error loading DexScreener data</td></tr>';
            });
    }

    // ---------- GeckoTerminal Top Pools ----------
    // Homepage table of top pools from GeckoTerminal.
    // Polls /api/geckoterminal/top every 60s and renders the results into the
    // GeckoTerminal table body. Same layout as the DexScreener table.
    function loadGeckoTerminal() {
        const tbody = document.getElementById('geckoBody');
        if (!tbody) return;
        fetch('/api/geckoterminal/top')
            .then(r => r.json())
            .then(data => {
                tbody.innerHTML = '';
                data.forEach((coin, i) => {
                    const tr = document.createElement('tr');
                    const change = coin.change_24h || 0;
                    const color = change >= 0 ? '#00B894' : '#E17055';
                    const risk = coin.risk_score || { score: 0, risk_level: 'Unknown', emoji: '⚪' };
                    const riskClass = risk.risk_level.toLowerCase();
                    const riskHtml = `<span class="risk-badge risk-${riskClass}">${risk.emoji} ${risk.risk_level}</span>`;
                    tr.innerHTML = `
                        <td>${i+1}</td>
                        <td><strong>${coin.symbol}</strong><br><small>${coin.name}</small></td>
                        <td>$${coin.price.toFixed(6)}</td>
                        <td style="color:${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
                        <td>$${(coin.volume_24h/1e6).toFixed(2)}M</td>
                        <td>${riskHtml}</td>
                        <td><a href="${coin.url}" target="_blank" class="buy-btn">Buy</a></td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(() => {
                tbody.innerHTML = '<tr><td colspan="7">Error loading GeckoTerminal data</td></tr>';
            });
    }

    // ---------- GMGN Top 10 ----------
    // Homepage table of top tokens from GMGN.
    // Polls /api/gmgn/top every 60s and renders the results into the
    // GMGN table body. Same layout as the DexScreener and GeckoTerminal tables.
    function loadGmgn() {
        const tbody = document.getElementById('gmgnBody');
        if (!tbody) return;
        fetch('/api/gmgn/top')
            .then(r => r.json())
            .then(data => {
                tbody.innerHTML = '';
                data.forEach((coin, i) => {
                    const tr = document.createElement('tr');
                    const change = coin.change_24h || 0;
                    const color = change >= 0 ? '#00B894' : '#E17055';
                    const risk = coin.risk_score || { score: 0, risk_level: 'Unknown', emoji: '⚪' };
                    const riskClass = risk.risk_level.toLowerCase();
                    const riskHtml = `<span class="risk-badge risk-${riskClass}">${risk.emoji} ${risk.risk_level}</span>`;
                    tr.innerHTML = `
                        <td>${i+1}</td>
                        <td><strong>${coin.symbol}</strong><br><small>${coin.name}</small></td>
                        <td>$${coin.price.toFixed(6)}</td>
                        <td style="color:${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
                        <td>$${(coin.volume_24h/1e6).toFixed(2)}M</td>
                        <td>${riskHtml}</td>
                        <td><a href="${coin.url}" target="_blank" class="buy-btn">Buy</a></td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(() => {
                tbody.innerHTML = '<tr><td colspan="7">Error loading GMGN data</td></tr>';
            });
    }

    // ---------- DEXTools Top 10 ----------
    // Homepage table of top trending tokens from DEXTools.
    // Polls /api/dextools/top every 60s and renders the results into the
    // DEXTools table body. Same layout as the DexScreener, GeckoTerminal
    // and GMGN tables.
    function loadDextools() {
        const tbody = document.getElementById('dextoolsBody');
        if (!tbody) return;
        fetch('/api/dextools/top')
            .then(r => r.json())
            .then(data => {
                tbody.innerHTML = '';
                data.forEach((coin, i) => {
                    const tr = document.createElement('tr');
                    const change = coin.change_24h || 0;
                    const color = change >= 0 ? '#00B894' : '#E17055';
                    const risk = coin.risk_score || { score: 0, risk_level: 'Unknown', emoji: '⚪' };
                    const riskClass = risk.risk_level.toLowerCase();
                    const riskHtml = `<span class="risk-badge risk-${riskClass}">${risk.emoji} ${risk.risk_level}</span>`;
                    tr.innerHTML = `
                        <td>${i+1}</td>
                        <td><strong>${coin.symbol}</strong><br><small>${coin.name}</small></td>
                        <td>$${coin.price.toFixed(6)}</td>
                        <td style="color:${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
                        <td>$${(coin.volume_24h/1e6).toFixed(2)}M</td>
                        <td>${riskHtml}</td>
                        <td><a href="${coin.url}" target="_blank" class="buy-btn">Buy</a></td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(() => {
                tbody.innerHTML = '<tr><td colspan="7">Error loading DEXTools data</td></tr>';
            });
    }

    // ---------- Birdeye Top 10 ----------
    // Homepage table of top trending tokens from Birdeye.
    // Polls /api/birdeye/top every 60s and renders the results into the
    // Birdeye table body. Same layout as the DexScreener, GeckoTerminal,
    // GMGN and DEXTools tables.
    function loadBirdeye() {
        const tbody = document.getElementById('birdeyeBody');
        if (!tbody) return;
        fetch('/api/birdeye/top')
            .then(r => r.json())
            .then(data => {
                tbody.innerHTML = '';
                data.forEach((coin, i) => {
                    const tr = document.createElement('tr');
                    const change = coin.change_24h || 0;
                    const color = change >= 0 ? '#00B894' : '#E17055';
                    const risk = coin.risk_score || { score: 0, risk_level: 'Unknown', emoji: '⚪' };
                    const riskClass = risk.risk_level.toLowerCase();
                    const riskHtml = `<span class="risk-badge risk-${riskClass}">${risk.emoji} ${risk.risk_level}</span>`;
                    tr.innerHTML = `
                        <td>${i+1}</td>
                        <td><strong>${coin.symbol}</strong><br><small>${coin.name}</small></td>
                        <td>$${coin.price.toFixed(6)}</td>
                        <td style="color:${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
                        <td>$${(coin.volume_24h/1e6).toFixed(2)}M</td>
                        <td>${riskHtml}</td>
                        <td><a href="${coin.url}" target="_blank" class="buy-btn">Buy</a></td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(() => {
                tbody.innerHTML = '<tr><td colspan="7">Error loading Birdeye data</td></tr>';
            });
    }

    // ---------- DexPaprika Top 10 ----------
    // Homepage table of top trending tokens from DexPaprika.
    // Polls /api/dexpaprika/top every 60s and renders the results into the
    // DexPaprika table body. Same layout as the other Top 10 tables.
    function loadDexpaprika() {
        const tbody = document.getElementById('dexpaprikaBody');
        if (!tbody) return;
        fetch('/api/dexpaprika/top')
            .then(r => r.json())
            .then(data => {
                tbody.innerHTML = '';
                data.forEach((coin, i) => {
                    const tr = document.createElement('tr');
                    const change = coin.change_24h || 0;
                    const color = change >= 0 ? '#00B894' : '#E17055';
                    const risk = coin.risk_score || { score: 0, risk_level: 'Unknown', emoji: '⚪' };
                    const riskClass = risk.risk_level.toLowerCase();
                    const riskHtml = `<span class="risk-badge risk-${riskClass}">${risk.emoji} ${risk.risk_level}</span>`;
                    tr.innerHTML = `
                        <td>${i+1}</td>
                        <td><strong>${coin.symbol}</strong><br><small>${coin.name}</small></td>
                        <td>$${coin.price.toFixed(6)}</td>
                        <td style="color:${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
                        <td>$${(coin.volume_24h/1e6).toFixed(2)}M</td>
                        <td>${riskHtml}</td>
                        <td><a href="${coin.url}" target="_blank" class="buy-btn">Buy</a></td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(() => {
                tbody.innerHTML = '<tr><td colspan="7">Error loading DexPaprika data</td></tr>';
            });
    }

    // ---------- three.ws Top 10 ----------
    // Homepage table of top trending tokens from three.ws.
    // Polls /api/threews/top every 60s and renders the results into the
    // three.ws table body. Same layout as the other Top 10 tables.
    function loadThreews() {
        const tbody = document.getElementById('threewsBody');
        if (!tbody) return;
        fetch('/api/threews/top')
            .then(r => r.json())
            .then(data => {
                tbody.innerHTML = '';
                data.forEach((coin, i) => {
                    const tr = document.createElement('tr');
                    const change = coin.change_24h || 0;
                    const color = change >= 0 ? '#00B894' : '#E17055';
                    const risk = coin.risk_score || { score: 0, risk_level: 'Unknown', emoji: '⚪' };
                    const riskClass = risk.risk_level.toLowerCase();
                    const riskHtml = `<span class="risk-badge risk-${riskClass}">${risk.emoji} ${risk.risk_level}</span>`;
                    tr.innerHTML = `
                        <td>${i+1}</td>
                        <td><strong>${coin.symbol}</strong><br><small>${coin.name}</small></td>
                        <td>$${coin.price.toFixed(6)}</td>
                        <td style="color:${color}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
                        <td>$${(coin.volume_24h/1e6).toFixed(2)}M</td>
                        <td>${riskHtml}</td>
                        <td><a href="${coin.url}" target="_blank" class="buy-btn">Buy</a></td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(() => {
                tbody.innerHTML = '<tr><td colspan="7">Error loading three.ws data</td></tr>';
            });
    }

    // Load all seven tables on page load and every 60 seconds
    loadDexScreener();
    loadGeckoTerminal();
    loadGmgn();
    loadDextools();
    loadBirdeye();
    loadDexpaprika();
    loadThreews();
    setInterval(loadDexScreener, 60000);
    setInterval(loadGeckoTerminal, 60000);
    setInterval(loadGmgn, 60000);
    setInterval(loadDextools, 60000);
    setInterval(loadBirdeye, 60000);
    setInterval(loadDexpaprika, 60000);
    setInterval(loadThreews, 60000);
})();
