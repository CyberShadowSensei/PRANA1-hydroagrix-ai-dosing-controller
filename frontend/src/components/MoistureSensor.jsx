import React, { useState, useEffect } from "react";
import axios from "axios";
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

const MoistureSensor = () => {
  const [currentMoisture, setCurrentMoisture] = useState({
    level: 0,
    state: "Dry",
  });
  const [moistureData, setMoistureData] = useState([]);
  const maxDataPoints = 20; // Limit the number of points shown on graph

  useEffect(() => {
    const fetchMoistureData = async () => {
      try {
        const response = await axios.get(`/get_moisture_data`);
        const data = response.data;
        const formattedData = data.moisture_data.map((item) => ({
          time: item.date,
          level: parseFloat(item.moisture_level),
          state: item.state,
        }));
        
        // Set historical data
        const recentData = formattedData.slice(-maxDataPoints);
        setMoistureData(recentData);
        
        // Set current value from the latest entry
        if (recentData.length > 0) {
          const latestEntry = recentData[recentData.length - 1];
          setCurrentMoisture({
            level: latestEntry.level,
            state: latestEntry.state
          });

        }
      } catch (error) {
        console.error("Error fetching moisture data:", error);
      }
    };

    fetchMoistureData();
    const moistureInterval = setInterval(fetchMoistureData, 300000); // Update every 5 minutes
    return () => clearInterval(moistureInterval);
  }, []);

  const getStateColor = (state) => {
    switch (state?.toLowerCase()) {
      case 'wet':
        return 'text-blue-400';
      case 'moist':
        return 'text-green-400';
      case 'dry':
        return 'text-yellow-400';
      default:
        return 'text-gray-400';
    }
  };

  return (
    <div className="w-full min-h-screen bg-slate-950 p-4 sm:p-6 text-slate-200">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)]">
            Soil Moisture Monitor
          </h1>
          <p className="text-slate-400 mt-2">Precision moisture tracking for optimal irrigation</p>
        </div>

        {/* Content */}
        <div className="space-y-8">
          {/* Current Readings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 transform hover:scale-[1.01] transition-all duration-300">
              <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-emerald-400 mb-4">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                Moisture Level
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-6xl font-black text-white tracking-tighter">
                  {currentMoisture.level}
                </span>
                <span className="text-xl font-medium text-slate-500 uppercase tracking-widest">Raw</span>
              </div>
              <div className="mt-6 h-3 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                <div 
                  className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400 transition-all duration-1000 shadow-[0_0_10px_rgba(16,185,129,0.3)]"
                  style={{ width: `${Math.min(100, (currentMoisture.level / 1023) * 100)}%` }}
                ></div>
              </div>
            </div>
            
            <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 transform hover:scale-[1.01] transition-all duration-300 flex flex-col justify-center">
              <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-cyan-400 mb-4">
                Hydration Status
              </div>
              <div className={`text-5xl font-bold tracking-tight ${getStateColor(currentMoisture.state)} drop-shadow-md`}>
                {currentMoisture.state || "Stable"}
              </div>
              <p className="text-slate-500 mt-4 text-sm font-medium">
                The soil is currently <span className="text-slate-300">{currentMoisture.state?.toLowerCase()}</span>.
              </p>
            </div>
          </div>

          {/* Chart */}
          <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50">
            <h3 className="text-lg font-semibold text-slate-100 mb-6 flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-500"></div>
              Hydration History
            </h3>
            <div className="h-[350px] w-full bg-slate-950/30 rounded-lg p-4 border border-slate-800/30">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={moistureData}>
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
                    domain={[0, 1023]}
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
                    dataKey="level"
                    stroke="#06b6d4"
                    strokeWidth={4}
                    dot={{ r: 4, fill: '#06b6d4', strokeWidth: 0 }}
                    activeDot={{ r: 8, strokeWidth: 0 }}
                    name="Moisture Level"
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

export default MoistureSensor;