from playwright.sync_api import sync_playwright

def scrape_gmgn_trending():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://gmgn.ai/trending")
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
                coins.append({
                    'symbol': symbol.strip(),
                    'name': name.strip(),
                    'price': float(price),
                    'change_24h': float(change),
                    'volume_24h': float(volume),
                    'url': f"https://gmgn.ai{url}" if url else "#"
                })
            except Exception:
                continue
        browser.close()
        return coins