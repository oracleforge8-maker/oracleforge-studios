"""OracleForge Studios — The Watchtower.

Health monitoring agent that runs on a schedule and produces structured,
color-coded health reports:

- ``health_checker`` — runs all checks (API, DB, social, website, logs)
- ``reporter``       — builds structured reports + persists history
- ``dashboard_api``  — exposes health data to the Observatory dashboard

The Watchtower feeds The Mechanic (repair) and the Observatory (human view).
"""