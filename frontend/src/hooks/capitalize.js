/**
 * String Capitalization Utility
 * Capitalizes the first character of provided strings for UI display.
 */

export function capitalizeFirstLetter(val) {
    return String(val).charAt(0).toUpperCase() + String(val).slice(1);
}


