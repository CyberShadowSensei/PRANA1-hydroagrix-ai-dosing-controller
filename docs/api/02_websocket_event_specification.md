# WebSocket Event Specification (Socket.IO)

## Emitted Events

### `telemetry_update`
Emitted every 500ms containing live pH, EC, water temperature, ambient air temperature, and humidity.

### `pump_activity`
Emitted upon peristaltic pump activation with duration and trigger type.
