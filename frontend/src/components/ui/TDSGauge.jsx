import React from "react";
import SmoothGauge from "./SmoothGauge";

const TDSGauge = ({ value, time }) => {
  // Ensure value is within 0-15 range
  const normalizedValue = Math.min(Math.max(Number(value) || 0, 0), 15);
  
  // Convert to percentage for the gauge (0-15 → 0-1)
  const percentValue = normalizedValue / 15;

  return (
    <div className="w-full h-full p-6 rounded-xl bg-gradient-to-br from-slate-800 via-slate-900 to-slate-800 flex flex-col shadow-lg relative">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-white">Water EC</h2>
        <div className="px-3 py-1 bg-slate-700/50 rounded-full">
          <span className="text-sm text-emerald-400 font-medium">{time}</span>
        </div>
      </div>
      
      <div className="flex-1 flex flex-col items-center justify-center relative">
        <div className="relative w-48">
          <SmoothGauge
            percent={percentValue}
            arcsLength={[0.07, 0.13, 0.8]}
            colors={["#FFDD00", "#00FF44", "#FF0F0F"]}
          />
        </div>

        {/* Value display below gauge */}
        <div className="mt-6 text-center bg-slate-700/30 px-6 py-3 rounded-lg">
          <span className="text-3xl font-bold text-white">{normalizedValue.toFixed(2)}</span>
          <span className="text-lg text-slate-400 ml-2">ms/cm</span>
        </div>
      </div>

      {/* Scale labels */}
      <div className="w-full relative">
        <div className="absolute left-12 top-32 text-slate-400 text-xs">0</div>
        <div className="absolute left-1/4 top-28 text-slate-400 text-xs">3.0</div>
        <div className="absolute left-1/2 top-24 transform -translate-x-1/2 text-slate-400 text-xs">7.5</div>
        <div className="absolute right-12 top-32 text-slate-400 text-xs">15.0</div>
      </div>

      {/* Subtle gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-slate-900/20 to-transparent rounded-xl pointer-events-none" />
    </div>
  );
};

export default TDSGauge;