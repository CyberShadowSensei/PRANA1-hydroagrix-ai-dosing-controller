import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import {BrowserRouter} from 'react-router-dom'
import axios from 'axios';

// HARDCODE YOUR RETERMINAL IP HERE
// If you are accessing from your laptop, use the ReTerminal's IP (e.g., 192.168.150.100)
// Or use this dynamic line which works from anywhere:
axios.defaults.baseURL = `http://${window.location.hostname}:5000`;

console.log("FIX APPLIED: Axios Base URL set to:", axios.defaults.baseURL);


ReactDOM.createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
)
