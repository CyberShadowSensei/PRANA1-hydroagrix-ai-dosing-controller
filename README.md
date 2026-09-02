<!-- Hydroagrix Automated Smart Dosing & Nutrient Controller (Production Grade) -->
# Prana 1: The AI-Enabled Nutrient Dosing Unit

> **An autonomous, self-learning hydroponic engine engineered to eliminate human error in precision agriculture.**
> Prana 1 transforms volatile hydroponic reservoirs into stable, mathematically predictable environments using edge computer vision, closed-loop feedback algorithms, and high-frequency sensor telemetry.

> Detailed developer onboarding, architectural specs, and API endpoints are available in [`DOCUMENTATION.md`](file:///E:/Hydroagrix%20Ai/Ai%20Dosing%20Unit/DOCUMENTATION.md).

---

## The Engineering Challenge & Our Solution

In precision hydroponics, environmental volatility is the enemy. A sudden 0.5 drift in pH can instantly lock out critical nutrient absorption, stalling crop growth. Commercial analog sensors experience thermal drift, peristaltic pumps degrade over time causing unpredictable flow rates, and crops demand entirely different chemical balances depending on their real-time physiological growth stage.

**Prana 1** is designed to master these complexities at the edge:
1. **It sees the crop:** Using V4L2 USB cameras and hybrid HSV/YOLO computer vision, it classifies the exact growth stage of the plant (e.g., Vegetative vs. Flowering) and dynamically shifts the dosing targets to match the plant's immediate biological needs.
2. **It calibrates reality:** It reads raw I2C analog signals at 500ms intervals and mathematically reconstructs accurate pH and EC values, actively compensating for thermal drift using the Nernst equation and multi-point piecewise linear interpolation.
3. **It learns its own hardware:** After calculating and dispensing a precise milliliter dose, the system waits for the chemical reaction to stabilize, measures the actual sensor delta against its mathematical prediction, and automatically adjusts its internal pump efficacy models to compensate for real-world hardware wear and tear.

This is a highly fault-tolerant, self-healing control system built for the harsh realities of agricultural automation.

---

## System Architecture & Data Flow

Prana 1's architecture is organized into distinct, decoupled subsystems for telemetry, closed-loop actuation, edge intelligence, and operator interaction.

### 1. High-Level System & Edge Hardware Topology

```mermaid
flowchart TB
    subgraph SENSORS ["Analog & Digital Sensing"]
        direction TB
        EC_PROBE["EC / TDS Analog Probe"] -->|Analog 0-3.3V| ADC["ManualADC (I2C 0x04)"]
        PH_PROBE["pH Analog Probe"] -->|Analog 0-3.3V| ADC
        TEMP_PROBE["DS18B20 Temp Probe"] -->|1-Wire /sys/bus/w1| HAL_DRV["HAL Driver Module"]
        DHT_PROBE["DHT22 Climate Sensor"] -->|GPIO BCM 5| HAL_DRV
        ADC -->|I2C SMBus 1| HAL_DRV
    end

    subgraph ACTUATORS ["Dosing Actuation"]
        direction TB
        L298N["L298N Dual H-Bridge Drivers"] -->|Channel 1-4| PUMPS["4x 12V Peristaltic Pumps\n(Nutrient A, B, pH UP, pH DOWN)"]
        HAL_DRV -->|GPIO BCM 18-27| L298N
    end

    subgraph VISION ["Computer Vision Pipeline"]
        CAM["USB Camera (/dev/video0)"] -->|V4L2 Capture| CV_ENGINE["OpenCV Frame Worker"]
        CV_ENGINE -->|Leaf Coverage Analysis| STAGE_DET["Growth Stage Classifier"]
    end

    subgraph CORE_BACKEND ["Embedded Controller (Python 3.10 / Flask / Socket.IO)"]
        direction TB
        HAL_DRV --> SENSORS_ENGINE["Telemetry & Calibration Engine\n(sensors.py)"]
        SENSORS_ENGINE -->|Piecewise Linear & Temp Comp| TRACKER["CirculationPlateauTracker\n(Drain Detection & RO Settle)"]
        TRACKER --> FETCH_DAEMON["500ms Realtime Fetch Loop\n(main.py)"]
        FETCH_DAEMON --> DOSING_ENGINE["Adaptive Dosing Controller\n(dosing.py)"]
        DOSING_ENGINE -->|Safe Pulse Execution| HAL_DRV
        
        STAGE_DET -->|Advisory Stage Telemetry| REST_API["Flask REST API Layer\n(routes.py)"]
        GROW_MGR["Grow Cycle Progression Helper\n(grow_cycle_helper.py)"] -->|Target Chemistry Bounds| DOSING_ENGINE
        
        FETCH_DAEMON -->|500ms Telemetry Stream| WS_SERVER["Flask-SocketIO Server"]
        CV_ENGINE -->|Live Camera Frames| WS_SERVER
        
        DOSING_ENGINE --> DB[("SQLite DB (WAL Mode)\n(mydatabase.db)")]
        REST_API --> DB
    end

    subgraph FRONTEND ["Operator Interface (React 18 / Vite / Tailwind)"]
        direction TB
        WS_SERVER <-->|WebSocket Stream| WS_CLIENT["Socket.IO Client Singleton\n(socket.js)"]
        WS_CLIENT --> DASHBOARD["Live HUD & Gauges\n(Dashboard.jsx)"]
        WS_CLIENT --> CAMERA_VIEW["Live Stream Widget\n(QuickCameraWidget.jsx)"]
        
        REST_API <-->|HTTP REST Requests| DASHBOARD
        REST_API <-->|HTTP REST Requests| PRESETS_MGR["Plant Presets Manager\n(PlantPresets.jsx)"]
        REST_API <-->|HTTP REST Requests| PUMP_CTRL["Manual Controls & Priming\n(Pump.jsx)"]
        REST_API <-->|HTTP REST Requests| SETTINGS["Configuration & Calibration\n(Settings.jsx)"]
    end
```

### 2. Closed-Loop Adaptive Dosing State Machine

```mermaid
stateDiagram-v2
    [*] --> IdleMonitoring: 500ms Telemetry Fetch

    state IdleMonitoring {
        [*] --> CheckDrainCycle
        CheckDrainCycle --> DosingPaused: is_drain_cycle == True
        CheckDrainCycle --> CheckBounds: is_drain_cycle == False
        CheckBounds --> EmergencyHalt: pH < 3.0 or > 10.0 OR EC >= 8.0 mS/cm
        CheckBounds --> CheckCooldown: Within Safe Limits
    }

    CheckCooldown --> InCooldown: Time < 15 Minutes
    CheckCooldown --> ReadyToDose: Cooldown Elapsed & Delta > Tolerance

    state DosingExecution {
        ReadyToDose --> CalcDose: Target Delta * Reservoir Vol * Nutrient Factor
        CalcDose --> ClampRuntime: Clamp to [2.0s min, 300.0s max]
        ClampRuntime --> RunPump: Pulse Selected Peristaltic Pump
        RunPump --> RecordPrediction: Store Expected Delta & Timestamp
    }

    DosingExecution --> MixingCooldown: Pump Pulse Complete

    state MixingCooldown {
        [*] --> AwaitCirculation: Wait 15-Minute Mixing Period
        AwaitCirculation --> DeferredCheck: Drain Cycle Active (Defer Eval)
        AwaitCirculation --> SelfTuningEval: Reservoir Stable Submerged
        SelfTuningEval --> UpdateFactor: Exponential Moving Average Recalibration
    }

    MixingCooldown --> IdleMonitoring: Recalibration Complete
    EmergencyHalt --> [*]: Locked Out (Requires Operator Intervention)
```

### 3. Flood-and-Drain Circulation Plateau Tracker Flow

```mermaid
flowchart TD
    RAW_IN["Raw EC Sensor Reading (500ms)"] --> SUB_CHECK{"Is Raw EC < Plateau - 0.6 mS/cm?"}

    SUB_CHECK -->|Yes: Probe Exposed to Air| DRAIN_DETECTED["Flag Drain Cycle Active\n(is_drain_cycle = True)"]
    DRAIN_DETECTED --> HOLD_PLATEAU["Hold Effective EC = Plateau Value"]
    HOLD_PLATEAU --> PAUSE_DOSING["Pause Dosing & Defer Calibration\n(Suppresses False Alarms)"]

    SUB_CHECK -->|No: Probe Submerged| LEVEL_CHECK{"Was System in Drain Cycle?"}
    
    LEVEL_CHECK -->|Yes: Water Returning| SETTLE_DELAY["Settle Counter Check\n(Require 20 ticks / 10s within 0.3 mS/cm)"]
    SETTLE_DELAY --> S_CHECK{"Settle Complete?"}
    S_CHECK -->|No| HOLD_PLATEAU
    S_CHECK -->|Yes| STABLE_RETURN["Set is_drain_cycle = False\nSet is_stable_plateau = True"]

    LEVEL_CHECK -->|No: Continuous Submersion| RO_CHECK{"Is Raw EC < 0.4 mS/cm & Stable for >15 mins?"}
    RO_CHECK -->|Yes: Fresh RO Water Refill| RO_ADAPT["Adapt Plateau to RO Baseline\n(Enable Dosing from Scratch)"]
    RO_CHECK -->|No| NORMAL_READING["Maintain Active Plateau\nNormal Adaptive Dosing Allowed"]
```

---

## Core System Features

### Autonomous Dosing & Closed-Loop Control
- **Dynamic Delta Dosing Algorithm**: The core engine calculates target chemical deltas, reservoir volumes in liters, and calibrated pump flow rates in mL/s to dispense micro-precise nutrient and pH adjustments.
- **Self-Learning Calibration (Auto-Tuning)**: Evaluates actual vs. predicted sensor deltas after a strict mixing cooldown period. If a pump under-delivers due to tube wear, the system recalculates and updates the efficacy multiplier for the next run.
- **Intelligent Crop Cycle Management**: Automatically tracks crop growth timelines (Tomatoes, Lettuce, Basil, or Custom presets), managing phase transitions and shifting target chemical boundaries without human intervention.

### Circulation Plateau Tracking & RO Water Auto-Detection
- **Flood-and-Drain Resilient Tracking**: In circulating hydroponic systems where water rotates between the tank and channels, probe dry exposure causes temporary EC drops (0.3–0.5 mS/cm). The `CirculationPlateauTracker` holds the true solution plateau EC, flags drain cycles, and pauses dosing until water returns and stabilizes.
- **Fresh RO Water Fill Detection**: Seamlessly distinguishes temporary drain drops from fresh pure water refills. If a reservoir is refilled with pure RO water, the tracker identifies the flat low baseline ($\Delta < 0.05$ over 15 mins) and adapts the plateau down, allowing automated dosing from scratch.
- **Deferred Adaptive Calibration**: Automatically defers self-tuning feedback evaluation during drain dips, preventing corrupted exponential moving average factors.

### High-Precision Sensing & Edge Vision
- **Nernst Temperature Compensation**: Analog probes are notoriously sensitive to water temperature. Prana 1 applies multi-point piecewise linear interpolation and active Nernst equation compensation using DS18B20 thermal readings to guarantee laboratory-grade accuracy.
- **Edge Vision Classification**: A dedicated background pipeline captures USB camera feeds, analyzing HSV leaf coverage ratios to determine if the crop is in germination, vegetative, or flowering stages.
- **Ultra-Low Latency Telemetry**: Emits a 500ms Socket.IO sensor stream (pH, EC, water temperature, air temperature/humidity) alongside live base64 camera frames directly to the operator's web dashboard.

### Safety, Monitoring & Diagnostics
- **Sub-Second Emergency Failsafes**: The hardware abstraction layer continuously evaluates critical thresholds. If readings become dangerous (pH < 3.0 or > 10.0, EC >= 8.0 mS/cm), the system triggers an immediate emergency halt, locking out all pumps.
- **Debounced Alert Subsystem**: Dispatches automated email notifications for high EC conditions, tank depletion, and system exceptions, utilizing backoff timers to prevent alert fatigue.
- **Native Database Diagnostics**: Includes a custom CLI utility (`hydro-db-check.sh`) to inspect the integrity of the SQLite WAL journal, table row counts, and audit logs directly on the edge hardware.

---

## Deployment Scripts & Configuration Files

Deploying complex hardware-software stacks to edge devices requires precision. Prana 1 includes robust, automated deployment tooling:

- **`deploy_full.ps1`**: The primary full-stack PowerShell deployment runner. It safely executes the local pytest suite, compiles the Vite frontend production bundle, packages the application tarball, transfers it via SCP, executes database schema migrations, and reloads the systemd daemons on the target hardware.
- **`deploy_quick.ps1`**: A fast hot-patch script designed for rapid iteration, transferring modified backend Python modules and compiled frontend assets in seconds.
- **`hydro-db-check.sh`**: The command-line database health diagnostic script, deployed to `~/hydro-db-check.sh` on the target SBC to monitor system health.
- **`start_reterminal.sh`**: The hardware environment initialization and startup wrapper script.
- **`systemd/hydro-backend.service`**: The systemd daemon configuration ensuring the Flask/Socket.IO backend server runs persistently and recovers from crashes.
- **`systemd/hydro-frontend.service`**: The systemd daemon configuration responsible for serving the React web dashboard.

---

## Automated Test Suites

Reliability is non-negotiable. Prana 1 is heavily verified by **233 total passing automated tests** across the entire stack:

### Backend Pytest Suite (204 Tests)
- **System Health & Circulation Telemetry (`test_system_health_and_circulation_api.py`)**: Validates health check responses, SQLite WAL status, and circulation metrics endpoints.
- **Circulation & Flood-Drain Tracking (`test_circulation_plateau.py`)**: Tests submerged plateau hold, settle ticks on water return, fresh RO water baseline adaptation, and drain-cycle dosing lockouts.
- **HAL Hardware Layer (`test_hal.py`)**: Extensively tests hardware fallback mocks, ADC channel validation bounds, strict L298N pump lock reentrancy, and DS18B20 1-Wire parsing.
- **Dosing & Safety Control (`test_dosing.py`, `test_new_dosing.py`, `test_mid_dose_cutoff.py`)**: Validates the complex volume mathematics, strict runtime clamping (2s minimum to 300s maximum), cooldown timer logic, mid-dose emergency cutoffs, and the self-learning calibration math.
- **REST APIs & Routes (`test_api.py`, `test_api_dosing.py`, `test_api_plants.py`)**: Tests endpoint payload validation, asynchronous pump priming, crop preset selection, and cycle completion state machines.
- **Grow Cycles & Persistence (`test_grow_cycle.py`, `test_models.py`, `test_new_features.py`)**: Ensures accurate phase duration resolution, cumulative start day inference, and database model integrity.
- **Alerts & System Stress (`test_alerts.py`, `test_performance_stress.py`)**: Benchmarks high-EC alert debouncing, asynchronous email queue resilience, and concurrent database locking under heavy load.

### Frontend Vitest Suite (29 Tests)
- **UI Components (`Dashboard.test.jsx`, `GlobalHUD.test.jsx`, `CirculationBadge.test.jsx`, `QuickCameraWidget.test.jsx`)**: Verifies accurate gauge rendering, real-time circulation alerts, critical state badges, and camera stream fallbacks.
- **Preset Management (`PlantPresets.test.jsx`, `PresetManagerModal.test.jsx`, `GrowCycleBanner.test.jsx`)**: Tests timeline visualization logic, complex form submissions, and manual pump override controls.

### Test Execution Commands
- **Backend Tests**: `cd backend && python -m pytest -v --tb=short -p no:cacheprovider`
- **Frontend Tests**: `cd frontend && npm test`

---

## Technical Stack

- **Backend Logic & AI**: Python 3.10+ (Flask, Flask-SocketIO, SQLAlchemy, OpenCV, smbus2)
- **Frontend Dashboard**: Node.js v18+ (React 18, Vite, TailwindCSS, Chart.js, Socket.IO Client)
- **Hardware Target**: Raspberry Pi / Seeed reTerminal (Linux SBC with direct I2C and GPIO control)
- **Process Management**: systemd

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
