import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import GlobalHUD from './GlobalHUD';

const { mockOn, mockOff, mockDisconnect } = vi.hoisted(() => {
  return {
    mockOn: vi.fn(),
    mockOff: vi.fn(),
    mockDisconnect: vi.fn(),
  };
});

vi.mock('socket.io-client', () => {
  return {
    io: () => ({
      on: mockOn,
      off: mockOff,
      disconnect: mockDisconnect
    })
  };
});

describe('GlobalHUD Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial state correctly with missing telemetry', () => {
    render(<GlobalHUD />);
    expect(screen.getByText('pH Level')).toBeInTheDocument();
    
    // The initial state has '--' for values
    const dashes = screen.getAllByText('--');
    expect(dashes.length).toBeGreaterThan(0);
  });

  it('updates state based on socket events', () => {
    render(<GlobalHUD />);
    
    // Simulate connection
    const connectCallback = mockOn.mock.calls.find(c => c[0] === 'connect')[1];
    act(() => connectCallback());
    
// LIVE DATALINK removed per UI requirements

    // Simulate telemetry
    const telemetryCallback = mockOn.mock.calls.find(c => c[0] === 'telemetry_update')[1];
    act(() => {
      telemetryCallback({
        ph: 6.512,
        ec: 1.5,
        temperature: 24.1,
        humidity: 60.0
      });
    });

    expect(screen.getByText('6.51')).toBeInTheDocument();
    expect(screen.getByText('1.50')).toBeInTheDocument();
    expect(screen.getByText('24.1')).toBeInTheDocument();
  });
  
  it('does not display OFFLINE when disconnected', () => {
    render(<GlobalHUD />);
    const disconnectCallback = mockOn.mock.calls.find(c => c[0] === 'disconnect')[1];
    act(() => disconnectCallback());
    
    expect(screen.queryByText('OFFLINE')).not.toBeInTheDocument();
  });
});
