# Diagnostics & Troubleshooting Runbook

## Diagnostic Commands
Run `hydro-db-check.sh` on the reTerminal SBC to verify:
- SQLite database integrity (`PRAGMA quick_check;`).
- Table counts and recent alarm logs.
- Solution tank capacities and remaining volumes.
