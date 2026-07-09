# Hydroagrix Dosing Controller 🎛️💧

[![GitHub Repo](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/CyberShadowSensei/hydroagrix-ai-dosing-controller)

The hardware automation, sensing, and control platform for the Hydroagrix hydroponic NFT system. Executes sensor telemetry (pH/EC), runs automatic dosing logic, and serves the system control panel dashboard.

---

## 📊 System Architecture & Data Loops

```mermaid
graph TD
    %% Telemetry Loop
    subgraph Sensors [Telemetry Layer]
        style Sensors fill:#111,stroke:#30363d,stroke-width:2px,color:#fff
        A["EC & pH Sensors"] -->|Analog Signals| B["Grove Base HAT (ADS1115 ADC via I2C)"]
        B -->|Register 0x30 Ratio| C["sensors.py (TDS/pH Telemetry Engine)"]
    end

    %% Flask Server & Database
    subgraph Server [Backend Controller & DB]
        style Server fill:#111,stroke:#30363d,stroke-width:2px,color:#fff
        C -->|TDS / pH Readings| D["routes.py (Flask API / Socket.IO)"]
        D -->|Write Logs| E["SQLite Database (EventLog/PumpLog)"]
        D -->|Read Stage Settings| F["system_config.json (Stage Limits)"]
    end

    %% Camera & ML Loop
    subgraph ML_Inference [ML Inference Layer]
        style ML_Inference fill:#111,stroke:#30363d,stroke-width:2px,color:#fff
        G["USB Camera (Hiwonder)"] -->|RGB Frame| H["camera_ml.py (Inference Engine)"]
        H -->|stage_detect.pt (YOLOv8 Plant Detector)| I["Update PlantStageStatus DB"]
        I -->|Dynamically adjusts EC/pH limits| F
    end

    %% Web UI
    D -->|Real-Time Gauges & Charts| J["React Frontend (Dashboard UI)"]
    J -->|Manual Pump Trigger POST| D

    %% Dosing Actuation
    D -->|Pump Control Signals| K["hal.py (Hardware Abstraction Layer)"]
    K -->|Relays / GPIO| L["Peristaltic Pumps (A/B Nutrients, pH Down)"]
```

---

## ⚙️ Core Services & Local Commands

The reTerminal runs two systemd service layers for managing the hydroponic operations:

*   **`hydro-backend.service`**: Powers the Flask API, SQLite logger, and the automated I2C dosing loops.
*   **`hydro-frontend.service`**: Serves the React UI/web dashboard.

### **Management Commands on the reTerminal:**

*   **Restart both services:**
    ```bash
    sudo systemctl restart hydro-backend.service hydro-frontend.service
    ```
*   **Check service status:**
    ```bash
    sudo systemctl status hydro-backend.service hydro-frontend.service
    ```
*   **View live backend logs:**
    ```bash
    sudo journalctl -u hydro-backend.service -f
    ```

---

## 🚀 Quick Start & Setup

Initialize the repository and track active development files:

```bash
git init
git add .
git commit -m "initial commit: add dosing controller backend, React frontend, and HAL scripts"
git remote add origin https://github.com/CyberShadowSensei/hydroagrix-ai-dosing-controller
git branch -M main
git push -u origin main
```
