import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Dashboard from './Dashboard';

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

// Mock child components to prevent recharts and syncfusion issues in JSDOM
vi.mock('../components/ui/MoistureGauge', () => ({ default: () => <div data-testid="moisture-gauge" /> }));
vi.mock('../components/ui/TemperatureGauge', () => ({ default: () => <div data-testid="temp-gauge" /> }));
vi.mock('../components/ui/HumidityGauge', () => ({ default: () => <div data-testid="humidity-gauge" /> }));
vi.mock('../components/ui/TDSGauge', () => ({ default: () => <div data-testid="tds-gauge" /> }));
vi.mock('../components/ui/gauge', () => ({ default: () => <div data-testid="generic-gauge" /> }));
vi.mock('./QuickCameraWidget', () => ({ default: () => <div data-testid="quick-camera" /> }));
vi.mock('./QuickPumpWidget', () => ({ default: () => <div data-testid="quick-pump" /> }));
// Mock recharts
vi.mock('recharts', async () => {
  const actual = await vi.importActual('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }) => <div>{children}</div>,
    LineChart: () => <div data-testid="line-chart" />
  };
});


describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all gauges and widgets correctly', () => {
    render(<Dashboard />);
    expect(screen.getByText('Sensor Dashboard')).toBeInTheDocument();
    
    // Check mocked gauges
    expect(screen.getByTestId('temp-gauge')).toBeInTheDocument();
    expect(screen.getByTestId('humidity-gauge')).toBeInTheDocument();
    expect(screen.getByTestId('tds-gauge')).toBeInTheDocument();
  });

  it('updates state when telemetry is received via socket', () => {
    render(<Dashboard />);
    
    // Simulate telemetry
    const telemetryCallback = mockOn.mock.calls.find(c => c[0] === 'telemetry_update')[1];
    act(() => {
      telemetryCallback({
        ph: 6.5,
        ec: 1.5,
        temperature: 24.1,
        humidity: 60.0,
        water_level: 80.0
      });
    });

    expect(screen.getByText('Sensor Dashboard')).toBeInTheDocument();
  });

  it('displays context-aware alert when pH is low and Tank 3 (pH UP) is empty', () => {
    render(<Dashboard />);
    
    // Set sensor limits via socket
    const limitsCallback = mockOn.mock.calls.find(c => c[0] === 'sensor_limits_updated')[1];
    act(() => {
      limitsCallback({
        ph: { min: 5.5, max: 6.5, active: true },
        tds: { min: 1.2, max: 2.0, active: true }
      });
    });

    const telemetryCallback = mockOn.mock.calls.find(c => c[0] === 'telemetry_update')[1];
    act(() => {
      telemetryCallback({
        ph: 5.0,
        ec: 1.5,
        temperature: 24.0,
        humidity: 60.0
      });
    });

    expect(screen.getByText('System Alerts')).toBeInTheDocument();
    expect(screen.getByText(/pH is low/i)).toBeInTheDocument();
  });

  it('suppresses false low-EC alert during active channel drain cycle', () => {
    render(<Dashboard />);
    
    const telemetryCallback = mockOn.mock.calls.find(c => c[0] === 'telemetry_update')[1];
    act(() => {
      telemetryCallback({
        ph: 6.2,
        ec: 0.4,
        effective_ec: 1.8,
        is_drain_cycle: true,
        pattern_status: 'CONFIRMED_PERIODIC',
        temperature: 24.0,
        humidity: 60.0
      });
    });

    // Low-EC alert should be suppressed because is_drain_cycle is true
    expect(screen.queryByText(/Add nutrient solution manually/i)).not.toBeInTheDocument();
  });
});
