/**
 * Root Application Component
 * Configures React router routes, global HUD layout, and application shell.
 */
import { useState, useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import PlantCamera from "./components/PlantCamera";
import MoistureSensor from "./components/MoistureSensor";
import Temperature from "./components/Temperature";
import TDS from './components/TDS';
import History from "./pages/History";
import PHSensor from "./components/PhSensor";
import Dashboard from "./components/Dashboard";
import Pump from './components/Pump';
import PlantPresets from "./components/PlantPresets";
import Settings from "./pages/Settings";
import './index.css';

const SensorDashboard = () => {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="dashboard" replace />}/>
        <Route path="/camera" element={<PlantCamera/>}/>
        <Route path="/history" element={<History/>}/>
        <Route path="/moist" element={<MoistureSensor/>}/>
        <Route path="/temp" element={<Temperature/>}/>
        <Route path="/tds" element={<TDS/>}/>
        <Route path="/ph" element={<PHSensor/>}/>
        <Route path="/dashboard" element={<Dashboard/>}/>
        <Route path="/pump" element={<Pump/>}/>
        <Route path="/plant-presets" element={<PlantPresets/>}/>
        <Route path="/settings" element={<Settings/>}/>
        <Route path="/*" element={<Navigate to="/dashboard" replace />}/>
      </Route>
    </Routes>
  );
};

export default SensorDashboard;