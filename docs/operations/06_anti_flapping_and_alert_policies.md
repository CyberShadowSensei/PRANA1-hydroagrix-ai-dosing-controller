# Anti-Flapping & Email Notification Policies

## Alert Rate Limiting
- **Critical Alerts**: Dispatched immediately on first occurrence with bypass cooldown.
- **Subsequent Faults**: Throttled to 1 email per hour.
- **Recovery Notifications**: Enforce a strict 1-hour quiet period between resolutions.
- **Empty Tank Backoff**: Exponential progression (Immediate, 1h, 4h, 12h, 24h).
