/**
 * Subtle UI Micro-Interaction Audio Cues (Optional Web Audio)
 * Provides soft haptic/audio feedback for pump priming and setting saves.
 */
export function playHapticFeedback() {
  if (typeof window !== 'undefined' && window.navigator && window.navigator.vibrate) {
    window.navigator.vibrate(10);
  }
}
