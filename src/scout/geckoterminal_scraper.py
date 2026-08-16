from playwright.sync_api import sync_playwright


def scrape_geckoterminal_trending():
    """Scrape trending tokens from GeckoTerminal.
    
    Returns:
        List of dicts with token data: symbol, name, price, change_24h, 
        volume_24h, url.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.geckoterminal.com/trending")
        page.wait_for_selector("table", timeout=10000)
        tokens = []
        rows = page.query_selector_all("tbody tr")
        for row in rows[:10]:
            try:
                symbol = row.query_selector(".token-symbol").inner_text()
                name = row.query_selector(".token-name").inner_text()
                price = row.query_selector(".price").inner_text().replace('$', '').replace(',', '')
                change = row.query_selector(".change").inner_text().replace('%', '').replace('+', '')
                volume = row.query_selector(".volume").inner_text().replace('$', '').replace(',', '')
                url = row.query_selector("a").get_attribute("href")
                tokens.append({
                    'symbol': symbol.strip(),
                    'name': name.strip(),
                    'price': float(price),
                    'change_24h': float(change),
                    'volume_24h': float(volume),
                    'url': f"https://www.geckoterminal.com{url}" if url else "#"
                })
            except Exception:
                continue
        browser.close()
        return tokens