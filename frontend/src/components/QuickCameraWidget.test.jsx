import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import QuickCameraWidget from './QuickCameraWidget';

const mockOn = vi.fn();
const mockDisconnect = vi.fn();
vi.mock('socket.io-client', () => {
  return {
    io: () => ({
      on: mockOn,
      disconnect: mockDisconnect
    })
  };
});

vi.mock('axios');

describe('QuickCameraWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.post.mockResolvedValue({ status: 200 });
  });

  it('renders correctly in offline state', () => {
    render(<QuickCameraWidget />);
    expect(screen.getByText('Live Camera Feed')).toBeInTheDocument();
    expect(screen.getByText('START')).toBeInTheDocument();
    expect(screen.getByText('Stream is offline')).toBeInTheDocument();
  });

  it('starts streaming when START button is clicked', async () => {
    render(<QuickCameraWidget />);
    
    const startBtn = screen.getByText('START');
    fireEvent.click(startBtn);

    expect(screen.getByText('Connecting...')).toBeInTheDocument();
    expect(screen.getByText('STOP')).toBeInTheDocument();

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/start_stream');
    });

    // Simulate receiving a frame
    const frameCallback = mockOn.mock.calls.find(c => c[0] === 'camera_frame')[1];
    act(() => {
      frameCallback({ image: 'base64imagedata' });
    });

    // The image should appear
    const img = await screen.findByAltText('Live Plant Feed');
    expect(img).toBeInTheDocument();
    expect(img.src).toContain('base64imagedata');
  });

  it('stops streaming when STOP button is clicked', async () => {
    render(<QuickCameraWidget />);
    
    // Start it first
    fireEvent.click(screen.getByText('START'));
    
    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/start_stream');
    });

    // Stop it
    fireEvent.click(screen.getByText('STOP'));

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/stop_stream');
      expect(mockDisconnect).toHaveBeenCalled();
    });
    
    expect(screen.getByText('START')).toBeInTheDocument();
    expect(screen.getByText('Stream is offline')).toBeInTheDocument();
  });
});
