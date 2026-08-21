import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { HiOutlineClock, HiOutlineBeaker, HiOutlineExclamationCircle } from 'react-icons/hi';
import socket from '../socket';

const PumpLogs = () => {
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchLogs = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await axios.get('/get_pump_logs');
      if (response.status === 200) {
        setLogs(response.data.pump_logs || []);
      }
    } catch (e) {
      console.error('Error fetching pump logs:', e);
      setError('Failed to load pump logs');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
    
    // Listen to pump_activity socket events and update
    socket.on('pump_activity', fetchLogs);
    
    return () => {
      socket.off('pump_activity', fetchLogs);
    };
  }, []);

  const getDosingAction = (name) => {
    const lower = name.toLowerCase();
    if (lower.includes('ph up') || lower.includes('pump 3')) return 'pH Up';
    if (lower.includes('ph down') || lower.includes('pump 4')) return 'pH Down';
    if (lower.includes('nutrient a') || lower.includes('pump 1')) return 'Solution A';
    if (lower.includes('nutrient b') || lower.includes('pump 2')) return 'Solution B';
    return name;
  };

  const getActionColor = (action) => {
    if (action === 'pH Up') return 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20';
    if (action === 'pH Down') return 'text-orange-400 bg-orange-400/10 border-orange-400/20';
    if (action === 'Solution A') return 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20';
    if (action === 'Solution B') return 'text-teal-400 bg-teal-400/10 border-teal-400/20';
    return 'text-slate-300 bg-slate-800 border-slate-700';
  };

  return (
    <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 w-full">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-slate-100 flex items-center">
            <HiOutlineClock className="w-6 h-6 mr-2 text-emerald-400" />
            Pump Logs
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Real-time feed of dosing activities, durations, and triggers
          </p>
        </div>
        <button
          onClick={fetchLogs}
          disabled={isLoading}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-medium transition-colors border border-slate-700 cursor-pointer"
        >
          {isLoading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error ? (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-lg flex items-center">
          <HiOutlineExclamationCircle className="w-5 h-5 mr-2" />
          {error}
        </div>
      ) : logs.length === 0 ? (
        <div className="text-center py-10 border border-dashed border-slate-700 rounded-lg bg-slate-900/30">
          <HiOutlineBeaker className="w-12 h-12 mx-auto text-slate-600 mb-3" />
          <p className="text-slate-400">No dosing events recorded yet</p>
        </div>
      ) : (
        <div className="space-y-4 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
          {logs.map((log) => {
            const action = getDosingAction(log.pump_name);
            return (
              <div key={log.id} className="bg-slate-950/50 p-4 rounded-xl border border-slate-800/50 hover:border-slate-700/80 transition-colors flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className={`px-3 py-2 rounded-lg border font-bold text-sm tracking-wide ${getActionColor(action)}`}>
                    {action}
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${log.trigger_type.includes('Auto') ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' : 'bg-blue-500/20 text-blue-300 border border-blue-500/30'}`}>
                        {log.trigger_type}
                      </span>
                      <span className="text-emerald-400 text-sm font-semibold">{log.duration} sec</span>
                    </div>
                  </div>
                </div>
                <div className="text-xs text-slate-500 font-medium">
                  {log.timestamp}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PumpLogs;
