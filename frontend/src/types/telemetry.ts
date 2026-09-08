/**
 * Telemetry State Type Definitions
 * Represents live WebSocket and REST telemetry payloads.
 */
export interface TelemetryState {
  ph: number;
  tds: number;
  waterTemp: number;
  airTemp: number;
  humidity: number;
  isDrainCycle: boolean;
}
