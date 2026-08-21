# Hydroagrix AI Dosing Controller

> **Autonomous closed-loop hydroponics engine powering reTerminal SBCs with real-time Nernst sensor calibration, computer vision crop stage classification, and adaptive dosing.**

---

## System Highlights

* **500ms Control Loop**: Continuous high-frequency telemetry polling and real-time Socket.IO streaming.
* **Closed-Loop Dosing**: Self-calibrating Nernst-compensated EC & pH dosing with automatic pump efficacy estimation.
* **Computer Vision Edge Classifier**: Hybrid OpenCV HSV color coverage analysis and YOLO stage detection via V4L2 USB camera.
* **221 Passing Automated Tests**: 195 backend Pytest suite + 26 frontend Vitest UI component tests.
* **Production-Grade SBC Deployment**: Pre-configured systemd daemons, hot-patch deployment scripts, and CLI database diagnostics (`hydro-db-check.sh`).

---

## System Architecture

```mermaid
graph TD
    A[EC & pH Sensors] --> B[ManualADC SMBus 0x04 via I2C]
    B --> C[sensors.py Telemetry Engine]
    C --> D[routes.py Flask API & Socket.IO]
    D --> E[SQLite EventLog & PumpLog]
    D --> F[system_config.json Stage Limits]
    G[USB Camera V4L2] --> H[camera_ml.py Growth Classifier]
    H --> I[Update PlantStageStatus DB]
    I --> F
    D --> J[React Frontend Dashboard UI]
    J --> D
    D --> K[hal.py Hardware Abstraction Layer]
    K --> L[4x Peristaltic Pumps Nutrients A/B, pH UP/DOWN]
```

---

## System Capabilities

### Autonomous Dosing & Closed-Loop Control
- **Dynamic Delta Dosing**: Automatically calculates target chemical deltas, reservoir volumes (L), and calibrated pump flow rates (mL/s) for precise dosing.
- **Self-Learning Calibration**: Evaluates post-dosing sensor deltas against mathematical predictions after mixing cooldowns to adjust dosing factors automatically.
- **Crop Cycle Management**: Tracks crop growth timelines (Tomatoes, Lettuce, Basil, Custom), managing phase transitions and active target boundaries.

### High-Precision Sensing & Edge Vision
- **Nernst Temperature Compensation**: Multi-point piecewise linear interpolation for EC and pH sensor probes with DS18B20 water temperature compensation.
- **Edge Vision Classification**: Captures USB camera feeds (`/dev/video0`) with HSV leaf coverage ratio analysis for growth stage tracking.
- **Real-Time Telemetry Stream**: Emits 500ms Socket.IO sensor telemetry and live base64 camera frames to web clients.

### Safety, Monitoring & Diagnostics
- **Multi-Tiered Safety Bounds**: Triggers immediate emergency halts for out-of-bound readings (pH < 3.0 or > 10.0, EC >= 8.0 mS/cm).
- **Debounced Email Alerts**: Dispatches automated notifications for high EC conditions, tank depletion, and system exceptions with backoff timers.
- **CLI Database Diagnostics**: Native `hydro-db-check.sh` utility to inspect SQLite WAL journal status, table row counts, and warning/danger event logs.

---

## Deployment Tools

- **`deploy_full.ps1`**: Full-stack PowerShell deployment runner (executes pytest suite, builds Vite frontend production bundle, packages tarball, transfers via SCP, updates DB schemas, reloads systemd).
- **`deploy_quick.ps1`**: Fast hot-patch script for transferring modified backend modules and compiled frontend assets in seconds.
- **`hydro-db-check.sh`**: Command-line database health diagnostic script deployed to `~/hydro-db-check.sh` on target SBC hardware.
- **`start_reterminal.sh`**: Hardware environment initialization and startup wrapper script.
- **`systemd/hydro-backend.service`**: Systemd daemon configuration for the Flask/Socket.IO backend server.
- **`systemd/hydro-frontend.service`**: Systemd daemon configuration for serving the React web dashboard.

---

## Test Verification

The codebase features 221 total passing automated tests:

### Backend Pytest Suite (195 Tests)
- **HAL Hardware Layer (`test_hal.py`)**: Hardware mocks, ADC channel validation, L298N pump lock reentrancy, DS18B20 1-Wire parsing.
- **Dosing & Safety Control (`test_dosing.py`, `test_new_dosing.py`, `test_mid_dose_cutoff.py`)**: Volume calculations, runtime clamping (2s-300s), cooldown timers, mid-dose cutoffs.
- **REST APIs & Routes (`test_api.py`, `test_api_dosing.py`, `test_api_plants.py`)**: Endpoint payloads, pump priming, crop preset selection, cycle completion.
- **Grow Cycles & Persistence (`test_grow_cycle.py`, `test_models.py`, `test_new_features.py`)**: Phase duration resolution, cumulative start day inference, DB model integrity.
- **Alerts & System Stress (`test_alerts.py`, `test_performance_stress.py`)**: High-EC debouncing, email queue resilience, concurrent DB lock benchmarks.

### Frontend Vitest Suite (26 Tests)
- **UI Components (`Dashboard.test.jsx`, `GlobalHUD.test.jsx`, `QuickCameraWidget.test.jsx`)**: Gauge rendering, state badges, camera fallbacks.
- **Preset Management (`PlantPresets.test.jsx`, `PresetManagerModal.test.jsx`, `GrowCycleBanner.test.jsx`)**: Timeline visualization, form submissions, manual pump overrides.

### Running Tests
- **Backend Tests**: `cd backend && python -m pytest -v --tb=short -p no:cacheprovider`
- **Frontend Tests**: `cd frontend && npm test`

---

## Tech Stack

- **Backend**: Python 3.10+ (Flask, Flask-SocketIO, SQLAlchemy, smbus2)
- **Frontend**: Node.js v18+ (React 18, Vite, TailwindCSS, Chart.js, Socket.IO Client)
- **Hardware Target**: Raspberry Pi / Seeed reTerminal (Linux SBC with I2C bus enabled)
- **Service Management**: systemd

---

## Quick Start & Operations

### Installation
- **Clone Repository**: `git clone https://github.com/CyberShadowSensei/hydroagrix-ai-dosing-controller.git`
- **Backend Setup**: `cd backend && pip install -r requirements.txt`
- **Frontend Setup**: `cd frontend && npm install`

### Runtime Commands (Target Device)
- **Restart Services**: `sudo systemctl restart hydro-backend.service hydro-frontend.service`
- **View Live Logs**: `sudo journalctl -u hydro-backend.service -f`
- **Run DB Diagnostics**: `~/hydro-db-check.sh`

---

## License & Copyright

Copyright (c) 2026 Hydroagrix AI / CyberShadowSensei. All Rights Reserved.

**PROPRIETARY AND CONFIDENTIAL.**

Unauthorized copying, reproduction, distribution, modification, sublicensing, or use of this software and associated documentation, via any medium or in any form, is strictly prohibited. See [`LICENSE`](file:///E:/Hydroagrix%20Ai/Ai%20Dosing%20Unit/LICENSE) for full legal terms.
