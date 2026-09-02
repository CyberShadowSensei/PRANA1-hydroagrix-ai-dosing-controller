/**
 * GlobalHUD Component
 * Persistent header heads-up-display rendering live telemetry, network connectivity, and drain badges.
 */
import React, { useEffect, useState } from 'react';
import socket from '../socket';

const GlobalHUD = () => {
  const [telemetry, setTelemetry] = useState({
    ph: '--',
    ec: '--',
    rawEc: null,
    temperature: '--',
    humidity: '--',
    isDrainCycle: false,
    patternStatus: 'STATIC'
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

      const displayEc = (data.effective_ec !== null && data.effective_ec !== undefined)
        ? data.effective_ec
        : data.ec;

      setTelemetry({
        ph: formatVal(data.ph, 2),
        ec: formatVal(displayEc, 2),
        rawEc: data.ec !== null && data.ec !== undefined ? parseFloat(data.ec).toFixed(2) : null,
        temperature: formatVal(data.temperature, 1),
        humidity: formatVal(data.humidity, 1),
        isDrainCycle: Boolean(data.is_drain_cycle),
        patternStatus: data.pattern_status || 'STATIC'
      });
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('telemetry_update');
    };
  }, []);

  const getPhColor = () => {
    if (telemetry.ph === '--') return 'text-slate-400';
    const num = parseFloat(telemetry.ph);
    if (num < 4.5 || num > 8.5) return 'text-rose-400';
    if (num < 5.5 || num > 6.8) return 'text-amber-400';
    return 'text-cyan-400';
  };

  const getEcColor = () => {
    if (telemetry.isDrainCycle && telemetry.patternStatus === 'CONFIRMED_PERIODIC') {
      return 'text-cyan-400';
    }
    if (telemetry.ec === '--') return 'text-slate-400';
    const num = parseFloat(telemetry.ec);
    if (num < 0.4 || num > 3.2) return 'text-rose-400';
    if (num < 0.8) return 'text-amber-400';
    return 'text-emerald-400';
  };

  return (
    <div className="w-full bg-slate-900/80 backdrop-blur-md border-b border-slate-800 flex justify-between items-center px-6 py-3 shadow-md z-40 relative">
      <div className="flex items-center space-x-2">
        <span className={`inline-block w-2 h-2 rounded-full ${connected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
        <span className="text-xs text-slate-400 font-mono">{connected ? 'ONLINE' : 'DISCONNECTED'}</span>
      </div>

      <div className="flex space-x-6">
        <div className="flex flex-col items-center">
          <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">pH Level</span>
          <span className={`text-xl font-bold ${getPhColor()}`}>{telemetry.ph}</span>
        </div>
        <div className="w-px h-8 bg-slate-800" />
        <div className="flex flex-col items-center">
          <div className="flex items-center space-x-1">
            <span className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">EC (mS/cm)</span>
            {telemetry.isDrainCycle && telemetry.patternStatus === 'CONFIRMED_PERIODIC' && (
              <span className="text-[9px] bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 rounded px-1 font-mono">DRAIN</span>
            )}
          </div>
          <span className={`text-xl font-bold ${getEcColor()}`}>{telemetry.ec}</span>
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
