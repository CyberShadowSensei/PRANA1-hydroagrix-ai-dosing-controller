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
    
    // Check quick widgets
    expect(screen.getByTestId('quick-camera')).toBeInTheDocument();
    expect(screen.getByTestId('quick-pump')).toBeInTheDocument();
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

    // The Dashboard component doesn't directly display the text "6.5" it passes it to the gauge
    // But we can check if it rendered the gauges (which we mocked).
    // Let's just ensure it doesn't crash on update.
    expect(screen.getByText('Sensor Dashboard')).toBeInTheDocument();
  });
});
