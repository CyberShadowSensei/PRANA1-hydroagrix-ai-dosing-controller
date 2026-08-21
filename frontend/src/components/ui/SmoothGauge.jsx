import React from 'react';

const SmoothGauge = ({ percent = 0, arcsLength = [1], colors = ["#00FF44"] }) => {
  const circumference = Math.PI * 40; 
  let currentOffset = 0;
  
  const arcs = arcsLength.map((len, i) => {
    const dashLength = len * circumference;
    const offset = currentOffset;
    currentOffset -= dashLength;

    return (
      <path
        key={i}
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke={colors[i] || "#ccc"}
        strokeWidth={10}
        strokeDasharray={`${dashLength} ${circumference - dashLength}`}
        strokeDashoffset={offset}
      />
    );
  });

  return (
    <div className="w-full flex justify-center">
      <svg viewBox="0 0 100 55" className="w-full max-w-[200px] overflow-visible">
        {arcs}
        <g 
          style={{ 
            transform: `translate(50px, 50px) rotate(${percent * 180 - 90}deg)`, 
            transition: 'transform 0.4s cubic-bezier(0.4, 0, 0.2, 1)'
          }}
        >
          <path d="M -2 0 L 2 0 L 0 -38 Z" fill="#E2E8F0" />
          <circle cx="0" cy="0" r="4" fill="#475569" />
        </g>
      </svg>
    </div>
  );
};

export default SmoothGauge;
