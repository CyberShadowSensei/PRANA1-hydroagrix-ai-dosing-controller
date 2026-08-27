import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CirculationBadge from './CirculationBadge';

describe('CirculationBadge', () => {
  it('renders nothing when system is stable and not in drain cycle', () => {
    const { container } = render(
      <CirculationBadge isDrainCycle={false} isStablePlateau={true} plateauEc={2.1} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders amber warning badge during channel drain cycle', () => {
    render(
      <CirculationBadge isDrainCycle={true} isStablePlateau={false} plateauEc={2.35} />
    );
    const badge = screen.getByTestId('circulation-drain-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('Channel Circulation Active');
    expect(badge).toHaveTextContent('2.35 mS/cm');
    expect(badge).toHaveTextContent('Dosing Paused');
  });

  it('renders blue settling badge when water has returned but settling ticks remain', () => {
    render(
      <CirculationBadge isDrainCycle={false} isStablePlateau={false} plateauEc={2.2} />
    );
    const badge = screen.getByTestId('circulation-settle-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('Water Returned • Settling Reading');
  });
});
