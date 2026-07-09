# Hydroagrix Dosing Controller

This repository contains the hardware automation, sensing, and control platform for the Hydroagrix hydroponic NFT system. It manages sensor telemetry (pH/EC), executes automatic dosing logic, and serves the system control panel dashboard.

---

## System Architecture and Data Loops

The system integrates real-time telemetry inputs, computer vision classification, and output actuation:

```
+-----------------------------------------------------------------------------------+
|                                  Telemetry Layer                                  |
|                                                                                   |
|  [EC & pH Sensors] ---> [Grove Base HAT (ADS1115 via I2C)] ---> [sensors.py]      |
+-----------------------------------------------------------------------------------+
                                                                  |
                                                                  v
+-----------------------------------------------------------------------------------+
|                             Backend Controller & Database                         |
|                                                                                   |
|  [sensors.py] ---> [routes.py (Flask API / Socket.IO)] <---> [SQLite Database]    |
|                          ^                                 (EventLog/PumpLog)     |
|                          |                                                        |
|                          v                                                        |
|              [system_config.json] <---+                                           |
+-----------------------------------------------------------------------------------+
                                        |                                           
                                        |                                           
+---------------------------------------+-------------------------------------------+
|                              ML Inference Layer                                   |
|                                                                                   |
|  [USB Camera] ---> [camera_ml.py (YOLOv8 Plant Detector)] ---> [PlantStageStatus]  |
+-----------------------------------------------------------------------------------+
                                                                  |
                                                                  v
+-----------------------------------------------------------------------------------+
|                                 Actuation Layer                                   |
|                                                                                   |
|  [routes.py] ---> [hal.py (Hardware Abstraction)] ---> [Peristaltic Pumps]        |
+-----------------------------------------------------------------------------------+
```

---

## Core Services and Local Commands

The Raspberry Pi reTerminal runs two systemd service layers for managing hydroponic operations:

*   **`hydro-backend.service`**: Powers the Flask API, SQLite logger, and the automated I2C dosing loops.
*   **`hydro-frontend.service`**: Serves the React UI/web dashboard.

### Management Commands on the reTerminal

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

## Quick Start and Setup

Initialize the repository and track active development files:

```bash
git init
git add .
git commit -m "initial commit: add dosing controller backend, React frontend, and HAL scripts"
git remote add origin https://github.com/CyberShadowSensei/hydroagrix-ai-dosing-controller.git
git branch -M main
git push -u origin main
```
