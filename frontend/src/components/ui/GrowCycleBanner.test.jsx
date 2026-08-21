import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import GrowCycleBanner from './GrowCycleBanner';

const { mockOn, mockOff } = vi.hoisted(() => {
  return {
    mockOn: vi.fn(),
    mockOff: vi.fn(),
  };
});

vi.mock('../../socket', () => ({
  default: {
    on: mockOn,
    off: mockOff,
  }
}));

vi.mock('axios', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: [{ id: 1, name: 'Lettuce' }] })),
    post: vi.fn(() => Promise.resolve({ status: 200, data: {} })),
  }
}));

describe('GrowCycleBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders inactive state when no grow cycle is active', async () => {
    await act(async () => {
      render(
        <GrowCycleBanner 
          cycleStatus={{ active: false }} 
          isAutomatic={false} 
        />
      );
    });

    expect(screen.getByText('No Active Grow Cycle')).toBeInTheDocument();
    expect(screen.getByText('Start Grow Cycle')).toBeInTheDocument();
  });

  it('renders all 4 required fields when cycle is active and omits advice', async () => {
    const activeCycle = {
      active: true,
      day: 7,
      phase: 'Vegetative',
      phase_source: 'Schedule',
      next_phase_name: 'Flowering',
      expected_transition_day: 'Day 14 (in 7 day(s))',
      advice: 'This advice text should not be visible anywhere in the UI'
    };

    await act(async () => {
      render(
        <GrowCycleBanner 
          cycleStatus={activeCycle} 
          isAutomatic={true} 
        />
      );
    });

    // 1. Growth Cycle Day
    expect(screen.getByText('Day 7')).toBeInTheDocument();

    // 2. Current Phase
    expect(screen.getByText('Vegetative')).toBeInTheDocument();

    // 3. Next Phase
    expect(screen.getByText('Flowering')).toBeInTheDocument();

    // 4. Expected Transition Day
    expect(screen.getByText('Day 14 (in 7 day(s))')).toBeInTheDocument();

    // Verify advice section is removed
    expect(screen.queryByText(/This advice text should not be visible/i)).not.toBeInTheDocument();
  });

  it('updates display when grow_cycle_update socket event fires', async () => {
    const initialCycle = {
      active: true,
      day: 1,
      phase: 'Germination',
      phase_source: 'Schedule',
      next_phase_name: 'Vegetative',
      expected_transition_day: 'Day 5 (in 4 day(s))'
    };

    const onRefreshMock = vi.fn();

    await act(async () => {
      render(
        <GrowCycleBanner 
          cycleStatus={initialCycle} 
          isAutomatic={true}
          onRefresh={onRefreshMock}
        />
      );
    });

    expect(screen.getByText('Day 1')).toBeInTheDocument();
    expect(screen.getByText('Germination')).toBeInTheDocument();

    // Find socket.on handler for 'grow_cycle_update'
    const socketCallback = mockOn.mock.calls.find(call => call[0] === 'grow_cycle_update')?.[1];
    expect(socketCallback).toBeDefined();

    // Simulate socket event
    const updatedCycle = {
      active: true,
      day: 5,
      phase: 'Vegetative',
      phase_source: 'ML',
      next_phase_name: 'Flowering',
      expected_transition_day: 'Day 15 (in 10 day(s))'
    };

    await act(async () => {
      socketCallback(updatedCycle);
    });

    expect(screen.getByText('Day 5')).toBeInTheDocument();
    expect(screen.getByText('Vegetative')).toBeInTheDocument();
    expect(screen.getByText('Flowering')).toBeInTheDocument();
    expect(screen.getByText('Day 15 (in 10 day(s))')).toBeInTheDocument();
    expect(onRefreshMock).toHaveBeenCalled();
  });
});
