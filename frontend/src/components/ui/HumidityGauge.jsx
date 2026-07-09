import React from "react";
import GaugeChart from "react-gauge-chart";

const HumidityGauge = ({ value, time }) => {
  const normalizedValue = Math.min(Math.max(Number(value) || 0, 0), 100);
  const percentValue = normalizedValue / 100;

  return (
    <div className="w-full h-full p-6 rounded-xl bg-gradient-to-br from-slate-800 via-slate-900 to-slate-800 flex flex-col shadow-lg">
      <div className="flex items-center mb-4">
        <h2 className="text-xl font-bold text-white">Humidity</h2>
        <div className="ml-auto px-2 py-0.5 bg-slate-700/50 rounded-full">
          <span className="text-sm text-emerald-400 font-medium">{time}</span>
        </div>
      </div>
      
      <div className="flex-1 flex flex-col items-center justify-center relative">
        <div className="relative w-48">
          <GaugeChart
            id="humidity-gauge"
            nrOfLevels={20}
            arcsLength={[45 / 100, 20 / 100, 35 / 100]}
            colors={["#FF0F0F", "#00FF44", "#FF0F0F"]}
            percent={percentValue}
            arcWidth={0.12}
            arcPadding={0.02}
            needleColor="#E2E8F0"
            needleBaseColor="#475569"
            textColor="transparent"
            formatTextValue={() => ""}
            cornerRadius={5}
          />
        </div>

        {/* Scale markers with improved styling */}
        {/* <div className="w-full relative mt-2">
          <div className="absolute left-6 -top-20 text-slate-400 text-xs">0</div>
          <div className="absolute left-[39%] -top-28 text-slate-400 text-xs">45</div>
          <div className="absolute left-1/2 -top-32 transform -translate-x-1/2 text-slate-400 text-xs">65</div>
          <div className="absolute right-6 -top-20 text-slate-400 text-xs">100</div>
        </div> */}

        {/* Value display below gauge */}
        <div className="mt-6 text-center bg-slate-700/30 px-6 py-3 rounded-lg">
          <span className="text-2xl font-bold text-white">{normalizedValue.toFixed(1)}</span>
          <span className="text-lg text-slate-400 ml-2">%</span>
        </div>
      </div>

      {/* Added subtle gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-slate-900/20 to-transparent rounded-xl pointer-events-none" />
    </div>
  );
};

export default HumidityGauge;