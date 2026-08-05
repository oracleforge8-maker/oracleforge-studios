"""OracleForge agents package.

Contains the autonomous agents:
- Scout:     Data scraping (Twitter, Pump.fun, CMC, Reddit, DEXScreener)
- Brain:     DeepSeek Flash AI processing (trends, content, replies)
- Forge:     DALL-E 3 image generation with SVG fallback
- Chronicler: SQLite storage, JSON archival, financial tracking, reports
- Social:    Twitter/Discord/LinkedIn autonomous posting

Each agent is independently runnable and isolated so a failure in one
does not take down the others.
"""