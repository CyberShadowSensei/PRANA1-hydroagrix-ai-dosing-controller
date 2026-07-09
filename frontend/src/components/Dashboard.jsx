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
import MoistureGauge from "../components/ui/MoistureGauge";
import TemperatureGauge from "../components/ui/TemperatureGauge";
import HumidityGauge from "../components/ui/HumidityGauge";
import TDSGauge from "../components/ui/TDSGauge";
import Gauge from "../components/ui/gauge";
import DosingHistory from "./DosingHistory";


const Dashboard = () => {
  // Current sensor values
  const [currentMoisture, setCurrentMoisture] = useState({ value: 0, state: "Dry", time: "N/A" });
  const [currentTemperature, setCurrentTemperature] = useState({ value: 0, time: "N/A" });
  const [currentHumidity, setCurrentHumidity] = useState({ value: 0, time: "N/A" });
  const [currentPH, setCurrentPH] = useState({ value: 0, state: "Neutral", time: "N/A" });
  const [currentTDS, setCurrentTDS] = useState({ value: 0, time: "N/A" });

  // Historical data for all sensors
  const [sensorData, setSensorData] = useState([]);
  // Specific pH data with state information
  const [phData, setPHData] = useState([]);
  // Specific moisture data with state information
  const [moistureData, setMoistureData] = useState([]);
  // Specific TDS data
  const [tdsData, setTdsData] = useState([]);

  const maxPHDataPoints = 20;
  const maxMoistureDataPoints = 20;

  // Helper function to safely parse numeric values
  const safeParseFloat = (value) => {
    if (value === null || value === undefined) return null;
    const parsed = parseFloat(value);
    return isNaN(parsed) ? null : parsed;
  };

  const getLatestValue = (data, key) => {
    if (!data || data.length === 0) return null;
    for (let i = data.length - 1; i >= 0; i--) {
      if (data[i] && data[i][key] !== null && data[i][key] !== undefined) {
        return { value: data[i][key], time: data[i].time };
      }
    }
    return null;
  };

  const getMoistureState = (value) => {
    const moistureValue = safeParseFloat(value);
    if (moistureValue === null) return "Unknown";
    if (moistureValue < 300) return "Dry";
    if (moistureValue < 600) return "Moist";
    return "Wet";
  };

  const getPHState = (ph) => {
    if (isNaN(ph)) return "Neutral";
    if (ph < 6.5) return "Acidic";
    if (ph > 7.5) return "Alkaline";
    return "Neutral";
  };

  const fetchTDSData = async () => {
    try {
      const response = await axios.get('/get_tds_history');
      const historyData = response.data;
      const formattedData = (historyData.tds_data || []).map(item => ({
        time: item.date,
        tds_value: safeParseFloat(item.tds_value)
      }));
      setTdsData(formattedData);
      if (formattedData.length > 0) {
        const latest = formattedData[formattedData.length - 1];
        setCurrentTDS({ value: latest.tds_value, time: latest.time });
      }
      return formattedData;
    } catch (error) {
      console.error("Error fetching TDS data:", error);
      return [];
    }
  };

  const fetchMoistureData = async () => {
    try {
      const response = await axios.get('/get_moisture_data');
      const data = response.data;
      const formattedData = (data.moisture_data || []).map((item) => {
        const level = safeParseFloat(item.moisture_level);
        return {
          time: item.date,
          value: level,
          state: item.state || getMoistureState(level)
        };
      });
      const recentData = formattedData.slice(-maxMoistureDataPoints);
      setMoistureData(recentData);
      if (recentData.length > 0) {
        const latest = recentData[recentData.length - 1];
        setCurrentMoisture({ value: latest.value, state: latest.state, time: latest.time });
      }
      return formattedData;
    } catch (error) {
      console.error("Error fetching moisture data:", error);
      return [];
    }
  };

  const fetchPHData = async () => {
    try {
      const response = await axios.get('/get_ph_history');
      const data = response.data;
      const formattedData = (data.ph_data || []).map((item) => {
        const phValue = parseFloat(item.ph_value);
        return {
          time: item.timestamp,
          ph_value: isNaN(phValue) ? 0 : parseFloat(phValue.toFixed(1)),
          state: getPHState(isNaN(phValue) ? 0 : phValue)
        };
      });
      const recentData = formattedData.slice(-maxPHDataPoints);
      setPHData(recentData);
      if (recentData.length > 0) {
        const latest = recentData[recentData.length - 1];
        setCurrentPH({ value: latest.ph_value, state: latest.state, time: latest.time });
      }
      return formattedData;
    } catch (error) {
      console.error("Error fetching PH data:", error);
      return [];
    }
  };

  useEffect(() => {
    const fetchHistoricalData = async () => {
      try {
        const tempHumRes = await axios.get('/get_temperature_humidity_history');
        const tempHumData = tempHumRes.data;

        const phFormatted = await fetchPHData();
        const moistureFormatted = await fetchMoistureData();
        const tdsFormatted = await fetchTDSData();

        const mergedData = (tempHumData.temperature_humidity_data || []).map(item => {
          const matchingPH = phFormatted.find(p => p.time === item.date);
          return {
            time: item.date,
            temperature: safeParseFloat(item.temperature),
            humidity: safeParseFloat(item.humidity),
            ph_value: matchingPH ? matchingPH.ph_value : null
          };
        });

        setSensorData(mergedData);
      } catch (error) {
        console.error("Dashboard Global Fetch Error:", error);
      }
    };

    fetchHistoricalData();
    const historyInterval = setInterval(fetchHistoricalData, 300000);

    // Using singleton socket imported from ../socket
    socket.on('telemetry_update', (data) => {
      const now = new Date().toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

      if (data.ph !== null && data.ph !== undefined) {
        setCurrentPH({ value: data.ph, state: getPHState(data.ph), time: 'Live' });
        setPHData(prev => {
          const withoutLive = prev.filter(p => !p.isLive);
          return [...withoutLive, { time: now, ph_value: data.ph, state: getPHState(data.ph), isLive: true }];
        });
      }

      if (data.ec !== null && data.ec !== undefined) {
        setCurrentTDS({ value: data.ec, time: 'Live' });
        setTdsData(prev => {
          const withoutLive = prev.filter(p => !p.isLive);
          return [...withoutLive, { time: now, tds_value: data.ec, isLive: true }];
        });
      }

      if (data.temperature !== null && data.temperature !== undefined) {
        setCurrentTemperature({ value: data.temperature, time: 'Live' });
        if (data.humidity !== null && data.humidity !== undefined) {
           setCurrentHumidity({ value: data.humidity, time: 'Live' });
        }
        setSensorData(prev => {
          if (prev.length === 0) return prev;
          const withoutLive = prev.filter(p => !p.isLive);
          const lastPh = data.ph !== null && data.ph !== undefined ? data.ph : withoutLive[withoutLive.length - 1]?.ph_value;
          return [...withoutLive, { time: now, temperature: data.temperature, humidity: data.humidity, ph_value: lastPh, isLive: true }];
        });
      }
    });

    return () => {
      clearInterval(historyInterval);
      socket.off('telemetry_update');
    };
  }, []);

  // Custom dot: renders a glowing blinking circle ONLY on the live (most recent injected) point
  const LiveDot = ({ cx, cy, payload, color = '#10b981', glow = '#6ee7b7' }) => {
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

  const TempDot  = (props) => <LiveDot {...props} color="#FF9F40" glow="#fed7aa" />;
  const HumDot   = (props) => <LiveDot {...props} color="#36A2EB" glow="#bae6fd" />;
  const PhDot    = (props) => <LiveDot {...props} color="#4ade80" glow="#bbf7d0" />;


  const chartStyle = {
    backgroundColor: "rgba(15, 23, 42, 0.6)",
    borderRadius: "12px",
    boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)",
    border: "1px solid rgba(100, 116, 139, 0.1)"
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const isLive = payload[0]?.payload?.isLive;
      return (
        <div className="rounded-lg bg-slate-800 border border-slate-700 shadow-lg p-4">
          <p className="text-slate-300 text-sm mb-2 font-bold">{isLive ? "🟢 Live" : `Time: ${label}`}</p>
          {payload.map((entry, index) => (
            <p key={`item-${index}`} style={{ color: entry.color }} className="text-sm font-medium">
              {`${entry.name}: ${entry.value?.toFixed(2) || 'N/A'}`}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  const TDSTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const isLive = payload[0]?.payload?.isLive;
      return (
        <div className="rounded-lg bg-slate-800 border border-slate-700 shadow-lg p-4">
          <p className="text-slate-300 text-sm mb-2 font-bold">{isLive ? "🟢 Live" : `Time: ${label}`}</p>
          {payload.map((entry, index) => (
            <p key={`item-${index}`} style={{ color: entry.color }} className="text-sm font-medium">
              {`${entry.name}: ${entry.value?.toFixed(2) || 'N/A'} ms/cm`}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full min-h-screen bg-slate-950 p-2 sm:p-6">
      <div className="max-w-7xl mx-auto w-full">
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)]">
            Sensor Dashboard
          </h1>
          <p className="text-slate-400 mt-2">Real-time monitoring of your hydroponic system</p>
        </div>

        <div className="w-full grid grid-cols-2 sm:grid-cols-3 gap-4 mb-8">
          <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl transform hover:scale-[1.02] transition-all duration-300">
            <Gauge value={currentPH?.value} time={currentPH?.time} state={currentPH?.state} />
          </div>
          <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl transform hover:scale-[1.02] transition-all duration-300">
            <HumidityGauge value={currentHumidity?.value} time={currentHumidity?.time} />
          </div>
          <div className="col-span-2 sm:col-span-1 bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl transform hover:scale-[1.02] transition-all duration-300">
            <TemperatureGauge value={currentTemperature?.value} time={currentTemperature?.time} />
          </div>
        </div>

        <div className="w-full bg-slate-900/50 rounded-xl p-4 sm:p-6 mb-8 shadow-xl border border-slate-800/50 backdrop-blur-sm">
          <h3 className="text-lg sm:text-xl font-semibold text-slate-100 mb-4 ml-2">Environmental Parameters</h3>
          <div style={chartStyle} className="p-1 sm:p-4">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={sensorData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.15)" />
                <XAxis dataKey="time" stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
                <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8' }} yAxisId="temp" />
                <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8' }} orientation="right" yAxisId="ph" domain={[0, 14]} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ paddingTop: '15px', color: '#e2e8f0' }} />
                <Line type="monotone" dataKey="humidity" stroke="#36A2EB" strokeWidth={2} dot={<HumDot />} activeDot={{ r: 5 }} name="Humidity" yAxisId="temp" connectNulls={true} />
                <Line type="monotone" dataKey="temperature" stroke="#FF9F40" strokeWidth={2} dot={<TempDot />} activeDot={{ r: 5 }} name="Temperature" yAxisId="temp" connectNulls={true} />
                <Line type="monotone" dataKey="ph_value" stroke="#4ade80" strokeWidth={2} dot={<PhDot />} activeDot={{ r: 5 }} name="pH Level" yAxisId="ph" connectNulls={true} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="w-full grid grid-cols-1 gap-4 mb-8">
          <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl transform hover:scale-[1.02] transition-all duration-300">
            <TDSGauge value={currentTDS?.value} time={currentTDS?.time} />
          </div>
        </div>

        <div className="w-full bg-slate-900/50 rounded-xl p-4 sm:p-6 mb-8 shadow-xl border border-slate-800/50 backdrop-blur-sm">
          <h3 className="text-lg sm:text-xl font-semibold text-white mb-2 sm:mb-4 ml-2">EC Measurements</h3>
          <div style={chartStyle} className="p-1 sm:p-4">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={tdsData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.15)" />
                <XAxis dataKey="time" stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
                <YAxis stroke="#94a3b8" tick={{ fill: '#94a3b8' }} />
                <Tooltip content={<TDSTooltip />} />
                <Legend wrapperStyle={{ paddingTop: '15px', color: '#e2e8f0' }} />
                <Line type="monotone" dataKey="tds_value" stroke="#fb7185" strokeWidth={2} dot={<LiveDot />} activeDot={{ r: 5 }} name="EC (ms/cm)" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="w-full mb-8 flex justify-center">
          <DosingHistory />
        </div>

      </div>
    </div>
  );
};

export default Dashboard;