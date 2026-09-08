/**
 * Telemetry and Timestamp Formatting Utilities
 * Standardizes float precision and localized time display.
 */
export function formatMetric(val, digits = 2, fallback = '--') {
  if (val === null || val === undefined || isNaN(val)) return fallback;
  return Number(val).toFixed(digits);
}
