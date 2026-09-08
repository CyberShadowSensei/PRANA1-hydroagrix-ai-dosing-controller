/**
 * Plant Preset & Growth Stage Types
 * Defines multi-stage crop recipe schedules and target limits.
 */
export interface PlantStage {
  name: string;
  duration_days: number;
  ph_min: number;
  ph_max: number;
  ec_min: number;
  ec_max: number;
}
