/**
 * PresetManagerModal Component
 * Full-featured modal for creating, modifying, and deleting multi-stage crop preset recipes.
 */
import React, { useState, useEffect } from 'react';
import { HiX, HiCheckCircle } from 'react-icons/hi';

// Using local downloaded images for offline capability
const avatars = [
    { id: 'leaf', name: 'Leafy Green', url: '/images/leafy green.avif' },
    { id: 'vine', name: 'Vine Crop', url: '/images/vine crop.jpg' },
    { id: 'fruiting', name: 'Fruiting Crop', url: '/images/Fruiting Crop.webp' },
    { id: 'herb', name: 'Herb', url: '/images/Herb.webp' },
    { id: 'berry', name: 'Berry', url: '/images/Berry.webp' },
    { id: 'strawberry', name: 'Strawberry', url: '/images/strawberry.PNG' },
    { id: 'tomato', name: 'Tomato', url: '/images/tomato.jpg' },
    { id: 'spinach', name: 'Spinach', url: '/images/spinach.jpg' },
    { id: 'lettuce', name: 'Lettuce', url: '/images/lettuce.jpg' },
    { id: 'tulsi_basil', name: 'Tulsi/Basil', url: '/images/tulsi_basil.jpg' }
];

export const STAGE_KEYS = ['Seedling', 'Vegetative', 'Harvesting'];

export const stageLabels = {
    Seedling: "1. Seedling / Germination",
    Vegetative: "2. Vegetative Growth",
    Harvesting: "3. Harvesting / Maturity"
};

const defaultStages = {
    Seedling: { ec: { min: 0.8, max: 1.2 }, ph: { min: 5.5, max: 6.5 }, duration_days: 7 },
    Vegetative: { ec: { min: 1.2, max: 2.0 }, ph: { min: 5.8, max: 6.8 }, duration_days: 14 },
    Harvesting: { ec: { min: 1.5, max: 2.2 }, ph: { min: 5.8, max: 6.5 }, duration_days: 30 }
};

const getStageDefaults = (stagesInput, stageKey, fallbackKeys, defaultVal) => {
    let raw = stagesInput?.[stageKey];
    if (!raw && fallbackKeys) {
        for (const fKey of fallbackKeys) {
            if (stagesInput?.[fKey]) {
                raw = stagesInput[fKey];
                break;
            }
        }
    }
    return {
        ec: {
            min: raw?.ec?.min !== undefined ? raw.ec.min : defaultVal.ec.min,
            max: raw?.ec?.max !== undefined ? raw.ec.max : defaultVal.ec.max
        },
        ph: {
            min: raw?.ph?.min !== undefined ? raw.ph.min : defaultVal.ph.min,
            max: raw?.ph?.max !== undefined ? raw.ph.max : defaultVal.ph.max
        },
        duration_days: raw?.duration_days !== undefined ? raw.duration_days : defaultVal.duration_days
    };
};

