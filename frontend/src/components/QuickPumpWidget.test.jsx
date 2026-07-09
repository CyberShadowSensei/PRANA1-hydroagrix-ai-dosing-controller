import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import QuickPumpWidget from './QuickPumpWidget';

vi.mock('axios');

describe('QuickPumpWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: { pump1: 'stopped', pump2: 'stopped', pump3: 'stopped', pump4: 'stopped' } });
  });

  it('renders correctly and fetches initial status', async () => {
    render(<QuickPumpWidget />);
    expect(screen.getByText('Manual Dosing')).toBeInTheDocument();
    
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/pump/status');
    });
    
    expect(screen.getByText('Nutrient A')).toBeInTheDocument();
    expect(screen.getByText('pH Down')).toBeInTheDocument();
  });

  it('triggers a pump start when clicked', async () => {
    axios.post.mockResolvedValue({ status: 200 });
    
    render(<QuickPumpWidget />);
    
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/pump/status');
    });

    const pump1Btn = screen.getByText('Nutrient A').closest('button');
    fireEvent.click(pump1Btn);

    await waitFor(() => {
      // It uses the default duration of 10
      expect(axios.post).toHaveBeenCalledWith('/pump/1/start', { duration: 10 });
    });
  });

  it('updates duration state via slider', async () => {
    render(<QuickPumpWidget />);
    
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/pump/status');
    });
    
    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '25' } });
    
    // Check if the text matches the new duration
    expect(screen.getByText('25s (ml)')).toBeInTheDocument();
  });
});
