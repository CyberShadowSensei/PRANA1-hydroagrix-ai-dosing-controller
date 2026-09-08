# Performance & Stress Benchmark Matrix

| Benchmark | Load Profile | Metric Target | Result |
| :--- | :--- | :--- | :--- |
| Sequential Report Generation | 50 consecutive calls | p95 < 200ms | 0.82ms (PASS) |
| Concurrent Request Callers | 30 concurrent threads | p95 < 300ms | 1.84ms (PASS) |
| Background SMTP Failures | 20 concurrent errors | 0 DB lockups | 100% (PASS) |
