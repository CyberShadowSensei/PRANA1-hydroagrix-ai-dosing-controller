import { io } from 'socket.io-client';
import axios from 'axios';

// Ensure the socket connects to the backend API server
const socketUrl = axios.defaults.baseURL || `http://${window.location.hostname}:5000`;

// Create a SINGLETON socket connection to prevent connection flooding on the backend
const socket = io(socketUrl, {
  transports: ['polling', 'websocket']
});

export default socket;
