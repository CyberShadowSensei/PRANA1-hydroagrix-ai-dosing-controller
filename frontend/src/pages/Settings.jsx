import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Save, Mail, Lock, User } from 'lucide-react';

const Settings = () => {
  const [config, setConfig] = useState({
    sender_email: '',
    recipient_email: '',
    sender_password: ''
  });
  const [loading, setLoading] = useState(false);
  const [isSendingReport, setIsSendingReport] = useState(false);
  const [status, setStatus] = useState({ type: '', message: '' });
  const [dosingConfig, setDosingConfig] = useState({
    ph_dose_seconds: 5,
    nutrient_dose_seconds: 10,
    cooldown_minutes: 15,
    nutrient_gap_seconds: 10
  });

  useEffect(() => {
    fetchConfig();
    fetchDosingConfig();
  }, []);


  const handleSendReport = async () => {
    setIsSendingReport(true);
    setStatus({ type: '', message: '' });
    try {
      const response = await axios.post('/send_report_email');
      if (response.status === 200) {
        setStatus({ type: 'success', message: 'Report email sent successfully!' });
      }
    } catch (error) {
      setStatus({ type: 'error', message: `Error: ${error.response?.data?.error || error.message}` });
    } finally {
      setIsSendingReport(false);
    }
  };

  const fetchConfig = async () => {
    try {
      const response = await axios.get('/get_email_config');
      const data = response.data;
      setConfig({
        sender_email: data.sender_email,
        recipient_email: data.recipient_email,
        sender_password: '' // Don't show the real password
      });
    } catch (error) {
      console.error('Error fetching config:', error);
    }
  };

  const fetchDosingConfig = async () => {
    try {
      const response = await axios.get('/api/dosing_config');
      setDosingConfig(response.data);
    } catch (error) {
      console.error('Error fetching dosing config:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setStatus({ type: '', message: '' });

    try {
      // Save Email Config
      const emailRes = await axios.post('/update_email_config', config);

      if (emailRes.status === 200) {
        const emailData = emailRes.data;
        if (emailData.error) throw new Error(emailData.error);

        // Save Dosing Config
        await axios.post('/api/dosing_config', dosingConfig);

        setStatus({ type: 'success', message: 'Settings saved successfully!' });
        setConfig(prev => ({ ...prev, sender_password: '' })); // Clear password field
      }
    } catch (error) {
      setStatus({ type: 'error', message: `Error: ${error.response?.data?.error || error.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="pt-20 md:pt-6 px-4 md:px-8 pb-8 min-h-screen bg-slate-950 text-slate-200 w-full">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-2 text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500">
          System Settings
        </h1>
        <p className="text-slate-400 mb-8">Configure alerts and system preferences</p>

        <div className="space-y-8">
          <form onSubmit={handleSubmit} className="space-y-8">
            {/* Email Alerts Section */}
            <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800 shadow-lg">
              <div className="flex items-center mb-6 pb-4 border-b border-slate-800">
                <Mail className="w-6 h-6 text-emerald-400 mr-3" />
                <h2 className="text-xl font-semibold text-white">Email Alerts</h2>
              </div>

              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Sender Email (Gmail)
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
                    <input
                      type="email"
                      value={config.sender_email}
                      onChange={(e) => setConfig({ ...config, sender_email: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 pl-10 pr-4 text-white focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none transition-all"
                      placeholder="system@gmail.com"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    App Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
                    <input
                      type="password"
                      value={config.sender_password}
                      onChange={(e) => setConfig({ ...config, sender_password: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 pl-10 pr-4 text-white focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none transition-all"
                      placeholder="Enter new App Password to update"
                    />
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Leave blank to keep existing password. Use a Gmail App Password.
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Receiver Email
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-3 w-5 h-5 text-slate-500" />
                    <input
                      type="text"
                      value={config.recipient_email}
                      onChange={(e) => setConfig({ ...config, recipient_email: e.target.value })}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 pl-10 pr-4 text-white focus:ring-2 focus:ring-emerald-500 focus:border-transparent outline-none transition-all"
                      placeholder="user1@mail.com, user2@mail.com"
                    />
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Separate multiple emails with commas (e.g., user1@mail.com, user2@mail.com)
                  </p>
                </div>
              </div>
            </div>

            {/* Dosing Configuration Section */}
            <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800 shadow-lg">
              <div className="flex items-center mb-6 pb-4 border-b border-slate-800">
                <span className="w-6 h-6 text-emerald-400 mr-3 text-xl">💧</span>
                <h2 className="text-xl font-semibold text-white">Dosing Configuration</h2>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Tank Capacity (Liters)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="1"
                    max="1000"
                    value={dosingConfig.reservoir_volume_l || 10.0}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, reservoir_volume_l: parseFloat(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none"
                  />
                  <p className="text-xs text-slate-500 mt-1">Total reservoir volume used for proportional dosing math.</p>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    pH Dose Duration (Seconds)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="300"
                    value={dosingConfig.ph_dose_seconds}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, ph_dose_seconds: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none"
                  />
                  <p className="text-xs text-slate-500 mt-1">Runtime for pH UP/DOWN pumps.</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Nutrient Dose Duration (Seconds)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="600"
                    value={dosingConfig.nutrient_dose_seconds}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, nutrient_dose_seconds: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none"
                  />
                  <p className="text-xs text-slate-500 mt-1">Runtime for Nutrients A & B pumps.</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Cooldown Interval (Minutes)
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="120"
                    value={dosingConfig.cooldown_minutes}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, cooldown_minutes: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none"
                  />
                  <p className="text-xs text-slate-500 mt-1">Wait time before next dosing cycle.</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Nutrient A-to-B Gap (Seconds)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="120"
                    value={dosingConfig.nutrient_gap_seconds}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, nutrient_gap_seconds: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none"
                  />
                  <p className="text-xs text-slate-500 mt-1">Delay between Pump A and Pump B.</p>
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-6 bg-gradient-to-r from-emerald-500 to-cyan-600 hover:from-emerald-600 hover:to-cyan-700 text-white font-bold py-4 rounded-xl shadow-lg shadow-emerald-900/20 transition-all transform active:scale-[0.98] flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="animate-pulse">Saving Changes...</span>
              ) : (
                <>
                  <Save className="w-5 h-5 mr-2" />
                  Save All Settings
                </>
              )}
            </button>
          </form>

          {/* System Actions */}
          <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800 shadow-lg">
            <div className="flex items-center mb-4 pb-4 border-b border-slate-800">
              <div className="w-6 h-6 text-emerald-400 mr-3">⚡️</div>
              <h2 className="text-xl font-semibold text-white">System Actions</h2>
            </div>
            <button
              onClick={handleSendReport}
              disabled={isSendingReport}
              className="w-full bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white font-bold py-3 rounded-xl shadow-lg shadow-blue-900/20 transition-all transform active:scale-[0.98] flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSendingReport ? (
                <span className="animate-pulse">Sending Report...</span>
              ) : (
                <>
                  <Mail className="w-5 h-5 mr-2" />
                  Send Report Email
                </>
              )}
            </button>
          </div>

          {status.message && (
            <div className={`p-4 rounded-lg ${status.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
              }`}>
              {status.message}
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

export default Settings;