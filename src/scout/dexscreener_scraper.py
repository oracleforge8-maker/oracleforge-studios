import requests

def scrape_dexscreener_trending():
    # Use DexScreener's public API (no Cloudflare blocking)
    url = "https://api.dexscreener.com/latest/dex/search?q=meme"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"API error: {e}")
        return []
    
    pairs = data.get('pairs', [])
    if not pairs:
        print("No pairs found in API response")
        return []
    
    coins = []
    for pair in pairs[:10]:
        try:
            base = pair.get('baseToken', {})
            price = float(pair.get('priceUsd', 0))
            change = float(pair.get('priceChange', {}).get('h24', 0))
            volume = float(pair.get('volume', {}).get('h24', 0))
            
            coins.append({
                'symbol': base.get('symbol', '?').upper(),
                'name': base.get('name', ''),
                'price': price,
                'change_24h': change,
                'volume_24h': volume,
                'url': pair.get('url', '#')
            })
        except Exception:
            continue
    
    print(f"Searching for 'meme' keyword - Found {len(coins)} coins via API")
    return coins