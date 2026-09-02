/**
 * QuickCameraWidget Component
 * Dashboard thumbnail widget displaying live webcam stream and growth stage badge.
 */
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import socket from "../socket";
import { Camera, Video, AlertCircle } from 'lucide-react';

const QuickCameraWidget = () => {
  const [isLiveStreaming, setIsLiveStreaming] = useState(false);
  const [liveStreamFrame, setLiveStreamFrame] = useState(null);

  useEffect(() => {
    if (isLiveStreaming) {
      // Using singleton socket
      socket.on('connect', () => console.log('CameraWidget SocketIO: Connected'));
      socket.on('camera_frame', (data) => setLiveStreamFrame(`data:image/jpeg;base64,${data.image}`));
      socket.on('connect_error', (err) => console.error('CameraWidget Connection Error:', err));
      
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

  return (
    <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-800/50 shadow-xl h-full flex flex-col">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
          <Camera size={20} className="text-emerald-400" />
          Live Camera Feed
        </h3>
        {isLiveStreaming ? (
          <button 
            onClick={() => setIsLiveStreaming(false)}
            className="px-3 py-1 bg-red-500/10 text-red-400 border border-red-500/30 rounded-lg text-sm font-semibold hover:bg-red-500/20 transition-all flex items-center gap-2"
          >
            <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse shadow-[0_0_8px_#ef4444]"></div>
            STOP
          </button>
        ) : (
          <button 
            onClick={() => setIsLiveStreaming(true)}
            className="px-3 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded-lg text-sm font-semibold hover:bg-emerald-500/20 transition-all flex items-center gap-2"
          >
            <Video size={14} />
            START
          </button>
        )}
      </div>

      <div className="flex-grow aspect-video bg-slate-950/80 rounded-lg border border-slate-800/80 flex items-center justify-center overflow-hidden relative">
        {!isLiveStreaming ? (
          <div className="text-center text-slate-500">
            <Camera size={32} className="mx-auto mb-2 opacity-50" />
            <p className="text-sm">Stream is offline</p>
          </div>
        ) : liveStreamFrame ? (
          <img src={liveStreamFrame} alt="Live Plant Feed" className="w-full h-full object-contain" />
        ) : (
          <div className="text-center text-slate-400">
            <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            <p className="text-sm">Connecting...</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default QuickCameraWidget;
