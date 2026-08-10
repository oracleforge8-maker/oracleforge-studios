from playwright.sync_api import sync_playwright

def _calculate_risk_score(liquidity, holders, price_change_abs):
    score = 0
    if liquidity > 100000:
        score += 20
    if holders > 1000:
        score += 20
    if price_change_abs < 50:
        score += 20
    # Cap at 100
    score = min(score, 100)
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
        for row in rows[:10]:
            try:
                symbol = row.query_selector(".token-symbol").inner_text()
                name = row.query_selector(".token-name").inner_text()
                price = row.query_selector(".price").inner_text().replace('$', '').replace(',', '')
                change = row.query_selector(".change").inner_text().replace('%', '').replace('+', '')
                volume = row.query_selector(".volume").inner_text().replace('$', '').replace(',', '')
                url = row.query_selector("a").get_attribute("href")
                # Try to scrape liquidity and holders (if available)
                liquidity = 0
                holders = 0
                try:
                    liquidity_text = row.query_selector(".liquidity").inner_text().replace('$', '').replace(',', '')
                    liquidity = float(liquidity_text) if liquidity_text else 0
                except:
                    pass
                try:
                    holders_text = row.query_selector(".holders").inner_text().replace(',', '')
                    holders = int(holders_text) if holders_text else 0
                except:
                    pass
                price_change_abs = abs(float(change))
                risk_score = _calculate_risk_score(liquidity, holders, price_change_abs)
                coins.append({
                    'symbol': symbol.strip(),
                    'name': name.strip(),
                    'price': float(price),
                    'change_24h': float(change),
                    'volume_24h': float(volume),
                    'url': f"https://dexscreener.com{url}" if url else "#",
                    'risk_score': risk_score
                })
            except Exception:
                continue
        browser.close()
        return coins