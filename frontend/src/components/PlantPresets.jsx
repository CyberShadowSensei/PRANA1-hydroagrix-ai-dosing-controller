import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { HiPlus, HiPencil, HiTrash, HiCalendar, HiTag, HiChip, HiArrowRight, HiClock, HiX } from 'react-icons/hi';
import PresetManagerModal from './PresetManagerModal';
import PresetHistory from './PresetHistory';
import socket from '../socket';

export const ManageProgressModal = ({ isOpen, onClose, cycleStatus, plantStatus, onProgressUpdated }) => {
    const [day, setDay] = useState(1);
    const [phase, setPhase] = useState('Seedling');
    const [isSubmitting, setIsSubmitting] = useState(false);

    useEffect(() => {
        if (isOpen) {
            setDay(cycleStatus?.day !== undefined ? cycleStatus.day : 1);
            const initialPhase = cycleStatus?.phase || plantStatus?.plant_stage || 'Seedling';
            setPhase(['Seedling', 'Vegetative', 'Harvesting'].includes(initialPhase) ? initialPhase : 'Seedling');
        }
    }, [isOpen, cycleStatus, plantStatus]);

    if (!isOpen) return null;

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            setIsSubmitting(true);
            const targetDay = parseInt(day, 10) || 0;
            const response = await axios.post('/update_grow_cycle_progress', {
                day: targetDay,
                phase: phase,
                plant_stage: phase
            });

            if (response.status === 200) {
                const [plantRes, cycleRes] = await Promise.all([
                    axios.get('/get_plant_status').catch(() => ({ data: {} })),
                    axios.get('/get_grow_cycle_status').catch(() => ({ data: null }))
                ]);
                if (onProgressUpdated) {
                    onProgressUpdated(plantRes.data, cycleRes.data);
                }
                onClose();
            } else {
                alert('Failed to update progress');
            }
        } catch (error) {
            console.error('Error updating grow cycle progress:', error);
            alert('Failed to update grow cycle progress');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-slate-900 border border-slate-700 w-full max-w-md rounded-2xl shadow-2xl overflow-hidden flex flex-col">
                <div className="flex justify-between items-center p-6 border-b border-slate-800 bg-slate-900/50">
                    <h2 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 flex items-center gap-2">
                        <HiClock className="text-emerald-400 w-5 h-5" />
                        Manage Grow Cycle Progress
                    </h2>
                    <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-white transition-colors">
                        <HiX className="w-6 h-6" />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-6">
                    <div className="space-y-2">
                        <label className="block text-sm font-medium text-slate-300">
                            Current Cycle Day
                        </label>
                        <input
                            type="number"
                            min="0"
                            required
                            aria-label="Current Cycle Day"
                            title="Current Cycle Day"
                            value={day}
                            onChange={(e) => setDay(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none transition-all"
                        />
                    </div>

                    <div className="space-y-2">
                        <label className="block text-sm font-medium text-slate-300">
                            Growth Phase
                        </label>
                        <select
                            value={phase}
                            aria-label="Growth Phase"
                            title="Growth Phase"
                            onChange={(e) => setPhase(e.target.value)}
                            className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none transition-all"
                        >
                            <option value="Seedling">Seedling</option>
                            <option value="Vegetative">Vegetative</option>
                            <option value="Harvesting">Harvesting</option>
                        </select>
                    </div>

                    <div className="pt-4 border-t border-slate-800 flex justify-end space-x-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-5 py-2 rounded-xl text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={isSubmitting}
                            className="px-5 py-2 rounded-xl text-sm font-bold bg-gradient-to-r from-emerald-400 to-cyan-500 text-white hover:shadow-lg hover:shadow-emerald-500/20 active:scale-[0.98] transition-all disabled:opacity-50"
                        >
                            {isSubmitting ? 'Updating...' : 'Update Progress'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

const PlantPresets = () => {
  const [isAutomatic, setIsAutomatic] = useState(false);
  const [plantStatus, setPlantStatus] = useState({
    plant_name: '',
    plant_stage: '',
    state: false
  });
  const [cycleStatus, setCycleStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const [plantCatalog, setPlantCatalog] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingPreset, setEditingPreset] = useState(null);
  const [isManageProgressOpen, setIsManageProgressOpen] = useState(false);

  const fetchPresets = async () => {
    try {
      const resp = await axios.get('/api/presets');
      if (resp.status === 200) {
        setPlantCatalog(resp.data);
      }
    } catch (error) {
      console.error('Error fetching presets:', error);
    }
  };

  useEffect(() => {
    fetchPresets();
  }, []);

  const handleSavePreset = async (presetData) => {
    try {
      const url = editingPreset ? `/api/presets/${editingPreset.id}` : '/api/presets';
      const method = editingPreset ? 'put' : 'post';
      const response = await axios({
        url,
        method,
        data: presetData
      });
      if (response.status === 200) {
        setIsModalOpen(false);
        setEditingPreset(null);
        fetchPresets();
      } else {
        alert("Failed to save preset");
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeletePreset = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to remove this preset?")) return;
    try {
      const response = await axios.delete(`/api/presets/${id}`);
      if (response.status === 200) fetchPresets();
    } catch (e) {
      console.error(e);
      if (e.response && e.response.data && e.response.data.error) {
        alert(e.response.data.error);
      } else {
        alert("Failed to remove preset.");
      }
    }
  };

  // Fetch current plant status from backend
  useEffect(() => {
    const fetchPlantStatus = async () => {
      try {
        setIsLoading(true);
        const [plantRes, cycleRes] = await Promise.all([
          axios.get('/get_plant_status').catch(() => ({ data: {} })),
          axios.get('/get_grow_cycle_status').catch(() => ({ data: null }))
        ]);
        
        const data = plantRes.data;
        setPlantStatus(data);
        setIsAutomatic(data.state);
        setCycleStatus(cycleRes.data);
      } catch (error) {
        console.error('Error fetching status:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchPlantStatus();

    // Real-time sync: listen for grow_cycle_update from backend
    const handleGrowCycleUpdate = (data) => {
      if (data) {
        setCycleStatus(data);
        // Sync the is_automatic toggle state from the event
        if (typeof data.is_automatic === 'boolean') {
          setIsAutomatic(data.is_automatic);
          setPlantStatus(prev => ({ ...prev, state: data.is_automatic }));
        }
      }
    };
    socket.on('grow_cycle_update', handleGrowCycleUpdate);
    return () => {
      socket.off('grow_cycle_update', handleGrowCycleUpdate);
    };
  }, []);

  const handlePhaseChange = async (direction) => {
    try {
      setIsLoading(true);
      const response = await axios.post('/api/grow_cycle/change_phase', { direction });
      if (response.status === 200) {
        const [plantRes, cycleRes] = await Promise.all([
          axios.get('/get_plant_status').catch(() => ({ data: {} })),
          axios.get('/get_grow_cycle_status').catch(() => ({ data: null }))
        ]);
        setPlantStatus(plantRes.data);
        setCycleStatus(cycleRes.data);
      }
    } catch (error) {
      console.error('Error changing phase:', error);
      alert('Failed to change growth phase');
    } finally {
      setIsLoading(false);
    }
  };

  const endGrowCycle = async () => {
    try {
      setIsLoading(true);
      const [response, cycleRes] = await Promise.all([
        axios.post('/complete_cycle'),
        axios.get('/get_grow_cycle_status').catch(() => ({ data: null }))
      ]);
      if (response.status === 200) {
        setPlantStatus({
          plant_name: '',
          plant_stage: '',
          state: false
        });
        setIsAutomatic(false);
        setCycleStatus(cycleRes.data);
      }
    } catch (error) {
      console.error('Error ending cycle:', error);
      alert('Failed to end cycle');
    } finally {
      setIsLoading(false);
    }
  };

  const setActivePlant = async (plantName) => {
    const originalStatus = { ...plantStatus };

    // Optimistically update UI
    setPlantStatus(prev => ({ ...prev, plant_name: plantName }));

    try {
      const [response, cycleRes] = await Promise.all([
        axios.post('/set_active_plant', { plant_name: plantName }),
        axios.get('/get_grow_cycle_status').catch(() => ({ data: null }))
      ]);

      if (response.status !== 200) {
        throw new Error('Failed to set active plant on the server.');
      }

      // Re-sync with definitive state from server
      const data = response.data;
      setPlantStatus(data);
      setIsAutomatic(data.state);
      setCycleStatus(cycleRes.data);

    } catch (error) {
      console.error('Error setting active plant:', error);
      // Rollback UI on error
      setPlantStatus(originalStatus);
    }
  };

  const deselectPlant = async () => {
    try {
      setIsLoading(true);
      const [response, cycleRes] = await Promise.all([
        axios.post('/set_active_plant', { plant_name: '' }),
        axios.get('/get_grow_cycle_status').catch(() => ({ data: null }))
      ]);
      if (response.status === 200) {
        setPlantStatus(response.data);
        setIsAutomatic(response.data.state);
        setCycleStatus(cycleRes.data);
      }
    } catch (error) {
      console.error('Error deselecting plant:', error);
      alert('Failed to clear plant preset');
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleMode = async (targetMode) => {
    const originalState = isAutomatic;
    setIsAutomatic(targetMode);
    setPlantStatus(prev => ({ ...prev, state: targetMode }));

    try {
      const response = await axios.post('/update_plant_status', { state: targetMode });
      if (response.status !== 200) {
        throw new Error('Failed to update mode');
      }
    } catch (error) {
      console.error('Error updating mode:', error);
      setIsAutomatic(originalState);
      setPlantStatus(prev => ({ ...prev, state: originalState }));
    }
  };

  const getStageDataFromPreset = (stages, primaryKey, fallbackKeys = []) => {
    if (!stages) return null;
    if (stages[primaryKey]) return stages[primaryKey];
    for (const key of fallbackKeys) {
      if (stages[key]) return stages[key];
    }
    return null;
  };

  return (
    <div className="w-full min-h-screen bg-slate-950 p-4 sm:p-6 text-slate-200">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8 flex flex-col sm:flex-row justify-between items-start sm:items-center">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)]">
              Plant Presets
            </h1>
            <p className="text-slate-400 mt-2">
              Configure automated controls based on plant needs and growth stages
            </p>
          </div>
          <div className="mt-4 sm:mt-0">
            {!plantStatus?.plant_name ? (
              <div className="text-slate-400 text-sm font-medium italic">Start a grow cycle to configure system mode</div>
            ) : (
              <div className={`flex items-center bg-slate-950/50 p-2 rounded-full border border-slate-800/50`}>
                <span onClick={() => handleToggleMode(false)} className={`px-4 py-1.5 rounded-full text-sm cursor-pointer transition-all duration-300 ${!isAutomatic ? 'bg-slate-800 text-white font-medium shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}>
                  Manual
                </span>
                <div
                  onClick={() => handleToggleMode(!isAutomatic)}
                  className={`w-14 h-7 flex items-center rounded-full p-1 mx-2 cursor-pointer transition-colors duration-300 ${isAutomatic ? 'bg-emerald-500' : 'bg-slate-700'}`}
                >
                  <div
                    className={`bg-white w-5 h-5 rounded-full shadow-md transform transition-transform duration-300 ${isAutomatic ? 'translate-x-7' : 'translate-x-0'}`}
                  />
                </div>
                <span onClick={() => handleToggleMode(true)} className={`px-4 py-1.5 rounded-full text-sm cursor-pointer transition-all duration-300 ${isAutomatic ? 'bg-emerald-500/20 text-emerald-400 font-medium' : 'text-slate-500 hover:text-slate-300'}`}>
                  Autonomous
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Current Plant Status */}
        <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 mb-8 shadow-xl border border-slate-800/50">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4">
            <h2 className="text-xl font-semibold text-slate-100 flex items-center">
              <span className="w-2 h-2 bg-emerald-500 rounded-full mr-2 animate-pulse"></span>
              Current Plant Status
            </h2>
            <div className="flex flex-wrap gap-3">
              {plantStatus.plant_name && (
                <button
                  onClick={() => setIsManageProgressOpen(true)}
                  className="px-4 py-2 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/50 rounded-lg text-sm font-semibold transition-colors flex items-center gap-1.5"
                >
                  <HiClock className="w-4 h-4" />
                  Manage Progress
                </button>
              )}
              {plantStatus.plant_name && (
                <button
                  onClick={deselectPlant}
                  className="px-4 py-2 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700 rounded-lg text-sm font-semibold transition-colors"
                >
                  Clear Preset
                </button>
              )}
              {plantStatus.plant_name && (
                <button
                  onClick={endGrowCycle}
                  className="px-4 py-2 bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/50 rounded-lg text-sm font-semibold transition-colors"
                >
                  End Cycle
                </button>
              )}
            </div>
          </div>
          {isLoading ? (
            <div className="flex items-center space-x-2 text-slate-400 mt-4">
              <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
              <span>Loading current configuration...</span>
            </div>
          ) : (
            <div className="space-y-5">
              {/* Active Plant + System State row */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-slate-950/50 p-4 rounded-xl border border-slate-800/30 hover:border-emerald-500/30 transition-colors duration-300">
                  <p className="text-slate-500 text-xs uppercase tracking-wider font-bold mb-1">Active Plant</p>
                  <p className="text-lg font-semibold text-white">{plantStatus.plant_name || 'None selected'}</p>
                </div>
                <div className="bg-slate-950/50 p-4 rounded-xl border border-slate-800/30 hover:border-emerald-500/30 transition-colors duration-300">
                  <p className="text-slate-500 text-xs uppercase tracking-wider font-bold mb-1">System State</p>
                  <p className={`text-lg font-semibold ${isAutomatic ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {isAutomatic ? 'Autonomous Control' : 'Manual Override'}
                  </p>
                </div>
              </div>

              {/* Growth Cycle Info — 5-field metric grid */}
              {plantStatus.plant_name && cycleStatus && cycleStatus.active && (() => {
                const {
                  day = 1,
                  phase = 'Unknown',
                  phase_source = 'Schedule',
                  next_phase_name,
                  expected_transition_day,
                  next_milestone
                } = cycleStatus;
                const displayNextPhase = next_phase_name && next_phase_name !== 'N/A' ? next_phase_name : (next_milestone || 'Harvest');
                const displayTransition = expected_transition_day && expected_transition_day !== 'N/A' ? expected_transition_day : 'Harvest / End of Cycle';
                return (
                  <div className="bg-slate-950/40 rounded-xl border border-emerald-500/20 p-4">
                    <div className="flex items-center gap-2 mb-4">
                      <span className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></span>
                      <h3 className="text-sm font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400 uppercase tracking-wider">Growth Cycle Info</h3>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                      {/* Cycle Day */}
                      <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between hover:border-emerald-500/30 transition-all">
                        <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
                          <HiCalendar className="text-emerald-400 w-4 h-4" />
                          Cycle Day
                        </span>
                        <span className="text-base font-bold text-white mt-1.5">Day {day}</span>
                      </div>
                      {/* Current Phase */}
                      <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between hover:border-emerald-500/30 transition-all">
                        <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
                          <HiTag className="text-cyan-400 w-4 h-4" />
                          Current Phase
                        </span>
                        <span className="text-base font-bold text-emerald-400 mt-1.5 truncate">{phase}</span>
                      </div>
                      {/* Phase Source */}
                      <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between hover:border-emerald-500/30 transition-all">
                        <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
                          <HiChip className="text-purple-400 w-4 h-4" />
                          Phase Source
                        </span>
                        <div className="mt-1.5">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                            phase_source === 'Both' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                            phase_source === 'ML' ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' :
                            'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                          }`}>{phase_source}</span>
                        </div>
                      </div>
                      {/* Next Phase */}
                      <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between hover:border-emerald-500/30 transition-all">
                        <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
                          <HiArrowRight className="text-amber-400 w-4 h-4" />
                          Next Phase
                        </span>
                        <span className="text-sm font-bold text-slate-200 mt-1.5 truncate">{displayNextPhase}</span>
                      </div>
                      {/* Expected Transition */}
                      <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-3 flex flex-col justify-between hover:border-emerald-500/30 transition-all col-span-2 sm:col-span-1">
                        <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
                          <HiClock className="text-teal-400 w-4 h-4" />
                          Expected Transition
                        </span>
                        <span className="text-xs font-semibold text-teal-300 mt-1.5">{displayTransition}</span>
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}
        </div>

        {/* Plant Catalog */}
        <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold text-slate-100">Plant Catalog</h2>
            <div className="flex items-center space-x-4">
              <span className="text-xs text-slate-500 bg-slate-950 px-3 py-1 rounded-full border border-slate-800">
                {plantCatalog.length} Presets Available
              </span>
              <button
                onClick={() => { setEditingPreset(null); setIsModalOpen(true); }}
                className="flex items-center px-4 py-2 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/50 rounded-lg text-sm font-semibold transition-colors"
              >
                <HiPlus className="mr-1" /> Add Custom
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-6">
            {plantCatalog.map((plant) => (
              <div
                key={plant.name}
                className={`group bg-slate-950/50 rounded-2xl overflow-hidden border transition-all duration-300 ease-in-out ${plantStatus.plant_name === plant.name
                  ? 'border-emerald-500/70 ring-2 ring-emerald-500/50 shadow-2xl shadow-emerald-800/20 scale-[1.03]'
                  : 'border-slate-800/50 hover:border-emerald-500/50 hover:scale-[1.02]'
                  }`}
              >
                <div className="w-full h-52 relative overflow-hidden">
                  <img
                    src={plant.image || plant.image_url}
                    alt={plant.name}
                    className="w-full h-full object-cover transform group-hover:scale-110 transition-transform duration-700 ease-out"
                    onError={(e) => {
                      e.target.onerror = null;
                      e.target.src = "/images/logo.jpg";
                    }}
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/20 to-transparent opacity-60 group-hover:opacity-40 transition-opacity duration-500"></div>
                  <div className="absolute top-4 right-4 flex space-x-2 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                    <button onClick={(e) => { e.stopPropagation(); setEditingPreset(plant); setIsModalOpen(true); }} className="p-2 bg-slate-900/50 hover:bg-emerald-500/50 rounded-full text-white backdrop-blur-md transition-colors"><HiPencil /></button>
                    <button onClick={(e) => handleDeletePreset(plant.id, e)} className="p-2 bg-slate-900/50 hover:bg-red-500/50 rounded-full text-white backdrop-blur-md transition-colors"><HiTrash /></button>
                  </div>
                  <div className="absolute bottom-4 left-4">
                    <h3 className="text-2xl font-bold text-white drop-shadow-lg">{plant.name}</h3>
                  </div>
                </div>

                <div className="p-5">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 sm:gap-4">
                    {[
                      { key: 'Seedling', label: 'Seedling', fallbackKeys: ['Germination'], colorClass: 'bg-teal-500', textClass: 'text-teal-400', borderHover: 'group-hover:border-teal-500/20' },
                      { key: 'Vegetative', label: 'Vegetative', fallbackKeys: [], colorClass: 'bg-emerald-500', textClass: 'text-emerald-400', borderHover: 'group-hover:border-emerald-500/20' },
                      { key: 'Harvesting', label: 'Harvesting', fallbackKeys: ['Flowering', 'Maturity'], colorClass: 'bg-amber-500', textClass: 'text-amber-400', borderHover: 'group-hover:border-amber-500/20' }
                    ].map(stage => {
                      const stageData = getStageDataFromPreset(plant.stages || plant.stages_json, stage.key, stage.fallbackKeys);
                      return (
                        <div key={stage.key} className="space-y-3">
                          <div className="flex items-center space-x-2">
                            <div className={`w-1.5 h-1.5 rounded-full ${stage.colorClass}`}></div>
                            <span className={`${stage.textClass} text-[9px] sm:text-[10px] font-bold uppercase tracking-widest truncate`}>{stage.label}</span>
                          </div>
                          <div className="space-y-2">
                            <div className={`bg-slate-900/80 p-2 sm:p-2.5 rounded-lg border border-slate-800/50 transition-colors ${stage.borderHover}`}>
                              <span className="text-slate-500 text-[9px] uppercase font-bold block mb-0.5">EC Range</span>
                              <p className="text-white text-[11px] sm:text-xs font-medium">{stageData?.ec?.min ?? 0} - {stageData?.ec?.max ?? 0}</p>
                            </div>
                            <div className={`bg-slate-900/80 p-2 sm:p-2.5 rounded-lg border border-slate-800/50 transition-colors ${stage.borderHover}`}>
                              <span className="text-slate-500 text-[9px] uppercase font-bold block mb-0.5">pH Range</span>
                              <p className="text-white text-[11px] sm:text-xs font-medium">{stageData?.ph?.min ?? 0} - {stageData?.ph?.max ?? 0}</p>
                            </div>
                            <div className={`bg-slate-900/80 p-2 sm:p-2.5 rounded-lg border border-slate-800/50 transition-colors ${stage.borderHover}`}>
                              <span className="text-slate-500 text-[9px] uppercase font-bold block mb-0.5">Duration</span>
                              <p className="text-white text-[11px] sm:text-xs font-medium">
                                {stageData?.duration_days !== undefined ? `${stageData.duration_days} Days` : 'N/A'}
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="mt-6 pt-4 border-t border-slate-900 flex flex-col items-center">
                    <button
                      onClick={() => {
                        if (plantStatus.plant_name === plant.name) {
                          deselectPlant();
                        } else {
                          setActivePlant(plant.name);
                        }
                      }}
                      className={`w-full py-3 rounded-xl font-bold transition-all duration-300 transform ${
                        plantStatus.plant_name === plant.name 
                          ? 'active:scale-[0.98] bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700' 
                          : 'active:scale-[0.98] bg-gradient-to-r from-emerald-500 to-cyan-500 text-white hover:shadow-lg hover:shadow-emerald-500/20'
                      }`}
                    >
                      {plantStatus.plant_name === plant.name ? "Deselect Preset" : "Start Grow Cycle"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <PresetHistory />
      </div>
      <PresetManagerModal
        isOpen={isModalOpen}
        onClose={() => { setIsModalOpen(false); setEditingPreset(null); }}
        presetToEdit={editingPreset}
        onSave={handleSavePreset}
      />
      <ManageProgressModal
        isOpen={isManageProgressOpen}
        onClose={() => setIsManageProgressOpen(false)}
        cycleStatus={cycleStatus}
        plantStatus={plantStatus}
        onProgressUpdated={(newPlant, newCycle) => {
          if (newPlant) setPlantStatus(newPlant);
          if (newCycle) setCycleStatus(newCycle);
        }}
      />
    </div>
  );
};

export default PlantPresets;