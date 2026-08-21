import React, { useEffect, useState } from 'react';
import socket from '../socket';

const GlobalHUD = () => {
  const [telemetry, setTelemetry] = useState({
    ph: '--',
    ec: '--',
    temperature: '--',
    humidity: '--'
  });

  const [connected, setConnected] = useState(false);

  useEffect(() => {
    socket.on('connect', () => setConnected(true));
    socket.on('disconnect', () => setConnected(false));
    socket.on('telemetry_update', (data) => {
      const formatVal = (val, decimals) => {
        if (val === null || val === undefined) return '--';
        const num = parseFloat(val);
        return isNaN(num) ? '--' : num.toFixed(decimals);
      };
      setTelemetry({
        ph: formatVal(data.ph, 2),
        ec: formatVal(data.ec, 2),
        temperature: formatVal(data.temperature, 1),
        humidity: formatVal(data.humidity, 1)
      });
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('telemetry_update');
    };
  }, []);

  return (
    <div className="w-full bg-slate-900/80 backdrop-blur-md border-b border-slate-800 flex justify-between items-center px-6 py-3 shadow-md z-40 relative">
      <div className="flex items-center space-x-2">
      </div>

      <div className="flex space-x-6">
        <div className="flex flex-col items-center">
          <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">pH Level</span>
          <span className="text-xl font-bold text-cyan-400">{telemetry.ph}</span>
        </div>
        <div className="w-px h-8 bg-slate-800" />
        <div className="flex flex-col items-center">
          <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">EC (mS/cm)</span>
          <span className="text-xl font-bold text-emerald-400">{telemetry.ec}</span>
        </div>
        <div className="w-px h-8 bg-slate-800" />
        <div className="flex flex-col items-center">
          <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Temp (°C)</span>
          <span className="text-xl font-bold text-orange-400">{telemetry.temperature}</span>
        </div>
      </div>
    </div>
  );
};

export default GlobalHUD;
