import React, { useState, useEffect } from "react";
import axios from "axios";
import socket from "../socket";
import { HiOutlineInformationCircle } from "react-icons/hi";
import PumpLogs from "./PumpLogs";
// import './pump.css';

const Pump = (props) => {
  const [pumpStatus, setPumpStatus] = useState({
    pump1: "stopped",
    pump2: "stopped",
    pump3: "stopped",
    pump4: "stopped"
  });
  const [duration, setDuration] = useState(5);
  const [saveStatus, setSaveStatus] = useState("");
  const [pumpLogs, setPumpLogs] = useState([]);
  const [isProcessing, setIsProcessing] = useState({});
  const [isAutoMode, setIsAutoMode] = useState(false);
  const [activePlant, setActivePlant] = useState("");

  // Store original ranges for when sensors are turned back on
  const [phOriginalRange, setPhOriginalRange] = useState({ min: 5.5, max: 7.5 });
  const [tdsOriginalRange, setTdsOriginalRange] = useState({ min: 1, max: 3 });
  const [temperatureOriginalRange, setTemperatureOriginalRange] = useState({ min: 18, max: 24 });
  const [humidityOriginalRange, setHumidityOriginalRange] = useState({ min: 40, max: 80 });

  // Added states for sensor limits
  const [phLimits, setPhLimits] = useState({
    min: 5.5,
    max: 7.5,
    active: true
  });

  const [tdsLimits, setTdsLimits] = useState({
    min: 1,
    max: 3,
    active: true
  });

  const [temperatureLimits, setTemperatureLimits] = useState({
    min: 18,
    max: 24,
    active: true
  });

  const [humidityLimits, setHumidityLimits] = useState({
    min: 40,
    max: 80,
    active: true
  });

  const startPump = async (pumpId) => {
    setIsProcessing(prev => ({ ...prev, [pumpId]: true }));
    try {
      const response = await axios.post(`/pump/${pumpId}/start`, { duration });
      if (response.status === 200) {
        await fetchPumpStatus();
      }
    } catch (error) {
      console.error(`Error starting pump ${pumpId}:`, error);
    } finally {
      setIsProcessing(prev => ({ ...prev, [pumpId]: false }));
    }
  };

  const stopPump = async (pumpId) => {
    setIsProcessing(prev => ({ ...prev, [pumpId]: true }));
    try {
      const response = await axios.post(`/pump/${pumpId}/stop`);
      if (response.status === 200) {
        await fetchPumpStatus();
      }
    } catch (error) {
      console.error(`Error stopping pump ${pumpId}:`, error);
    } finally {
      setIsProcessing(prev => ({ ...prev, [pumpId]: false }));
    }
  };

  const startAllPumps = async () => {
    setIsProcessing(prev => ({ ...prev, 'all': true }));
    try {
      const response = await axios.post(`/pump/all/start`, { duration });
      if (response.status === 200) {
        await fetchPumpStatus();
      }
    } catch (error) {
      console.error("Error starting all pumps:", error);
    } finally {
      setIsProcessing(prev => ({ ...prev, 'all': false }));
    }
  };

  const stopAllPumps = async () => {
    setIsProcessing(prev => ({ ...prev, 'all': true }));
    try {
      const response = await axios.post(`/pump/all/stop`);
      if (response.status === 200) {
        await fetchPumpStatus();
      }
    } catch (error) {
      console.error("Error stopping all pumps:", error);
    } finally {
      setIsProcessing(prev => ({ ...prev, 'all': false }));
    }
  };

  // Fetch the status of all pumps
  const fetchPumpStatus = async () => {
    try {
      const response = await axios.get(`/pump/status`);
      if (response.status === 200) {
        setPumpStatus(response.data);
      }
    } catch (error) {
      console.error("Error fetching pump status:", error);
    }
  };

  // Fetch current limits and pump status on component mount and listen for mode/cycle updates
  useEffect(() => {
    fetchPumpStatus();
    fetchLimits();
    socket.on('grow_cycle_update', fetchLimits);
    socket.on('pump_status_update', setPumpStatus);
    return () => {
      socket.off('grow_cycle_update', fetchLimits);
      socket.off('pump_status_update', setPumpStatus);
    };
  }, []);

  const fetchLimits = async () => {
    try {
      const response = await axios.get(`/sensor/limits`);
      if (response.status === 200) {
        const data = response.data;
        setIsAutoMode(data.auto_mode || false);
        setActivePlant(data.active_plant || "");
        if (data.ph) {
          setPhLimits(data.ph);
          if (data.ph.active) {
            setPhOriginalRange({ min: data.ph.min, max: data.ph.max });
          }
        }
        if (data.temperature) {
          setTemperatureLimits(data.temperature);
          if (data.temperature.active) {
            setTemperatureOriginalRange({ min: data.temperature.min, max: data.temperature.max });
          }
        }
        if (data.humidity) {
          setHumidityLimits(data.humidity);
          if (data.humidity.active) {
            setHumidityOriginalRange({ min: data.humidity.min, max: data.humidity.max });
          }
        }
        if (data.tds) {
          setTdsLimits(data.tds);
          if (data.tds.active) {
            setTdsOriginalRange({ min: data.tds.min, max: data.tds.max });
          }
        }
      }
    } catch (error) {
      console.error("Error fetching sensor limits:", error);
    }
  };

  // Validate ranges and update sensor limits
  const updateSensorLimits = async (overrideLimits = null) => {
    try {
      const isCustomPayload = overrideLimits && typeof overrideLimits === "object" && ("ph" in overrideLimits || "tds" in overrideLimits || "temperature" in overrideLimits || "humidity" in overrideLimits);

      const payloadPh = isCustomPayload && overrideLimits.ph ? overrideLimits.ph : phLimits;
      const payloadTds = isCustomPayload && overrideLimits.tds ? overrideLimits.tds : tdsLimits;
      const payloadTemp = isCustomPayload && overrideLimits.temperature ? overrideLimits.temperature : temperatureLimits;
      const payloadHum = isCustomPayload && overrideLimits.humidity ? overrideLimits.humidity : humidityLimits;

      const minPh = parseFloat(payloadPh.min);
      const maxPh = parseFloat(payloadPh.max);
      const minTds = parseFloat(payloadTds.min);
      const maxTds = parseFloat(payloadTds.max);
      const minTemp = parseFloat(payloadTemp.min);
      const maxTemp = parseFloat(payloadTemp.max);
      const minHum = parseFloat(payloadHum.min);
      const maxHum = parseFloat(payloadHum.max);

      if (payloadPh.active && (isNaN(minPh) || isNaN(maxPh) || minPh < 0 || maxPh > 14 || minPh > maxPh)) {
        setSaveStatus("Error: Invalid pH limits");
        setTimeout(() => setSaveStatus(""), 3000);
        return;
      }
      if (payloadTds.active && (isNaN(minTds) || isNaN(maxTds) || minTds < 0 || maxTds > 10 || minTds > maxTds)) {
        setSaveStatus("Error: Invalid EC limits");
        setTimeout(() => setSaveStatus(""), 3000);
        return;
      }

      setSaveStatus("Saving...");
      const response = await axios.post(`/sensor/limits`, {
        ph: { ...payloadPh, min: isNaN(minPh) ? payloadPh.min : minPh, max: isNaN(maxPh) ? payloadPh.max : maxPh },
        tds: { ...payloadTds, min: isNaN(minTds) ? payloadTds.min : minTds, max: isNaN(maxTds) ? payloadTds.max : maxTds },
        temperature: { ...payloadTemp, min: isNaN(minTemp) ? payloadTemp.min : minTemp, max: isNaN(maxTemp) ? payloadTemp.max : maxTemp },
        humidity: { ...payloadHum, min: isNaN(minHum) ? payloadHum.min : minHum, max: isNaN(maxHum) ? payloadHum.max : maxHum }
      });

      if (response.status === 200) {
        setSaveStatus("Saved successfully!");
        setTimeout(() => setSaveStatus(""), 3000);
      } else {
        setSaveStatus("Error saving");
        setTimeout(() => setSaveStatus(""), 3000);
      }
    } catch (error) {
      console.error("Error updating sensor limits:", error);
      setSaveStatus("Error saving");
      setTimeout(() => setSaveStatus(""), 3000);
    }
  };

  const handleInputChange = (sensor, field, value) => {
    const isBool = field === "active";
    const storedVal = isBool ? Boolean(value) : value;

    if (sensor === "ph") {
      const updated = { ...phLimits, [field]: storedVal };
      setPhLimits(updated);
      if (isBool) updateSensorLimits({ ph: updated });
    } else if (sensor === "tds") {
      const updated = { ...tdsLimits, [field]: storedVal };
      setTdsLimits(updated);
      if (isBool) updateSensorLimits({ tds: updated });
    } else if (sensor === "temperature") {
      const updated = { ...temperatureLimits, [field]: storedVal };
      setTemperatureLimits(updated);
      if (isBool) updateSensorLimits({ temperature: updated });
    } else if (sensor === "humidity") {
      const updated = { ...humidityLimits, [field]: storedVal };
      setHumidityLimits(updated);
      if (isBool) updateSensorLimits({ humidity: updated });
    }
  };

  return (
    <div className="w-full min-h-screen py-6 px-4 md:px-6 lg:px-8 md:pt-6">
      <div className="w-full max-w-7xl mx-auto">
        {/* Header Section */}
        <div className="mb-8 mt-12 md:mt-2 flex flex-col sm:flex-row justify-between items-start sm:items-center">
          <div>
            <h2 className="text-2xl md:text-3xl font-bold text-white">Pump Control System</h2>
            <p className="text-slate-400 mt-2">Monitor and control your hydroponic system</p>
          </div>
          <div className="mt-4 sm:mt-0">
            {!activePlant ? (
              <div className="text-slate-400 text-sm font-medium italic">Start a grow cycle in presets to configure system mode</div>
            ) : (
              <div className={`flex items-center bg-slate-950/50 p-2 rounded-full border border-slate-800/50`}>
                <span onClick={() => handleToggleMode(false)} className={`px-4 py-1.5 rounded-full text-sm cursor-pointer transition-all duration-300 ${!isAutoMode ? 'bg-slate-800 text-white font-medium shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}>
                  Manual
                </span>
                <div
                  onClick={() => handleToggleMode(!isAutoMode)}
                  className={`w-14 h-7 flex items-center rounded-full p-1 mx-2 cursor-pointer transition-colors duration-300 ${isAutoMode ? 'bg-emerald-500' : 'bg-slate-700'}`}
                >
                  <div
                    className={`bg-white w-5 h-5 rounded-full shadow-md transform transition-transform duration-300 ${isAutoMode ? 'translate-x-7' : 'translate-x-0'}`}
                  />
                </div>
                <span onClick={() => handleToggleMode(true)} className={`px-4 py-1.5 rounded-full text-sm cursor-pointer transition-all duration-300 ${isAutoMode ? 'bg-emerald-500/20 text-emerald-400 font-medium' : 'text-slate-500 hover:text-slate-300'}`}>
                  Autonomous
                </span>
              </div>
            )}
          </div>
        </div>

        {/* System Overview Card */}
        <div className="mt-6 bg-gradient-to-r from-slate-800/80 to-slate-900/80 rounded-xl p-4 border border-slate-700/30 shadow-lg">
            <div className="flex flex-wrap gap-6 justify-between">
              <div className="flex items-center">
                <div className={`w-3 h-3 rounded-full mr-3 ${Object.values(pumpStatus).some(status => status === "running") ? "bg-emerald-400" : "bg-slate-400"}`}></div>
                <div>
                  <p className="text-slate-300 text-sm font-medium">System Status</p>
                  <p className="text-sm font-semibold text-white">
                    {Object.values(pumpStatus).some(status => status === "running") ? "Active" : "Idle"}
                  </p>
                </div>
              </div>

              <div className="flex items-center">
                <div className={`w-3 h-3 rounded-full mr-3 ${phLimits.active ? "bg-blue-400" : "bg-slate-400"}`}></div>
                <div>
                  <p className="text-slate-300 text-sm font-medium">pH Monitoring</p>
                  <p className="text-sm font-semibold text-white">
                    {phLimits.active ? `${phLimits.min} - ${phLimits.max}` : "Disabled"}
                  </p>
                </div>
              </div>

              <div className="flex items-center">
                <div className={`w-3 h-3 rounded-full mr-3 ${tdsLimits.active ? "bg-purple-400" : "bg-slate-400"}`}></div>
                <div>
                  <p className="text-slate-300 text-sm font-medium">EC Monitoring</p>
                  <p className="text-sm font-semibold text-white">
                    {tdsLimits.active ? `${tdsLimits.min} - ${tdsLimits.max} ppm` : "Disabled"}
                  </p>
                </div>
              </div>

              <div className="flex items-center">
                <div className={`w-3 h-3 rounded-full mr-3 ${temperatureLimits.active ? "bg-red-400" : "bg-slate-400"}`}></div>
                <div>
                  <p className="text-slate-300 text-sm font-medium">Temperature Monitoring</p>
                  <p className="text-sm font-semibold text-white">
                    {temperatureLimits.active ? `${temperatureLimits.min} - ${temperatureLimits.max}°C` : "Disabled"}
                  </p>
                </div>
              </div>

              <div className="flex items-center">
                <div className={`w-3 h-3 rounded-full mr-3 ${humidityLimits.active ? "bg-cyan-400" : "bg-slate-400"}`}></div>
                <div>
                  <p className="text-slate-300 text-sm font-medium">Humidity Monitoring</p>
                  <p className="text-sm font-semibold text-white">
                    {humidityLimits.active ? `${humidityLimits.min} - ${humidityLimits.max}%` : "Disabled"}
                  </p>
                </div>
              </div>

              <div className="flex items-center">
                <div>
                  <p className="text-slate-300 text-sm font-medium">Pump Duration</p>
                  <p className="text-sm font-semibold text-emerald-400">{duration} seconds</p>
                </div>
              </div>
            </div>
          </div>

        <div className="flex flex-col lg:flex-row gap-8 mt-6">
          {/* Sensor Limits Panel */}
          <div className="w-full lg:w-1/2">
            <div className="bg-gradient-to-br from-slate-800/90 via-slate-900/90 to-slate-800/90 rounded-xl p-6 shadow-lg border border-slate-700/30 backdrop-blur-sm text-white h-full">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-semibold text-blue-400">
                  Sensor Limits
                </h3>
                <div className="flex items-center gap-3">
                  {saveStatus && (
                    <span className="text-xs font-semibold text-emerald-400 animate-pulse">
                      {saveStatus}
                    </span>
                  )}
                  <button
                    onClick={() => updateSensorLimits()}
                    className="px-3 py-1.5 bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 border border-blue-500/50 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5"
                    title="Save Custom Sensor Limits"
                  >
                    Save Limits
                  </button>
                  <div className="flex items-center bg-slate-800/70 px-3 py-1 rounded-full border border-slate-700/50">
                    <div className={`w-2 h-2 rounded-full mr-2 ${phLimits.active || tdsLimits.active || temperatureLimits.active || humidityLimits.active ? "bg-blue-400" : "bg-slate-400"}`}></div>
                    <span className="text-xs font-medium text-slate-300">
                      {phLimits.active || tdsLimits.active || temperatureLimits.active || humidityLimits.active ? "Monitoring Active" : "Monitoring Off"}
                    </span>
                  </div>
                </div>
              </div>

              {!isAutoMode ? (
                <div className="mb-6 bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                  <div className="flex items-start">
                    <HiOutlineInformationCircle className="w-5 h-5 text-blue-400 mr-2 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-blue-400">Manual Limits Mode Active</p>
                      <p className="text-xs text-slate-300 mt-1">
                        Automated dosing is active using the sensor limits configured below. Plant preset limits are not applied — enable the sensors you want monitored and set your target ranges. Pumps will fire automatically when readings fall outside those bounds.
                      </p>
                    </div>
                  </div>
                </div>
              ) : activePlant ? (
                <div className="mb-6 bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4">
                  <div className="flex items-start">
                    <HiOutlineInformationCircle className="w-5 h-5 text-emerald-400 mr-2 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-emerald-400">Auto Mode Active</p>
                      <p className="text-xs text-slate-300 mt-1">
                        pH and EC limits are currently being managed automatically by the 
                        <strong> {activePlant} </strong> preset.
                      </p>
                    </div>
                  </div>
                </div>
              ) : null}

              {/* pH Sensor Limits */}
              <div className="mb-6 bg-slate-800/40 rounded-lg p-5 border border-slate-700/30 hover:border-blue-500/20 transition-colors duration-300">
                <div className="flex justify-between items-center mb-4">
                  <div className="flex items-center">
                    <div className={`w-2 h-2 rounded-full mr-2 ${phLimits.active ? "bg-blue-400" : "bg-slate-400"}`}></div>
                    <span className={`text-sm font-medium ${phLimits.active ? "text-blue-400" : "text-slate-500"}`}>
                      pH Sensor
                    </span>
                  </div>
                  <label className={`flex items-center ${isAutoMode ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}>
                    <div className="relative">
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={phLimits.active}
                        disabled={isAutoMode}
                        onChange={(e) => handleInputChange("ph", "active", e.target.checked)}
                      />
                      <div className={`block w-12 h-6 rounded-full ${phLimits.active ? 'bg-blue-500/50' : 'bg-slate-600/30'}`}></div>
                      <div className={`absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform ${phLimits.active ? 'transform translate-x-6' : ''}`}></div>
                    </div>
                    <span className="ml-2 text-xs font-medium text-slate-300">{phLimits.active ? 'ON' : 'OFF'}</span>
                  </label>
                </div>

                {phLimits.active ? (
                  <>
                    <div className="grid grid-cols-2 gap-6 mb-4">
                      <div>
                        <label className="block text-xs text-slate-400 mb-1">Min pH</label>
                        <input
                          type="number"
                          value={phLimits.min}
                          onChange={(e) => handleInputChange("ph", "min", e.target.value)}
                          onBlur={() => updateSensorLimits()}
                          min="0"
                          max="14"
                          step="0.1"
                          disabled={isAutoMode}
                          className="w-full py-2 px-3 rounded bg-slate-700/50 border border-slate-600/50 text-blue-300 text-sm focus:border-blue-500/50 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <p className="mt-1 text-xs text-slate-500">When pH drops below this value, base solution (Pump 3) will activate</p>
                      </div>
                      <div>
                        <label className="block text-xs text-slate-400 mb-1">Max pH</label>
                        <input
                          type="number"
                          value={phLimits.max}
                          onChange={(e) => handleInputChange("ph", "max", e.target.value)}
                          onBlur={() => updateSensorLimits()}
                          min="0"
                          max="14"
                          step="0.1"
                          disabled={isAutoMode}
                          className="w-full py-2 px-3 rounded bg-slate-700/50 border border-slate-600/50 text-blue-300 text-sm focus:border-blue-500/50 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <p className="mt-1 text-xs text-slate-500">When pH rises above this value, acid solution (Pump 4) will activate</p>
                      </div>
                    </div>

                    {/* pH Range Visualization */}
                    <div className="mt-4">
                      <div className="h-2 bg-gradient-to-r from-red-500 via-yellow-500 via-green-500 to-blue-500 rounded-full"></div>
                      <div className="flex justify-between mt-1">
                        <span className="text-xs text-slate-400">0</span>
                        <span className="text-xs text-blue-400">{phLimits.min}</span>
                        <span className="text-xs text-blue-400">{phLimits.max}</span>
                        <span className="text-xs text-slate-400">14</span>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center p-6 bg-slate-800/20 rounded border border-slate-700/20">
                    <span className="text-slate-500 font-semibold mb-1">Sensor Not Connected / Disabled</span>
                    <span className="text-xs text-slate-600 text-center">Toggle the sensor ON to configure its automated dosing limits.</span>
                  </div>
                )}
              </div>

              {/* TDS Sensor Limits */}
              <div className="mb-6 bg-slate-800/40 rounded-lg p-5 border border-slate-700/30 hover:border-purple-500/20 transition-colors duration-300">
                <div className="flex justify-between items-center mb-4">
                  <div className="flex items-center">
                    <div className={`w-2 h-2 rounded-full mr-2 ${tdsLimits.active ? "bg-purple-400" : "bg-slate-400"}`}></div>
                    <span className={`text-sm font-medium ${tdsLimits.active ? "text-purple-400" : "text-slate-500"}`}>
                      EC Sensor
                    </span>
                  </div>
                  <label className={`flex items-center ${isAutoMode ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}>
                    <div className="relative">
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={tdsLimits.active}
                        disabled={isAutoMode}
                        onChange={(e) => handleInputChange("tds", "active", e.target.checked)}
                      />
                      <div className={`block w-12 h-6 rounded-full ${tdsLimits.active ? 'bg-purple-500/50' : 'bg-slate-600/30'}`}></div>
                      <div className={`absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform ${tdsLimits.active ? 'transform translate-x-6' : ''}`}></div>
                    </div>
                    <span className="ml-2 text-xs font-medium text-slate-300">{tdsLimits.active ? 'ON' : 'OFF'}</span>
                  </label>
                </div>

                {tdsLimits.active ? (
                  <>
                    <div className="grid grid-cols-2 gap-6 mb-4">
                      <div>
                        <label className="block text-xs text-slate-400 mb-1">Min Ec (ms/cm)</label>
                        <input
                          type="number"
                          value={tdsLimits.min}
                          onChange={(e) => handleInputChange("tds", "min", e.target.value)}
                          min="0"
                          max="20"
                          step="0.5"
                          disabled={isAutoMode}
                          className="w-full py-2 px-3 rounded bg-slate-700/50 border border-slate-600/50 text-purple-300 text-sm focus:border-purple-500/50 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <p className="mt-1 text-xs text-slate-500">Nutrient A (Pump 1) will activate</p>
                      </div>
                      <div>
                        <label className="block text-xs text-slate-400 mb-1">Max EC (ms/cm)</label>
                        <input
                          type="number"
                          value={tdsLimits.max}
                          onChange={(e) => handleInputChange("tds", "max", e.target.value)}
                          min="0"
                          max="20"
                          step="0.5"
                          disabled={isAutoMode}
                          className="w-full py-2 px-3 rounded bg-slate-700/50 border border-slate-600/50 text-purple-300 text-sm focus:border-purple-500/50 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <p className="mt-1 text-xs text-slate-500">Nutrients B(Pump 2) will activate </p>
                      </div>
                    </div>

                    {/* TDS Range Visualization */}
                    <div className="mt-4">
                      <div className="h-2 bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 rounded-full"></div>
                      <div className="flex justify-between mt-1">
                        <span className="text-xs text-slate-400">0</span>
                        <span className="text-xs text-purple-400">{tdsLimits.min}</span>
                        <span className="text-xs text-purple-400">{tdsLimits.max}</span>
                        <span className="text-xs text-slate-400">20</span>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center p-6 bg-slate-800/20 rounded border border-slate-700/20">
                    <span className="text-slate-500 font-semibold mb-1">Sensor Not Connected / Disabled</span>
                    <span className="text-xs text-slate-600 text-center">Toggle the sensor ON to configure its automated dosing limits.</span>
                  </div>
                )}
              </div>

              {/* Temperature Sensor Limits */}
              <div className="mb-6 bg-slate-800/40 rounded-lg p-5 border border-slate-700/30 hover:border-red-500/20 transition-colors duration-300">
                <div className="flex justify-between items-center mb-4">
                  <div className="flex items-center">
                    <div className={`w-2 h-2 rounded-full mr-2 ${temperatureLimits.active ? "bg-red-400" : "bg-slate-400"}`}></div>
                    <span className={`text-sm font-medium ${temperatureLimits.active ? "text-red-400" : "text-slate-500"}`}>
                      Temperature Sensor
                    </span>
                  </div>
                  <label className={`flex items-center ${isAutoMode ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}>
                    <div className="relative">
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={temperatureLimits.active}
                        disabled={isAutoMode}
                        onChange={(e) => handleInputChange("temperature", "active", e.target.checked)}
                      />
                      <div className={`block w-12 h-6 rounded-full ${temperatureLimits.active ? 'bg-red-600' : 'bg-slate-600/30'}`}></div>
                      <div className={`absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform ${temperatureLimits.active ? 'transform translate-x-6' : ''}`}></div>
                    </div>
                    <span className="ml-2 text-xs font-medium text-slate-300">{temperatureLimits.active ? 'ON' : 'OFF'}</span>
                  </label>
                </div>

                {temperatureLimits.active ? (
                  <>
                    <div className="grid grid-cols-2 gap-6 mb-4">
                      <div>
                        <label className="block text-xs text-slate-400 mb-1">Min Temperature (°C)</label>
                        <input
                          type="number"
                          value={temperatureLimits.min}
                          onChange={(e) => handleInputChange("temperature", "min", e.target.value)}
                          onBlur={() => updateSensorLimits()}
                          min="0"
                          max="50"
                          step="0.5"
                          disabled={isAutoMode}
                          className="w-full py-2 px-3 rounded bg-slate-700/50 border border-slate-600/50 text-red-300 text-sm focus:border-red-500/50 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <p className="mt-1 text-xs text-slate-500">Minimum safe water temperature</p>
                      </div>
                      <div>
                        <label className="block text-xs text-slate-400 mb-1">Max Temperature (°C)</label>
                        <input
                          type="number"
                          value={temperatureLimits.max}
                          onChange={(e) => handleInputChange("temperature", "max", e.target.value)}
                          onBlur={() => updateSensorLimits()}
                          min="0"
                          max="50"
                          step="0.5"
                          disabled={isAutoMode}
                          className="w-full py-2 px-3 rounded bg-slate-700/50 border border-slate-600/50 text-red-300 text-sm focus:border-red-500/50 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <p className="mt-1 text-xs text-slate-500">Maximum safe water temperature</p>
                      </div>
                    </div>

                    <div className="mt-4">
                      <div className="h-2 bg-gradient-to-r from-blue-500 via-amber-500 to-red-500 rounded-full"></div>
                      <div className="flex justify-between mt-1">
                        <span className="text-xs text-slate-400">0</span>
                        <span className="text-xs text-red-400">{temperatureLimits.min}°C</span>
                        <span className="text-xs text-red-400">{temperatureLimits.max}°C</span>
                        <span className="text-xs text-slate-400">50</span>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center p-6 bg-slate-800/20 rounded border border-slate-700/20">
                    <span className="text-slate-500 font-semibold mb-1">Sensor Not Monitored / Disabled</span>
                    <span className="text-xs text-slate-600 text-center">Toggle the sensor ON to configure its automated monitoring limits.</span>
                  </div>
                )}
              </div>

              {/* Humidity Sensor Limits */}
              <div className="mb-6 bg-slate-800/40 rounded-lg p-5 border border-slate-700/30 hover:border-cyan-500/20 transition-colors duration-300">
                <div className="flex justify-between items-center mb-4">
                  <div className="flex items-center">
                    <div className={`w-2 h-2 rounded-full mr-2 ${humidityLimits.active ? "bg-cyan-400" : "bg-slate-400"}`}></div>
                    <span className={`text-sm font-medium ${humidityLimits.active ? "text-cyan-400" : "text-slate-500"}`}>
                      Humidity Sensor
                    </span>
                  </div>
                  <label className={`flex items-center ${isAutoMode ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}>
                    <div className="relative">
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={humidityLimits.active}
                        disabled={isAutoMode}
                        onChange={(e) => handleInputChange("humidity", "active", e.target.checked)}
                      />
                      <div className={`block w-12 h-6 rounded-full ${humidityLimits.active ? 'bg-cyan-600' : 'bg-slate-600/30'}`}></div>
                      <div className={`absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform ${humidityLimits.active ? 'transform translate-x-6' : ''}`}></div>
                    </div>
                    <span className="ml-2 text-xs font-medium text-slate-300">{humidityLimits.active ? 'ON' : 'OFF'}</span>
                  </label>
                </div>

                {humidityLimits.active ? (
                  <>
                    <div className="grid grid-cols-2 gap-6 mb-4">
                      <div>
                        <label className="block text-xs text-slate-400 mb-1">Min Humidity (%)</label>
                        <input
                          type="number"
                          value={humidityLimits.min}
                          onChange={(e) => handleInputChange("humidity", "min", e.target.value)}
                          onBlur={() => updateSensorLimits()}
                          min="0"
                          max="100"
                          step="1"
                          disabled={isAutoMode}
                          className="w-full py-2 px-3 rounded bg-slate-700/50 border border-slate-600/50 text-cyan-300 text-sm focus:border-cyan-500/50 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <p className="mt-1 text-xs text-slate-500">Minimum safe air humidity</p>
                      </div>
                      <div>
                        <label className="block text-xs text-slate-400 mb-1">Max Humidity (%)</label>
                        <input
                          type="number"
                          value={humidityLimits.max}
                          onChange={(e) => handleInputChange("humidity", "max", e.target.value)}
                          onBlur={() => updateSensorLimits()}
                          min="0"
                          max="100"
                          step="1"
                          disabled={isAutoMode}
                          className="w-full py-2 px-3 rounded bg-slate-700/50 border border-slate-600/50 text-cyan-300 text-sm focus:border-cyan-500/50 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        <p className="mt-1 text-xs text-slate-500">Maximum safe air humidity</p>
                      </div>
                    </div>

                    <div className="mt-4">
                      <div className="h-2 bg-gradient-to-r from-amber-500 via-cyan-500 to-blue-500 rounded-full"></div>
                      <div className="flex justify-between mt-1">
                        <span className="text-xs text-slate-400">0</span>
                        <span className="text-xs text-cyan-400">{humidityLimits.min}%</span>
                        <span className="text-xs text-cyan-400">{humidityLimits.max}%</span>
                        <span className="text-xs text-slate-400">100</span>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center justify-center p-6 bg-slate-800/20 rounded border border-slate-700/20">
                    <span className="text-slate-500 font-semibold mb-1">Sensor Not Monitored / Disabled</span>
                    <span className="text-xs text-slate-600 text-center">Toggle the sensor ON to configure its automated monitoring limits.</span>
                  </div>
                )}
              </div>

              {/* Save Button */}
              <div className="flex items-center">
                <button
                  onClick={updateSensorLimits}
                  disabled={isAutoMode}
                  className={`bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600 text-white font-medium py-2 px-4 rounded-lg shadow-md transition-all duration-300 ${isAutoMode ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  Save Settings
                </button>
                {saveStatus && (
                  <span className={`ml-4 text-sm ${saveStatus.includes('Error') ? 'text-red-400' : 'text-green-400'}`}>
                    {saveStatus}
                  </span>
                )}
              </div>

              {/* Information Card */}
              <div className="mt-6 bg-slate-800/30 rounded-lg p-4 border border-slate-700/30">
                <div className="flex items-start">
                  <HiOutlineInformationCircle className="w-5 h-5 text-blue-400 mr-2" />
                  <p className="text-xs text-slate-400">
                    Sensor monitoring automatically prevents pumps from activating when pH, EC, or temperature levels are outside the specified ranges.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Pump Controls Panel */}
          <div className="w-full lg:w-1/2">
            <div className="bg-gradient-to-br from-slate-800/90 via-slate-900/90 to-slate-800/90 rounded-xl p-6 shadow-lg border border-slate-700/30 backdrop-blur-sm text-white h-full">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-semibold text-emerald-400">
                  Pump Controls
                </h3>
                <div className="flex items-center bg-slate-800/70 px-3 py-1 rounded-full border border-slate-700/50">
                  <div className={`w-2 h-2 rounded-full mr-2 ${Object.values(pumpStatus).some(status => status === "running") ? "bg-emerald-400" : "bg-slate-400"}`}></div>
                  <span className="text-xs font-medium text-slate-300">
                    {Object.values(pumpStatus).some(status => status === "running") ? "Pumps Active" : "All Idle"}
                  </span>
                </div>
              </div>

              {/* Duration Selector */}
              <div className="mb-8 bg-slate-800/40 rounded-lg p-5 border border-slate-700/30 hover:border-emerald-500/20 transition-colors duration-300">
                <label className="block mb-3 text-slate-300 text-sm font-medium">Duration (1sec = 1ml):</label>
                <div className="flex items-center gap-4">
                  <input
                    type="range"
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                    min="1"
                    max="60"
                    step="1"
                    className="flex-grow h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer"
                  />
                  <span className="w-12 text-center font-bold text-lg text-emerald-400">{duration}</span>
                </div>
                <div className="flex justify-between mt-2">
                  <span className="text-xs text-slate-400">1s</span>
                  <span className="text-xs text-slate-400">30s</span>
                  <span className="text-xs text-slate-400">60s</span>
                </div>

                {/* Quick Duration Buttons */}
                <div className="flex gap-2 mt-4">
                  {[5, 10, 30, 60].map((value) => (
                    <button
                      key={value}
                      onClick={() => setDuration(value)}
                      className={`px-3 py-1 rounded-md text-xs font-medium transition-colors duration-300 ${duration === value
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-slate-700/50 text-slate-400 border border-slate-600/30 hover:bg-slate-700"
                        }`}
                    >
                      {value}s
                    </button>
                  ))}
                </div>
              </div>

              {/* Individual Pump Controls */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                {[1, 2, 3, 4].map((pumpId) => (
                  <div key={pumpId} className={`bg-slate-800/40 rounded-lg p-4 border ${pumpStatus[`pump${pumpId}`] === "running"
                      ? "border-emerald-500/30"
                      : "border-slate-700/30 hover:border-slate-600/50"
                    } transition-colors duration-300`}>
                    <div className="flex justify-between items-center mb-3">
                      <div className="flex items-center">
                        <div className={`w-2 h-2 rounded-full mr-2 ${pumpStatus[`pump${pumpId}`] === "running" ? "bg-emerald-400" : "bg-slate-400"}`}></div>
                        <div className="flex flex-col">
                          <span className={`text-sm font-medium ${pumpStatus[`pump${pumpId}`] === 'running' ? 'text-emerald-400' : 'text-slate-300'}`}>
                            {pumpId === 1 && "Nutrient A"}
                            {pumpId === 2 && "Nutrient B"}
                            {pumpId === 3 && "pH Up"}
                            {pumpId === 4 && "pH Down"}
                          </span>
                          <span className="text-xs text-slate-500">
                            Pump {pumpId}
                          </span>
                        </div>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded-full ${pumpStatus[`pump${pumpId}`] === "running"
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-slate-700/50 text-slate-400 border border-slate-700/30"
                        }`}>
                        {pumpStatus[`pump${pumpId}`] === "running" ? "ACTIVE" : "IDLE"}
                      </span>
                    </div>
                    <button
                      onClick={() => pumpStatus[`pump${pumpId}`] === "running" ? stopPump(pumpId) : startPump(pumpId)}
                      disabled={isProcessing[pumpId] || isProcessing['all']}
                      className={`w-full py-2 px-4 rounded-lg text-sm font-medium transition-all duration-300 ${isProcessing[pumpId] || isProcessing['all'] ? "opacity-50 cursor-not-allowed bg-slate-700 text-slate-400" : (pumpStatus[`pump${pumpId}`] === "running"
                          ? "bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/30"
                          : "bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30"
                        )}`}
                    >
                      {isProcessing[pumpId] ? "Processing..." : (pumpStatus[`pump${pumpId}`] === "running" ? "Stop" : "Start")}
                    </button>
                  </div>
                ))}
              </div>

              {/* All Pumps Controls */}
              <div className="grid grid-cols-2 gap-6 mt-8">
                <button
                  onClick={startAllPumps}
                  disabled={isProcessing['all']}
                  className={`py-3 rounded-lg border font-medium transition-colors duration-300 shadow-lg ${isProcessing['all'] ? "opacity-50 cursor-not-allowed bg-slate-700 text-slate-400 border-slate-600" : "bg-gradient-to-r from-emerald-500/20 to-cyan-500/20 hover:from-emerald-500/30 hover:to-cyan-500/30 text-emerald-300 border-emerald-500/30"}`}
                >
                  {isProcessing['all'] ? "Processing..." : "Start All"}
                </button>
                <button
                  onClick={stopAllPumps}
                  disabled={isProcessing['all']}
                  className={`py-3 rounded-lg border font-medium transition-colors duration-300 shadow-lg ${isProcessing['all'] ? "opacity-50 cursor-not-allowed bg-slate-700 text-slate-400 border-slate-600" : "bg-gradient-to-r from-red-500/20 to-orange-500/20 hover:from-red-500/30 hover:to-orange-500/30 text-red-300 border-red-500/30"}`}
                >
                  {isProcessing['all'] ? "Processing..." : "Stop All"}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Pump Audit Log Section */}
        <div className="mt-8 w-full">
          <PumpLogs />
        </div>

        {/* Footer Info */}
        <div className="mt-8 text-center">
          <p className="text-xs text-slate-500">Last updated: {new Date().toLocaleTimeString()}</p>
        </div>
      </div>
    </div>
  );
};

export default Pump;