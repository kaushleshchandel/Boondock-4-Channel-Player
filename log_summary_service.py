"""Log summary service for tracking device sessions from serial logs."""
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime, date, timedelta

LOG_SUMMARY_FOLDER = os.path.join(os.path.dirname(__file__), 'log_summary')
SESSION_TIMEOUT_SECONDS = 300  # 5 minutes

class LogSummaryService:
    def __init__(self):
        """Initialize the log summary service."""
        os.makedirs(LOG_SUMMARY_FOLDER, exist_ok=True)
        # Track active sessions by port and session_id: (port, session_id) -> session dict
        self.active_sessions = {}  # (port, session_id) -> session dict
        # Track current active session per port: port -> (port, session_id) key
        self.port_active_session = {}  # port -> (port, session_id) key
        # Track active sessions by MAC and session_id to prevent duplicates: (mac, session_id) -> (port, session_id) key
        self.mac_session_lookup = {}  # (mac, session_id) -> (port, session_id) key
        # Track last message time per port for timeout detection
        self.last_message_time = {}  # port -> timestamp
        # Lock for thread safety
        self.lock = threading.Lock()
        # Start timeout checker thread
        self.timeout_checker_running = True
        self.timeout_thread = threading.Thread(target=self._check_timeouts, daemon=True)
        self.timeout_thread.start()
    
    def _get_summary_file_path(self, mac, date_str):
        """Get the path to the summary file for a device and date."""
        device_folder = os.path.join(LOG_SUMMARY_FOLDER, mac)
        os.makedirs(device_folder, exist_ok=True)
        return os.path.join(device_folder, f'{date_str}.json')
    
    def _load_summary(self, mac, date_str):
        """Load summary data for a device and date."""
        summary_file = self._get_summary_file_path(mac, date_str)
        if os.path.exists(summary_file):
            try:
                with open(summary_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            'device_mac': mac,
            'date': date_str,
            'sessions': []
        }
    
    def _save_summary(self, mac, date_str, summary_data):
        """Save summary data for a device and date."""
        summary_file = self._get_summary_file_path(mac, date_str)
        try:
            with open(summary_file, 'w') as f:
                json.dump(summary_data, f, indent=2)
        except Exception as e:
            print(f"Error saving summary: {e}")
    
    def _detect_reboot(self, message):
        """Detect if a message indicates a device reboot."""
        if not message:
            return False
        # Check for reboot pattern: rst:0xc (SW_CPU_RESET),boot:0x1f (SPI_FAST_FLASH_BOOT)
        return 'rst:0xc (SW_CPU_RESET),boot:0x1f (SPI_FAST_FLASH_BOOT)' in message
    
    def _detect_init_message(self, message):
        """Detect if a message is an INIT message (device startup)."""
        if not message:
            return False
        # Check for INIT message pattern: "INIT - Reset reason: ..."
        return 'INIT' in message and 'Reset reason' in message
    
    def process_init_message(self, port, mac, timestamp, message, reset_reason=None, session_id=None):
        """Process an INIT message to mark session start with reset reason."""
        if not port or not mac:
            return
        
        # Normalize MAC address
        mac = mac.replace(':', '').replace('-', '').upper()
        
        # Extract session ID from message if not provided
        if not session_id:
            session_id = self._extract_session_id_from_message(message)
        
        # If we have a session_id, ensure we create/update a session with reset reason
        if session_id:
            session_key = (port, session_id)
            
            with self.lock:
                # Get date from timestamp
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    date_str = dt.date().isoformat()
                except:
                    date_str = date.today().isoformat()
                
                # Check if session exists
                if session_key in self.active_sessions:
                    session = self.active_sessions[session_key]
                    # Update session with INIT info
                    session['reset_reason'] = reset_reason
                    session['init_message'] = message
                    session['start'] = timestamp  # Update start time to INIT time
                    session['mac'] = mac
                else:
                    # Create new session with INIT info
                    session = {
                        'start': timestamp,
                        'end': timestamp,
                        'uptime': 0,
                        'recordings': 0,
                        'recordings_duration': 0,
                        'uploads': 0,
                        'firmware': None,
                        'session_id': session_id,
                        'port': port,
                        'mac': mac,
                        'is_active': True,
                        'reset_reason': reset_reason,
                        'init_message': message
                    }
                    self.active_sessions[session_key] = session
                    self.port_active_session[port] = session_key
                    
                    # Add to MAC lookup
                    mac_session_key = (mac, session_id)
                    self.mac_session_lookup[mac_session_key] = session_key
                
                # Update last message time
                self.last_message_time[port] = timestamp
                
                # Save summary
                summary = self._load_summary(mac, date_str)
                self._save_summary(mac, date_str, summary)
    
    def _detect_recording_start(self, message):
        """Detect if a message indicates recording started."""
        if not message:
            return False
        # Check for: [Record] 🔴 Start Audio recording
        return '[Record]' in message and '🔴' in message and 'Start Audio recording' in message
    
    def _detect_recording_stop(self, message):
        """Detect if a message indicates recording stopped."""
        if not message:
            return False
        # Check for: [Record] ⏹️ Stop recording
        return '[Record]' in message and '⏹️' in message and 'Stop recording' in message
    
    def _extract_recording_duration(self, message):
        """Extract recording duration in milliseconds from stop message."""
        if not message:
            return 0
        # Pattern: Duration = 4544 ms
        match = re.search(r'Duration\s*=\s*(\d+)\s*ms', message)
        if match:
            try:
                return int(match.group(1))
            except:
                pass
        return 0
    
    def _detect_upload(self, message):
        """Detect if a message indicates a file upload."""
        if not message:
            return False
        # Check for: [Upload] ✅ Sent
        return '[Upload]' in message and '✅' in message and 'Sent' in message
    
    def _extract_uptime_from_json(self, json_data):
        """Extract uptime from a JSON message (short type)."""
        if isinstance(json_data, dict):
            return json_data.get('ut', 0)
        return 0
    
    def _extract_session_id(self, json_data):
        """Extract session ID from a JSON message."""
        if isinstance(json_data, dict):
            si = json_data.get('si')
            if si:
                return str(si)  # Convert to string for consistency
        return None
    
    def _extract_session_id_from_message(self, message):
        """Extract session ID from message string (handles nested JSON)."""
        # Try to parse as JSON first
        json_data = self._parse_message_content(message)
        if json_data:
            si = self._extract_session_id(json_data)
            if si:
                return si
        
        # Try regex pattern for nested JSON: {"ty":"...","si":"123",...} or {"ty":"...","si":123,...}
        # Handle both string and numeric session IDs
        si_match = re.search(r'"si"\s*:\s*(?:"(\d+)"|(\d+))', message)
        if si_match:
            return si_match.group(1) or si_match.group(2)
        
        return None
    
    def _session_id_matches(self, message, expected_session_id):
        """Check if message contains the expected session ID."""
        if not expected_session_id:
            return True  # If no expected ID, match all
        
        message_session_id = self._extract_session_id_from_message(message)
        return message_session_id == expected_session_id
    
    def _parse_message_content(self, message):
        """Parse message content to extract JSON if present."""
        if not message:
            return None
        
        # Try to parse as JSON
        try:
            return json.loads(message)
        except:
            pass
        
        # Try to find JSON object in message (handle nested JSON)
        # Look for complete JSON objects
        brace_count = 0
        json_start = -1
        for i, char in enumerate(message):
            if char == '{':
                if brace_count == 0:
                    json_start = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0 and json_start >= 0:
                    json_str = message[json_start:i+1]
                    try:
                        return json.loads(json_str)
                    except:
                        pass
        
        # Try simple regex for JSON with "ty" field
        json_match = re.search(r'\{[^{}]*"ty"[^{}]*\}', message)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass
        
        return None
    
    def _check_timeouts(self):
        """Background thread to check for session timeouts."""
        while self.timeout_checker_running:
            try:
                current_time = datetime.now()
                with self.lock:
                    ports_to_close = []
                    for port, last_time_str in list(self.last_message_time.items()):
                        try:
                            last_time = datetime.fromisoformat(last_time_str.replace('Z', '+00:00'))
                            time_diff = (current_time - last_time).total_seconds()
                            if time_diff > SESSION_TIMEOUT_SECONDS:
                                ports_to_close.append(port)
                        except:
                            pass
                    
                    # Close timed-out sessions
                    for port in ports_to_close:
                        self._close_port_session(port, current_time.isoformat())
                        self.last_message_time.pop(port, None)
                
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                print(f"Error in timeout checker: {e}")
                time.sleep(60)
    
    def _close_port_session(self, port, timestamp):
        """Close the active session for a port."""
        if port not in self.port_active_session:
            return
        
        session_key = self.port_active_session[port]
        if session_key in self.active_sessions:
            session = self.active_sessions[session_key]
            session['end'] = timestamp
            session['is_active'] = False
            
            # Get MAC and session_id from session
            mac = session.get('mac', '')
            session_id = session.get('session_id')
            
            if mac:
                # Get date from timestamp
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    date_str = dt.date().isoformat()
                except:
                    date_str = date.today().isoformat()
                
                # Load and save summary
                summary = self._load_summary(mac, date_str)
                summary['sessions'].append(session)
                self._save_summary(mac, date_str, summary)
            
            # Remove from MAC lookup
            if mac and session_id:
                mac_session_key = (mac, session_id)
                if self.mac_session_lookup.get(mac_session_key) == session_key:
                    self.mac_session_lookup.pop(mac_session_key, None)
            
            # Remove from active sessions
            del self.active_sessions[session_key]
        
        # Remove from port mapping
        self.port_active_session.pop(port, None)
    
    def process_message(self, port, mac, timestamp, message, msg_type='received'):
        """Process a serial message and update session data.
        
        Sessions are determined by the serial message tag **si** (session ID). Each device
        sends si in messages (e.g. health, short, config, log). When si changes for a
        device (e.g. after reboot), that indicates a new session: the previous session
        is closed and persisted to Sessions history (log_summary/<mac>/<date>.json),
        and a new session is started for the new si.
        """
        if not port:
            return
        
        # Normalize MAC address
        if mac:
            mac = mac.replace(':', '').replace('-', '').upper()
        
        # Extract session ID (si) and MAC (mc) from message - these drive session identity
        session_id = None
        json_data = None
        if msg_type == 'received':
            json_data = self._parse_message_content(message)
            if json_data and isinstance(json_data, dict):
                session_id = self._extract_session_id(json_data)
                if not mac and json_data.get('mc'):
                    mac = (json_data.get('mc') or '').replace(':', '').replace('-', '').upper()
            if not session_id:
                session_id = self._extract_session_id_from_message(message)
        
        # Update last message time for timeout detection
        with self.lock:
            self.last_message_time[port] = timestamp
        
        # Get date from timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            date_str = dt.date().isoformat()
        except:
            date_str = date.today().isoformat()
        
        # Extract firmware from message if present
        firmware_from_message = None
        if msg_type == 'received':
            if not json_data:
                json_data = self._parse_message_content(message)
            if json_data and isinstance(json_data, dict):
                if json_data.get('ty') == 'config':
                    firmware_from_message = json_data.get('fw')
            if not firmware_from_message:
                firmware_match = re.search(r'\{"ty"\s*:\s*"config"[^}]*"fw"\s*:\s*"([^"]+)"', message)
                if firmware_match:
                    firmware_from_message = firmware_match.group(1)
        
        # If we have firmware but no si in this message, just update existing session if any
        if firmware_from_message and not session_id:
            with self.lock:
                if port in self.port_active_session:
                    session_key = self.port_active_session[port]
                    if session_key in self.active_sessions:
                        session = self.active_sessions[session_key]
                        session['firmware'] = firmware_from_message
                        session['end'] = timestamp
                        if mac:
                            session['mac'] = mac
                        if mac:
                            summary = self._load_summary(mac, date_str)
                            self._save_summary(mac, date_str, summary)
                        return
            return
        
        # No session ID in message: skip session tracking (si is required for session identity)
        if not session_id:
            return
        
        session_key = (port, session_id)
        
        with self.lock:
            # Session boundary: si changed = new device session. Close current session for this port if si differs.
            if port in self.port_active_session:
                current_key = self.port_active_session[port]
                if current_key != session_key and current_key in self.active_sessions:
                    old_session = self.active_sessions[current_key]
                    if old_session.get('session_id') != session_id:
                        old_session['end'] = timestamp
                        old_session['is_active'] = False
                        old_mac = old_session.get('mac', '')
                        if old_mac:
                            old_summary = self._load_summary(old_mac, date_str)
                            old_summary['sessions'].append(old_session)
                            self._save_summary(old_mac, date_str, old_summary)
                        if old_mac and old_session.get('session_id'):
                            old_mac_key = (old_mac, old_session['session_id'])
                            if self.mac_session_lookup.get(old_mac_key) == current_key:
                                self.mac_session_lookup.pop(old_mac_key, None)
                        del self.active_sessions[current_key]
                    self.port_active_session.pop(port, None)
            
            # First, check if a session with this MAC and session_id already exists
            # This prevents duplicate sessions for the same device and session ID
            existing_session_key = None
            if mac:
                mac_session_key = (mac, session_id)
                existing_session_key = self.mac_session_lookup.get(mac_session_key)
            
            # If we found an existing session for this MAC and session_id, use it
            if existing_session_key and existing_session_key in self.active_sessions:
                # Session exists for this MAC and session_id - update it instead of creating new one
                session = self.active_sessions[existing_session_key]
                session['end'] = timestamp  # Update end time to current time (but keep active)
                
                # Update port if it changed (device moved to different port)
                if existing_session_key[0] != port:
                    # Remove old port mapping
                    old_port = existing_session_key[0]
                    if old_port in self.port_active_session and self.port_active_session[old_port] == existing_session_key:
                        self.port_active_session.pop(old_port, None)
                    
                    # Update session port
                    session['port'] = port
                    # Create new session_key with new port
                    new_session_key = (port, session_id)
                    # Move session to new key
                    self.active_sessions[new_session_key] = session
                    del self.active_sessions[existing_session_key]
                    # Update lookup
                    self.mac_session_lookup[mac_session_key] = new_session_key
                    self.port_active_session[port] = new_session_key
                    session_key = new_session_key
            elif session_key in self.active_sessions:
                # Session exists for this port and session_id - update it
                session = self.active_sessions[session_key]
                session['end'] = timestamp  # Update end time to current time (but keep active)
                
                # Ensure it's in MAC lookup to prevent duplicates
                if mac:
                    mac_session_key = (mac, session_id)
                    if mac_session_key not in self.mac_session_lookup:
                        self.mac_session_lookup[mac_session_key] = session_key
                    elif self.mac_session_lookup[mac_session_key] != session_key:
                        # Another session exists for this MAC and session_id - use the existing one instead
                        existing_key = self.mac_session_lookup[mac_session_key]
                        if existing_key in self.active_sessions:
                            # Use existing session, close this duplicate
                            session['end'] = timestamp
                            session['is_active'] = False
                            # Save duplicate session
                            if mac:
                                summary = self._load_summary(mac, date_str)
                                summary['sessions'].append(session)
                                self._save_summary(mac, date_str, summary)
                            # Remove duplicate
                            del self.active_sessions[session_key]
                            if port in self.port_active_session and self.port_active_session[port] == session_key:
                                self.port_active_session.pop(port, None)
                            # Use existing session
                            session = self.active_sessions[existing_key]
                            session['end'] = timestamp
                            session_key = existing_key
                            # Update port if needed
                            if existing_key[0] != port:
                                old_port = existing_key[0]
                                session['port'] = port
                                new_session_key = (port, session_id)
                                self.active_sessions[new_session_key] = session
                                del self.active_sessions[existing_key]
                                self.mac_session_lookup[mac_session_key] = new_session_key
                                if old_port in self.port_active_session and self.port_active_session[old_port] == existing_key:
                                    self.port_active_session.pop(old_port, None)
                                self.port_active_session[port] = new_session_key
                                session_key = new_session_key
            else:
                # Create new session for this (port, si). Old session for this port already closed above if si changed.
                # Check if there's an active session for this MAC with different session_id (e.g. device moved ports)
                if mac:
                    mac_session_key = (mac, session_id)
                    # Check all active sessions for this MAC with different session_id
                    for (p, sid), sess in list(self.active_sessions.items()):
                        if sess.get('mac') == mac and sid != session_id and sess.get('is_active', False):
                            # Close old session for this MAC with different session_id
                            sess['end'] = timestamp
                            sess['is_active'] = False
                            
                            # Save old session
                            if mac:
                                old_summary = self._load_summary(mac, date_str)
                                old_summary['sessions'].append(sess)
                                self._save_summary(mac, date_str, old_summary)
                            
                            # Remove from MAC lookup
                            old_mac_session_key = (mac, sid)
                            if self.mac_session_lookup.get(old_mac_session_key) == (p, sid):
                                self.mac_session_lookup.pop(old_mac_session_key, None)
                            
                            # Remove from port mapping if it matches
                            if p in self.port_active_session and self.port_active_session[p] == (p, sid):
                                self.port_active_session.pop(p, None)
                            
                            # Remove old session
                            del self.active_sessions[(p, sid)]
                            break
                
                # Create new session (only if it doesn't exist)
                session = {
                    'start': timestamp,
                    'end': timestamp,  # Set to current time but keep active
                    'uptime': 0,
                    'recordings': 0,
                    'recordings_duration': 0,  # in milliseconds
                    'uploads': 0,
                    'firmware': firmware_from_message,  # Set firmware if available
                    'session_id': session_id,
                    'port': port,
                    'mac': mac,
                    'is_active': True,
                    'reset_reason': None,  # Will be set if INIT message is received
                    'init_message': None,  # Will be set if INIT message is received
                    'health_stats': {}  # Will store health statistics
                }
                self.active_sessions[session_key] = session
                self.port_active_session[port] = session_key
                
                # Add to MAC lookup to prevent duplicates
                if mac:
                    mac_session_key = (mac, session_id)
                    self.mac_session_lookup[mac_session_key] = session_key
            
            # Update session with message data
            session = self.active_sessions[session_key]
            session['end'] = timestamp  # Always update end time to current time
            
            # Update MAC if available
            if mac:
                session['mac'] = mac
            
            # Process message content for uptime, firmware, recordings, uploads
            if msg_type == 'received':
                json_data = self._parse_message_content(message)
                
                if json_data and isinstance(json_data, dict):
                    msg_type_field = json_data.get('ty')
                    if msg_type_field == 'short':
                        uptime = self._extract_uptime_from_json(json_data)
                        if uptime > 0:
                            session['uptime'] = max(session.get('uptime', 0), uptime)
                    elif msg_type_field == 'health':
                        # Capture all health stats in session
                        if 'health_stats' not in session:
                            session['health_stats'] = {}
                        
                        health_stats = session['health_stats']
                        # Session statistics
                        if 'rc' in json_data:
                            health_stats['recording_count'] = json_data.get('rc')
                        if 'uc' in json_data:
                            health_stats['uploaded_count'] = json_data.get('uc')
                        if 'ec' in json_data:
                            health_stats['error_count'] = json_data.get('ec')
                        if 'pq' in json_data:
                            health_stats['pending_queue'] = json_data.get('pq')
                        if 'td' in json_data:
                            health_stats['total_duration'] = json_data.get('td')
                        if 'lr' in json_data:
                            health_stats['last_recording'] = json_data.get('lr')
                        
                        # Lifetime upload statistics
                        if 'tu' in json_data:
                            health_stats['total_uploads'] = json_data.get('tu')
                        if 'ta' in json_data:
                            health_stats['total_attempts'] = json_data.get('ta')
                        if 'ur' in json_data:
                            health_stats['upload_rate'] = json_data.get('ur')
                        if 'lu' in json_data:
                            health_stats['last_upload'] = json_data.get('lu')
                        
                        # Event statistics
                        if 'ev' in json_data:
                            health_stats['event_count'] = json_data.get('ev')
                        if 'le' in json_data:
                            health_stats['last_event'] = json_data.get('le')
                        
                        # Warning and fatal counts
                        if 'wc' in json_data:
                            health_stats['warning_count'] = json_data.get('wc')
                        if 'fc' in json_data:
                            health_stats['fatal_count'] = json_data.get('fc')
                        
                        # Memory information
                        if 'ht' in json_data:
                            health_stats['heap_total'] = json_data.get('ht')
                        if 'hf' in json_data:
                            health_stats['heap_free'] = json_data.get('hf')
                        
                        # System status
                        if 'tm' in json_data:
                            health_stats['time_valid'] = json_data.get('tm')
                        if 'su' in json_data:
                            health_stats['storage_util'] = json_data.get('su')
                        
                        # WiFi information
                        if 'wi' in json_data:
                            health_stats['wifi'] = json_data.get('wi')
                        if 'ip' in json_data:
                            health_stats['ip'] = json_data.get('ip')
                        if 'ri' in json_data:
                            health_stats['rssi'] = json_data.get('ri')
                        
                        # Storage information
                        if 'st' in json_data:
                            health_stats['storage_mode'] = json_data.get('st')
                        if 'sd' in json_data:
                            health_stats['sd_available'] = json_data.get('sd')
                        
                        # Yearly summary metrics (if present)
                        if 'yr' in json_data:
                            health_stats['year'] = json_data.get('yr')
                            health_stats['year_files'] = json_data.get('yf', 0)
                            health_stats['year_size'] = json_data.get('ys', '')
                            health_stats['year_hours'] = json_data.get('yh', 0)
                            health_stats['year_months'] = json_data.get('ym', 0)
                            health_stats['year_days'] = json_data.get('yd', 0)
                        
                        # Update last health timestamp
                        health_stats['last_health_update'] = timestamp
                        
                    elif msg_type_field == 'log':
                        # Check for INIT message
                        message_text = json_data.get('ms', '')
                        reset_reason = json_data.get('rr')
                        if self._detect_init_message(message_text) or reset_reason:
                            # Update session with INIT info if not already set
                            if 'reset_reason' not in session or not session.get('reset_reason'):
                                session['reset_reason'] = reset_reason
                                session['init_message'] = message_text
                                # Update start time to INIT time if earlier
                                try:
                                    init_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                    start_time = datetime.fromisoformat(session.get('start', timestamp).replace('Z', '+00:00'))
                                    if init_time < start_time:
                                        session['start'] = timestamp
                                except:
                                    pass
                    
                    elif msg_type_field == 'config':
                        # Update firmware - always update if received
                        firmware = json_data.get('fw')
                        if firmware:
                            session['firmware'] = firmware
                
                # Also check nested JSON for firmware - always update if found
                if firmware_from_message:
                    session['firmware'] = firmware_from_message
                else:
                    # Fallback: try regex if firmware_from_message wasn't set
                    firmware_match = re.search(r'\{"ty"\s*:\s*"config"[^}]*"fw"\s*:\s*"([^"]+)"', message)
                    if firmware_match:
                        session['firmware'] = firmware_match.group(1)
                
                # Also check nested JSON for uptime
                nested_json_match = re.search(r'\{"ty"\s*:\s*"short"[^}]*"ut"\s*:\s*(\d+)', message)
                if nested_json_match:
                    try:
                        uptime = int(nested_json_match.group(1))
                        if uptime > 0:
                            session['uptime'] = max(session.get('uptime', 0), uptime)
                    except:
                        pass
                
                # Check for recording start (match session ID)
                if self._detect_recording_start(message) and self._session_id_matches(message, session_id):
                    session['recordings'] = session.get('recordings', 0) + 1
                
                # Check for recording stop (match session ID)
                if self._detect_recording_stop(message) and self._session_id_matches(message, session_id):
                    duration = self._extract_recording_duration(message)
                    session['recordings_duration'] = session.get('recordings_duration', 0) + duration
                
                # Check for upload (match session ID)
                if self._detect_upload(message) and self._session_id_matches(message, session_id):
                    session['uploads'] = session.get('uploads', 0) + 1
            
            # Periodically save summary (every message for now)
            if mac:
                summary = self._load_summary(mac, date_str)
                self._save_summary(mac, date_str, summary)
    
    def get_sessions(self, mac, date_str=None):
        """Get sessions for a device, optionally filtered by date."""
        if date_str:
            summary = self._load_summary(mac, date_str)
            return summary.get('sessions', [])
        else:
            # Get all sessions from all dates
            device_folder = os.path.join(LOG_SUMMARY_FOLDER, mac)
            if not os.path.exists(device_folder):
                return []
            
            all_sessions = []
            for filename in os.listdir(device_folder):
                if filename.endswith('.json'):
                    date_from_file = filename.replace('.json', '')
                    summary = self._load_summary(mac, date_from_file)
                    all_sessions.extend(summary.get('sessions', []))
            
            # Sort by start time (most recent first)
            all_sessions.sort(key=lambda x: x.get('start', ''), reverse=True)
            return all_sessions
    
    def get_current_session(self, mac):
        """Get the current active session for a device by MAC."""
        if not mac:
            return None
        # Normalize MAC address
        mac = mac.replace(':', '').replace('-', '').upper()
        
        with self.lock:
            # Find active session for this MAC
            for session_key, session in self.active_sessions.items():
                if session.get('mac') == mac and session.get('is_active', False):
                    return session.copy()
        return None
    
    def get_current_session_by_port(self, port):
        """Get the current active session for a port."""
        if not port:
            return None
        
        with self.lock:
            if port in self.port_active_session:
                session_key = self.port_active_session[port]
                session = self.active_sessions.get(session_key)
                if session:
                    return session.copy()
        return None
    
    def get_all_active_sessions(self):
        """Get all active sessions."""
        with self.lock:
            return [session.copy() for session in self.active_sessions.values() if session.get('is_active', False)]
    
    def close_port_session(self, port, timestamp=None):
        """Manually close a session for a port (e.g., when port disconnects)."""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        with self.lock:
            self._close_port_session(port, timestamp)
            self.last_message_time.pop(port, None)
    
    def get_summary_dates(self, mac):
        """Get list of dates with summary data for a device."""
        device_folder = os.path.join(LOG_SUMMARY_FOLDER, mac)
        if not os.path.exists(device_folder):
            return []
        
        dates = []
        for filename in os.listdir(device_folder):
            if filename.endswith('.json'):
                dates.append(filename.replace('.json', ''))
        
        return sorted(dates, reverse=True)

    def clear_all_sessions(self):
        """Clear all sessions: in-memory state and all persisted session files."""
        with self.lock:
            self.active_sessions.clear()
            self.port_active_session.clear()
            self.mac_session_lookup.clear()
            self.last_message_time.clear()
        if os.path.exists(LOG_SUMMARY_FOLDER):
            for name in os.listdir(LOG_SUMMARY_FOLDER):
                path = os.path.join(LOG_SUMMARY_FOLDER, name)
                if os.path.isdir(path):
                    try:
                        shutil.rmtree(path)
                    except Exception as e:
                        return {'success': False, 'error': str(e)}
        return {'success': True, 'message': 'All sessions cleared'}

# Global instance
log_summary_service = LogSummaryService()

