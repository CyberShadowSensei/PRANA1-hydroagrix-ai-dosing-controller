import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
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

import TemperatureGauge from "../components/ui/TemperatureGauge";
import HumidityGauge from "../components/ui/HumidityGauge";
import TDSGauge from "../components/ui/TDSGauge";
import Gauge from "../components/ui/gauge";
import PumpLogs from "./PumpLogs";
import GrowCycleBanner from "./ui/GrowCycleBanner";
import { HiExclamationCircle } from "react-icons/hi";
import TankLevels from "./TankLevels";


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

const TempDot = (props) => <LiveDot {...props} color="#FF9F40" glow="#fed7aa" />;
const HumDot = (props) => <LiveDot {...props} color="#36A2EB" glow="#bae6fd" />;
const PhDot = (props) => <LiveDot {...props} color="#4ade80" glow="#bbf7d0" />;

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const isLive = payload[0]?.payload?.isLive;
    return (
      <div className="rounded-lg bg-slate-800 border border-slate-700 shadow-lg p-4">
        <p className="text-slate-300 text-sm mb-2 font-bold">
          {isLive ? <><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-2"></span> Live</> : `Time: ${label}`}
        </p>
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
        <p className="text-slate-300 text-sm mb-2 font-bold">
          {isLive ? <><span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-2"></span> Live</> : `Time: ${label}`}
        </p>
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

const useThrottle = (callback, delay) => {
  const timeoutRef = useRef(null);
  const lastExecRef = useRef(0);
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return useCallback((...args) => {
    const now = Date.now();
    const timeSinceLast = now - lastExecRef.current;

    if (timeSinceLast >= delay) {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      callbackRef.current(...args);
      lastExecRef.current = now;
    } else {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args);
        lastExecRef.current = Date.now();
      }, delay - timeSinceLast);
    }
  }, [delay]);
};

