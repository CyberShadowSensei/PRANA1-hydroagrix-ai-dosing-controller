import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import PresetManagerModal, { STAGE_KEYS } from './PresetManagerModal';

describe('PresetManagerModal', () => {
    const mockOnSave = vi.fn();
    const mockOnClose = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders null when isOpen is false', () => {
        const { container } = render(
            <PresetManagerModal isOpen={false} onClose={mockOnClose} onSave={mockOnSave} />
        );
        expect(container.firstChild).toBeNull();
    });

    it('renders 3-phase growth duration input fields when isOpen is true', () => {
        render(
            <PresetManagerModal isOpen={true} onClose={mockOnClose} onSave={mockOnSave} />
        );

        expect(screen.getByText('Add a New Plant')).toBeInTheDocument();
        expect(screen.getByText('1. Seedling / Germination')).toBeInTheDocument();
        expect(screen.getByText('2. Vegetative Growth')).toBeInTheDocument();
        expect(screen.getByText('3. Harvesting / Maturity')).toBeInTheDocument();

        // Check for duration inputs for all 3 canonical phases
        STAGE_KEYS.forEach(stage => {
            const durationInput = screen.getByTitle(`${stage} Duration (Days)`);
            expect(durationInput).toBeInTheDocument();
            expect(durationInput).toHaveAttribute('type', 'number');
            expect(durationInput).toHaveAttribute('required');
        });
    });

    it('blocks browser form validation when phase duration input is empty', () => {
        render(
            <PresetManagerModal isOpen={true} onClose={mockOnClose} onSave={mockOnSave} />
        );

        STAGE_KEYS.forEach(stage => {
            const durationInput = screen.getByTitle(`${stage} Duration (Days)`);
            expect(durationInput.checkValidity()).toBe(true);

            fireEvent.change(durationInput, { target: { value: '' } });
            expect(durationInput.checkValidity()).toBe(false);
            expect(durationInput.validity.valueMissing).toBe(true);
        });
    });

    it('calculates cumulative start_day values upon form submission', async () => {
        render(
            <PresetManagerModal isOpen={true} onClose={mockOnClose} onSave={mockOnSave} />
        );

        // Fill plant name
        const nameInput = screen.getByPlaceholderText(/Enter plant name/i);
        fireEvent.change(nameInput, { target: { value: 'Test Tomato' } });

        // Set durations: Seedling=10, Vegetative=25, Harvesting=20
        const seedlingDuration = screen.getByTitle('Seedling Duration (Days)');
        const vegDuration = screen.getByTitle('Vegetative Duration (Days)');
        const harvestDuration = screen.getByTitle('Harvesting Duration (Days)');

        fireEvent.change(seedlingDuration, { target: { value: '10' } });
        fireEvent.change(vegDuration, { target: { value: '25' } });
        fireEvent.change(harvestDuration, { target: { value: '20' } });

        // Submit form
        const saveButton = screen.getByRole('button', { name: /Save Plant/i });
        await act(async () => {
            fireEvent.click(saveButton);
        });

        expect(mockOnSave).toHaveBeenCalledTimes(1);
        const payload = mockOnSave.mock.calls[0][0];

        expect(payload.name).toBe('Test Tomato');
        expect(payload.stages.Seedling.duration_days).toBe(10);
        expect(payload.stages.Seedling.start_day).toBe(0);

        expect(payload.stages.Vegetative.duration_days).toBe(25);
        expect(payload.stages.Vegetative.start_day).toBe(10);

        expect(payload.stages.Harvesting.duration_days).toBe(20);
        expect(payload.stages.Harvesting.start_day).toBe(35);
    });

    it('populates fields when editing an existing preset', () => {
        const presetToEdit = {
            id: 1,
            name: 'Basil Special',
            image: '/images/Herb.webp',
            stages: {
                Seedling: { ec: { min: 1.0, max: 1.4 }, ph: { min: 5.8, max: 6.2 }, duration_days: 8, start_day: 0 },
                Vegetative: { ec: { min: 1.5, max: 2.1 }, ph: { min: 5.8, max: 6.5 }, duration_days: 18, start_day: 8 },
                Harvesting: { ec: { min: 1.8, max: 2.4 }, ph: { min: 6.0, max: 6.5 }, duration_days: 22, start_day: 26 }
            }
        };

        render(
            <PresetManagerModal isOpen={true} onClose={mockOnClose} presetToEdit={presetToEdit} onSave={mockOnSave} />
        );

        expect(screen.getByText('Edit Plant Settings')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Basil Special')).toBeInTheDocument();
        expect(screen.getByDisplayValue('8')).toBeInTheDocument();
        expect(screen.getByDisplayValue('18')).toBeInTheDocument();
        expect(screen.getByDisplayValue('22')).toBeInTheDocument();
    });
});
