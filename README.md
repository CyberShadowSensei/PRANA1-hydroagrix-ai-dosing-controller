# Hydroagrix AI Dosing Controller

> The hardware automation, sensing, and control platform for the Hydroagrix hydroponic NFT system, featuring automatic dosing logic and a real-time web dashboard.

## Features
* **Real-Time Telemetry:** Continuous monitoring of pH, Electrical Conductivity (EC), and environmental parameters.
* **Automated Dosing:** Intelligent, feedback-driven peristaltic pump control to maintain optimal nutrient levels.
* **Vision Integration:** Seamlessly interfaces with the edge vision pipeline to adjust dosing limits based on the plant's current growth stage.

## Prerequisites
* Node.js v18+ (for Frontend)
* Python 3.10+ (for Backend)
* I2C enabled on Raspberry Pi

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/CyberShadowSensei/hydroagrix-ai-dosing-controller.git
   ```
2. Navigate to the project directory:
   ```bash
   cd hydroagrix-ai-dosing-controller
   ```
3. Install backend dependencies:
   ```bash
   cd backend && pip install -r requirements.txt
   ```
4. Install frontend dependencies:
   ```bash
   cd ../frontend && npm install
   ```

## Usage
```bash
# Restart the backend and frontend systemd services on the reTerminal
sudo systemctl restart hydro-backend.service hydro-frontend.service
```

## Configuration
* **I2C_ADDR:** Address of the Grove Base HAT ADC (default: `0x48`).
* **TARGET_PH:** Ideal pH level for the dosing algorithm (configurable via dashboard).

## Contributing
1. Fork the Project
2. Create your Feature Branch (git checkout -b feature/AmazingFeature)
3. Commit your Changes (git commit -m 'Add some AmazingFeature')
4. Push to the Branch (git push origin feature/AmazingFeature)
5. Open a Pull Request

## License
Distributed under the MIT License. See `LICENSE` for more information.
