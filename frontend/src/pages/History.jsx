/**
 * History Page Component
 * Historical time-series analytics, sensor charting, and event log exploration interface.
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { capitalizeFirstLetter } from '../hooks/capitalize';

const History = () => {
  const [temperatureHumidityData, setTemperatureHumidityData] = useState([]);
  const [moistureData, setMoistureData] = useState([]);
  const [tdsData, setTdsData] = useState([]);
  const [phData, setPHData] = useState([]);
  const [reportStartDate, setReportStartDate] = useState('');
  const [reportEndDate, setReportEndDate] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  const deleteTemperatureHumidityHistory = async () => {
    try {
      const response = await axios.post(`/delete_temperature_humidity_data`);
      if (response.status === 200) {
        setTemperatureHumidityData([]);
      }
    } catch (error) {
      console.error("Error clearing temperature and humidity history:", error);
    }
  };

  const deleteMoistureHistory = async () => {
    try {
      const response = await axios.post(`/delete_moisture_data`);
      if (response.status === 200) {
        setMoistureData([]);
      }
    } catch (error) {
      console.error("Error clearing moisture history:", error);
    }
  };

  const deleteTDSHistory = async () => {
    try {
      const response = await axios.post(`/delete_tds_data`);
      if (response.status === 200) {
        setTdsData([]);
      }
    } catch (error) {
      console.error("Error clearing TDS history:", error);
    }
  };

  const deletePHHistory = async () => {
    try {
      const response = await axios.post(`/delete_ph_data`);
      if (response.status === 200) {
        setPHData([]);
      }
    } catch (error) {
      console.error("Error clearing PH history:", error);
    }
  };
  
  const downloadCSV = async () => {
    try {
      const response = await axios.get('/download_database_csv', { responseType: 'blob' });
      if (response.status === 200) {
        const url = window.URL.createObjectURL(response.data);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'PlantCareDashboard.csv';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } else {
        console.error("Failed to fetch database csv");
      }
    } catch (error) {
      console.error("Error downloading database CSV:", error);
    }
  };



  useEffect(() => {
    const fetchTemperatureHumidityData = async () => {
      try {
        const historyResponse = await axios.get('/get_temperature_humidity_history');
        const historyData = historyResponse.data;

        const formattedData = historyData.temperature_humidity_data.map(item => {
          // Parse the timestamp manually to handle the IST timezone
          const timestampStr = item.date;
          // Remove the IST part and replace with a standard timezone offset
          const standardTimestamp = timestampStr.includes("IST") 
            ? timestampStr.replace(" IST", "+05:30") 
            : timestampStr;
          
          return {
            time: item.date, // Keep original for display
            date: new Date(standardTimestamp), // Create proper date object
            temperature: parseFloat(item.temperature),
            humidity: parseFloat(item.humidity)
          };
        });

        // Sort by date descending (newest first) and take only top 10
        const sortedData = formattedData
          .sort((a, b) => b.date - a.date) // Use the date object for sorting
          .slice(0, 10);

        setTemperatureHumidityData(sortedData);
      } catch (error) {
        console.error("Error fetching temperature and humidity data:", error);
      }
    };
  
    fetchTemperatureHumidityData();
    const interval = setInterval(fetchTemperatureHumidityData, 300000);
  
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchMoistureData = async () => {
      try {
        const response = await axios.get('/get_moisture_data');
        const data = response.data;
        const formattedData = data.moisture_data.map((item) => ({
          time: new Date(item.date).toLocaleTimeString(),
          date: new Date(item.date), // Keep the date object for sorting
          level: parseFloat(item.moisture_level),
          state: item.state,
        }));
        
        // Sort by date descending (newest first) and take only top 10
        const sortedData = formattedData
          .sort((a, b) => b.date - a.date)
          .slice(0, 10)
          .map(({ date, ...rest }) => rest); // Remove the date object after sorting
        
        setMoistureData(sortedData);
      } catch (error) {
        console.error("Error fetching moisture data:", error);
      }
    };
  
    fetchMoistureData();
    const interval = setInterval(fetchMoistureData, 300000);
  
    return () => clearInterval(interval);
  }, []);
  
  useEffect(() => {
    const fetchTDSData = async () => {
      try {
        const historyResponse = await axios.get('/get_tds_history');
        const historyData = historyResponse.data;

        const formattedData = historyData.tds_data.map(item => {
          // Parse the timestamp manually to handle the IST timezone
          const timestampStr = item.date;
          // Remove the IST part and replace with a standard timezone offset
          const standardTimestamp = timestampStr.includes("IST") 
            ? timestampStr.replace(" IST", "+05:30") 
            : timestampStr;
          
          return {
            time: item.date, // Keep original for display
            date: new Date(standardTimestamp), // Create proper date object
            tds_value: parseFloat(item.tds_value)
          };
        });

        // Sort by date descending (newest first) and take only top 10
        const sortedData = formattedData
          .sort((a, b) => b.date - a.date) // Use the date object for sorting
          .slice(0, 10);

        setTdsData(sortedData);
      } catch (error) {
        console.error("Error fetching TDS data:", error);
      }
    };
    fetchTDSData();
    const interval = setInterval(fetchTDSData, 300000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchPHData = async () => {
      try {
        const historyResponse = await axios.get('/get_ph_history');
        const historyData = historyResponse.data;

        const formattedData = historyData.ph_data.map(item => {
          // Parse the timestamp manually to handle the IST timezone
          const timestampStr = item.timestamp;
          // Remove the IST part and replace with a standard timezone offset
          // IST is typically UTC+5:30
          const standardTimestamp = timestampStr.replace(" IST", "+05:30");
          
          return {
            time: item.timestamp, // Keep original for display
            date: new Date(standardTimestamp), // Create proper date object
            ph_value: parseFloat(item.ph_value)
          };
        });

        // Sort by date descending (newest first) and take only top 10
        const sortedData = formattedData
          .sort((a, b) => b.date - a.date) // Use the date object for sorting
          .slice(0, 10);
                
        setPHData(sortedData);
      } catch (error) {
        console.error("Error fetching PH data:", error);
      }
    };
    fetchPHData();
    const interval = setInterval(fetchPHData, 300000);
    return () => clearInterval(interval);
  }, []);
  
  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-6">
      <div className="rounded-lg bg-gradient-to-b from-slate-800 to-slate-900 border border-slate-700/30 overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700/30 flex flex-col md:flex-row items-center justify-between gap-4">
          <h2 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)] mb-3 md:mb-0">
            Sensor History (Latest 10 entries)
          </h2>
          <div className="flex gap-4">
            <button 
              onClick={downloadCSV} 
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg transition duration-200"
            >
              Download CSV
            </button>

          </div>
        </div>

        {/* Content */}
        <div className="p-4 md:p-6">


          <div className="grid md:grid-cols-2 gap-4">
            
            {/* Temperature & Humidity History */}
            <div className="rounded-lg bg-slate-800/50 border border-slate-700/30 overflow-hidden h-96 flex flex-col">
              <div className="p-3 bg-slate-700/30 flex justify-between items-center">
                <h3 className="font-medium text-blue-400">Temperature & Humidity History</h3>
                <button
                  onClick={deleteTemperatureHumidityHistory}
                  className="px-3 py-1 bg-red-600/80 hover:bg-red-700 text-white text-sm rounded-md transition"
                >
                  Clear
                </button>
              </div>
              <div className="p-4 overflow-y-auto flex-grow">
                {temperatureHumidityData.length ? (
                  <ul className="space-y-2">
                    {temperatureHumidityData.map((data, index) => (
                      <li key={index} className="p-2 border-b border-slate-700/30 text-slate-300">
                        <span className="text-white font-medium">{data.time}</span>
                        <div className="flex justify-between mt-1">
                          <span className="text-blue-400">{data.temperature}°C</span>
                          <span className="text-green-400">{data.humidity}%</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-400 text-center pt-8">No temperature and humidity history available.</p>
                )}
              </div>
            </div>
            
            {/* Moisture History */}
            <div className="rounded-lg bg-slate-800/50 border border-slate-700/30 overflow-hidden h-96 flex flex-col">
              <div className="p-3 bg-slate-700/30 flex justify-between items-center">
                <h3 className="font-medium text-blue-400">Moisture History</h3>
                <button
                  onClick={deleteMoistureHistory}
                  className="px-3 py-1 bg-red-600/80 hover:bg-red-700 text-white text-sm rounded-md transition"
                >
                  Clear
                </button>
              </div>
              <div className="p-4 overflow-y-auto flex-grow">
                {moistureData.length ? (
                  <ul className="space-y-2">
                    {moistureData.map((data, index) => (
                      <li key={index} className="p-2 border-b border-slate-700/30 text-slate-300">
                        <span className="text-white font-medium">{data.time}</span>
                        <div className="flex justify-between mt-1">
                          <span className={`${
                            data.state.toLowerCase() === 'wet' ? 'text-blue-400' :
                            data.state.toLowerCase() === 'moist' ? 'text-green-400' : 'text-yellow-400'
                          } capitalize`}>
                            {data.state}
                          </span>
                          <span className="text-indigo-400">{data.level}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-400 text-center pt-8">No moisture history available.</p>
                )}
              </div>
            </div>
            
            {/* TDS History */}
            <div className="rounded-lg bg-slate-800/50 border border-slate-700/30 overflow-hidden h-96 flex flex-col">
              <div className="p-3 bg-slate-700/30 flex justify-between items-center">
                <h3 className="font-medium text-blue-400">EC History</h3>
                <button
                  onClick={deleteTDSHistory}
                  className="px-3 py-1 bg-red-600/80 hover:bg-red-700 text-white text-sm rounded-md transition"
                >
                  Clear
                </button>
              </div>
              <div className="p-4 overflow-y-auto flex-grow">
                {tdsData.length ? (
                  <ul className="space-y-2">
                    {tdsData.map((data, index) => (
                      <li key={index} className="p-2 border-b border-slate-700/30 text-slate-300">
                        <span className="text-white font-medium">{data.time}</span>
                        <div className="flex justify-between mt-1">
                          <span className="text-purple-400">TDS:</span>
                          <span className="text-indigo-400">{Math.floor(data.tds_value * 100)/100}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-400 text-center pt-8">No EC history available.</p>
                )}
              </div>
            </div>
            
            {/* PH History */}
            <div className="rounded-lg bg-slate-800/50 border border-slate-700/30 overflow-hidden h-96 flex flex-col">
              <div className="p-3 bg-slate-700/30 flex justify-between items-center">
                <h3 className="font-medium text-blue-400">PH History</h3>
                <button
                  onClick={deletePHHistory}
                  className="px-3 py-1 bg-red-600/80 hover:bg-red-700 text-white text-sm rounded-md transition"
                >
                  Clear
                </button>
              </div>
              <div className="p-4 overflow-y-auto flex-grow">
                {phData.length ? (
                  <ul className="space-y-2">
                    {phData.map((data, index) => (
                      <li key={index} className="p-2 border-b border-slate-700/30 text-slate-300">
                        <span className="text-white font-medium">{data.time}</span>
                        <div className="flex justify-between mt-1">
                          <span className="text-green-400">PH:</span>
                          <span className={`${
                            data.ph_value < 6.5 ? 'text-yellow-400' :
                            data.ph_value > 7.5 ? 'text-blue-400' : 'text-green-400'
                          }`}>
                            {Math.floor(data.ph_value * 100)/100}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-400 text-center pt-8">No PH history available.</p>
                )}
              </div>
            </div>
            
          </div>
          

        </div>
      </div>
    </div>
  );
};

export default History;