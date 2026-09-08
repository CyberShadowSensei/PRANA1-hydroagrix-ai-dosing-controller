/**
 * Peristaltic Pump Activity Types
 * Represents pump log items and manual priming requests.
 */
export interface PumpActivityLog {
  id: number;
  pump_name: string;
  duration: number;
  trigger_type: 'Automatic' | 'Manual' | 'Priming';
  timestamp: string;
}
