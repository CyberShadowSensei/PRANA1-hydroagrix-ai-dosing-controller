import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Camera, Square, Lightbulb, Fan, Video, X } from 'lucide-react';
import socket from "../socket";

const ENABLE_PERIPHERALS = false;

const PlantCamera = () => {
  const [isCapturing, setIsCapturing] = useState(false);
  const [isLiveStreaming, setIsLiveStreaming] = useState(false);
  const [capturedPhoto, setCapturedPhoto] = useState(null);
  const [liveStreamFrame, setLiveStreamFrame] = useState(null);
  const [lightStatus, setLightStatus] = useState('OFF');
  const [fanStatus, setFanStatus] = useState('OFF');

  useEffect(() => {
    fetchLatestPhoto();
    fetchLightStatus();
    fetchFanStatus();
  }, []);

  useEffect(() => {
    if (isLiveStreaming) {
      // Using singleton socket

      socket.on('connect', () => console.log('SocketIO: Connected'));
      socket.on('camera_frame', (data) => setLiveStreamFrame(`data:image/jpeg;base64,${data.image}`));
      socket.on('connect_error', (err) => console.error('SocketIO Connection Error:', err));
      socket.on('disconnect', (reason) => console.log('SocketIO Disconnected:', reason));

      // Request stream start from backend
      axios.post('/start_stream').catch(console.error);
    }

    return () => {
      socket.off('camera_frame');
      if (isLiveStreaming) {
        axios.post('/stop_stream').catch(console.error);
        setLiveStreamFrame(null);
      }
    };
  }, [isLiveStreaming]);

  const fetchStatus = async (endpoint, setter) => {
    try {
      const response = await axios.get(endpoint);
      if (response.status === 200) {
        setter(response.data.status);
      }
    } catch (error) {
      console.error(`Error fetching status from ${endpoint}:`, error);
    }
  };

  const fetchLightStatus = () => fetchStatus('/get_relay_status', setLightStatus);
  const fetchFanStatus = () => fetchStatus('/get_relay_status_fan', setFanStatus);
  
  const toggleDevice = async (endpoint, setter) => {
    try {
      const response = await axios.post(endpoint);
      if (response.status === 200) {
        setter(response.data.status);
      }
    } catch (error) {
      console.error(`Error toggling device at ${endpoint}:`, error);
    }
  };

  const toggleLight = () => toggleDevice('/toggle_relay', setLightStatus);
  const toggleFan = () => toggleDevice('/toggle_relay_fan', setFanStatus);
  
  const fetchLatestPhoto = async () => {
    try {
      const response = await axios.get(`/get_latest_photo?${new Date().getTime()}`, {
        responseType: 'blob'
      });
      if (response.status === 200) {
        setCapturedPhoto(URL.createObjectURL(response.data));
      } else {
        setCapturedPhoto(null);
      }
    } catch (error) {
      console.error('Error fetching latest photo:', error);
      setCapturedPhoto(null);
    }
  };

  const capturePhoto = async () => {
    setIsCapturing(true);
    try {
      const response = await axios.post('/capture_photo');
      if (response.status === 200) {
        await new Promise(resolve => setTimeout(resolve, 500)); // Give backend time to save
        await fetchLatestPhoto();
      }
    } catch (error) {
      console.error('Error capturing photo:', error);
    } finally {
      setIsCapturing(false);
    }
  };

  return (
    <div className="w-full min-h-screen bg-slate-950 p-4 sm:p-6 text-slate-200">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)]">
              Camera & Device Control
            </h1>
            <p className="text-slate-400 mt-2">Remote viewing and peripheral device control.</p>
          </div>
          {isLiveStreaming && (
            <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/30 px-4 py-2 rounded-lg">
              <div className="w-2.5 h-2.5 bg-red-500 rounded-full animate-pulse shadow-[0_0_10px_#ef4444]"></div>
              <span className="text-red-400 font-bold text-sm uppercase tracking-wider">LIVE</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main Content: Image Display */}
          <div className="lg:col-span-2 bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50">
            <h2 className="text-xl font-semibold text-slate-100 mb-4">Latest Captured Photo</h2>
            <div className="aspect-video w-full rounded-lg bg-slate-950/50 border border-slate-800 flex items-center justify-center overflow-hidden">
              {capturedPhoto ? (
                <img src={capturedPhoto} alt="Latest from plant" className="w-full h-full object-cover" />
              ) : (
                <div className="text-center text-slate-500">
                  <Camera size={48} className="mx-auto mb-2" />
                  <p>No photo available. Press 'Capture Photo' to get started.</p>
                </div>
              )}
            </div>
          </div>

          {/* Right Sidebar: Controls */}
          <div className="space-y-8">
            <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50">
              <h3 className="text-lg font-semibold text-slate-100 mb-4">Camera Actions</h3>
              <div className="space-y-4">
                <button
                  onClick={capturePhoto}
                  disabled={isCapturing || isLiveStreaming}
                  className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-lg font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  <Camera size={18} />
                  <span>{isCapturing ? 'Capturing...' : 'Capture Photo'}</span>
                </button>
                <button
                  onClick={() => setIsLiveStreaming(true)}
                  disabled={isLiveStreaming}
                  className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-lg font-semibold bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  <Video size={18} />
                  <span>Start Live Feed</span>
                </button>
              </div>
            </div>

            {ENABLE_PERIPHERALS && (
              <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50">
                <h3 className="text-lg font-semibold text-slate-100 mb-4">Device Toggles</h3>
                <div className="space-y-4">
                  <div className="flex justify-between items-center bg-slate-950/50 p-4 rounded-lg border border-slate-800">
                    <div className="flex items-center gap-3">
                      <Lightbulb className={`transition-colors ${lightStatus === 'ON' ? 'text-yellow-400' : 'text-slate-600'}`} size={20} />
                      <span className="font-semibold text-white">Grow Light</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-xs font-bold uppercase ${lightStatus === 'ON' ? 'text-yellow-400' : 'text-slate-500'}`}>{lightStatus}</span>
                      <button
                        onClick={toggleLight}
                        className={`w-12 h-6 flex items-center rounded-full p-1 cursor-pointer transition-colors ${lightStatus === 'ON' ? 'bg-yellow-400/30' : 'bg-slate-700'}`}
                      >
                        <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${lightStatus === 'ON' ? 'translate-x-6' : 'translate-x-0'}`} />
                      </button>
                    </div>
                  </div>
                  <div className="flex justify-between items-center bg-slate-950/50 p-4 rounded-lg border border-slate-800">
                    <div className="flex items-center gap-3">
                      <Fan className={`transition-colors ${fanStatus === 'ON' ? 'text-sky-400' : 'text-slate-600'}`} size={20} />
                      <span className="font-semibold text-white">Air Circulation</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-xs font-bold uppercase ${fanStatus === 'ON' ? 'text-sky-400' : 'text-slate-500'}`}>{fanStatus}</span>
                      <button
                        onClick={toggleFan}
                        className={`w-12 h-6 flex items-center rounded-full p-1 cursor-pointer transition-colors ${fanStatus === 'ON' ? 'bg-sky-400/30' : 'bg-slate-700'}`}
                      >
                        <div className={`bg-white w-4 h-4 rounded-full shadow-md transform transition-transform duration-300 ${fanStatus === 'ON' ? 'translate-x-6' : 'translate-x-0'}`} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Live Stream Modal */}
      {isLiveStreaming && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-lg z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="relative w-full max-w-4xl bg-slate-900/50 border border-slate-700/50 rounded-2xl shadow-2xl p-4">
            <div className="aspect-video w-full flex items-center justify-center bg-black rounded-lg overflow-hidden">
              {liveStreamFrame ? (
                <img src={liveStreamFrame} alt="Live Plant Feed" className="w-full h-full object-contain" />
              ) : (
                <div className="text-center text-slate-400">
                  <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                  <p>Connecting to camera...</p>
                </div>
              )}
            </div>
            <button
              onClick={() => setIsLiveStreaming(false)}
              className="absolute -top-4 -right-4 w-10 h-10 bg-red-600 rounded-full flex items-center justify-center text-white hover:bg-red-700 transition-all transform hover:scale-110 shadow-lg"
              aria-label="Close live stream"
            >
              <X size={24} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default PlantCamera;