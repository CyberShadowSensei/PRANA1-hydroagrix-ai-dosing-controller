/**
 * System Event & Audit Log Types
 * Represents structured event log entries and alert categories.
 */
export interface SystemEvent {
  id: number;
  event_id: string;
  category: 'DOSING' | 'SENSORS' | 'SYSTEM' | 'ALARM';
  message: string;
  timestamp: string;
}
