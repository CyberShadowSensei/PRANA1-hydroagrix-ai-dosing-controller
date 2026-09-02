/**
 * TankLevels Component
 * Visual solution tank inventory gauge displaying remaining volume and capacity for all 4 bottles.
 */
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import socket from '../socket';

const TankLevels = () => {
  const [tanks, setTanks] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchTanks = async () => {
    try {
      const response = await axios.get(`/get_tank_levels?t=${new Date().getTime()}`);
      // Handle either direct array or { tanks: [...] } wrapper
      const tanksData = response.data.tanks || response.data || [];
      if (Array.isArray(tanksData)) {
        setTanks(tanksData);
      }
    } catch (error) {
      console.error("Error fetching tank levels:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTanks();
    
    // Listen to pump_activity socket events and update
    socket.on('pump_activity', fetchTanks);
    
    return () => {
      socket.off('pump_activity', fetchTanks);
    };
  }, []);

  const handleRefill = async (tank_id) => {
    try {
      await axios.post('/refill_tank', { tank_id });
      fetchTanks();
    } catch (error) {
      console.error("Error refilling tank:", error);
    }
  };

  if (loading && tanks.length === 0) return null;

  return (
    <div className="w-full bg-slate-900/50 rounded-xl p-4 sm:p-6 mb-8 shadow-xl border border-slate-800/50 backdrop-blur-sm">
      <h2 className="text-lg sm:text-xl font-semibold text-slate-100 mb-4 ml-2">Solution Tanks</h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {tanks.map((tank) => {
          const percentage = Math.max(0, Math.min(100, (tank.current_volume_ml / tank.capacity_ml) * 100));
          const isLow = percentage < 20;
          return (
            <div key={tank.tank_id} className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 flex flex-col items-center">
              <h3 className="text-slate-300 font-medium mb-3 text-center">{tank.name}</h3>
              
              {/* Vertical Progress Bar */}
              <div className="w-12 h-32 bg-slate-700 rounded-lg overflow-hidden relative mb-4 border border-slate-600 shadow-inner">
                <div 
                  className={`absolute bottom-0 w-full transition-all duration-500 ease-out ${isLow ? 'bg-red-500' : 'bg-emerald-500'}`}
                  style={{ height: `${percentage}%` }}
                >
                  {/* Subtle gradient overlay for liquid effect */}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent"></div>
                  <div className="absolute top-0 w-full h-1 bg-white/20"></div>
                </div>
              </div>
              
              <div className="text-slate-200 font-bold mb-1">
                {Math.round(percentage)}%
              </div>
              <div className="text-slate-400 text-xs mb-4">
                {Math.round(tank.current_volume_ml)} / {tank.capacity_ml} mL
              </div>
              
              <button 
                onClick={() => handleRefill(tank.tank_id)}
                className="w-full px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-sm font-medium transition-colors border border-slate-600 active:bg-slate-800"
              >
                Refill
              </button>
            </div>
          );
        })}
        {tanks.length === 0 && !loading && (
          <div className="col-span-full text-center text-slate-400 py-4">
            No tank data available.
          </div>
        )}
      </div>
    </div>
  );
};

export default TankLevels;
