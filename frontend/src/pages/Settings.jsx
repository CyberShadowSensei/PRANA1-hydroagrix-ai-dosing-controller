import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Save, Mail, Lock, User, Sliders } from 'lucide-react';

const Settings = () => {
  const [config, setConfig] = useState({
    sender_email: '',
    recipient_email: '',
    sender_password: ''
  });
  const [emailLoading, setEmailLoading] = useState(false);
  const [dosingLoading, setDosingLoading] = useState(false);
  const [isSendingReport, setIsSendingReport] = useState(false);
  
  const [emailStatus, setEmailStatus] = useState({ type: '', message: '' });
  const [dosingStatus, setDosingStatus] = useState({ type: '', message: '' });

  const [dosingConfig, setDosingConfig] = useState({
    reservoir_volume_l: 10.0,
    pump_flow_rate_ml_per_sec: 1.0,
    nutrient_ml_per_l_per_ec: 2.0,
    ph_up_ml_per_l_per_ph: 0.5,
    ph_down_ml_per_l_per_ph: 0.5,
    max_dose_time_sec: 60,
    min_dose_time_sec: 2.0,
    cooldown_minutes: 15,
    nutrient_gap_seconds: 10,
    dry_run_mode: false,
    nutrient_a_capacity_ml: 5000,
    nutrient_a_volume_ml: 5000,
    nutrient_b_capacity_ml: 5000,
    nutrient_b_volume_ml: 5000,
    ph_up_capacity_ml: 5000,
    ph_up_volume_ml: 5000,
    ph_down_capacity_ml: 5000,
    ph_down_volume_ml: 5000
  });

  useEffect(() => {
    fetchConfig();
    fetchDosingConfig();
  }, []);

  const handleSendReport = async () => {
    setIsSendingReport(true);
    setEmailStatus({ type: '', message: '' });
    try {
      const response = await axios.post('/send_report_email');
      if (response.status === 200) {
        setEmailStatus({ type: 'success', message: 'Report email sent successfully!' });
      }
    } catch (error) {
      setEmailStatus({ type: 'error', message: `Error: ${error.response?.data?.error || error.message}` });
    } finally {
      setIsSendingReport(false);
    }
  };

  const fetchConfig = async () => {
    try {
      const response = await axios.get(`/get_email_config?t=${new Date().getTime()}`);
      const data = response.data;
      setConfig({
        sender_email: data.sender_email,
        recipient_email: data.receiver_email || data.recipient_email,
        sender_password: '' // Don't show the real password
      });
    } catch (error) {
      console.error('Error fetching config:', error);
    }
  };

  const fetchDosingConfig = async () => {
    try {
      const response = await axios.get(`/api/dosing_config?t=${new Date().getTime()}`);
      setDosingConfig(response.data);
    } catch (error) {
      console.error('Error fetching dosing config:', error);
    }
  };

  // 1. Independent Email Form Submission
  const handleSaveEmailConfig = async (e) => {
    e.preventDefault();
    setEmailLoading(true);
    setEmailStatus({ type: '', message: '' });

    try {
      const emailPayload = {
        sender_email: config.sender_email,
        receiver_email: config.recipient_email,
        sender_password: config.sender_password
      };
      const emailRes = await axios.post('/update_email_config', emailPayload);
      if (emailRes.status === 200 && !emailRes.data?.error) {
        setEmailStatus({ type: 'success', message: 'Email settings saved successfully!' });
        setConfig(prev => ({ ...prev, sender_password: '' }));
      } else {
        throw new Error(emailRes.data?.error || 'Failed to update email settings.');
      }
    } catch (error) {
      setEmailStatus({ type: 'error', message: `Error: ${error.response?.data?.error || error.message}` });
    } finally {
      setEmailLoading(false);
    }
  };

  // Default values dictionary for system & dosing configuration
  const DOSING_DEFAULTS = {
    reservoir_volume_l: 10.0,
    pump_flow_rate_ml_per_sec: 0.62,
    max_dose_time_sec: 60,
    min_dose_time_sec: 2.0,
    cooldown_minutes: 15,
    nutrient_gap_seconds: 10,
    dry_run_mode: false,
    nutrient_a_capacity_ml: 5000,
    nutrient_a_volume_ml: 5000,
    nutrient_b_capacity_ml: 5000,
    nutrient_b_volume_ml: 5000,
    ph_up_capacity_ml: 5000,
    ph_up_volume_ml: 5000,
    ph_down_capacity_ml: 5000,
    ph_down_volume_ml: 5000
  };

  // 2. Independent Dosing / System Specs Form Submission
  const handleSaveDosingConfig = async (e) => {
    e.preventDefault();
    setDosingLoading(true);
    setDosingStatus({ type: '', message: '' });

    try {
      // Fill any blank/unfilled fields with default values
      const sanitizedConfig = {};
      Object.keys(DOSING_DEFAULTS).forEach(key => {
        const val = dosingConfig[key];
        if (val === '' || val === null || val === undefined || Number.isNaN(val)) {
          sanitizedConfig[key] = DOSING_DEFAULTS[key];
        } else {
          sanitizedConfig[key] = val;
        }
      });

      await axios.post('/api/dosing_config', sanitizedConfig);
      setDosingStatus({ type: 'success', message: 'System & Dosing parameters saved successfully!' });
      await fetchDosingConfig();
    } catch (error) {
      setDosingStatus({ type: 'error', message: `Error saving system settings: ${error.response?.data?.error || error.message}` });
    } finally {
      setDosingLoading(false);
    }
  };

  return (
    <div className="pt-20 md:pt-6 px-4 md:px-8 pb-8 min-h-screen bg-slate-950 text-slate-200 w-full">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold mb-2 text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-500">
          System Settings
        </h1>
        <p className="text-slate-400 mb-8">Configure hardware parameters, tank capacities, and alert preferences independently.</p>

        <div className="space-y-10">
          {/* SECTION 1: SYSTEM & DOSING PARAMETERS */}
          <form onSubmit={handleSaveDosingConfig} className="bg-slate-900/50 rounded-xl p-6 border border-slate-800 shadow-lg space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div className="flex items-center">
                <Sliders className="w-6 h-6 text-cyan-400 mr-3" />
                <div>
                  <h2 className="text-xl font-semibold text-white">System & Dosing Setup</h2>
                  <p className="text-xs text-slate-400">Reservoir volume, pump rates, and tank capacities</p>
                </div>
              </div>
            </div>

            {/* System Specs */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">
                  Tank Capacity (Liters)
                </label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  max="1000"
                  value={dosingConfig.reservoir_volume_l ?? 10}
                  onChange={(e) => setDosingConfig({ ...dosingConfig, reservoir_volume_l: e.target.value === '' ? '' : Math.round(Number(e.target.value)) })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-cyan-500 outline-none"
                />
                <p className="text-xs text-slate-500 mt-1">Total volume of main reservoir.</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">
                  Pump Flow Rate (mL/s)
                </label>
                <input
                  type="number"
                  step="any"
                  min="0.01"
                  placeholder="0.62"
                  value={dosingConfig.pump_flow_rate_ml_per_sec ?? ''}
                  onChange={(e) => setDosingConfig({ ...dosingConfig, pump_flow_rate_ml_per_sec: e.target.value === '' ? '' : Number(e.target.value) })}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-cyan-500 outline-none"
                />
                <p className="text-xs text-slate-500 mt-1">Calibrated pump speed in mL/s (e.g., 0.62 mL/s = ~37 mL/min).</p>
              </div>
            </div>

            {/* Chemical Solution Tanks */}
            <div className="pt-4 border-t border-slate-800/60">
              <h3 className="text-base font-semibold text-slate-200 mb-4">Solution Tank Levels</h3>
              <div className="space-y-4">
                {/* Nutrient A */}
                <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-purple-400 mb-3">Nutrient A Tank</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Current Volume (mL)</label>
                      <input
                        type="number"
                        step="any"
                        min="0"
                        value={dosingConfig.nutrient_a_volume_ml ?? 500}
                        onChange={(e) => setDosingConfig({ ...dosingConfig, nutrient_a_volume_ml: e.target.value === '' ? '' : Number(e.target.value) })}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg py-2 px-3 text-white text-sm focus:ring-2 focus:ring-purple-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Max Capacity (mL)</label>
                      <input
                        type="number"
                        step="any"
                        min="1"
                        value={dosingConfig.nutrient_a_capacity_ml ?? 5000}
                        onChange={(e) => setDosingConfig({ ...dosingConfig, nutrient_a_capacity_ml: e.target.value === '' ? '' : Number(e.target.value) })}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg py-2 px-3 text-white text-sm focus:ring-2 focus:ring-purple-500 outline-none"
                      />
                    </div>
                  </div>
                </div>

                {/* Nutrient B */}
                <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-purple-400 mb-3">Nutrient B Tank</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Current Volume (mL)</label>
                      <input
                        type="number"
                        step="any"
                        min="0"
                        value={dosingConfig.nutrient_b_volume_ml ?? 500}
                        onChange={(e) => setDosingConfig({ ...dosingConfig, nutrient_b_volume_ml: e.target.value === '' ? '' : Number(e.target.value) })}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg py-2 px-3 text-white text-sm focus:ring-2 focus:ring-purple-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Max Capacity (mL)</label>
                      <input
                        type="number"
                        step="any"
                        min="1"
                        value={dosingConfig.nutrient_b_capacity_ml ?? 5000}
                        onChange={(e) => setDosingConfig({ ...dosingConfig, nutrient_b_capacity_ml: e.target.value === '' ? '' : Number(e.target.value) })}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg py-2 px-3 text-white text-sm focus:ring-2 focus:ring-purple-500 outline-none"
                      />
                    </div>
                  </div>
                </div>

                {/* pH Up */}
                <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-400 mb-3">pH Up Tank</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Current Volume (mL)</label>
                      <input
                        type="number"
                        step="any"
                        min="0"
                        value={dosingConfig.ph_up_volume_ml ?? 500}
                        onChange={(e) => setDosingConfig({ ...dosingConfig, ph_up_volume_ml: e.target.value === '' ? '' : Number(e.target.value) })}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg py-2 px-3 text-white text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Max Capacity (mL)</label>
                      <input
                        type="number"
                        step="any"
                        min="1"
                        value={dosingConfig.ph_up_capacity_ml ?? 5000}
                        onChange={(e) => setDosingConfig({ ...dosingConfig, ph_up_capacity_ml: e.target.value === '' ? '' : Number(e.target.value) })}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg py-2 px-3 text-white text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                      />
                    </div>
                  </div>
                </div>

                {/* pH Down */}
                <div className="bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-rose-400 mb-3">pH Down Tank</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Current Volume (mL)</label>
                      <input
                        type="number"
                        step="any"
                        min="0"
                        value={dosingConfig.ph_down_volume_ml ?? 500}
                        onChange={(e) => setDosingConfig({ ...dosingConfig, ph_down_volume_ml: e.target.value === '' ? '' : Number(e.target.value) })}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg py-2 px-3 text-white text-sm focus:ring-2 focus:ring-rose-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Max Capacity (mL)</label>
                      <input
                        type="number"
                        step="any"
                        min="1"
                        value={dosingConfig.ph_down_capacity_ml ?? 5000}
                        onChange={(e) => setDosingConfig({ ...dosingConfig, ph_down_capacity_ml: e.target.value === '' ? '' : Number(e.target.value) })}
                        className="w-full bg-slate-900 border border-slate-800 rounded-lg py-2 px-3 text-white text-sm focus:ring-2 focus:ring-rose-500 outline-none"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Dosing Controls & Safety */}
            <div className="pt-4 border-t border-slate-800/60">
              <h3 className="text-base font-semibold text-slate-200 mb-4">Dosing Safety & Intervals</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Max Single Dose Time (Seconds)
                  </label>
                  <input
                    type="number"
                    min="5"
                    max="600"
                    value={dosingConfig.max_dose_time_sec ?? 60}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, max_dose_time_sec: e.target.value === '' ? '' : Number(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-cyan-500 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Min Dose Time Ceiling (Seconds)
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    min="0.5"
                    max="60"
                    value={dosingConfig.min_dose_time_sec ?? 2.0}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, min_dose_time_sec: e.target.value === '' ? '' : Number(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-cyan-500 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Cooldown Interval (Minutes)
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="120"
                    value={dosingConfig.cooldown_minutes ?? 15}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, cooldown_minutes: e.target.value === '' ? '' : Number(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-cyan-500 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-400 mb-2">
                    Nutrient A-to-B Gap (Seconds)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="120"
                    value={dosingConfig.nutrient_gap_seconds ?? 10}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, nutrient_gap_seconds: e.target.value === '' ? '' : Number(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 px-4 text-white focus:ring-2 focus:ring-cyan-500 outline-none"
                  />
                </div>

                <div className="flex items-center space-x-3 mt-4 md:col-span-2">
                  <input
                    type="checkbox"
                    id="dry_run_mode"
                    checked={dosingConfig.dry_run_mode || false}
                    onChange={(e) => setDosingConfig({ ...dosingConfig, dry_run_mode: e.target.checked })}
                    className="w-5 h-5 bg-slate-950 border-slate-800 rounded text-cyan-500 focus:ring-cyan-500 focus:ring-2 accent-cyan-500"
                  />
                  <label htmlFor="dry_run_mode" className="text-sm font-medium text-slate-300">
                    Dry Run Mode (Simulate dosing without running physical pumps)
                  </label>
                </div>
              </div>
            </div>

            {/* Dosing Status Banner */}
            {dosingStatus.message && (
              <div className={`p-4 rounded-lg text-sm font-medium ${
                dosingStatus.type === 'success' 
                  ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30' 
                  : 'bg-rose-500/10 text-rose-300 border border-rose-500/30'
              }`}>
                {dosingStatus.message}
              </div>
            )}

            <button
              type="submit"
              disabled={dosingLoading}
              className="w-full bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold py-3.5 rounded-xl shadow-lg shadow-cyan-950/40 transition-all transform active:scale-[0.98] flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {dosingLoading ? (
                <span className="animate-pulse">Saving System Setup...</span>
              ) : (
                <>
                  <Save className="w-5 h-5 mr-2" />
                  Save System & Dosing Specs
                </>
              )}
            </button>
          </form>

          {/* SECTION 2: EMAIL ALERTS */}
          <form onSubmit={handleSaveEmailConfig} className="bg-slate-900/50 rounded-xl p-6 border border-slate-800 shadow-lg space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div className="flex items-center">
                <Mail className="w-6 h-6 text-emerald-400 mr-3" />
                <div>
                  <h2 className="text-xl font-semibold text-white">Email Alerts & Notifications</h2>
                  <p className="text-xs text-slate-400">Configure SMTP credentials and alert distribution lists</p>
                </div>
              </div>
            </div>

            <div className="space-y-5">
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
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 pl-10 pr-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none transition-all"
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
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 pl-10 pr-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none transition-all"
                    placeholder="Enter new App Password to update"
                  />
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Leave blank to keep existing password.
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
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2.5 pl-10 pr-4 text-white focus:ring-2 focus:ring-emerald-500 outline-none transition-all"
                    placeholder="user1@mail.com, user2@mail.com"
                  />
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Separate multiple emails with commas.
                </p>
              </div>
            </div>

            {/* Email Status Banner */}
            {emailStatus.message && (
              <div className={`p-4 rounded-lg text-sm font-medium ${
                emailStatus.type === 'success' 
                  ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30' 
                  : 'bg-rose-500/10 text-rose-300 border border-rose-500/30'
              }`}>
                {emailStatus.message}
              </div>
            )}

            <button
              type="submit"
              disabled={emailLoading}
              className="w-full bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold py-3.5 rounded-xl shadow-lg shadow-emerald-950/40 transition-all transform active:scale-[0.98] flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {emailLoading ? (
                <span className="animate-pulse">Saving Email Settings...</span>
              ) : (
                <>
                  <Save className="w-5 h-5 mr-2" />
                  Save Email Settings
                </>
              )}
            </button>
          </form>

          {/* SECTION 3: SYSTEM ACTIONS */}
          <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800 shadow-lg space-y-4">
            <div className="flex items-center pb-4 border-b border-slate-800">
              <Mail className="w-6 h-6 text-indigo-400 mr-3" />
              <div>
                <h2 className="text-xl font-semibold text-white">Manual Diagnostic Actions</h2>
                <p className="text-xs text-slate-400">Trigger manual email reports and system health checks</p>
              </div>
            </div>

            <button
              onClick={handleSendReport}
              disabled={isSendingReport}
              className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold py-3 rounded-xl shadow-lg shadow-indigo-950/40 transition-all transform active:scale-[0.98] flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSendingReport ? (
                <span className="animate-pulse">Sending Report Email...</span>
              ) : (
                <>
                  <Mail className="w-5 h-5 mr-2" />
                  Send Instant Daily Report Email
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;