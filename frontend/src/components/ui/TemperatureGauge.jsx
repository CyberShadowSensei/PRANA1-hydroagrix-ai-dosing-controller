import React from "react";
import SmoothGauge from "./SmoothGauge";

const TemperatureGauge = ({ value, time }) => {
  const normalizedValue = Math.min(Math.max(Number(value) || 0, 0), 100);
  const percentValue = normalizedValue / 100;

  return (
    <div className="w-full h-full p-6 rounded-xl bg-gradient-to-br from-slate-800 via-slate-900 to-slate-800 flex flex-col shadow-lg">
      <div className="flex items-center mb-4">
        <h2 className="text-xl font-bold text-white">Temperature</h2>
        <div className="ml-auto px-2 py-0.5 bg-slate-700/50 rounded-full">
          <span className="text-sm text-emerald-400 font-medium">{time}</span>
        </div>
      </div>
      
      <div className="flex-1 flex flex-col items-center justify-center relative">
        <div className="relative w-48">
          <SmoothGauge
            percent={percentValue}
            arcsLength={[20 / 100, 10 / 100, 30/100, 40 / 100]}
            colors={["#0066FF", "#00FF44", "#FFD700", "#FF0F0F"]}
          />
        </div>

        {/* Scale markers with improved styling */}
        {/* <div className="w-full relative mt-2">
          <div className="absolute left-6 -top-20 text-slate-400 text-xs">0</div>
          <div className="absolute left-[20%] -top-28 text-slate-400 text-xs">20</div>
          <div className="absolute left-[30%] -top-32 transform -translate-x-1/2 text-slate-400 text-xs">30</div>
          <div className="absolute left-[60%] -top-32 transform -translate-x-1/2 text-slate-400 text-xs">60</div>
          <div className="absolute right-6 -top-20 text-slate-400 text-xs">100</div>
        </div> */}

        {/* Value display below gauge */}
        <div className="mt-6 text-center bg-slate-700/30 px-6 py-3 rounded-lg">
          <span className="text-2xl font-bold text-white">{normalizedValue.toFixed(1)}</span>
          <span className="text-lg text-slate-400 ml-2">°C</span>
        </div>
      </div>

      {/* Added subtle gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-slate-900/20 to-transparent rounded-xl pointer-events-none" />
    </div>
  );
};

export default TemperatureGauge;