# Security & Secrets Management Standards

## Secret Storage Policy
- Passwords and SMTP tokens must reside exclusively in `email_config.json`.
- `email_config.json` and `system_config.json` are excluded from version control via `.gitignore`.
- Configuration files use atomic temp-file replace (`os.replace`) to prevent corruption.
