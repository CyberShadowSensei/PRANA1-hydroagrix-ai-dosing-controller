/**
 * Solution Tank Inventory Types
 * Represents reservoir bottle levels and capacity definitions.
 */
export interface SolutionTank {
  tank_id: number;
  name: string;
  capacity_ml: number;
  current_volume_ml: number;
  last_alert_sent: number;
}
