"""Serial port management service for ESP32 devices."""
import serial
import serial.tools.list_ports
import threading
import time
import json
import os
from datetime import datetime, date
from collections import deque
from log_summary_service import log_summary_service

HISTORY_FOLDER = os.path.join(os.path.dirname(__file__), 'serial_history')
SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'sessions.json')

# USB profile for ESP32 devices (CP2102)
ESP32_USB_PROFILES = [
    'CP2102',
    'CP210x',
    'USB to UART',
    'Silicon Labs',
]

class SerialService:
    def __init__(self):
        self.connections = {}  # port -> serial connection
        self.messages = deque(maxlen=1000)  # Store last 1000 messages
        self.running = {}  # port -> bool
        self.threads = {}  # port -> thread
        self.lock = threading.Lock()
        self.baud_rate = 115200
        self.device_data = {}  # port -> parsed device data
        self.mac_to_port = {}  # mac -> current port
        self.sessions = {}  # mac -> list of sessions
        self.current_sessions = {}  # mac -> current session data
        self.last_uptime = {}  # mac -> last known uptime
        self.known_ports = set()  # Track known ports for change detection
        self.monitor_thread = None
        self.monitor_running = False
        self.settings_fetched = set()  # Track MACs that have had export command sent
        
        # Ensure history folder exists
        os.makedirs(HISTORY_FOLDER, exist_ok=True)
        
        # Load existing sessions
        self._load_sessions()
        
        # Start USB monitor and auto-connect
        self._start_usb_monitor()
    
    def _is_esp32_device(self, port_info):
        """Check if a port matches ESP32 USB profile (CP2102)."""
        description = port_info.description or ''
        for profile in ESP32_USB_PROFILES:
            if profile.lower() in description.lower():
                return True
        return False
    
    def _start_usb_monitor(self):
        """Start background thread to monitor USB changes and auto-connect."""
        self.monitor_running = True
        self.monitor_thread = threading.Thread(target=self._usb_monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        # Initial auto-connect
        self._auto_connect_esp32_devices()
    
    def _usb_monitor_loop(self):
        """Monitor for USB device changes."""
        while self.monitor_running:
            try:
                current_ports = set(p.device for p in serial.tools.list_ports.comports())
                
                # Check for changes
                if current_ports != self.known_ports:
                    added = current_ports - self.known_ports
                    removed = self.known_ports - current_ports
                    
                    # Handle removed devices
                    for port in removed:
                        if port in self.connections:
                            self.disconnect(port)
                    
                    # Auto-connect new ESP32 devices
                    if added:
                        self._auto_connect_esp32_devices()
                    
                    self.known_ports = current_ports
                
                time.sleep(2)  # Check every 2 seconds
            except Exception:
                time.sleep(5)
    
    def _auto_connect_esp32_devices(self):
        """Auto-connect to all ESP32 devices (CP2102)."""
        ports = serial.tools.list_ports.comports()
        for port_info in ports:
            if self._is_esp32_device(port_info):
                if port_info.device not in self.connections:
                    result = self.connect(port_info.device)
                    if result.get('success'):
                        with self.lock:
                            self.messages.append({
                                'timestamp': datetime.now().isoformat(),
                                'port': port_info.device,
                                'message': f'[AUTO] Connected to {port_info.description}',
                                'type': 'system'
                            })
    
    def _load_sessions(self):
        """Load sessions from file."""
        if os.path.exists(SESSIONS_FILE):
            try:
                with open(SESSIONS_FILE, 'r') as f:
                    self.sessions = json.load(f)
            except:
                self.sessions = {}
    
    def _save_sessions(self):
        """Save sessions to file."""
        try:
            with open(SESSIONS_FILE, 'w') as f:
                json.dump(self.sessions, f, indent=2)
        except:
            pass
    
    def _save_history_message(self, mac, timestamp, port, message, msg_type):
        """Save a message to the daily history file for a device."""
        if not mac:
            return
        
        today = date.today().isoformat()
        device_folder = os.path.join(HISTORY_FOLDER, mac)
        os.makedirs(device_folder, exist_ok=True)
        
        history_file = os.path.join(device_folder, f'{today}.jsonl')
        
        entry = {
            'ts': timestamp,
            'port': port,
            'msg': message,
            'type': msg_type
        }
        
        try:
            with open(history_file, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except:
            pass
    
    def _check_session(self, mac, uptime, port):
        """Check if a new session has started based on uptime."""
        # Session tracking is now handled by log_summary_service
        # This method is kept for backward compatibility but does minimal work
        if not mac:
            return
        
        self.last_uptime[mac] = uptime
    
    def _end_session(self, mac):
        """End the current session for a device."""
        if mac not in self.current_sessions:
            return
        
        session = self.current_sessions[mac]
        session['end'] = datetime.now().isoformat()
        
        # Add to sessions list
        if mac not in self.sessions:
            self.sessions[mac] = []
        self.sessions[mac].insert(0, session)  # Most recent first
        
        # Keep only last 100 sessions per device
        self.sessions[mac] = self.sessions[mac][:100]
        
        self._save_sessions()
        del self.current_sessions[mac]
    
    def _log_error_to_session(self, mac, error_type, message):
        """Log an error or warning to the current session."""
        if mac not in self.current_sessions:
            return
        
        entry = {
            'time': datetime.now().isoformat(),
            'message': message[:200]  # Truncate long messages
        }
        
        if error_type == 'error' or error_type == 'fatal':
            self.current_sessions[mac]['errors'].append(entry)
            self.current_sessions[mac]['errors'] = self.current_sessions[mac]['errors'][-50:]
        elif error_type == 'warning':
            self.current_sessions[mac]['warnings'].append(entry)
            self.current_sessions[mac]['warnings'] = self.current_sessions[mac]['warnings'][-50:]
    
    def get_serial_devices(self):
        """Get list of available serial ports (ESP32 devices)."""
        ports = serial.tools.list_ports.comports()
        devices = []
        for port in ports:
            devices.append({
                'port': port.device,
                'description': port.description,
                'hwid': port.hwid,
                'vid': port.vid,
                'pid': port.pid,
                'connected': port.device in self.connections
            })
        return devices
    
    def connect(self, port):
        """Connect to a serial port."""
        if port in self.connections:
            return {'success': True, 'message': 'Already connected'}
        
        try:
            ser = serial.Serial(port, self.baud_rate, timeout=0.1)
            self.connections[port] = ser
            self.running[port] = True
            
            # Start reader thread
            thread = threading.Thread(target=self._read_loop, args=(port,), daemon=True)
            self.threads[port] = thread
            thread.start()
            
            return {'success': True, 'message': f'Connected to {port}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def disconnect(self, port):
        """Disconnect from a serial port."""
        if port not in self.connections:
            return {'success': False, 'message': 'Not connected'}
        
        self.running[port] = False
        time.sleep(0.2)  # Wait for thread to stop
        
        # Close session for this port
        log_summary_service.close_port_session(port)
        
        try:
            self.connections[port].close()
        except:
            pass
        
        del self.connections[port]
        if port in self.threads:
            del self.threads[port]
        if port in self.running:
            del self.running[port]
        
        return {'success': True, 'message': f'Disconnected from {port}'}
    
    def disconnect_all(self):
        """Disconnect all serial ports."""
        ports = list(self.connections.keys())
        for port in ports:
            self.disconnect(port)
        return {'success': True}
    
    def send_message(self, message, ports=None):
        """Send a message to specified ports or all connected ports."""
        if ports is None:
            ports = list(self.connections.keys())
        
        results = []
        for port in ports:
            if port in self.connections:
                try:
                    data = (message + '\n').encode('utf-8')
                    self.connections[port].write(data)
                    results.append({'port': port, 'success': True})
                    
                    timestamp = datetime.now().isoformat()
                    # Log sent message
                    with self.lock:
                        self.messages.append({
                            'timestamp': timestamp,
                            'port': port,
                            'message': f'>> {message}',
                            'type': 'sent'
                        })
                    
                    # Save to history
                    mac = self.device_data.get(port, {}).get('mac', '')
                    self._save_history_message(mac, timestamp, port, f'>> {message}', 'sent')
                    
                    # Process message for log summary (session tracking)
                    # Pass port and mac to track sessions by port
                    log_summary_service.process_message(port, mac, timestamp, f'>> {message}', 'sent')
                    
                except Exception as e:
                    results.append({'port': port, 'success': False, 'error': str(e)})
        
        return results
    
    def get_messages(self, since=None):
        """Get messages, optionally filtered by timestamp."""
        with self.lock:
            if since:
                return [m for m in self.messages if m['timestamp'] > since]
            return list(self.messages)
    
    def clear_messages(self):
        """Clear all messages."""
        with self.lock:
            self.messages.clear()
        return {'success': True}
    
    def get_connected_ports(self):
        """Get list of connected ports."""
        return list(self.connections.keys())
    
    def get_port_for_mac(self, mac):
        """Get the current serial port for a given MAC address."""
        return self.mac_to_port.get(mac)
    
    def send_commands_to_mac(self, mac, commands):
        """
        Send a list of CLI commands to the device identified by MAC.
        
        Returns a dict with success flag and per-command results.
        """
        port = self.get_port_for_mac(mac)
        if not port or port not in self.connections:
            return {'success': False, 'error': f'Device {mac} not connected or port unknown.'}
        
        results = []
        all_success = True
        for cmd in commands:
            res = self.send_message(cmd, ports=[port])
            if res and res[0].get('success'):
                results.append({'command': cmd, 'success': True})
            else:
                all_success = False
                results.append({'command': cmd, 'success': False, 'error': res[0].get('error', 'Unknown error') if res else 'No response'})
        return {'success': all_success, 'results': results, 'port': port}
    
    def get_device_data(self):
        """Get parsed device data keyed by MAC address."""
        with self.lock:
            result = {}
            for port, data in self.device_data.items():
                mac = data.get('mac', '')
                if mac:
                    result[mac] = {**data, 'port': port}
                    
                    # Structure health data from flat device data
                    health = {
                        # Storage
                        'st': data.get('storage_mode', ''),
                        'sd': data.get('sd_available', False),
                        'su': data.get('storage_util', None),
                        
                        # Session statistics
                        'ec': data.get('error_count', 0),
                        'td': data.get('total_duration', 0),
                        'lr': data.get('last_recording', 0),
                        
                        # Upload statistics
                        'tu': data.get('total_uploads', 0),
                        'ta': data.get('total_attempts', 0),
                        'ur': data.get('upload_rate', None),
                        'lu': data.get('last_upload', 0),
                        
                        # Event statistics
                        'ev': data.get('event_count', 0),
                        'le': data.get('last_event', 0),
                        
                        # Health counts
                        'wc': data.get('warning_count', 0),
                        'fc': data.get('fatal_count', 0),
                        
                        # Memory
                        'ht': data.get('heap_total', ''),
                        'hf': data.get('heap_free', ''),
                        'pt': data.get('psram_total', ''),
                        'pu': data.get('psram_used', ''),
                        
                        # System
                        'tm': data.get('time_valid', False),
                        'wi': data.get('wifi', False),
                        'ip': data.get('ip', ''),
                        'ri': data.get('rssi', 0),
                        'ut': data.get('uptime', 0),
                        
                        # Yearly summary
                        'yr': data.get('year'),
                        'yf': data.get('year_files'),
                        'ys': data.get('year_size'),
                        'yh': data.get('year_hours'),
                    }
                    result[mac]['health'] = health
                    
                    # Parse storage information from health data
                    storage_util = data.get('storage_util')
                    if storage_util is not None and isinstance(storage_util, (int, float)):
                        result[mac]['storage_percent'] = storage_util
                    
                    # Include current session info from log summary service
                    current_session = log_summary_service.get_current_session(mac)
                    if current_session:
                        # Convert to expected format
                        result[mac]['current_session'] = {
                            'start': current_session.get('start'),
                            'end': current_session.get('end'),
                            'recordings': current_session.get('recordings', 0),
                            'uploaded': current_session.get('uploads', 0),
                            'uptime': current_session.get('uptime', 0),
                            'recordings_duration': current_session.get('recordings_duration', 0),
                            'session_id': current_session.get('session_id'),
                            'reset_reason': current_session.get('reset_reason'),
                            'firmware': current_session.get('firmware')
                        }
                        # Use firmware from current session if device firmware is not set
                        if not result[mac].get('firmware') and current_session.get('firmware'):
                            result[mac]['firmware'] = current_session.get('firmware')
                    
                    # Get last reboot reason from init_message or current_session
                    if data.get('init_message') and data['init_message'].get('reset_reason'):
                        result[mac]['last_reboot_reason'] = data['init_message']['reset_reason']
                    elif current_session and current_session.get('reset_reason'):
                        result[mac]['last_reboot_reason'] = current_session.get('reset_reason')
                    
                    # Include recent sessions (first 5) from log summary
                    all_sessions = log_summary_service.get_sessions(mac)
                    if all_sessions:
                        # Convert to expected format
                        result[mac]['sessions'] = [
                            {
                                'start': s.get('start'),
                                'end': s.get('end'),
                                'recordings': s.get('recordings', 0),
                                'uploaded': s.get('uploads', 0),
                                'uptime': s.get('uptime', 0),
                                'recordings_duration': s.get('recordings_duration', 0)
                            }
                            for s in all_sessions[:5]
                        ]
                        result[mac]['total_sessions'] = len(all_sessions)
                else:
                    result[port] = {**data, 'port': port}
            return result
    
    def get_sessions(self, mac, page=0, per_page=10):
        """Get paginated sessions for a device."""
        # Get sessions from log summary service
        all_sessions = log_summary_service.get_sessions(mac)
        
        if not all_sessions:
            return {'sessions': [], 'total': 0, 'page': page, 'per_page': per_page, 'current_session': None}
        
        # Convert to expected format
        formatted_sessions = [
            {
                'start': s.get('start'),
                'end': s.get('end'),
                'recordings': s.get('recordings', 0),
                'uploaded': s.get('uploads', 0),
                'uptime': s.get('uptime', 0),
                'recordings_duration': s.get('recordings_duration', 0)
            }
            for s in all_sessions
        ]
        
        start = page * per_page
        end = start + per_page
        
        # Get current session
        current_session = log_summary_service.get_current_session(mac)
        formatted_current = None
        if current_session:
            formatted_current = {
                'start': current_session.get('start'),
                'end': current_session.get('end'),
                'recordings': current_session.get('recordings', 0),
                'uploaded': current_session.get('uploads', 0),
                'uptime': current_session.get('uptime', 0),
                'recordings_duration': current_session.get('recordings_duration', 0),
                'session_id': current_session.get('session_id')
            }
        
        return {
            'sessions': formatted_sessions[start:end],
            'total': len(formatted_sessions),
            'page': page,
            'per_page': per_page,
            'current_session': formatted_current
        }
    
    def get_history_dates(self, mac):
        """Get list of dates with history for a device."""
        device_folder = os.path.join(HISTORY_FOLDER, mac)
        if not os.path.exists(device_folder):
            return []
        
        dates = []
        for f in os.listdir(device_folder):
            if f.endswith('.jsonl'):
                dates.append(f.replace('.jsonl', ''))
        
        return sorted(dates, reverse=True)
    
    def get_history(self, mac, date_str, offset=0, limit=500):
        """Get history messages for a device on a specific date."""
        history_file = os.path.join(HISTORY_FOLDER, mac, f'{date_str}.jsonl')
        if not os.path.exists(history_file):
            return {'messages': [], 'total': 0}
        
        messages = []
        try:
            with open(history_file, 'r') as f:
                for line in f:
                    try:
                        messages.append(json.loads(line.strip()))
                    except:
                        pass
        except:
            pass
        
        total = len(messages)
        # If limit is None or 0, return all messages
        if limit is None or limit == 0:
            messages = messages[offset:]
        else:
            messages = messages[offset:offset + limit]
        
        return {'messages': messages, 'total': total, 'offset': offset, 'limit': limit}
    
    def get_history_multiple_devices(self, macs, date_str, offset=0, limit=None):
        """Get history messages from multiple devices on a specific date."""
        all_messages = []
        for mac in macs:
            history_file = os.path.join(HISTORY_FOLDER, mac, f'{date_str}.jsonl')
            if not os.path.exists(history_file):
                continue
            
            messages = []
            try:
                with open(history_file, 'r') as f:
                    for line in f:
                        try:
                            msg = json.loads(line.strip())
                            # Add device MAC to message for identification
                            msg['device_mac'] = mac
                            messages.append(msg)
                        except:
                            pass
            except:
                pass
            
            all_messages.extend(messages)
        
        # Sort by timestamp
        all_messages.sort(key=lambda x: x.get('ts', ''))
        
        total = len(all_messages)
        # If limit is None or 0, return all messages
        if limit is None or limit == 0:
            messages = all_messages[offset:]
        else:
            messages = all_messages[offset:offset + limit]
        
        return {'messages': messages, 'total': total, 'offset': offset, 'limit': limit}
    
    def get_all_devices_with_history(self):
        """Get list of all devices that have history."""
        if not os.path.exists(HISTORY_FOLDER):
            return []
        
        devices = []
        for mac in os.listdir(HISTORY_FOLDER):
            mac_folder = os.path.join(HISTORY_FOLDER, mac)
            if os.path.isdir(mac_folder):
                dates = self.get_history_dates(mac)
                devices.append({
                    'mac': mac,
                    'dates': dates[:10],  # Last 10 dates
                    'total_dates': len(dates)
                })
        
        return devices
    
    def _parse_json_message(self, port, line):
        """Parse JSON messages and update device data."""
        try:
            # Only process lines that look like JSON (start with {)
            if not line or not line.strip().startswith('{'):
                return
            
            # Try to find the first complete JSON object in the line
            # Handle cases where multiple JSON objects might be concatenated
            line = line.strip()
            
            # If line doesn't start with {, skip it
            if not line.startswith('{'):
                return
            
            # Try to parse as single JSON object first
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                # If that fails, try to find the first complete JSON object
                # Look for matching braces
                brace_count = 0
                json_start = -1
                json_end = -1
                
                for i, char in enumerate(line):
                    if char == '{':
                        if brace_count == 0:
                            json_start = i
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0 and json_start >= 0:
                            json_end = i + 1
                            break
                
                if json_start >= 0 and json_end > json_start:
                    # Extract the first complete JSON object
                    json_str = line[json_start:json_end]
                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError:
                        # If still can't parse, skip this line
                        return
                else:
                    # No complete JSON object found, skip
                    return
            
            msg_type = data.get('ty')
            
            if port not in self.device_data:
                self.device_data[port] = {
                    'mac': '',
                    'wifi': False,
                    'ip': '',
                    'rssi': 0,
                    'recording': False,
                    'uploading': False,
                    'queue': 0,
                    'uptime': 0,
                    'current_db': 0,
                    'min_db': 0,
                    'max_db': 0,
                    'dynamic_range': 0,
                    'total_recordings': 0,
                    'total_uploaded': 0,
                    'total_duration': 0,
                    'storage_mode': '',
                    'storage_size': '',
                    'storage_used': '',
                    'storage_percent': None,
                    'sd_available': False,
                    'recording_count': 0,
                    'uploaded_count': 0,
                    'error_count': 0,
                    'pending_queue': 0,
                    'last_recording': 0,
                    'total_uploads': 0,
                    'total_attempts': 0,
                    'upload_rate': None,
                    'last_upload': 0,
                    'event_count': 0,
                    'last_event': 0,
                    'warning_count': 0,
                    'fatal_count': 0,
                    'heap_total': '',
                    'heap_free': '',
                    'time_valid': False,
                    'storage_util': None,
                    'year': None,
                    'year_files': 0,
                    'year_size': '',
                    'year_hours': 0,
                    'year_months': 0,
                    'year_days': 0,
                    'init_message': None,
                    'last_update': None,
                    'config': {},
                    'health': {}
                }
            
            dev = self.device_data[port]
            dev['last_update'] = datetime.now().isoformat()
            
            if msg_type == 'short':
                mac = data.get('mc', dev['mac'])
                # Normalize MAC address (remove colons/dashes, uppercase)
                if mac:
                    mac = mac.replace(':', '').replace('-', '').upper()
                dev['mac'] = mac
                dev['wifi'] = data.get('wi', dev['wifi'])
                dev['ip'] = data.get('ip', dev['ip'])
                dev['rssi'] = data.get('ri', dev['rssi'])
                dev['recording'] = data.get('rg', dev['recording'])
                dev['uploading'] = data.get('ug', dev['uploading'])
                dev['queue'] = data.get('qe', dev.get('queue', 0))  # Note: 'qe' is queue in short messages
                uptime = data.get('ut', dev['uptime'])
                dev['uptime'] = uptime
                dev['current_db'] = data.get('cd', dev['current_db'])
                dev['min_db'] = data.get('mi', dev.get('min_db', 0))
                dev['max_db'] = data.get('mx', dev.get('max_db', 0))
                dev['dynamic_range'] = data.get('dr', dev.get('dynamic_range', 0))
                
                # Track MAC to port mapping
                if mac:
                    self.mac_to_port[mac] = port
                    # Check for new session
                    self._check_session(mac, uptime, port)
                    # Auto-fetch settings on first connection (if not already fetched)
                    if mac not in self.settings_fetched:
                        self.settings_fetched.add(mac)
                        # Send export command after a short delay to let device initialize
                        threading.Thread(target=self._delayed_export, args=(port,), daemon=True).start()
            
            elif msg_type == 'health':
                # Capture MAC and session ID from health message
                mac = data.get('mc', dev['mac'])
                if mac:
                    mac = mac.replace(':', '').replace('-', '').upper()
                dev['mac'] = mac
                
                # Capture all health fields according to documentation
                dev['storage_mode'] = data.get('st', dev.get('storage_mode', ''))
                dev['sd_available'] = data.get('sd', dev.get('sd_available', False))
                
                # Session statistics
                dev['recording_count'] = data.get('rc', dev.get('recording_count', 0))
                dev['uploaded_count'] = data.get('uc', dev.get('uploaded_count', 0))
                dev['error_count'] = data.get('ec', dev.get('error_count', 0))
                dev['pending_queue'] = data.get('pq', dev.get('pending_queue', 0))
                dev['total_duration'] = data.get('td', dev.get('total_duration', 0))
                dev['last_recording'] = data.get('lr', dev.get('last_recording', 0))
                
                # Lifetime upload statistics
                dev['total_uploads'] = data.get('tu', dev.get('total_uploads', 0))
                dev['total_attempts'] = data.get('ta', dev.get('total_attempts', 0))
                dev['upload_rate'] = data.get('ur', dev.get('upload_rate', None))
                dev['last_upload'] = data.get('lu', dev.get('last_upload', 0))
                
                # Event statistics
                dev['event_count'] = data.get('ev', dev.get('event_count', 0))
                dev['last_event'] = data.get('le', dev.get('last_event', 0))
                
                # Warning and fatal counts
                dev['warning_count'] = data.get('wc', dev.get('warning_count', 0))
                dev['fatal_count'] = data.get('fc', dev.get('fatal_count', 0))
                
                # Memory information
                dev['heap_total'] = data.get('ht', dev.get('heap_total', ''))
                dev['heap_free'] = data.get('hf', dev.get('heap_free', ''))
                dev['psram_total'] = data.get('pt', dev.get('psram_total', ''))
                dev['psram_used'] = data.get('pu', dev.get('psram_used', ''))
                
                # System status
                dev['time_valid'] = data.get('tm', dev.get('time_valid', False))
                dev['storage_util'] = data.get('su', dev.get('storage_util', None))
                
                # WiFi information
                dev['wifi'] = data.get('wi', dev.get('wifi', False))
                dev['ip'] = data.get('ip', dev.get('ip', ''))
                dev['rssi'] = data.get('ri', dev.get('rssi', 0))
                
                # Uptime
                uptime = data.get('ut', dev.get('uptime', 0))
                dev['uptime'] = uptime
                
                # Yearly summary metrics (if present)
                if 'yr' in data:
                    dev['year'] = data.get('yr')
                    dev['year_files'] = data.get('yf', 0)
                    dev['year_size'] = data.get('ys', '')
                    dev['year_hours'] = data.get('yh', 0)
                    dev['year_months'] = data.get('ym', 0)
                    dev['year_days'] = data.get('yd', 0)
                
                # Store full health data
                dev['health'] = data
                
                # Track MAC to port mapping
                if mac:
                    self.mac_to_port[mac] = port
                    # Check for new session
                    self._check_session(mac, uptime, port)
            
            elif msg_type == 'config':
                mac = data.get('mc', dev['mac'])
                # Normalize MAC address (remove colons/dashes, uppercase)
                if mac:
                    mac = mac.replace(':', '').replace('-', '').upper()
                dev['mac'] = mac
                
                # Store full config data
                dev['config'] = data
                
                # Also extract individual config fields for easy access
                dev['firmware'] = data.get('fw', dev.get('firmware', ''))
                dev['host'] = data.get('ho', dev.get('host', ''))
                dev['port'] = data.get('po', dev.get('port', 0))
                dev['ssid'] = data.get('ss', dev.get('ssid', ''))
                dev['static_ip_enabled'] = data.get('sie', dev.get('static_ip_enabled', False))
                dev['rtc_enabled'] = data.get('rte', dev.get('rtc_enabled', False))
                dev['use_sd_card'] = data.get('usc', dev.get('use_sd_card', False))
                dev['record_to_sd_card'] = data.get('rsc', dev.get('record_to_sd_card', False))
                dev['offset_hours'] = data.get('oh', dev.get('offset_hours', 0))
                dev['wifi_tx_power'] = data.get('wtp', dev.get('wifi_tx_power', 5))
                dev['sensitivity'] = data.get('se', dev.get('sensitivity', 0))
                dev['min_recording'] = data.get('mi', dev.get('min_recording', 0))
                dev['max_recording'] = data.get('mx', dev.get('max_recording', 0))
                dev['silence_threshold'] = data.get('sth', dev.get('silence_threshold', 0))
                dev['pre_record'] = data.get('pr', dev.get('pre_record', 0))
                dev['gain'] = data.get('gn', dev.get('gain', 0.0))
                dev['sample_rate'] = data.get('is', dev.get('sample_rate', 0))
                
                if mac:
                    self.mac_to_port[mac] = port
                    # Auto-fetch settings on first connection (if not already fetched)
                    if mac not in self.settings_fetched:
                        self.settings_fetched.add(mac)
                        # Send export command after a short delay to let device initialize
                        threading.Thread(target=self._delayed_export, args=(port,), daemon=True).start()
            
            # Full configuration export (no "ty" field, but structured settings JSON)
            # Device uses abbreviated keys: 'a' (audio), 'w' (wifi), 'u' (upload)
            elif msg_type is None and isinstance(data, dict) and (
                'a' in data or 'audio' in data or 
                'w' in data or 'wifi' in data or 
                'u' in data or 'upload' in data
            ):
                dev['full_config'] = data
                mac = data.get('mac') or dev.get('mac', '')
                # Normalize MAC address (remove colons/dashes, uppercase)
                if mac:
                    mac = mac.replace(':', '').replace('-', '').upper()
                if mac:
                    dev['mac'] = mac
                    self.mac_to_port[mac] = port
                return
            
            elif msg_type == 'log':
                # Handle log messages, especially INIT messages with reset reason
                mac = data.get('mc', dev.get('mac', ''))
                if mac:
                    mac = mac.replace(':', '').replace('-', '').upper()
                    dev['mac'] = mac
                    self.mac_to_port[mac] = port
                
                # Extract session ID from log message
                session_id = data.get('si')
                
                # Check for INIT message with reset reason
                message_text = data.get('ms', '')
                reset_reason = data.get('rr')
                
                if 'INIT' in message_text or reset_reason:
                    # This is an INIT message - mark as device startup
                    dev['init_message'] = {
                        'timestamp': datetime.now().isoformat(),
                        'message': message_text,
                        'reset_reason': reset_reason,
                        'session_id': session_id
                    }
                    # Process INIT message for session tracking
                    if mac:
                        log_summary_service.process_init_message(port, mac, datetime.now().isoformat(), message_text, reset_reason, session_id)
            
            elif msg_type in ('error', 'warning', 'fatal'):
                mac = dev.get('mac', '')
                if mac:
                    self._log_error_to_session(mac, msg_type, data.get('ms', ''))
                
        except json.JSONDecodeError:
            pass
        except Exception:
            pass
    
    def _read_loop(self, port):
        """Read loop for a serial port. Processes messages line by line, ensuring proper separation."""
        buffer = ''
        while self.running.get(port, False):
            try:
                if port not in self.connections:
                    break
                
                ser = self.connections[port]
                if ser.in_waiting:
                    # Read available data
                    data = ser.read(ser.in_waiting).decode('utf-8', errors='replace')
                    buffer += data
                    
                    # Process complete lines (ending with \n or \r\n)
                    lines = []
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        # Remove \r if present (handle \r\n or just \r)
                        line = line.rstrip('\r')
                        if line:  # Only process non-empty lines
                            lines.append(line)
                    
                    # Process all complete lines
                    for line in lines:
                        timestamp = datetime.now().isoformat()
                        with self.lock:
                            self.messages.append({
                                'timestamp': timestamp,
                                'port': port,
                                'message': line,
                                'type': 'received'
                            })
                        
                        # Parse JSON messages for device data
                        self._parse_json_message(port, line)
                        
                        # Save to history (after parsing so we have MAC)
                        mac = self.device_data.get(port, {}).get('mac', '')
                        self._save_history_message(mac, timestamp, port, line, 'received')
                        
                        # Process message for log summary (session tracking)
                        # Pass port and mac to track sessions by port
                        log_summary_service.process_message(port, mac, timestamp, line, 'received')
                    
                    # Limit buffer size to prevent memory issues (keep last 1KB of incomplete data)
                    if len(buffer) > 1024:
                        # If buffer is too large and no newline found, clear it to prevent issues
                        # This handles cases where device sends data without newlines
                        buffer = buffer[-512:]  # Keep last 512 chars
                else:
                    time.sleep(0.01)
            except Exception as e:
                timestamp = datetime.now().isoformat()
                with self.lock:
                    self.messages.append({
                        'timestamp': timestamp,
                        'port': port,
                        'message': f'[ERROR] {str(e)}',
                        'type': 'error'
                    })
                break
    
    def _delayed_export(self, port):
        """Send export command after a delay to fetch device settings."""
        time.sleep(1.0)  # Wait 1 second for device to be ready
        if port in self.connections and self.running.get(port, False):
            try:
                self.send_message('export', [port])
            except:
                pass

# Global instance
serial_service = SerialService()
