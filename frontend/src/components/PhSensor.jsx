import React, { useState, useEffect } from "react";
import axios from "axios";
import socket from "../socket";
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

const PHSensor = () => {
  const [currentPH, setCurrentPH] = useState({
    value: 0,
    state: "Neutral"
  });
  const [phData, setPHData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const maxDataPoints = 20; // Limit the number of points shown on graph

  useEffect(() => {
    const fetchPHHistoryData = async () => {
      setIsLoading(true);
      try {
        const response = await axios.get('/get_ph_history');
        const data = response.data;
        const formattedData = (data.ph_data || []).map((item) => {
          const phValue = parseFloat(item.ph_value);
          return {
            time: item.timestamp,
            value: isNaN(phValue) ? 0 : parseFloat(phValue.toFixed(2)),
            state: getPHState(isNaN(phValue) ? 0 : phValue)
          };
        });

        const recentData = formattedData.slice(-maxDataPoints);
        setPHData(recentData);
      } catch (error) {
        console.error("Error fetching historical PH data:", error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchPHHistoryData();
    const historyInterval = setInterval(fetchPHHistoryData, 300000); // Chart updates every 5 mins

    // Named handler so socket.off only removes THIS component's listener,
    // not all telemetry_update listeners on the singleton socket.
    const handleTelemetry = (data) => {
      const now = new Date().toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
      if (data.ph !== null && data.ph !== undefined) {
        setCurrentPH({ value: data.ph, state: getPHState(data.ph), time: 'Live' });
        setPHData(prev => {
          if (prev.length === 0) return prev;
          const withoutLive = prev.filter(p => !p.isLive);
          return [...withoutLive, { time: now, value: data.ph, state: getPHState(data.ph), isLive: true }];
        });
      }
    };

    socket.on('telemetry_update', handleTelemetry);

    return () => {
      clearInterval(historyInterval);
      socket.off('telemetry_update', handleTelemetry);
    };
  }, []);

  const getPHState = (ph) => {
    if (isNaN(ph)) return "Neutral"; // Handle NaN values
    if (ph < 6.5) return "Acidic";
    if (ph > 7.5) return "Alkaline";
    return "Neutral";
  };

  const getStateColor = (state) => {
    switch (state?.toLowerCase()) {
      case 'acidic':
        return 'text-yellow-400';
      case 'neutral':
        return 'text-green-400';
      case 'alkaline':
        return 'text-blue-400';
      default:
        return 'text-gray-400';
    }
  };

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
              pH Level Monitor
            </h1>
            <p className="text-slate-400 mt-2">Water acidity and alkalinity tracking</p>
          </div>
          
          <button 
            onClick={fetchPHData}
            disabled={isLoading}
            className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-slate-900 border border-emerald-500/30 hover:border-emerald-500 text-emerald-400 font-bold transition-all active:scale-95 disabled:opacity-50 group shadow-lg shadow-emerald-900/10"
          >
            <RefreshCw size={18} className={`${isLoading ? "animate-spin" : "group-hover:rotate-180 transition-transform duration-500"}`} />
            <span>Update Reading</span>
          </button>
        </div>

        {/* Content */}
        <div className="space-y-8">
          {/* Current Readings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 transform hover:scale-[1.01] transition-all duration-300">
              <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-emerald-400 mb-4">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                Live pH Value
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-6xl font-black text-white tracking-tighter">
                  {currentPH.value}
                </span>
                <span className="text-xl font-medium text-slate-500 uppercase">pH</span>
              </div>
              <div className="relative mt-6 h-3 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800 flex">
                <div className="h-full bg-red-500/50 w-[30%]"></div>
                <div className="h-full bg-emerald-500 w-[40%]"></div>
                <div className="h-full bg-blue-500/50 w-[30%]"></div>
                {/* Marker */}
                <div 
                  className="absolute h-full w-1 bg-white shadow-[0_0_10px_white] transition-all duration-1000"
                  style={{ left: `${(currentPH.value / 14) * 100}%` }}
                ></div>
              </div>
              <div className="flex justify-between mt-2 text-[10px] text-slate-500 font-bold uppercase tracking-tighter">
                <span>Acidic</span>
                <span>Neutral</span>
                <span>Alkaline</span>
              </div>
            </div>
            
            <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 transform hover:scale-[1.01] transition-all duration-300 flex flex-col justify-center">
              <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-cyan-400 mb-4">
                Water Condition
              </div>
              <div className={`text-5xl font-bold tracking-tight ${getStateColor(currentPH.state)} drop-shadow-md`}>
                {currentPH.state || "Stable"}
              </div>
              <p className="text-slate-500 mt-4 text-sm">
                System is maintaining optimal {currentPH.state?.toLowerCase()} balance for plant growth.
              </p>
            </div>
          </div>

          {/* Chart */}
          <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50">
            <h3 className="text-lg font-semibold text-slate-100 mb-6 flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-500"></div>
              pH Stability History
            </h3>
            <div className="h-[350px] w-full bg-slate-950/30 rounded-lg p-4 border border-slate-800/30">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={phData}>
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
                    domain={[0, 14]}
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
                    dataKey="value"
                    stroke="#10b981"
                    strokeWidth={4}
                    dot={<LiveDot />}
                    activeDot={{ r: 8, strokeWidth: 0 }}
                    name="pH Level"
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

export default PHSensor;