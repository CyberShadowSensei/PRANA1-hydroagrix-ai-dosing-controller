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
import { HiOutlineCloud } from "react-icons/hi";

const Temperature = () => {
  const [currentTemperatureHumidity, setCurrentTemperatureHumidity] = useState({
    temperature: 0,
    humidity: 0,
  });

  const [temperatureHumidityData, setTemperatureHumidityData] = useState([]);

  // Live blinking dot — only renders on the most recent injected point
  const LiveDot = ({ cx, cy, payload, color, glow }) => {
    if (!payload?.isLive) return null;
    return (
      <g>
        <circle cx={cx} cy={cy} r={9} fill={color} opacity={0.25}>
          <animate attributeName="r" values="6;11;6" dur="1.5s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.25;0;0.25" dur="1.5s" repeatCount="indefinite" />
        </circle>
        <circle cx={cx} cy={cy} r={6} fill={color} stroke={glow} strokeWidth={2}
          style={{ filter: `drop-shadow(0 0 6px ${color})` }} />
      </g>
    );
  };
  const TempDot = (props) => <LiveDot {...props} color="#10b981" glow="#6ee7b7" />;
  const HumDot  = (props) => <LiveDot {...props} color="#06b6d4" glow="#a5f3fc" />;

  useEffect(() => {
    const fetchTemperatureHumidityData = async () => {
      try {
        const historyResponse = await axios.get(`/get_temperature_humidity_history`);
        const historyData = historyResponse.data;
        
        const formattedData = historyData.temperature_humidity_data.map((item) => ({
          time: item.date,
          temperature: parseFloat(item.temperature),
          humidity: parseFloat(item.humidity)
        }));
        
        setTemperatureHumidityData(formattedData);
      } catch (error) {
        console.error("Error fetching temperature and humidity data:", error);
      }
    };

    fetchTemperatureHumidityData();
    const interval = setInterval(fetchTemperatureHumidityData, 30000);

    // Using singleton socket imported from ../socket
    socket.on('telemetry_update', (data) => {
      const temp = data.temperature ?? 0;
      const hum  = data.humidity ?? 0;
      setCurrentTemperatureHumidity({ temperature: temp, humidity: hum });

      const now = new Date().toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
      setTemperatureHumidityData(prev => {
        if (prev.length === 0) return prev;
        const withoutLive = prev.filter(p => !p.isLive);
        return [...withoutLive, { time: now, temperature: temp, humidity: hum, isLive: true }];
      });
    });

    return () => {
      clearInterval(interval);
      socket.off('telemetry_update');
    };
  }, []);

  return (
    <div className="w-full min-h-screen bg-slate-950 p-4 sm:p-6 text-slate-200">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)]">
            Temperature & Humidity
          </h1>
          <p className="text-slate-400 mt-2">Real-time environmental monitoring</p>
        </div>

        {/* Content */}
        <div className="space-y-8">
          {/* Current Readings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 transform hover:scale-[1.01] transition-all duration-300">
              <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-emerald-400 mb-4">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                Air Temperature
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-5xl font-bold text-white tracking-tight">
                  {Number(currentTemperatureHumidity.temperature || 0).toFixed(1)}
                </span>
                <span className="text-2xl font-medium text-slate-500">°C</span>
              </div>
              <div className="mt-4 h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-1000"
                  style={{ width: `${Math.min(100, (currentTemperatureHumidity.temperature / 50) * 100)}%` }}
                ></div>
              </div>
            </div>
            
            <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 transform hover:scale-[1.01] transition-all duration-300">
              <div className="flex items-center gap-3 text-sm font-bold uppercase tracking-widest text-cyan-400 mb-4">
                <HiOutlineCloud className="w-5 h-5" />
                Air Humidity
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-5xl font-bold text-white tracking-tight">
                  {Number(currentTemperatureHumidity.humidity || 0).toFixed(1)}
                </span>
                <span className="text-2xl font-medium text-slate-500">%</span>
              </div>
              <div className="mt-4 h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-cyan-500 to-blue-400 transition-all duration-1000"
                  style={{ width: `${currentTemperatureHumidity.humidity}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* Chart */}
          <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50">
            <h3 className="text-lg font-semibold text-slate-100 mb-6 flex items-center gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-500"></div>
              Environmental Trends
            </h3>
            <div className="h-[350px] w-full bg-slate-950/30 rounded-lg p-4 border border-slate-800/30">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={temperatureHumidityData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.1)" vertical={false} />
                  <XAxis 
                    dataKey="time" 
                    stroke="#475569"
                    tick={{ fill: '#64748b', fontSize: 12 }}
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
                    labelFormatter={(label, payload) => (payload?.[0]?.payload?.isLive ? "🟢 Live" : `Time: ${label}`)}
                  />
                  <Legend 
                    wrapperStyle={{ paddingTop: '20px' }}
                    iconType="circle"
                  />
                  <Line
                    type="monotone"
                    dataKey="humidity"
                    stroke="#06b6d4"
                    strokeWidth={3}
                    dot={<HumDot />}
                    activeDot={{ r: 6, strokeWidth: 0 }}
                    name="Humidity (%)"
                    connectNulls={true}
                  />
                  <Line
                    type="monotone"
                    dataKey="temperature"
                    stroke="#10b981"
                    strokeWidth={3}
                    dot={<TempDot />}
                    activeDot={{ r: 6, strokeWidth: 0 }}
                    name="Temperature (°C)"
                    connectNulls={true}
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

export default Temperature;