const PresetManagerModal = ({ isOpen, onClose, presetToEdit, onSave }) => {
    const defaultImageUrl = avatars[0].url; // Default to Leafy Green

    const [formData, setFormData] = useState({
        name: '',
        image_url: defaultImageUrl,
        stages: { ...defaultStages }
    });

    useEffect(() => {
        if (presetToEdit) {
            const rawStages = presetToEdit.stages || presetToEdit.stages_json || {};
            setFormData({
                name: presetToEdit.name || '',
                image_url: presetToEdit.image || presetToEdit.image_url || defaultImageUrl,
                stages: {
                    Seedling: getStageDefaults(rawStages, 'Seedling', ['Germination'], defaultStages.Seedling),
                    Vegetative: getStageDefaults(rawStages, 'Vegetative', [], defaultStages.Vegetative),
                    Harvesting: getStageDefaults(rawStages, 'Harvesting', ['Flowering', 'Maturity'], defaultStages.Harvesting)
                }
            });
        } else {
            setFormData({
                name: '',
                image_url: defaultImageUrl,
                stages: JSON.parse(JSON.stringify(defaultStages))
            });
        }
    }, [presetToEdit, isOpen]);

    if (!isOpen) return null;

    const handleStageChange = (stage, parameter, bound, value) => {
        setFormData(prev => ({
            ...prev,
            stages: {
                ...prev.stages,
                [stage]: {
                    ...prev.stages[stage],
                    [parameter]: {
                        ...prev.stages[stage][parameter],
                        [bound]: value === '' ? '' : parseFloat(value) || 0
                    }
                }
            }
        }));
    };

    const handleDurationChange = (stage, value) => {
        setFormData(prev => ({
            ...prev,
            stages: {
                ...prev.stages,
                [stage]: {
                    ...prev.stages[stage],
                    duration_days: value === '' ? '' : parseInt(value, 10) || 0
                }
            }
        }));
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        const seedlingDuration = parseInt(formData.stages.Seedling.duration_days, 10) || 7;
        const vegDuration = parseInt(formData.stages.Vegetative.duration_days, 10) || 14;
        const harvestDuration = parseInt(formData.stages.Harvesting.duration_days, 10) || 30;

        const payload = {
            name: formData.name,
            image_url: formData.image_url,
            image: formData.image_url,
            stages: {
                Seedling: {
                    ec: {
                        min: parseFloat(formData.stages.Seedling.ec.min) || 0,
                        max: parseFloat(formData.stages.Seedling.ec.max) || 0
                    },
                    ph: {
                        min: parseFloat(formData.stages.Seedling.ph.min) || 0,
                        max: parseFloat(formData.stages.Seedling.ph.max) || 0
                    },
                    duration_days: seedlingDuration,
                    start_day: 0
                },
                Vegetative: {
                    ec: {
                        min: parseFloat(formData.stages.Vegetative.ec.min) || 0,
                        max: parseFloat(formData.stages.Vegetative.ec.max) || 0
                    },
                    ph: {
                        min: parseFloat(formData.stages.Vegetative.ph.min) || 0,
                        max: parseFloat(formData.stages.Vegetative.ph.max) || 0
                    },
                    duration_days: vegDuration,
                    start_day: seedlingDuration
                },
                Harvesting: {
                    ec: {
                        min: parseFloat(formData.stages.Harvesting.ec.min) || 0,
                        max: parseFloat(formData.stages.Harvesting.ec.max) || 0
                    },
                    ph: {
                        min: parseFloat(formData.stages.Harvesting.ph.min) || 0,
                        max: parseFloat(formData.stages.Harvesting.ph.max) || 0
                    },
                    duration_days: harvestDuration,
                    start_day: seedlingDuration + vegDuration
                }
            }
        };

        onSave(payload);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-slate-900 border border-slate-700 w-full max-w-3xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
                <div className="flex justify-between items-center p-6 border-b border-slate-800 bg-slate-900/50">
                    <h2 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500">
                        {presetToEdit ? 'Edit Plant Settings' : 'Add a New Plant'}
                    </h2>
                    <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-white transition-colors">
                        <HiX className="w-6 h-6" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
                    <form id="presetForm" onSubmit={handleSubmit} className="space-y-8">
                        {/* Plant Info */}
                        <div className="space-y-6">
                            <div className="space-y-2">
                                <label className="block text-sm font-medium text-slate-300">What are you growing?</label>
                                <input
                                    required
                                    type="text"
                                    value={formData.name}
                                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-3 px-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none transition-all"
                                    placeholder="Enter plant name (e.g. Basil, Pepper)..."
                                />
                            </div>

                            <div className="space-y-4">
                                <label className="block text-sm font-medium text-slate-300">Pick a plant type:</label>
                                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                                    {avatars.map(av => (
                                        <div
                                            key={av.id}
                                            onClick={() => setFormData({ ...formData, image_url: av.url })}
                                            className={`relative cursor-pointer rounded-xl overflow-hidden border-2 transition-all ${formData.image_url === av.url ? 'border-emerald-500 shadow-lg shadow-emerald-500/20' : 'border-slate-800 hover:border-slate-600'
                                                }`}
                                        >
                                            <img 
                                                src={av.url} 
                                                alt={av.name} 
                                                className="w-full h-20 object-cover" 
                                                onError={(e) => {
                                                    e.target.onerror = null;
                                                    e.target.src = "/images/lettuce.jpg";
                                                }}
                                            />
                                            <div className="absolute inset-x-0 bottom-0 bg-black/60 p-1 text-center text-[10px] font-bold text-white uppercase tracking-tight">
                                                {av.name}
                                            </div>
                                            {formData.image_url === av.url && (
                                                <div className="absolute top-1.5 right-1.5 bg-emerald-500 rounded-full text-white">
                                                    <HiCheckCircle className="w-4 h-4" />
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {/* Growth Settings - 3 Canonical Phases */}
                        <div className="space-y-6">
                            <h3 className="text-lg font-semibold text-slate-200 border-b border-slate-800 pb-2">3-Phase Growth & Target Settings</h3>
                            <p className="text-xs text-slate-500 italic">Set the duration and target EC/pH ranges for each growth phase.</p>

                            {STAGE_KEYS.map(stage => (
                                <div key={stage} className="bg-slate-950/50 p-4 rounded-xl border border-slate-800 space-y-4">
                                    <h4 className="font-medium text-emerald-400">{stageLabels[stage]}</h4>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        {/* Nutrients */}
                                        <div className="space-y-2">
                                            <label className="text-xs text-slate-400 font-bold tracking-wide">Nutrients (EC)</label>
                                            <div className="flex space-x-2">
                                                <input
                                                    type="number" step="0.1" title={`${stage} Min EC`} aria-label={`${stage} Min EC`}
                                                    value={formData.stages[stage]?.ec?.min ?? 0}
                                                    onChange={e => handleStageChange(stage, 'ec', 'min', e.target.value)}
                                                    className="w-1/2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white outline-none focus:border-emerald-500"
                                                />
                                                <span className="text-slate-500 flex items-center">-</span>
                                                <input
                                                    type="number" step="0.1" title={`${stage} Max EC`} aria-label={`${stage} Max EC`}
                                                    value={formData.stages[stage]?.ec?.max ?? 0}
                                                    onChange={e => handleStageChange(stage, 'ec', 'max', e.target.value)}
                                                    className="w-1/2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white outline-none focus:border-emerald-500"
                                                />
                                            </div>
                                        </div>

                                        {/* Acidity */}
                                        <div className="space-y-2">
                                            <label className="text-xs text-slate-400 font-bold tracking-wide">Acidity (pH)</label>
                                            <div className="flex space-x-2">
                                                <input
                                                    type="number" step="0.1" title={`${stage} Min pH`} aria-label={`${stage} Min pH`}
                                                    value={formData.stages[stage]?.ph?.min ?? 0}
                                                    onChange={e => handleStageChange(stage, 'ph', 'min', e.target.value)}
                                                    className="w-1/2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white outline-none focus:border-emerald-500"
                                                />
                                                <span className="text-slate-500 flex items-center">-</span>
                                                <input
                                                    type="number" step="0.1" title={`${stage} Max pH`} aria-label={`${stage} Max pH`}
                                                    value={formData.stages[stage]?.ph?.max ?? 0}
                                                    onChange={e => handleStageChange(stage, 'ph', 'max', e.target.value)}
                                                    className="w-1/2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white outline-none focus:border-emerald-500"
                                                />
                                            </div>
                                        </div>

                                        {/* Duration */}
                                        <div className="space-y-2">
                                            <label className="text-xs text-slate-400 font-bold tracking-wide">Phase Duration (Days)</label>
                                            <input
                                                type="number" min="1" step="1" title={`${stage} Duration (Days)`} aria-label={`${stage} Duration (Days)`}
                                                required
                                                value={formData.stages[stage]?.duration_days ?? 7}
                                                onChange={e => handleDurationChange(stage, e.target.value)}
                                                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white outline-none focus:border-emerald-500"
                                                placeholder="Duration in days"
                                            />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </form>
                </div>

                <div className="p-6 border-t border-slate-800 bg-slate-900/80 flex justify-end space-x-4">
                    <button onClick={onClose} className="px-6 py-2.5 rounded-xl font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition-colors">
                        Cancel
                    </button>
                    <button type="submit" form="presetForm" className="px-6 py-2.5 rounded-xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-500 text-white hover:shadow-lg hover:shadow-emerald-500/20 active:scale-[0.98] transition-all">
                        Save Plant
                    </button>
                </div>
            </div>
        </div>
    );
};

export default PresetManagerModal;
