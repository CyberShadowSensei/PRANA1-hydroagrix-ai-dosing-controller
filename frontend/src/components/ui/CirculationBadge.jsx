/**
 * CirculationBadge Component
 * Contextual badge indicating flood-and-drain hydrodynamic circulation status.
 */
import React from 'react';

/**
 * CirculationBadge
 * Displays the real-time flood-and-drain / circulation state of the hydroponic reservoir.
 * 
 * @param {boolean} isDrainCycle - True when water is drained to channels and EC probe is exposed
 * @param {boolean} isStablePlateau - True when submerged reading has settled
 * @param {number|null} plateauEc - The established high plateau EC (mS/cm)
 */
export default function CirculationBadge({ isDrainCycle = false, isStablePlateau = true, plateauEc = null }) {
  if (!isDrainCycle && isStablePlateau) {
    return null;
  }

  if (isDrainCycle) {
    return (
      <div 
        data-testid="circulation-drain-badge"
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-semibold shadow-sm animate-pulse"
      >
        <span className="w-2 h-2 rounded-full bg-amber-400"></span>
        <span>Channel Circulation Active &bull; Holding Plateau ({plateauEc !== null ? `${plateauEc} mS/cm` : 'Stabilizing'}) &bull; Dosing Paused</span>
      </div>
    );
  }

  if (!isStablePlateau) {
    return (
      <div 
        data-testid="circulation-settle-badge"
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/30 text-blue-400 text-xs font-semibold shadow-sm"
      >
        <span className="w-2 h-2 rounded-full bg-blue-400 animate-ping"></span>
        <span>Water Returned &bull; Settling Reading</span>
      </div>
    );
  }

  return null;
}