const Dashboard = () => {
  // Current sensor values
  const [currentTemperature, setCurrentTemperature] = useState({ value: 0, time: "N/A" });
  const [currentHumidity, setCurrentHumidity] = useState({ value: 0, time: "N/A" });
  const [currentPH, setCurrentPH] = useState({ value: 0, state: "Neutral", time: "N/A" });
  const [currentTDS, setCurrentTDS] = useState({ value: 0, time: "N/A" });
  const [isDrainCycle, setIsDrainCycle] = useState(false);

  // Historical data for all sensors
  const [sensorData, setSensorData] = useState([]);
  // Specific pH data with state information
  const [phData, setPHData] = useState([]);
  // Specific TDS data
  const [tdsData, setTdsData] = useState([]);

  const [cycleStatus, setCycleStatus] = useState(null);
  const [isAutomatic, setIsAutomatic] = useState(false);
  const [sensorLimits, setSensorLimits] = useState({});

  const throttledSetPHData = useThrottle(setPHData, 1000);
  const throttledSetTdsData = useThrottle(setTdsData, 1000);
  const throttledSetSensorData = useThrottle(setSensorData, 1000);

  const fetchGrowCycleStatus = async (signal) => {
    try {
      const response = await axios.get('/get_grow_cycle_status', { signal });
      setCycleStatus(response.data);
      setIsAutomatic(response.data.is_automatic === true || response.data.state === true);
      setIsDrainCycle(response.data.is_drain_cycle === true);
    } catch (error) {
      if (!axios.isCancel(error)) {
        console.error("Error fetching grow cycle status:", error);
      }
    }
  };

  const fetchSensorLimits = async (signal) => {
    try {
      const response = await axios.get('/sensor/limits', { signal });
      // Store raw sensor limits keyed by type (ph, tds)
      setSensorLimits(response.data || {});
    } catch (error) {
      if (!axios.isCancel(error)) {
        console.error("Error fetching sensor limits:", error);
      }
    }
  };

  const handleToggleMode = async (targetMode) => {
    const originalState = isAutomatic;
    setIsAutomatic(targetMode);

    try {
      const response = await axios.post('/update_plant_status', { state: targetMode });
      if (response.status !== 200) {
        throw new Error('Failed to update mode on the server.');
      }
      await fetchGrowCycleStatus();
    } catch (error) {
      console.error('Error updating mode:', error);
      setIsAutomatic(originalState);
    }
  };

  const getEffectiveLimits = (type) => {
    const limit = sensorLimits[type] || sensorLimits[type.toUpperCase()] || null;
    if (limit && limit.active === false) return null;
    if (limit) return limit;
    if (isAutomatic && cycleStatus?.limits) {
        const mapping = { ph: 'ph', tds: 'ec', temperature: 'temp' };
        return cycleStatus.limits[mapping[type]] || null;
    }
    return null;
  };

  // Re-computes instantly whenever any sensor value, limits, or mode changes
  const activeWarnings = useMemo(() => {
    const warnings = [];

    // ALWAYS prefer user-configured sensor limits (from Settings / Pump page).
    // In auto mode, additionally use phase limits if a sensor limit isn't configured.
    const ph  = sensorLimits.ph  || sensorLimits.PH  || null;
    const tds = sensorLimits.tds || sensorLimits.TDS || null;
    const tmp = sensorLimits.temperature || null;

    const phLimits   = (ph && ph.active === false) ? null
                     : ph ? ph
                     : (isAutomatic && cycleStatus?.limits?.ph) ? cycleStatus.limits.ph
                     : null;
    const ecLimits   = (tds && tds.active === false) ? null
                     : tds ? tds
                     : (isAutomatic && cycleStatus?.limits?.ec) ? cycleStatus.limits.ec
                     : null;
    const tempLimits = (tmp && tmp.active !== false) ? tmp : null;

    const phaseName = cycleStatus?.phase || "active";

    // pH
    if (phLimits && currentPH.value !== null && currentPH.value !== undefined) {
      const { min, max } = phLimits;
      const val = currentPH.value;
      if (val < min) {
        warnings.push({
          message: isAutomatic
            ? `pH is low (${val}). Dosing pH UP — correcting toward ${phaseName} phase target.`
            : `pH is low (${val}). Add pH UP solution manually to raise it above ${min}.`,
          severity: 'amber',
        });
      } else if (val > max) {
        warnings.push({
          message: isAutomatic
            ? `pH is high (${val}). Dosing pH DOWN — correcting toward ${phaseName} phase target.`
            : `pH is high (${val}). Add pH DOWN solution manually to lower it below ${max}.`,
          severity: 'amber',
        });
      }
    }

    // EC/TDS
    if (ecLimits && currentTDS.value !== null && currentTDS.value !== undefined) {
      const { min, max } = ecLimits;
      const val = currentTDS.value;
      if (val < min) {
        warnings.push({
          message: isAutomatic
            ? `EC is low (${val} mS/cm). Dosing nutrients — correcting toward ${phaseName} phase target.`
            : `EC is low (${val} mS/cm). Add nutrient solution manually to raise it above ${min} mS/cm.`,
          severity: 'amber',
        });
      } else if (val > max) {
        warnings.push({
          message: `EC is high (${val} mS/cm — target max ${max} mS/cm). Dilute the reservoir with fresh water to bring EC down. Dosing is paused until EC recovers.`,
          severity: 'red',
        });
      }
    }

    // Temperature
    if (tempLimits && currentTemperature.value !== null && currentTemperature.value !== undefined) {
      const { min, max } = tempLimits;
      const val = currentTemperature.value;
      if (val < min) {
        warnings.push({
          message: `Water temperature is low (${val}°C). Check your heater — target range is ${min}–${max}°C.`,
          severity: 'amber',
        });
      } else if (val > max) {
        warnings.push({
          message: `Water temperature is high (${val}°C). Check cooling or aeration — target range is ${min}–${max}°C.`,
          severity: 'red',
        });
      }
    }

    return warnings;
  }, [currentPH, currentTDS, currentTemperature, isAutomatic, sensorLimits, cycleStatus]);

  const maxPHDataPoints = 20;
  const safeParseFloat = (value) => {
    if (value === null || value === undefined) return null;
    const parsed = parseFloat(value);
    return isNaN(parsed) ? null : parsed;
  };

  const getPHState = (ph) => {
    if (isNaN(ph)) return "Neutral";
    if (ph < 6.5) return "Acidic";
    if (ph > 7.5) return "Alkaline";
    return "Neutral";
  };

  const fetchTDSData = async (signal) => {
    try {
      const response = await axios.get('/get_tds_history', { signal });
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
      if (!axios.isCancel(error)) {
        console.error("Error fetching TDS data:", error);
      }
      return [];
    }
  };



  const fetchPHData = async (signal) => {
    try {
      const response = await axios.get('/get_ph_history', { signal });
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
      if (!axios.isCancel(error)) {
        console.error("Error fetching PH data:", error);
      }
      return [];
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    const signal = controller.signal;

    const fetchHistoricalData = async () => {
      try {
        // Parallelise the three independent history fetches instead of awaiting them
        // sequentially — reduces page load latency by 2x on slow connections.
        const [tempHumRes, phFormatted, tdsFormatted] = await Promise.all([
          axios.get('/get_temperature_humidity_history', { signal }),
          fetchPHData(signal),
          fetchTDSData(signal),
        ]);
        const tempHumData = tempHumRes.data;

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
        if (!axios.isCancel(error)) {
          console.error("Dashboard Global Fetch Error:", error);
        }
      }
    };

    fetchHistoricalData();
    fetchGrowCycleStatus(signal);
    fetchSensorLimits(signal);

    // 30-minute interval for chart history — data is aggregated every 10 minutes so
    // refreshing every 5 minutes was redundant. Grow cycle status is now updated via
    // socket events instead of this interval.
    const historyInterval = setInterval(fetchHistoricalData, 1800000);

    const handleTelemetry = (data) => {
      const now = new Date().toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

      if (data.is_drain_cycle !== undefined) {
        setIsDrainCycle(Boolean(data.is_drain_cycle));
      }

      if (data.ph !== null && data.ph !== undefined) {
        setCurrentPH({ value: data.ph, state: getPHState(data.ph), time: 'Live' });
        throttledSetPHData(prev => {
          const withoutLive = prev.filter(p => !p.isLive);
          return [...withoutLive, { time: now, ph_value: data.ph, state: getPHState(data.ph), isLive: true }];
        });
      }

      if (data.ec !== null && data.ec !== undefined) {
        const displayVal = data.is_drain_cycle && data.effective_ec ? data.effective_ec : data.ec;
        setCurrentTDS({ value: displayVal, time: 'Live' });
        throttledSetTdsData(prev => {
          const withoutLive = prev.filter(p => !p.isLive);
          return [...withoutLive, { time: now, tds_value: displayVal, isLive: true }];
        });
      }

      if (data.temperature !== null && data.temperature !== undefined) {
        setCurrentTemperature({ value: data.temperature, time: 'Live' });
        if (data.humidity !== null && data.humidity !== undefined) {
           setCurrentHumidity({ value: data.humidity, time: 'Live' });
        }
        throttledSetSensorData(prev => {
          if (prev.length === 0) return prev;
          const withoutLive = prev.filter(p => !p.isLive);
          const lastPh = data.ph !== null && data.ph !== undefined ? data.ph : withoutLive[withoutLive.length - 1]?.ph_value;
          return [...withoutLive, { time: now, temperature: data.temperature, humidity: data.humidity, ph_value: lastPh, isLive: true }];
        });
      }
    };

    // Re-fetch limits the instant they're saved in Settings (either event name).
    const handleLimitsUpdated = (newLimits) => {
      if (newLimits && typeof newLimits === 'object') {
        setSensorLimits(newLimits);
      } else {
        fetchSensorLimits();
      }
    };

    // Re-fetch grow cycle status whenever the backend signals a phase/day change.
    const handleCycleUpdated = () => fetchGrowCycleStatus();

    socket.on('telemetry_update', handleTelemetry);
    socket.on('sensor_limits_updated', handleLimitsUpdated);
    socket.on('limits_updated', handleLimitsUpdated);
    socket.on('grow_cycle_update', handleCycleUpdated);

    return () => {
      controller.abort();
      clearInterval(historyInterval);
      socket.off('telemetry_update', handleTelemetry);
      socket.off('sensor_limits_updated', handleLimitsUpdated);
      socket.off('limits_updated', handleLimitsUpdated);
      socket.off('grow_cycle_update', handleCycleUpdated);
    };

  }, []);


  const chartStyle = {
    backgroundColor: "rgba(15, 23, 42, 0.6)",
    borderRadius: "12px",
    boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)",
    border: "1px solid rgba(100, 116, 139, 0.1)"
  };

  return (
    <div className="w-full min-h-screen bg-slate-950 p-2 sm:p-6">
      <div className="max-w-7xl mx-auto w-full">
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-bold text-emerald-400">
            Sensor Dashboard
          </h1>
          <p className="text-slate-400 mt-2">Real-time monitoring of your hydroponic system</p>
        </div>

        <GrowCycleBanner 
           cycleStatus={cycleStatus} 
           isAutomatic={isAutomatic} 
           onToggleMode={handleToggleMode} 
           onRefresh={fetchGrowCycleStatus}
        />

        {activeWarnings.length > 0 && (
          <div className="mb-8">
            <div className="bg-slate-900/50 border border-slate-700 rounded-xl p-6 shadow-xl backdrop-blur-sm">
              <h2 className="text-xl font-semibold text-slate-100 mb-4 flex items-center">
                <HiExclamationCircle className="text-amber-500 mr-2 text-2xl" />
                System Alerts
              </h2>
              <ul className="space-y-3">
                {[...activeWarnings].reverse().map((warning, idx) => (
                  <li key={idx} className="flex items-start text-slate-300">
                    {warning.severity === 'red' ? (
                      <span className="text-red-500 mr-2 mt-0.5 font-bold text-lg">•</span>
                    ) : (
                      <span className="text-amber-400 mr-2 mt-0.5 font-bold text-lg">•</span>
                    )}
                    <span>{warning.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <div className="w-full grid grid-cols-2 sm:grid-cols-3 gap-4 mb-8">
          <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl">
            <Gauge value={currentPH?.value} time={currentPH?.time} state={currentPH?.state} />
          </div>
          <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl">
            <HumidityGauge value={currentHumidity?.value} time={currentHumidity?.time} />
          </div>
          <div className="col-span-2 sm:col-span-1 bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl">
            <TemperatureGauge value={currentTemperature?.value} time={currentTemperature?.time} />
          </div>
        </div>

        <div className="w-full bg-slate-900/50 rounded-xl p-4 sm:p-6 mb-8 shadow-xl border border-slate-800/50 backdrop-blur-sm">
          <h2 className="text-lg sm:text-xl font-semibold text-slate-100 mb-4 ml-2">Environmental Parameters</h2>
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
          <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl">
            <TDSGauge value={currentTDS?.value} time={currentTDS?.time} />
          </div>
        </div>

        <div className="w-full bg-slate-900/50 rounded-xl p-4 sm:p-6 mb-8 shadow-xl border border-slate-800/50 backdrop-blur-sm">
          <h2 className="text-lg sm:text-xl font-semibold text-white mb-2 sm:mb-4 ml-2">EC Measurements</h2>
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
          <TankLevels />
        </div>

        <div className="w-full mb-8 flex justify-center">
          <PumpLogs />
        </div>

      </div>
    </div>
  );
};

export default Dashboard;