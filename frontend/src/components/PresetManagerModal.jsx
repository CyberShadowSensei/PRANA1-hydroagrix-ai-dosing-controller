import React, { useState, useEffect } from 'react';
import { HiX, HiCheckCircle } from 'react-icons/hi';

// Using your local downloaded images for a fully offline-ready experience
const avatars = [
    { id: 'leaf', name: 'Leafy Green', url: '/images/leafy green.avif' },
    { id: 'vine', name: 'Vine Crop', url: '/images/vine crop.jpg' },
    { id: 'fruiting', name: 'Fruiting Crop', url: '/images/Fruiting Crop.webp' },
    { id: 'herb', name: 'Herb', url: '/images/Herb.webp' },
    { id: 'berry', name: 'Berry', url: '/images/Berry.webp' },
    { id: 'strawberry', name: 'Strawberry', url: '/images/strawberry.PNG' },
    { id: 'tomato', name: 'Tomato', url: '/images/tomato.jpg' },
    { id: 'spinach', name: 'Spinach', url: '/images/spinach.jpg' },
    { id: 'lettuce', name: 'Lettuce', url: '/images/lettuce.jpg' }
];

const stageLabels = {
    Germination: "1. Starting (Seeds)",
    Vegetative: "2. Growing (Leaves)",
    Flowering: "3. Blooming (Flowers)",
    Maturity: "4. Harvest (Ready)"
};

const PresetManagerModal = ({ isOpen, onClose, presetToEdit, onSave }) => {
    const defaultImageUrl = avatars[0].url; // Default to Leafy Green

    const [formData, setFormData] = useState({
        name: '',
        image_url: defaultImageUrl,
        stages: {
            Vegetative: { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } },
            Flowering: { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } },
            Maturity: { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } }
        }
    });

    useEffect(() => {
        if (presetToEdit) {
            setFormData({
                name: presetToEdit.name || '',
                image_url: presetToEdit.image || defaultImageUrl,
                stages: {
                    Vegetative: presetToEdit.stages?.Vegetative || { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } },
                    Flowering: presetToEdit.stages?.Flowering || { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } },
                    Maturity: presetToEdit.stages?.Maturity || { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } }
                }
            });
        } else {
            setFormData({
                name: '',
                image_url: defaultImageUrl,
                stages: {
                    Vegetative: { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } },
                    Flowering: { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } },
                    Maturity: { ec: { min: 0, max: 0 }, ph: { min: 0, max: 0 } }
                }
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
                        [bound]: parseFloat(value) || 0
                    }
                }
            }
        }));
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        onSave(formData);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-slate-900 border border-slate-700 w-full max-w-3xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
                <div className="flex justify-between items-center p-6 border-b border-slate-800 bg-slate-900/50">
                    <h2 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500">
                        {presetToEdit ? 'Edit Plant Settings' : 'Add a New Plant'}
                    </h2>
                    <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
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
                                                    e.target.src = "/images/lettuce.jpg"; // Internal fallback
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

                        {/* Growth Settings */}
                        <div className="space-y-6">
                            <h3 className="text-lg font-semibold text-slate-200 border-b border-slate-800 pb-2">Nutrient & Acidity Settings</h3>
                            <p className="text-xs text-slate-500 italic">Set the target levels for each stage of your plant's life.</p>

                            {['Vegetative', 'Flowering', 'Maturity'].map(stage => (
                                <div key={stage} className="bg-slate-950/50 p-4 rounded-xl border border-slate-800">
                                    <h4 className="font-medium text-emerald-400 mb-4">{stageLabels[stage]}</h4>
                                    <div className="grid grid-cols-2 gap-6">
                                        {/* Nutrients */}
                                        <div className="space-y-2">
                                            <label className="text-xs text-slate-400 font-bold tracking-wide">Nutrients (EC)</label>
                                            <div className="flex space-x-2">
                                                <input
                                                    type="number" step="0.1" title="Min Nutrients"
                                                    value={formData.stages[stage]?.ec?.min || 0}
                                                    onChange={e => handleStageChange(stage, 'ec', 'min', e.target.value)}
                                                    className="w-1/2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white outline-none focus:border-emerald-500"
                                                />
                                                <span className="text-slate-500 flex items-center">-</span>
                                                <input
                                                    type="number" step="0.1" title="Max Nutrients"
                                                    value={formData.stages[stage]?.ec?.max || 0}
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
                                                    type="number" step="0.1" title="Min pH"
                                                    value={formData.stages[stage]?.ph?.min || 0}
                                                    onChange={e => handleStageChange(stage, 'ph', 'min', e.target.value)}
                                                    className="w-1/2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white outline-none focus:border-emerald-500"
                                                />
                                                <span className="text-slate-500 flex items-center">-</span>
                                                <input
                                                    type="number" step="0.1" title="Max pH"
                                                    value={formData.stages[stage]?.ph?.max || 0}
                                                    onChange={e => handleStageChange(stage, 'ph', 'max', e.target.value)}
                                                    className="w-1/2 bg-slate-900 border border-slate-700 rounded-lg p-2 text-white outline-none focus:border-emerald-500"
                                                />
                                            </div>
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
