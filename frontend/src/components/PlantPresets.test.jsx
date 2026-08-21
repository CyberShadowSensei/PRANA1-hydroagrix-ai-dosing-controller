import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import axios from 'axios';
import PlantPresets, { ManageProgressModal } from './PlantPresets';

const { mockOn, mockOff } = vi.hoisted(() => ({
    mockOn: vi.fn(),
    mockOff: vi.fn(),
}));

vi.mock('../socket', () => ({
    default: {
        on: mockOn,
        off: mockOff,
    }
}));

vi.mock('axios', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    }
}));

describe('PlantPresets & ManageProgressModal', () => {
    const mockPresets = [
        {
            id: 1,
            name: 'Tomato',
            image: '/images/tomato.jpg',
            stages: {
                Seedling: { ec: { min: 0.8, max: 1.2 }, ph: { min: 5.5, max: 6.5 }, duration_days: 10, start_day: 0 },
                Vegetative: { ec: { min: 1.4, max: 2.0 }, ph: { min: 5.8, max: 6.8 }, duration_days: 25, start_day: 10 },
                Harvesting: { ec: { min: 1.8, max: 2.5 }, ph: { min: 6.0, max: 6.5 }, duration_days: 30, start_day: 35 }
            }
        }
    ];

    const mockPlantStatus = {
        plant_name: 'Tomato',
        plant_stage: 'Vegetative',
        state: true
    };

    const mockCycleStatus = {
        active: true,
        day: 15,
        phase: 'Vegetative',
        phase_source: 'Schedule',
        next_phase_name: 'Harvesting',
        expected_transition_day: 'Day 35 (in 20 day(s))'
    };

    beforeEach(() => {
        vi.clearAllMocks();
        axios.get.mockImplementation((url) => {
            if (url === '/api/presets') return Promise.resolve({ status: 200, data: mockPresets });
            if (url === '/get_plant_status') return Promise.resolve({ status: 200, data: mockPlantStatus });
            if (url === '/get_grow_cycle_status') return Promise.resolve({ status: 200, data: mockCycleStatus });
            if (url === '/api/preset_logs') return Promise.resolve({ status: 200, data: [] });
            return Promise.resolve({ status: 200, data: [] });
        });
        axios.post.mockImplementation((url) => {
            if (url === '/update_grow_cycle_progress') {
                return Promise.resolve({
                    status: 200,
                    data: {
                        status: 'success',
                        message: 'Grow cycle progress updated successfully',
                        current_day: 20,
                        plant_stage: 'Vegetative'
                    }
                });
            }
            return Promise.resolve({ status: 200, data: {} });
        });
    });

    it('renders plant presets catalog with 3-phase duration info', async () => {
        await act(async () => {
            render(<PlantPresets />);
        });

        expect(screen.getByText('Plant Presets')).toBeInTheDocument();
        expect(screen.getAllByText('Tomato').length).toBeGreaterThan(0);

        // Verify 3 canonical phase labels are rendered in the card grid
        expect(screen.getAllByText('Seedling').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Vegetative').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Harvesting').length).toBeGreaterThan(0);

        // Verify duration info is rendered
        expect(screen.getByText('10 Days')).toBeInTheDocument();
        expect(screen.getByText('25 Days')).toBeInTheDocument();
        expect(screen.getByText('30 Days')).toBeInTheDocument();
    });

    it('renders Manage Progress button when active plant cycle exists', async () => {
        await act(async () => {
            render(<PlantPresets />);
        });

        const manageProgressBtn = screen.getByRole('button', { name: /Manage Progress/i });
        expect(manageProgressBtn).toBeInTheDocument();
    });

    it('opens ManageProgressModal and submits progress update to API', async () => {
        await act(async () => {
            render(<PlantPresets />);
        });

        const manageProgressBtn = screen.getByRole('button', { name: /Manage Progress/i });
        await act(async () => {
            fireEvent.click(manageProgressBtn);
        });

        expect(screen.getByText('Manage Grow Cycle Progress')).toBeInTheDocument();
        expect(screen.getByDisplayValue('15')).toBeInTheDocument();

        // Change day to 20 and phase to Harvesting
        const dayInput = screen.getByLabelText('Current Cycle Day');
        const phaseSelect = screen.getByLabelText('Growth Phase');

        fireEvent.change(dayInput, { target: { value: '20' } });
        fireEvent.change(phaseSelect, { target: { value: 'Harvesting' } });

        const submitBtn = screen.getByRole('button', { name: /Update Progress/i });
        await act(async () => {
            fireEvent.click(submitBtn);
        });

        expect(axios.post).toHaveBeenCalledWith('/update_grow_cycle_progress', {
            day: 20,
            phase: 'Harvesting',
            plant_stage: 'Harvesting'
        });
    });

    it('ManageProgressModal direct unit test for props and callbacks', async () => {
        const mockOnClose = vi.fn();
        const mockOnProgressUpdated = vi.fn();

        render(
            <ManageProgressModal
                isOpen={true}
                onClose={mockOnClose}
                cycleStatus={{ day: 12, phase: 'Seedling' }}
                plantStatus={{ plant_name: 'Lettuce' }}
                onProgressUpdated={mockOnProgressUpdated}
            />
        );

        expect(screen.getByDisplayValue('12')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Seedling')).toBeInTheDocument();

        const submitBtn = screen.getByRole('button', { name: /Update Progress/i });
        await act(async () => {
            fireEvent.click(submitBtn);
        });

        expect(axios.post).toHaveBeenCalledWith('/update_grow_cycle_progress', {
            day: 12,
            phase: 'Seedling',
            plant_stage: 'Seedling'
        });

        await waitFor(() => {
            expect(mockOnProgressUpdated).toHaveBeenCalled();
            expect(mockOnClose).toHaveBeenCalled();
        });
    });
});
