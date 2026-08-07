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

    if (statsGrid) {
        const POLL_MS = 60000; // 60 seconds

        function formatCurrency(value) {
            if (value === null || value === undefined || isNaN(Number(value))) return '$0.00';
            const n = Number(value);
            if (!n) return '$0.00';

            // Format with commas and 2 decimal places for large numbers
            const opts = {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            };

            // For very large numbers (billions+), use compact notation
            if (Math.abs(n) >= 1e12) {
                opts.notation = 'compact';
                opts.maximumFractionDigits = 1;
            } else if (Math.abs(n) >= 1e9) {
                opts.notation = 'compact';
                opts.maximumFractionDigits = 2;
            }

            return n.toLocaleString('en-US', opts);
        }

        function formatPercentage(value) {
            if (value === null || value === undefined || isNaN(Number(value))) return '0.0%';
            const n = Number(value);
            return n.toFixed(1) + '%';
        }

        function updateStats(data) {
            // Update each stat card
            document.getElementById('totalMarketCap').textContent = formatCurrency(data.total_market_cap);
            document.getElementById('totalVolume').textContent = formatCurrency(data.total_volume);
            document.getElementById('btcDominance').textContent = formatPercentage(data.btc_dominance);
            document.getElementById('ethDominance').textContent = formatPercentage(data.eth_dominance);

            // Update timestamp
            if (statsUpdated) {
                statsUpdated.textContent = 'Updated ' +
                    new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) +
                    ' · auto-refreshes every 60s';
            }
        }

        async function loadQuickStats() {
            try {
                const res = await fetch('/api/quick-stats', {cache: 'no-store'});
                if (!res.ok) throw new Error('Quick stats API returned ' + res.status);
                const data = await res.json();
                updateStats(data);
            } catch (err) {
                console.warn('Quick stats fetch failed:', err);
                // Keep showing last data or placeholders on error
            }
        }

        // Load immediately, then refresh every 60 seconds
        loadQuickStats();
        setInterval(loadQuickStats, POLL_MS);
    }

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

    // ---------- 3h Chart with Moving Averages ----------
    // Homepage interactive chart showing price action and moving averages.
    // Loads Plotly.js from CDN and renders a line chart with price, 3h MA, and 10h MA.
    // Updates when coin selection changes or refresh button is clicked.
    const chartContainer = document.getElementById('chartContainer');
    const chartLoading = document.getElementById('chartLoading');
    const chartCoinSelect = document.getElementById('chartCoinSelect');
    const chartRefreshBtn = document.getElementById('chartRefreshBtn');

    if (chartContainer) {
        // Load Plotly.js from CDN
        let plotlyLoaded = false;
        let plotlyScript = null;

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
        }

        function hideLoading() {
            if (chartLoading) chartLoading.style.display = 'none';
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
                const ma3h = data.ma_3h.filter(item => item !== null);
                const ma10h = data.ma_10h.filter(item => item !== null);

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
                if (ma3h.length > 0) {
                    traces.push({
                        x: timestamps.slice(3), // MA starts after 3 periods
                        y: ma3h,
                        type: 'scatter',
                        mode: 'lines',
                        name: '3h MA',
                        line: { color: '#ff7f0e', dash: 'dash' }
                    });
                }

                if (ma10h.length > 0) {
                    traces.push({
                        x: timestamps.slice(10), // MA starts after 10 periods
                        y: ma10h,
                        type: 'scatter',
                        mode: 'lines',
                        name: '10h MA',
                        line: { color: '#2ca02c', dash: 'dot' }
                    });
                }

                // Plot layout
                const layout = {
                    title: `${symbol.toUpperCase()} Price Chart with Moving Averages`,
                    xaxis: {
                        title: 'Time',
                        rangeslider: { visible: false },
                        type: 'date'
                    },
                    yaxis: {
                        title: 'Price (USD)',
                        fixedrange: false
                    },
                    showlegend: true,
                    legend: {
                        x: 0,
                        y: 1.1,
                        orientation: 'h'
                    },
                    margin: { t: 50, r: 20, b: 50, l: 50 },
                    hovermode: 'closest',
                    plot_bgcolor: '#f8f9fa',
                    paper_bgcolor: '#ffffff'
                };

                // Render chart
                Plotly.newPlot(chartContainer, traces, layout, {
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false
                });

                hideLoading();

            } catch (error) {
                console.error('Chart loading failed:', error);
                hideLoading();
                chartContainer.innerHTML = `
                    <div class="chart-error">
                        <p>⚠️ Failed to load chart: ${error.message}</p>
                        <p>Please try refreshing the page or selecting a different coin.</p>
                    </div>
                `;
            }
        }

        // Event listeners
        if (chartCoinSelect) {
            chartCoinSelect.addEventListener('change', function() {
                loadChart(this.value);
            });
        }

        if (chartRefreshBtn) {
            chartRefreshBtn.addEventListener('click', function() {
                const currentSymbol = chartCoinSelect ? chartCoinSelect.value : 'pepe';
                loadChart(currentSymbol);
            });
        }

        // Load initial chart
        const initialSymbol = chartCoinSelect ? chartCoinSelect.value : 'pepe';
        loadChart(initialSymbol);
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
                const ma3h = data.ma_3h.filter(item => item !== null);
                const ma10h = data.ma_10h.filter(item => item !== null);

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
                if (ma3h.length > 0) {
                    traces.push({
                        x: timestamps.slice(3), // MA starts after 3 periods
                        y: ma3h,
                        type: 'scatter',
                        mode: 'lines',
                        name: '3h MA',
                        line: { color: '#ff7f0e', dash: 'dash' }
                    });
                }

                if (ma10h.length > 0) {
                    traces.push({
                        x: timestamps.slice(10), // MA starts after 10 periods
                        y: ma10h,
                        type: 'scatter',
                        mode: 'lines',
                        name: '10h MA',
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
})();
