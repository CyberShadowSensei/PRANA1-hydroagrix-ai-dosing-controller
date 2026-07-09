import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { HiInformationCircle, HiPlus, HiPencil, HiTrash } from 'react-icons/hi';
import PresetManagerModal from './PresetManagerModal';
import PresetHistory from './PresetHistory';

const PlantPresets = () => {
  const [isAutomatic, setIsAutomatic] = useState(false);
  const [plantStatus, setPlantStatus] = useState({
    plant_name: '',
    plant_stage: '',
    state: false
  });
  const [isLoading, setIsLoading] = useState(true);

  const [plantCatalog, setPlantCatalog] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingPreset, setEditingPreset] = useState(null);

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
    if (!window.confirm("Are you sure you want to delete this preset?")) return;
    try {
      const response = await axios.delete(`/api/presets/${id}`);
      if (response.status === 200) fetchPresets();
    } catch (e) {
      console.error(e);
    }
  };

  // Fetch current plant status from backend
  useEffect(() => {
    const fetchPlantStatus = async () => {
      try {
        setIsLoading(true);
        const response = await axios.get('/get_plant_status');
        const data = response.data;
        setPlantStatus(data);
        setIsAutomatic(data.state);
      } catch (error) {
        console.error('Error fetching plant status:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchPlantStatus();
  }, []);

  const toggleMode = async () => {
    const originalState = isAutomatic;
    const newState = !originalState;

    // Optimistically update UI
    setIsAutomatic(newState);
    setPlantStatus(prev => ({ ...prev, state: newState }));

    try {
      const response = await axios.post('/update_plant_status', { state: newState });

      if (response.status !== 200) {
        throw new Error('Failed to update mode on the server.');
      }

      // Re-sync with the definitive state from server
      const data = response.data;
      setIsAutomatic(data.state);
      setPlantStatus(data);

    } catch (error) {
      console.error('Error updating mode:', error);
      // Rollback UI on error
      setIsAutomatic(originalState);
      setPlantStatus(prev => ({ ...prev, state: originalState }));
    }
  };

  const setActivePlant = async (plantName) => {
    const originalStatus = { ...plantStatus };

    // Optimistically update UI
    setPlantStatus(prev => ({ ...prev, plant_name: plantName }));

    try {
      const response = await axios.post('/set_active_plant', { plant_name: plantName });

      if (response.status !== 200) {
        throw new Error('Failed to set active plant on the server.');
      }

      // Re-sync with definitive state from server
      const data = response.data;
      setPlantStatus(data);
      setIsAutomatic(data.state); // Also sync the automatic state

    } catch (error) {
      console.error('Error setting active plant:', error);
      // Rollback UI on error
      setPlantStatus(originalStatus);
    }
  };

  return (
    <div className="w-full min-h-screen bg-slate-950 p-4 sm:p-6 text-slate-200">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)]">
            Plant Presets
          </h1>
          <p className="text-slate-400 mt-2">
            Configure automated controls based on plant needs and growth stages
          </p>
        </div>

        {/* Mode Toggle */}
        <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 mb-8 shadow-xl border border-slate-800/50 transition-all duration-300">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center">
            <div>
              <h2 className="text-xl font-semibold text-slate-100">Control Mode</h2>
              <p className="text-slate-400 text-sm mt-1">Switch between automatic and manual control</p>
            </div>

            <div
              onClick={toggleMode}
              className="mt-4 md:mt-0 flex items-center bg-slate-950/50 p-2 rounded-full border border-slate-800/50 cursor-pointer"
            >
              <span className={`px-4 py-1.5 rounded-full text-sm transition-all duration-300 ${!isAutomatic ? 'bg-slate-800 text-white font-medium shadow-lg' : 'text-slate-500'}`}>
                Manual
              </span>
              <div
                className={`w-14 h-7 flex items-center rounded-full p-1 mx-2 transition-colors duration-300 ${isAutomatic ? 'bg-emerald-500' : 'bg-slate-700'
                  }`}
              >
                <div
                  className={`bg-white w-5 h-5 rounded-full shadow-md transform transition-transform duration-300 ${isAutomatic ? 'translate-x-7' : 'translate-x-0'
                    }`}
                />
              </div>
              <span className={`px-4 py-1.5 rounded-full text-sm transition-all duration-300 ${isAutomatic ? 'bg-emerald-500/20 text-emerald-400 font-medium' : 'text-slate-500'}`}>
                Automatic
              </span>
            </div>
          </div>
        </div>

        {/* Current Plant Status */}
        <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 mb-8 shadow-xl border border-slate-800/50">
          <h2 className="text-xl font-semibold text-slate-100 mb-4 flex items-center">
            <span className="w-2 h-2 bg-emerald-500 rounded-full mr-2 animate-pulse"></span>
            Current Plant Status
          </h2>
          {isLoading ? (
            <div className="flex items-center space-x-2 text-slate-400 mt-4">
              <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
              <span>Loading current configuration...</span>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-950/50 p-4 rounded-xl border border-slate-800/30 hover:border-emerald-500/30 transition-colors duration-300">
                <p className="text-slate-500 text-xs uppercase tracking-wider font-bold mb-1">Active Plant</p>
                <p className="text-lg font-medium text-white">{plantStatus.plant_name || 'None selected'}</p>
              </div>
              <div className="bg-slate-950/50 p-4 rounded-xl border border-slate-800/30 hover:border-emerald-500/30 transition-colors duration-300">
                <p className="text-slate-500 text-xs uppercase tracking-wider font-bold mb-1">Detected Stage</p>
                <p className="text-lg font-medium text-white">{plantStatus.plant_stage || 'Unknown'}</p>
              </div>
              <div className="bg-slate-950/50 p-4 rounded-xl border border-slate-800/30 hover:border-emerald-500/30 transition-colors duration-300">
                <p className="text-slate-500 text-xs uppercase tracking-wider font-bold mb-1">System State</p>
                <p className={`text-lg font-medium ${isAutomatic ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {isAutomatic ? 'Autonomous Control' : 'Manual Override'}
                </p>
              </div>
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
                    src={plant.image}
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
                      { key: 'Vegetative', label: 'Vegetative', colorClass: 'bg-emerald-500', textClass: 'text-emerald-400', borderHover: 'group-hover:border-emerald-500/20' },
                      { key: 'Flowering', label: 'Flowering', colorClass: 'bg-amber-500', textClass: 'text-amber-400', borderHover: 'group-hover:border-amber-500/20' },
                      { key: 'Maturity', label: 'Harvest', colorClass: 'bg-orange-500', textClass: 'text-orange-400', borderHover: 'group-hover:border-orange-500/20' }
                    ].map(stage => (
                      <div key={stage.key} className="space-y-3">
                        <div className="flex items-center space-x-2">
                          <div className={`w-1.5 h-1.5 rounded-full ${stage.colorClass}`}></div>
                          <span className={`${stage.textClass} text-[9px] sm:text-[10px] font-bold uppercase tracking-widest truncate`}>{stage.label}</span>
                        </div>
                        <div className="space-y-2">
                          <div className={`bg-slate-900/80 p-2 sm:p-2.5 rounded-lg border border-slate-800/50 transition-colors ${stage.borderHover}`}>
                            <span className="text-slate-500 text-[9px] uppercase font-bold block mb-0.5">EC Range</span>
                            <p className="text-white text-[11px] sm:text-xs font-medium">{plant.stages?.[stage.key]?.ec?.min || 0} - {plant.stages?.[stage.key]?.ec?.max || 0}</p>
                          </div>
                          <div className={`bg-slate-900/80 p-2 sm:p-2.5 rounded-lg border border-slate-800/50 transition-colors ${stage.borderHover}`}>
                            <span className="text-slate-500 text-[9px] uppercase font-bold block mb-0.5">pH Range</span>
                            <p className="text-white text-[11px] sm:text-xs font-medium">{plant.stages?.[stage.key]?.ph?.min || 0} - {plant.stages?.[stage.key]?.ph?.max || 0}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-6 pt-4 border-t border-slate-900 flex flex-col items-center">
                    <button
                      onClick={() => setActivePlant(plant.name)}
                      disabled={!isAutomatic}
                      className={`w-full py-3 rounded-xl font-bold transition-all duration-300 transform active:scale-[0.98] ${!isAutomatic
                        ? 'bg-slate-900 text-slate-600 cursor-not-allowed border border-slate-800'
                        : 'bg-gradient-to-r from-emerald-500 to-cyan-500 text-white hover:shadow-lg hover:shadow-emerald-500/20'
                        }`}
                    >
                      Apply Growth Preset
                    </button>

                    {!isAutomatic && (
                      <div className="flex items-center mt-3 text-amber-500/80 text-[10px] uppercase tracking-widest font-bold">
                        <HiInformationCircle className="mr-1 text-sm" />
                        <span>Enable Automatic Mode to switch</span>
                      </div>
                    )}
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
    </div>
  );
};

export default PlantPresets;