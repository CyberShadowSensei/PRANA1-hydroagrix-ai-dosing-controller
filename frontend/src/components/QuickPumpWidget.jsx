import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Droplets, Settings2, PlayCircle, StopCircle } from 'lucide-react';
import socket from '../socket';

const QuickPumpWidget = () => {
  const [pumpStatus, setPumpStatus] = useState({
    pump1: "stopped", pump2: "stopped", pump3: "stopped", pump4: "stopped"
  });
  const [duration, setDuration] = useState(10);
  const [loadingPump, setLoadingPump] = useState(null);

  const fetchStatus = async () => {
    try {
      const res = await axios.get('/pump/status');
      setPumpStatus(res.data);
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    fetchStatus();
    
    const handleTelemetry = (data) => {
      if (data && data.pumps) {
        setPumpStatus(data.pumps);
      }
    };
    
    socket.on('telemetry_update', handleTelemetry);
    socket.on('pump_status_update', setPumpStatus);
    return () => {
      socket.off('telemetry_update', handleTelemetry);
      socket.off('pump_status_update', setPumpStatus);
    };
  }, []);

  const triggerPump = async (pumpId) => {
    setLoadingPump(pumpId);
    try {
      const isRunning = pumpStatus[`pump${pumpId}`] === 'running';
      if (isRunning) {
        await axios.post(`/pump/${pumpId}/stop`);
      } else {
        await axios.post(`/pump/${pumpId}/start`, { duration });
      }
      fetchStatus();
    } catch (error) {
      console.error(`Error toggling pump ${pumpId}`, error);
    } finally {
      setLoadingPump(null);
    }
  };

  const pumps = [
    { id: 1, label: "Nutrient A", color: "blue" },
    { id: 2, label: "Nutrient B", color: "purple" },
    { id: 3, label: "pH Up", color: "red" },
    { id: 4, label: "pH Down", color: "orange" },
  ];

  const colorMaps = {
    blue: {
      activeBg: 'bg-blue-500/20',
      activeBorder: 'border-blue-500/50',
      activeText: 'text-blue-300',
      pulse: 'bg-blue-400'
    },
    purple: {
      activeBg: 'bg-purple-500/20',
      activeBorder: 'border-purple-500/50',
      activeText: 'text-purple-300',
      pulse: 'bg-purple-400'
    },
    red: {
      activeBg: 'bg-red-500/20',
      activeBorder: 'border-red-500/50',
      activeText: 'text-red-300',
      pulse: 'bg-red-400'
    },
    orange: {
      activeBg: 'bg-orange-500/20',
      activeBorder: 'border-orange-500/50',
      activeText: 'text-orange-300',
      pulse: 'bg-orange-400'
    }
  };

  return (
    <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl h-full flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
          <Droplets size={20} className="text-cyan-400" />
          Manual Dosing
        </h3>
        <div className="flex items-center gap-2 text-sm text-slate-400 bg-slate-950/50 px-2 py-1 rounded-md border border-slate-800">
          <Settings2 size={14} />
          {duration}s (ml)
        </div>
      </div>

      <div className="mb-4">
        <input 
          type="range" 
          min="1" max="60" 
          value={duration} 
          onChange={(e) => setDuration(parseInt(e.target.value))}
          className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer"
        />
        <div className="flex justify-between text-xs text-slate-500 mt-1">
          <span>1ml</span>
          <span>30ml</span>
          <span>60ml</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 flex-grow">
        {pumps.map(p => {
          const isRunning = pumpStatus[`pump${p.id}`] === 'running';
          const isLoading = loadingPump === p.id;
          const colors = colorMaps[p.color];
          return (
            <button
              key={p.id}
              onClick={() => triggerPump(p.id)}
              disabled={isLoading}
              className={`relative flex flex-col items-center justify-center p-3 rounded-lg border transition-all ${
                isRunning 
                  ? `${colors.activeBg} ${colors.activeBorder} ${colors.activeText}`
                  : 'bg-slate-950/40 border-slate-800 hover:border-slate-700 hover:bg-slate-800/50 text-slate-300'
              }`}
            >
              {isRunning && <div className={`absolute top-2 right-2 w-2 h-2 rounded-full ${colors.pulse} animate-pulse`} />}
              {isRunning ? <StopCircle size={24} className="mb-1" /> : <PlayCircle size={24} className="mb-1 opacity-70" />}
              <span className="text-xs font-semibold">{p.label}</span>
              <span className="text-[10px] opacity-60">Pump {p.id}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default QuickPumpWidget;
