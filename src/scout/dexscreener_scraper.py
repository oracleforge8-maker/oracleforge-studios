from playwright.sync_api import sync_playwright

def _is_usd_pair(symbol: str) -> bool:
    """Check if a trading pair symbol is a USD/USDT/USDC pair.
    
    Args:
        symbol: The trading pair symbol (e.g., "PEPE/USDT", "ETH/USDC").
    
    Returns:
        True if the symbol ends with /USD, /USDT, or /USDC.
    """
    symbol_upper = symbol.strip().upper()
    return symbol_upper.endswith('/USD') or symbol_upper.endswith('/USDT') or symbol_upper.endswith('/USDC')


def _calculate_risk_score(liquidity: float, holders: int, change_24h: float) -> dict:
    """Calculate a simple Risk Score based on token metrics.
    
    Args:
        liquidity: Liquidity in USD.
        holders: Number of holders.
        change_24h: 24h price change percentage.
    
    Returns:
        Dict with score (0-100), risk_level, emoji, and details.
    """
    score = 0
    
    # Liquidity check: > $100,000 → +20 points
    if liquidity > 100000:
        score += 20
    
    # Holders check: > 1,000 → +20 points
    if holders > 1000:
        score += 20
    
    # Price change check: < 50% → +20 points
    if abs(change_24h) < 50:
        score += 20
    
    # Cap at 100
    score = min(score, 100)
    
    # Determine risk level
    if score >= 80:
        risk_level = "Low"
        emoji = "🟢"
    elif score >= 50:
        risk_level = "Medium"
        emoji = "🟡"
    else:
        risk_level = "High"
        emoji = "🔴"
    
    return {
        "score": score,
        "risk_level": risk_level,
        "emoji": emoji
    }


def scrape_dexscreener_trending():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://dexscreener.com/trending")
        page.wait_for_selector("table", timeout=10000)
        coins = []
        rows = page.query_selector_all("tbody tr")
        for row in rows:
            try:
                symbol = row.query_selector(".token-symbol").inner_text()
                # Filter for USD pairs only
                if not _is_usd_pair(symbol):
                    continue
                    
                name = row.query_selector(".token-name").inner_text()
                price = row.query_selector(".price").inner_text().replace('$', '').replace(',', '')
                change = row.query_selector(".change").inner_text().replace('%', '').replace('+', '')
                volume = row.query_selector(".volume").inner_text().replace('$', '').replace(',', '')
                url = row.query_selector("a").get_attribute("href")
                
                # Extract liquidity if available on the row
                liquidity = 0.0
                liquidity_elem = row.query_selector(".liquidity")
                if liquidity_elem:
                    liquidity_text = liquidity_elem.inner_text().replace('$', '').replace(',', '')
                    try:
                        liquidity = float(liquidity_text)
                    except ValueError:
                        liquidity = 0.0
                
                # Extract holders if available on the row
                holders = 0
                holders_elem = row.query_selector(".holders")
                if holders_elem:
                    holders_text = holders_elem.inner_text().replace(',', '')
                    try:
                        holders = int(holders_text)
                    except ValueError:
                        holders = 0
                
                # Calculate risk score
                risk_data = _calculate_risk_score(liquidity, holders, float(change))
                
                coins.append({
                    'symbol': symbol.strip(),
                    'name': name.strip(),
                    'price': float(price),
                    'change_24h': float(change),
                    'volume_24h': float(volume),
                    'liquidity': liquidity,
                    'holders': holders,
                    'url': f"https://dexscreener.com{url}" if url else "#",
                    'risk_score': risk_data
                })
                # Stop once we have 10 USD pairs
                if len(coins) >= 10:
                    break
            except Exception:
                continue
        browser.close()
        return coins
