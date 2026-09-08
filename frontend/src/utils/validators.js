/**
 * Form Input Validation Helpers
 * Validates reservoir volume, pump flow rates, and email recipients.
 */
export function validateFlowRate(val) {
  const num = parseFloat(val);
  return !isNaN(num) && num > 0.0 && num <= 1000.0;
}
