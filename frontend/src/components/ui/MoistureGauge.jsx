/**
 * MoistureGauge Component
 * Radial gauge visualizer for root-zone moisture levels.
 */
import React from "react";
import SmoothGauge from "./SmoothGauge";

const MoistureGauge = ({ value, state, time }) => {
  console.log("MoistureGauge received value:", value, "type:", typeof value);
  console.log("MoistureGauge received state:", state);
  console.log("MoistureGauge received time:", time);

  const normalizedValue = Math.min(Math.max(Number(value) || 0, 0), 2000);
  console.log(value)
  const percentValue = normalizedValue / 2000;

  return (
    <div className="w-full h-full p-6 rounded-xl bg-gradient-to-br from-slate-800 via-slate-900 to-slate-800 flex flex-col shadow-lg">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-white">Moisture level</h2>
        <div className="px-3 py-1 bg-slate-700/50 rounded-full">
          <span className="text-sm text-emerald-400 font-medium">{time}</span>
        </div>
      </div>
      
      <div className="flex-1 flex flex-col items-center justify-center relative">
        <div className="relative w-48">
          <SmoothGauge
            percent={percentValue}
            arcsLength={[300 / 2000, 200 / 2000, 1400 / 2000]}
            colors={["#0074FF", "#00BFFF", "#000080"]}
          />
        </div>

        {/* Scale markers with improved styling */}
        {/* <div className="w-full relative mt-2">
          <div className="absolute left-6 -top-24 text-slate-400 text-xs">0</div>
          <div className="absolute left-1/4 -top-28 text-slate-400 text-xs">300</div>
          <div className="absolute left-1/2 -top-32 transform -translate-x-1/2 text-slate-400 text-xs">600</div>
          <div className="absolute right-6 -top-24 text-slate-400 text-xs">2000</div>
        </div> */}

        {/* Value display below gauge */}
        <div className="mt-6 text-center bg-slate-700/30 px-6 py-3 rounded-lg">
          <span className="text-3xl font-bold text-white">{normalizedValue.toFixed(1)}</span>
          <span className="text-lg text-slate-400 ml-2">{state}</span>
        </div>
      </div>

      {/* Added subtle gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-slate-900/20 to-transparent rounded-xl pointer-events-none" />
    </div>
  );
};

export default MoistureGauge;