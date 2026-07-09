import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import Pump from './Pump';

vi.mock('axios');

describe('Pump Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockImplementation((url) => {
      if (url === '/pump/status') {
        return Promise.resolve({ status: 200, data: { pump1: 'stopped', pump2: 'stopped', pump3: 'stopped', pump4: 'stopped' } });
      }
      if (url === '/sensor/limits') {
        return Promise.resolve({ status: 200, data: { 
          ph: { min: 5.5, max: 6.5, active: true }, 
          tds: { min: 1.0, max: 3.0, active: true },
          temperature: { min: 18, max: 24, active: true },
          humidity: { min: 40, max: 80, active: true }
        } });
      }
      return Promise.resolve({ status: 200, data: {} });
    });
  });

  it('renders correctly and fetches initial data', async () => {
    render(<Pump />);
    expect(screen.getByText('Pump Control System')).toBeInTheDocument();
    expect(screen.getByText('Pump Controls')).toBeInTheDocument();
    
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/pump/status');
      expect(axios.get).toHaveBeenCalledWith('/sensor/limits');
    });
  });

  it('triggers a pump start when clicked', async () => {
    axios.post.mockResolvedValue({ status: 200 });
    
    render(<Pump />);
    
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalledWith('/pump/status');
    });

    const triggerBtn = screen.getAllByText('Start')[0];
    fireEvent.click(triggerBtn);

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/pump/1/start', { duration: 5 });
    });
  });

  it('updates target setpoints and saves them', async () => {
    axios.post.mockResolvedValue({ status: 200 });
    render(<Pump />);
    
    await waitFor(() => {
      expect(screen.getByDisplayValue('6.5')).toBeInTheDocument();
    });

    const phMinInput = screen.getByDisplayValue('5.5');
    fireEvent.change(phMinInput, { target: { value: '5.8' } });
    
    const saveBtn = screen.getByText('Save Settings');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/sensor/limits', expect.objectContaining({
        ph: expect.objectContaining({ min: 5.8, max: 6.5 })
      }));
    });
  });
});
