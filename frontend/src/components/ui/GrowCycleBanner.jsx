/**
 * GrowCycleBanner Component
 * Top-level status banner displaying active plant name, current cycle day, and phase progression.
 */
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { HiPlay, HiStop, HiCalendar, HiTag, HiChip, HiArrowRight, HiClock } from 'react-icons/hi';
import toast from 'react-hot-toast';
import socket from '../../socket';

const GrowCycleBanner = ({ cycleStatus, isAutomatic, onToggleMode, onRefresh }) => {
  const [isToggling, setIsToggling] = useState(false);
  const [presets, setPresets] = useState([]);
  const [selectedPreset, setSelectedPreset] = useState('');
  const [isLoadingPresets, setIsLoadingPresets] = useState(false);
  const [statusData, setStatusData] = useState(cycleStatus);

  useEffect(() => {
    if (cycleStatus) {
      setStatusData(cycleStatus);
    }
  }, [cycleStatus]);

  useEffect(() => {
    const handleGrowCycleUpdate = (data) => {
      if (data) {
        setStatusData(data);
      }
      if (onRefresh) {
        onRefresh();
      }
    };

    socket.on('grow_cycle_update', handleGrowCycleUpdate);
    return () => {
      socket.off('grow_cycle_update', handleGrowCycleUpdate);
    };
  }, [onRefresh]);

  const currentStatus = statusData || cycleStatus;

  useEffect(() => {
    if (!currentStatus || !currentStatus.active) {
      setIsLoadingPresets(true);
      axios.get('/api/presets')
        .then(res => {
          setPresets(res.data || []);
          if (res.data && res.data.length > 0) {
            setSelectedPreset(res.data[0].name);
          }
        })
        .catch(err => console.error("Error fetching presets:", err))
        .finally(() => setIsLoadingPresets(false));
    }
  }, [currentStatus]);

  const handleToggle = async (targetMode) => {
    if (!onToggleMode) return;
    setIsToggling(true);
    try {
      await onToggleMode(targetMode);
    } finally {
      setIsToggling(false);
    }
  };

  const handleStartCycle = async () => {
    if (!selectedPreset) {
      toast.error("Please select a plant preset.");
      return;
    }
    setIsToggling(true);
    try {
      const response = await axios.post('/set_active_plant', { plant_name: selectedPreset });
      if (response.status === 200) {
        toast.success(`Started growth cycle for ${selectedPreset}!`);
        if (onRefresh) await onRefresh();
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to start growth cycle.");
    } finally {
      setIsToggling(false);
    }
  };

  const handleEndCycle = async () => {
    if (!window.confirm("Are you sure you want to end the current growth cycle? This will compile a report and return the system to manual idle.")) return;
    setIsToggling(true);
    try {
      const response = await axios.post('/complete_cycle');
      if (response.status === 200) {
        toast.success("Growth cycle ended successfully. Report is compiling in background.");
        if (onRefresh) await onRefresh();
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to complete growth cycle.");
    } finally {
      setIsToggling(false);
    }
  };

  const ModeToggle = () => (
    <div
      className={`flex items-center bg-slate-950/70 p-1.5 rounded-full border border-slate-800 ${isToggling ? 'opacity-50 pointer-events-none' : ''}`}
    >
      <button
        type="button"
        onClick={() => handleToggle(false)}
        className={`px-3.5 py-1 rounded-full text-xs font-medium cursor-pointer transition-all duration-300 ${!isAutomatic ? 'bg-slate-800 text-white shadow-md' : 'text-slate-400 hover:text-slate-200'}`}
      >
        Manual
      </button>
      <div
        onClick={() => handleToggle(!isAutomatic)}
        className={`w-12 h-6 flex items-center rounded-full p-1 mx-1.5 cursor-pointer transition-colors duration-300 ${isAutomatic ? 'bg-emerald-500' : 'bg-slate-700'}`}
      >
        <div
          className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${isAutomatic ? 'translate-x-6' : 'translate-x-0'}`}
        />
      </div>
      <button
        type="button"
        onClick={() => handleToggle(true)}
        className={`px-3.5 py-1 rounded-full text-xs font-medium cursor-pointer transition-all duration-300 ${isAutomatic ? 'bg-emerald-500/20 text-emerald-400 font-semibold' : 'text-slate-400 hover:text-slate-200'}`}
      >
        Autonomous
      </button>
    </div>
  );

  if (!currentStatus || !currentStatus.active) {
    return (
      <div className="bg-slate-900/50 backdrop-blur-md rounded-2xl p-6 mb-8 shadow-2xl border border-slate-800/80 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 bg-slate-500 rounded-full"></span>
            <h2 className="text-xl font-bold text-slate-100">No Active Grow Cycle</h2>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            The dosing controller is locked. Start a growth cycle to configure manual/autonomous control modes.
          </p>
        </div>
        
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-4 w-full md:w-auto">
          {isLoadingPresets ? (
            <div className="text-slate-400 text-sm">Loading presets...</div>
          ) : (
            <select
              className="bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white outline-none focus:border-emerald-500 text-sm min-w-[200px]"
              value={selectedPreset}
              onChange={(e) => setSelectedPreset(e.target.value)}
              disabled={isToggling}
            >
              {presets.map(p => (
                <option key={p.id || p.name} value={p.name}>{p.name}</option>
              ))}
              {presets.length === 0 && <option value="">No presets configured</option>}
            </select>
          )}
          <button
            onClick={handleStartCycle}
            disabled={isToggling || presets.length === 0}
            className="flex items-center justify-center px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold rounded-xl text-sm transition-all shadow-lg shadow-emerald-500/10 disabled:opacity-50 cursor-pointer"
          >
            <HiPlay className="w-5 h-5 mr-2" />
            Start Grow Cycle
          </button>
        </div>
      </div>
    );
  }

  const {
    day = 1,
    phase = 'Unknown',
    phase_source = 'Schedule',
    next_phase_name = 'N/A',
    expected_transition_day = 'N/A',
    next_milestone,
    ml_verification = 'Unconfirmed',
    ml_info = 'Awaiting ML inference...'
  } = currentStatus;

  const displayNextPhase = next_phase_name !== 'N/A' ? next_phase_name : (next_milestone || 'N/A');
  const displayTransitionDay = expected_transition_day !== 'N/A' ? expected_transition_day : 'N/A';

  return (
    <div className="bg-slate-900/60 backdrop-blur-md rounded-2xl p-6 mb-8 shadow-2xl border border-emerald-500/20">
      {/* Top Header */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 pb-4 border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <span className="w-3 h-3 bg-emerald-500 rounded-full animate-pulse flex-shrink-0"></span>
          <h2 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">
            Active Growth Cycle
          </h2>
        </div>

        <div className="flex flex-wrap items-center gap-4 w-full lg:w-auto justify-between lg:justify-end">
          <div className="flex items-center gap-3">
            <span className="text-slate-400 text-xs font-semibold uppercase tracking-wider">Control Mode</span>
            <ModeToggle />
          </div>
          
          <button
            onClick={handleEndCycle}
            disabled={isToggling}
            className="flex items-center justify-center px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 hover:border-red-500/50 rounded-xl text-sm font-semibold transition-all cursor-pointer"
          >
            <HiStop className="w-4 h-4 mr-1.5" />
            End Cycle
          </button>
        </div>
      </div>

      {/* 4 Field Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 mt-5">
        {/* Field 1: Growth Cycle Day */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3.5 flex flex-col justify-between hover:border-emerald-500/30 transition-all">
          <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
            <HiCalendar className="text-emerald-400 w-4 h-4" />
            Cycle Day
          </span>
          <span className="text-lg font-bold text-white mt-1.5">
            Day {day}
          </span>
        </div>

        {/* Field 2: Current Phase */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3.5 flex flex-col justify-between hover:border-emerald-500/30 transition-all">
          <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
            <HiTag className="text-cyan-400 w-4 h-4" />
            Current Phase
          </span>
          <span className="text-lg font-bold text-emerald-400 mt-1.5 truncate">
            {phase}
          </span>
        </div>

        {/* Field 3: Next Phase */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3.5 flex flex-col justify-between hover:border-emerald-500/30 transition-all">
          <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
            <HiArrowRight className="text-amber-400 w-4 h-4" />
            Next Phase
          </span>
          <span className="text-base font-bold text-slate-200 mt-1.5 truncate">
            {displayNextPhase}
          </span>
        </div>

        {/* Field 4: Expected Transition Day */}
        <div className="bg-slate-950/50 border border-slate-800/80 rounded-xl p-3.5 flex flex-col justify-between hover:border-emerald-500/30 transition-all">
          <span className="text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1.5">
            <HiClock className="text-teal-400 w-4 h-4" />
            Expected Transition
          </span>
          <span className="text-xs font-semibold text-teal-300 mt-1.5 truncate">
            {displayTransitionDay}
          </span>
        </div>
      </div>
    </div>
  );
};

export default GrowCycleBanner;

