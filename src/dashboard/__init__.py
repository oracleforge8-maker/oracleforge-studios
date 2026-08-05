"""OracleForge Studios — The Observatory.

Secure human-oversight dashboard:

- ``server`` — Flask app with basic auth + sessions, 7 pages, JSON APIs,
  and Server-Sent Events (SSE) for real-time health updates.
- Templates + static assets live under ``dashboard/``.

The dashboard lets a human:
- View real-time health status (green/yellow/red)
- See the activity feed of recent agent actions
- Pause/resume agents, trigger manual runs, adjust parameters
- Review financial metrics
- Access the encrypted credential vault (with master password)
"""