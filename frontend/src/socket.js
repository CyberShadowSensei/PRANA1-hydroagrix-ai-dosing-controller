/**
 * Socket.IO Singleton Client
 * Configures WebSocket streaming with auto-reconnection and exponential backoff.
 */
import { io } from 'socket.io-client';
import axios from 'axios';

// Ensure the socket connects to the backend API server
const socketUrl = axios.defaults.baseURL || `http://${window.location.hostname}:5000`;

// Create a SINGLETON socket connection with resilient reconnection parameters
const socket = io(socketUrl, {
  transports: ['polling', 'websocket'],
  reconnection: true,
  reconnectionAttempts: Infinity,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  timeout: 20000,
  autoConnect: true
});

export default socket;
