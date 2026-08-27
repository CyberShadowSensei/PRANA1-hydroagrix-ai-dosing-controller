import React, { useState, useEffect } from "react";
import axios from "axios";
import socket from "../socket";
import CirculationBadge from "./ui/CirculationBadge";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { RefreshCw } from "lucide-react";

const TDS = () => {
  const [tdsData, setTdsData] = useState([]);
  const [currentTDS, setCurrentTDS] = useState(0);
  const [isDrainCycle, setIsDrainCycle] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const maxDataPoints = 20; // Limit the number of points shown on graph

  // Lifted outside useEffect so the refresh button can call it too
  const fetchTDSHistoryData = async () => {
    setIsLoading(true);
    try {
      const response = await axios.get('/get_tds_history');
      const historyData = response.data;
      // Map to tds_value key to match the chart's dataKey and live socket injections
      const formattedData = historyData.tds_data.map(item => ({
        time: item.date,
        tds_value: parseFloat(item.tds_value)
      }));
      
      const recentData = formattedData.slice(-maxDataPoints);
      setTdsData(recentData);
    } catch (error) {
      console.error("Error fetching historical TDS data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTDSHistoryData();
    const historyInterval = setInterval(fetchTDSHistoryData, 300000); // Chart updates every 5 mins

    // Named handler stored in a variable so socket.off only removes THIS component's
    // listener, not all telemetry_update listeners on the singleton socket.
    const handleTelemetry = (data) => {
      const now = new Date().toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
      if (data.is_drain_cycle !== undefined) {
        setIsDrainCycle(Boolean(data.is_drain_cycle));
      }
      if (data.ec !== null && data.ec !== undefined) {
        const displayVal = data.is_drain_cycle && data.effective_ec ? data.effective_ec : data.ec;
        setCurrentTDS(parseFloat(displayVal).toFixed(1));
        setTdsData(prev => {
          if (prev.length === 0) return prev;
          const withoutLive = prev.filter(p => !p.isLive);
          return [...withoutLive, { time: now, tds_value: displayVal, isLive: true }];
        });
      }
    };

    socket.on('telemetry_update', handleTelemetry);

    return () => {
      clearInterval(historyInterval);
      socket.off('telemetry_update', handleTelemetry);
    };
  }, []);



  // Glowing dot rendered only on the live (most recent injected) point
  const LiveDot = (props) => {
    const { cx, cy, payload } = props;
    if (!payload?.isLive) return null;
    return (
      <circle cx={cx} cy={cy} r={7} fill="#10b981" stroke="#6ee7b7" strokeWidth={2}
        style={{ filter: 'drop-shadow(0 0 8px #10b981)' }} />
    );
  };

  return (
    <div className="w-full min-h-screen bg-slate-950 p-4 sm:p-6 text-slate-200">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)]">
              EC Conductivity
            </h1>
            <p className="text-slate-400 mt-2">Nutrient concentration monitoring (mS/cm)</p>
          </div>
          
          <button 
            onClick={fetchTDSHistoryData}
            disabled={isLoading}
            className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-slate-900 border border-emerald-500/30 hover:border-emerald-500 text-emerald-400 font-bold transition-all active:scale-95 disabled:opacity-50 group shadow-lg shadow-emerald-900/10"
          >
            <RefreshCw size={18} className={`${isLoading ? "animate-spin" : "group-hover:rotate-180 transition-transform duration-500"}`} />
            <span>Update EC Reading</span>
          </button>
        </div>

        {/* Content */}
        <div className="space-y-8">
          {/* Current Reading */}
          <div className="grid grid-cols-1 gap-6">
            <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-8 shadow-xl border border-slate-800/50 transform hover:scale-[1.01] transition-all duration-300 relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 rounded-full -mr-16 -mt-16 blur-3xl"></div>
              <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-emerald-400 mb-6">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                Nutrient Strength
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-7xl font-black text-white tracking-tighter">
                  {currentTDS}
                </span>
                <span className="text-2xl font-medium text-slate-500 uppercase tracking-widest">mS/cm</span>
              </div>
              <div className="mt-4">
                <CirculationBadge isDrainCycle={isDrainCycle} isStablePlateau={!isDrainCycle} plateauEc={currentTDS} />
              </div>
              <p className="text-slate-500 mt-6 text-sm max-w-md">
                Electrical Conductivity (EC) measures the amount of dissolved salts (nutrients) in the water. Keep this within the plant's optimal range for maximum growth.
              </p>
            </div>
          </div>

          {/* Chart */}
          <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50">
            <h3 className="text-lg font-semibold text-slate-100 mb-6 flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-500"></div>
              Nutrient Concentration History
            </h3>
            <div className="h-[350px] w-full bg-slate-950/30 rounded-lg p-4 border border-slate-800/30">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={tdsData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.1)" vertical={false} />
                  <XAxis 
                    dataKey="time" 
                    stroke="#475569"
                    tick={{ fill: '#64748b', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis 
                    stroke="#475569"
                    tick={{ fill: '#64748b', fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#0f172a',
                      border: '1px solid rgba(148, 163, 184, 0.2)',
                      borderRadius: '0.75rem',
                      boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)'
                    }}
                    labelStyle={{ color: '#94a3b8', marginBottom: '4px', fontWeight: 'bold' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="tds_value"
                    stroke="#10b981"
                    strokeWidth={4}
                    dot={<LiveDot />}
                    activeDot={{ r: 8, strokeWidth: 0 }}
                    name="EC (ms/cm)"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TDS;