import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { HiClock } from 'react-icons/hi';

const PresetHistory = () => {
    const [logs, setLogs] = useState([]);

    useEffect(() => {
        axios.get('/api/preset_logs')
            .then(res => setLogs(res.data))
            .catch(err => console.error(err));
    }, []);

    return (
        <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-6 shadow-xl border border-slate-800/50 mt-8">
            <div className="flex items-center mb-6">
                <HiClock className="text-2xl text-emerald-400 mr-3" />
                <h2 className="text-xl font-semibold text-slate-100">Audit History</h2>
            </div>
            <div className="overflow-x-auto custom-scrollbar">
                <table className="w-full text-left border-collapse min-w-[600px]">
                    <thead>
                        <tr className="border-b border-slate-700 text-slate-400 text-sm">
                            <th className="pb-3 px-4 font-medium uppercase tracking-wider">Timestamp</th>
                            <th className="pb-3 px-4 font-medium uppercase tracking-wider">Action</th>
                            <th className="pb-3 px-4 font-medium uppercase tracking-wider">Preset Name</th>
                            <th className="pb-3 px-4 font-medium uppercase tracking-wider">Details</th>
                        </tr>
                    </thead>
                    <tbody className="text-slate-300 text-sm">
                        {logs.map(log => (
                            <tr key={log.id} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                                <td className="py-3 px-4 whitespace-nowrap">{log.timestamp}</td>
                                <td className="py-3 px-4">
                                    <span className={`px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold ${log.action === 'Added' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                                            log.action === 'Modified' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' :
                                                log.action === 'Applied' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                                                    'bg-red-500/20 text-red-400 border border-red-500/30'
                                        }`}>
                                        {log.action}
                                    </span>
                                </td>
                                <td className="py-3 px-4 font-semibold text-white">{log.preset_name}</td>
                                <td className="py-3 px-4 text-slate-400">{log.details}</td>
                            </tr>
                        ))}
                        {logs.length === 0 && (
                            <tr>
                                <td colSpan="4" className="py-8 text-center text-slate-500 italic">No preset activities recorded yet.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default PresetHistory;
