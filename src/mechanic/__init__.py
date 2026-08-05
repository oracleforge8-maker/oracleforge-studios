"""OracleForge Studios — The Mechanic.

Self-healing agent that receives health reports from The Watchtower and
automatically repairs common issues:

- ``repair_engine``       — applies fixes (restart, retry, rotate, clear)
- ``escalation_manager``  — escalates to a human when repair fails

The Mechanic logs every repair attempt and outcome to the database so the
Observatory dashboard can show full transparency.
"""