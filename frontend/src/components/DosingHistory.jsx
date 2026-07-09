import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { HiOutlineClock, HiOutlineBeaker, HiOutlineCheckCircle, HiOutlineExclamationCircle } from 'react-icons/hi';

const DosingHistory = () => {
    const [events, setEvents] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchHistory = async () => {
        try {
            setIsLoading(true);
            setError(null);
            const resp = await axios.get('/api/dosing_events?limit=20');
            setEvents(resp.data || []);
        } catch (e) {
            console.error('Error fetching dosing history:', e);
            setError('Failed to load history');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchHistory();
        const interval = setInterval(fetchHistory, 10000); // refresh every 10 seconds
        return () => clearInterval(interval);
    }, []);

    const getActionColor = (action) => {
        if (action.includes('PH UP')) return 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20';
        if (action.includes('PH DOWN')) return 'text-orange-400 bg-orange-400/10 border-orange-400/20';
        if (action.includes('EC')) return 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20';
        if (action.includes('Actuated')) return 'text-indigo-400 bg-indigo-400/10 border-indigo-400/20';
        return 'text-slate-300 bg-slate-800 border-slate-700';
    };

    const getActionIcon = (action) => {
        if (action.includes('PH') || action.includes('EC')) return <HiOutlineBeaker className="w-5 h-5" />;
        return <HiOutlineCheckCircle className="w-5 h-5" />;
    };

    return (
        <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 w-full">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-xl font-semibold text-slate-100 flex items-center">
                        <HiOutlineClock className="w-6 h-6 mr-2 text-emerald-400" />
                        Dosing Decision History
                    </h2>
                    <p className="text-sm text-slate-400 mt-1">
                        Transparency log of automated system decisions and manual interventions
                    </p>
                </div>
                <button 
                    onClick={fetchHistory}
                    disabled={isLoading}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm font-medium transition-colors border border-slate-700"
                >
                    {isLoading ? 'Refreshing...' : 'Refresh'}
                </button>
            </div>

            {error ? (
                <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-lg flex items-center">
                    <HiOutlineExclamationCircle className="w-5 h-5 mr-2" />
                    {error}
                </div>
            ) : events.length === 0 ? (
                <div className="text-center py-10 border border-dashed border-slate-700 rounded-lg bg-slate-900/30">
                    <HiOutlineBeaker className="w-12 h-12 mx-auto text-slate-600 mb-3" />
                    <p className="text-slate-400">No dosing events recorded yet</p>
                </div>
            ) : (
                <div className="space-y-4">
                    {events.map((evt, idx) => (
                        <div key={idx} className="bg-slate-950/50 p-4 rounded-xl border border-slate-800/50 hover:border-slate-700/80 transition-colors">
                            <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-4">
                                
                                {/* Header / Action */}
                                <div className="flex items-start space-x-3">
                                    <div className={`p-2 rounded-lg border ${getActionColor(evt.action)}`}>
                                        {getActionIcon(evt.action)}
                                    </div>
                                    <div>
                                        <div className="flex items-center space-x-2">
                                            <h3 className="font-bold text-slate-200">{evt.action}</h3>
                                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${evt.type === 'Automatic' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
                                                {evt.type}
                                            </span>
                                        </div>
                                        <p className="text-sm text-slate-400 mt-1">{evt.reason}</p>
                                    </div>
                                </div>

                                {/* Details & Timestamp */}
                                <div className="flex flex-col items-start md:items-end space-y-2 min-w-[200px]">
                                    <div className="text-xs text-slate-500 font-medium">
                                        {evt.timestamp}
                                    </div>
                                    
                                    <div className="flex flex-wrap gap-2 justify-start md:justify-end">
                                        {evt.details?.target_ec !== undefined && (
                                            <span className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-xs text-slate-300">
                                                Target EC: <span className="text-white font-bold">{evt.details.target_ec.toFixed(2)}</span>
                                            </span>
                                        )}
                                        {evt.details?.target_ph !== undefined && (
                                            <span className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-xs text-slate-300">
                                                Target pH: <span className="text-white font-bold">{evt.details.target_ph.toFixed(2)}</span>
                                            </span>
                                        )}
                                        {evt.details?.pump_1_sec !== undefined && (
                                            <span className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-xs text-slate-300">
                                                Pump A/B: <span className="text-white font-bold">{evt.details.pump_1_sec}s</span>
                                            </span>
                                        )}
                                        {evt.details?.duration_sec !== undefined && (
                                            <span className="px-2 py-1 bg-slate-900 border border-slate-800 rounded text-xs text-slate-300">
                                                Duration: <span className="text-white font-bold">{evt.details.duration_sec}s</span>
                                            </span>
                                        )}
                                    </div>
                                </div>

                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default DosingHistory;
