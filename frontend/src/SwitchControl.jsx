import React from "react";

const SwitchControl = ({ lightStatus, onToggle }) => {
  return (
    <div>
      <h2>Light is currently: {lightStatus}</h2>
      <button onClick={onToggle}>
        {lightStatus === "ON" ? "Turn OFF" : "Turn ON"}
      </button>
    </div>
  );
};

export default SwitchControl;
