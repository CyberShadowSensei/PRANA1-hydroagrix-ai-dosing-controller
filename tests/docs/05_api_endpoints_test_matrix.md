# REST API Endpoint Test Matrix

| Route | Method | Test Verification |
| :--- | :--- | :--- |
| `/api/dosing_config` | GET/POST | Universal mL/min & mL/s conversion |
| `/get_tank_levels` | GET | Direct DB query with LRU write-through cache |
| `/refill_tank` | POST | Volume reset and blocked attempt clearing |
