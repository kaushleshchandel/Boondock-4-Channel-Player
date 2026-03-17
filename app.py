"""Flask application for Boondock 4 Channel Player."""
import os
import sys
import uuid
import threading
import time
import json
import queue
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, redirect, send_file
from werkzeug.utils import secure_filename
from config import Config
from models import init_db, AudioStream, AudioFile, OutputChannel, NoiseProfile, DeviceAlias, Firmware
from audio_service import audio_service, resample_audio, convert_audio
from serial_service import serial_service
from firmware_service import FirmwareService

# Initialize firmware service with serial service reference
firmware_service = FirmwareService(serial_service=serial_service)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

# Initialize database
init_db()

def normalize_mac(mac):
    """Normalize MAC address by removing colons/dashes and converting to uppercase."""
    if not mac:
        return ''
    return mac.replace(':', '').replace('-', '').upper()

# Routes - Pages
@app.route('/')
def index():
    return redirect('/devices')

@app.route('/terminal')
def terminal_page():
    return render_template('terminal.html')

@app.route('/devices')
def devices_page():
    return render_template('devices.html')

@app.route('/history')
def history_page():
    return render_template('history.html')

@app.route('/firmware')
def firmware_page():
    return render_template('firmware.html')

@app.route('/player')
def player_page():
    return render_template('player.html')

@app.route('/sessions')
def sessions_page():
    return render_template('sessions.html')

# API Routes - Noise Profiles
@app.route('/api/noise-profiles', methods=['GET'])
def get_noise_profiles():
    profiles = NoiseProfile.get_all()
    return jsonify(profiles)

@app.route('/api/noise-profiles', methods=['POST'])
def create_noise_profile():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    name = request.form.get('name', 'Unnamed Noise')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Supported audio formats
    allowed_extensions = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac', '.wma', '.mp4', '.m4v'}
    file_ext = os.path.splitext(file.filename.lower())[1]
    
    if file_ext not in allowed_extensions:
        return jsonify({'error': f'Unsupported file format. Supported formats: {", ".join(sorted(allowed_extensions))}'}), 400
    
    original_filename = secure_filename(file.filename)
    # Preserve original extension for temp file
    temp_path = os.path.join(Config.UPLOAD_FOLDER, f"{uuid.uuid4()}{file_ext}")
    file.save(temp_path)
    
    new_filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(Config.NOISE_FOLDER, new_filename)
    
    try:
        convert_audio(temp_path, output_path, Config.OUTPUT_SAMPLE_RATE, Config.TARGET_BITRATE)
        profile_id = NoiseProfile.create(name, new_filename, original_filename)
        os.remove(temp_path)
        
        return jsonify({
            'id': profile_id,
            'name': name,
            'filename': new_filename,
            'original_filename': original_filename
        })
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({'error': str(e)}), 500

@app.route('/api/noise-profiles/<int:profile_id>', methods=['DELETE'])
def delete_noise_profile(profile_id):
    NoiseProfile.delete(profile_id)
    return jsonify({'success': True})

# API Routes - Output Channels
@app.route('/api/output-channels', methods=['GET'])
def get_output_channels():
    channels = OutputChannel.get_all()
    status = audio_service.get_all_channel_status()
    for ch in channels:
        ch_status = status.get(ch['id'], {})
        ch['is_playing'] = ch_status.get('is_playing', False)
        ch['is_paused'] = ch_status.get('is_paused', False)
        ch['current_file'] = ch_status.get('current_file')
        ch['file_index'] = ch_status.get('file_index', 0)
        ch['total_files'] = ch_status.get('total_files', 0)
        ch['volume'] = ch_status.get('volume', ch.get('volume', 1.0))
        ch['noise_enabled'] = ch_status.get('noise_enabled', ch.get('noise_enabled', False))
        ch['noise_volume'] = ch_status.get('noise_volume', ch.get('noise_volume', 0.3))
        ch['file_delay'] = ch_status.get('file_delay', ch.get('file_delay', 0))
        ch['noise_during_delay'] = ch_status.get('noise_during_delay', ch.get('noise_during_delay', False))
        ch['in_delay'] = ch_status.get('in_delay', False)
        ch['play_duration'] = ch_status.get('play_duration', 0)
    return jsonify(channels)

@app.route('/api/output-channels', methods=['POST'])
def create_output_channel():
    data = request.json
    name = data.get('name', 'Unnamed Channel')
    device_id = data.get('device_id')
    
    if device_id is None:
        return jsonify({'error': 'device_id required'}), 400
    
    channel_id = OutputChannel.create(name, device_id)
    return jsonify({'id': channel_id, 'name': name, 'device_id': device_id})

@app.route('/api/output-channels/<int:channel_id>', methods=['PUT'])
def update_output_channel(channel_id):
    data = request.json
    OutputChannel.update(
        channel_id,
        data.get('name'),
        data.get('device_id')
    )
    return jsonify({'success': True})

@app.route('/api/output-channels/<int:channel_id>', methods=['DELETE'])
def delete_output_channel(channel_id):
    audio_service.stop_channel(channel_id)
    OutputChannel.delete(channel_id)
    return jsonify({'success': True})

@app.route('/api/output-channels/<int:channel_id>/stream', methods=['POST'])
def set_channel_stream(channel_id):
    data = request.json
    stream_id = data.get('stream_id')
    success = audio_service.set_channel_stream(channel_id, stream_id)
    return jsonify({'success': success})

@app.route('/api/output-channels/<int:channel_id>/volume', methods=['POST'])
def set_channel_volume(channel_id):
    data = request.json
    volume = data.get('volume', 1.0)
    success = audio_service.set_channel_volume(channel_id, volume)
    return jsonify({'success': success})

@app.route('/api/output-channels/<int:channel_id>/noise', methods=['POST'])
def set_channel_noise(channel_id):
    data = request.json
    enabled = data.get('enabled', False)
    profile_id = data.get('profile_id')
    noise_volume = data.get('noise_volume')
    preset = data.get('preset')  # Preset noise type
    success = audio_service.set_channel_noise(channel_id, enabled, profile_id, noise_volume, preset)
    return jsonify({'success': success})

@app.route('/api/noise-presets', methods=['GET'])
def get_noise_presets():
    presets = audio_service.get_preset_noises()
    return jsonify(presets)

@app.route('/api/output-channels/<int:channel_id>/delay', methods=['POST'])
def set_channel_delay(channel_id):
    data = request.json
    delay = data.get('delay', 0)
    noise_during_delay = data.get('noise_during_delay', False)
    success = audio_service.set_channel_delay(channel_id, delay, noise_during_delay)
    return jsonify({'success': success})

@app.route('/api/output-channels/<int:channel_id>/play', methods=['POST'])
def play_channel(channel_id):
    success = audio_service.play_channel(channel_id)
    return jsonify({'success': success})

@app.route('/api/output-channels/<int:channel_id>/pause', methods=['POST'])
def pause_channel(channel_id):
    success = audio_service.pause_channel(channel_id)
    return jsonify({'success': success})

@app.route('/api/output-channels/<int:channel_id>/resume', methods=['POST'])
def resume_channel(channel_id):
    success = audio_service.resume_channel(channel_id)
    return jsonify({'success': success})

@app.route('/api/output-channels/<int:channel_id>/stop', methods=['POST'])
def stop_channel(channel_id):
    success = audio_service.stop_channel(channel_id)
    return jsonify({'success': success})

@app.route('/api/output-channels/<int:channel_id>/test', methods=['POST'])
def test_output_channel(channel_id):
    channel = OutputChannel.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    success = audio_service.test_device(channel['device_id'])
    return jsonify({'success': success})

# API Routes - Streams
@app.route('/api/streams', methods=['GET'])
def get_streams():
    streams = AudioStream.get_all()
    for stream in streams:
        stream['files'] = AudioFile.get_by_stream(stream['id'])
    return jsonify(streams)

@app.route('/api/streams', methods=['POST'])
def create_stream():
    data = request.json
    name = data.get('name', 'Unnamed Stream')
    description = data.get('description', '')
    stream_id = AudioStream.create(name, description)
    return jsonify({'id': stream_id, 'name': name, 'description': description})

@app.route('/api/streams/<int:stream_id>', methods=['GET'])
def get_stream(stream_id):
    stream = AudioStream.get(stream_id)
    if stream:
        stream['files'] = AudioFile.get_by_stream(stream_id)
        return jsonify(stream)
    return jsonify({'error': 'Stream not found'}), 404

@app.route('/api/streams/<int:stream_id>', methods=['PUT'])
def update_stream(stream_id):
    data = request.json
    AudioStream.update(stream_id, data.get('name'), data.get('description'))
    return jsonify({'success': True})

@app.route('/api/streams/<int:stream_id>', methods=['DELETE'])
def delete_stream(stream_id):
    AudioStream.delete(stream_id)
    return jsonify({'success': True})

# API Routes - File Upload
@app.route('/api/streams/<int:stream_id>/upload', methods=['POST'])
def upload_file(stream_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Supported audio formats
    allowed_extensions = {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac', '.wma', '.mp4', '.m4v'}
    file_ext = os.path.splitext(file.filename.lower())[1]
    
    if file_ext not in allowed_extensions:
        return jsonify({'error': f'Unsupported file format. Supported formats: {", ".join(sorted(allowed_extensions))}'}), 400
    
    original_filename = secure_filename(file.filename)
    # Preserve original extension for temp file
    temp_path = os.path.join(Config.UPLOAD_FOLDER, f"{uuid.uuid4()}{file_ext}")
    file.save(temp_path)
    
    stream_folder = os.path.join(Config.STREAMS_FOLDER, str(stream_id))
    os.makedirs(stream_folder, exist_ok=True)
    
    new_filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(stream_folder, new_filename)
    
    try:
        convert_audio(temp_path, output_path, Config.OUTPUT_SAMPLE_RATE, Config.TARGET_BITRATE)
        file_id = AudioFile.add(stream_id, new_filename, original_filename)
        os.remove(temp_path)
        
        for ch in OutputChannel.get_all():
            if ch.get('stream_id') == stream_id:
                audio_service.reload_channel_files(ch['id'])
        
        return jsonify({
            'id': file_id,
            'filename': new_filename,
            'original_filename': original_filename
        })
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<int:file_id>', methods=['DELETE'])
def delete_file(file_id):
    AudioFile.delete(file_id)
    return jsonify({'success': True})

# API Routes - Devices
@app.route('/api/devices', methods=['GET'])
def get_devices():
    devices = audio_service.get_audio_devices()
    return jsonify(devices)

@app.route('/api/devices/test', methods=['POST'])
def test_device():
    data = request.json
    device_id = data.get('device_id')
    
    if device_id is None:
        return jsonify({'error': 'device_id required'}), 400
    
    success = audio_service.test_device(device_id)
    return jsonify({'success': success})

# API Routes - Serial Devices
@app.route('/api/serial/devices', methods=['GET'])
def get_serial_devices():
    devices = serial_service.get_serial_devices()
    return jsonify(devices)

@app.route('/api/serial/connect', methods=['POST'])
def connect_serial():
    data = request.json
    port = data.get('port')
    if not port:
        return jsonify({'error': 'Port required'}), 400
    result = serial_service.connect(port)
    return jsonify(result)

@app.route('/api/serial/disconnect', methods=['POST'])
def disconnect_serial():
    data = request.json
    port = data.get('port')
    if not port:
        return jsonify({'error': 'Port required'}), 400
    result = serial_service.disconnect(port)
    return jsonify(result)

@app.route('/api/serial/disconnect-all', methods=['POST'])
def disconnect_all_serial():
    result = serial_service.disconnect_all()
    return jsonify(result)

@app.route('/api/serial/send', methods=['POST'])
def send_serial():
    data = request.json
    message = data.get('message', '')
    ports = data.get('ports')  # None means all
    results = serial_service.send_message(message, ports)
    return jsonify(results)

@app.route('/api/serial/messages', methods=['GET'])
def get_serial_messages():
    since = request.args.get('since')
    messages = serial_service.get_messages(since)
    return jsonify(messages)

@app.route('/api/serial/messages/clear', methods=['POST'])
def clear_serial_messages():
    result = serial_service.clear_messages()
    return jsonify(result)

@app.route('/api/serial/connected', methods=['GET'])
def get_connected_ports():
    ports = serial_service.get_connected_ports()
    return jsonify(ports)

@app.route('/api/serial/device-data', methods=['GET'])
def get_device_data():
    data = serial_service.get_device_data()
    # Add device names from aliases
    aliases = DeviceAlias.get_all()
    for key, device in data.items():
        mac = device.get('mac', '')
        # Normalize MAC address (remove colons)
        if mac:
            normalized_mac = mac.replace(':', '').replace('-', '').upper()
            device['name'] = aliases.get(normalized_mac, '')
            # Also normalize the MAC in the device data
            device['mac'] = normalized_mac
        elif key and len(key) == 12 and all(c in '0123456789ABCDEFabcdef' for c in key):
            # Key is a MAC address (12 hex chars)
            normalized_key = key.upper()
            device['name'] = aliases.get(normalized_key, '')
            if 'mac' not in device or not device['mac']:
                device['mac'] = normalized_key
    return jsonify(data)

@app.route('/api/serial/device/<mac>/settings', methods=['POST'])
def set_device_settings(mac):
    """Apply device settings via CLI commands."""
    mac = normalize_mac(mac)
    data = request.json or {}
    commands = []
    
    # Audio settings
    if 'audio_min_ms' in data and data['audio_min_ms']:
        commands.append(f"set min {data['audio_min_ms']}")
    if 'audio_max_ms' in data and data['audio_max_ms']:
        commands.append(f"set max {data['audio_max_ms']}")
    if 'audio_silence_ms' in data and data['audio_silence_ms']:
        commands.append(f"set silence {data['audio_silence_ms']}")
    if 'audio_threshold' in data and data['audio_threshold']:
        commands.append(f"set sense {data['audio_threshold']}")
    if 'audio_pre_ms' in data and data['audio_pre_ms']:
        commands.append(f"set pre {data['audio_pre_ms']}")
    if 'codec_gain' in data and data['codec_gain']:
        commands.append(f"set gain {data['codec_gain']}")
    if 'discard_enabled' in data:
        enabled_str = 'true' if bool(data['discard_enabled']) else 'false'
        commands.append(f"set audio.discardSmallFilesEnabled {enabled_str}")
    if 'discard_min_ms' in data and data['discard_min_ms']:
        commands.append(f"set audio.discardSmallFilesMinMs {data['discard_min_ms']}")
    if 'audio_sample_rate' in data and data['audio_sample_rate']:
        commands.append(f"set audio.sampleRate {data['audio_sample_rate']}")
    if 'audio_buffer_samples' in data and data['audio_buffer_samples']:
        commands.append(f"set audio.bufferSamples {data['audio_buffer_samples']}")
    
    # WiFi settings - Network 0
    if 'wifi0_ssid' in data and data['wifi0_ssid']:
        commands.append(f"set ssid0 {data['wifi0_ssid']}")
    if 'wifi0_password' in data and data['wifi0_password']:
        commands.append(f"set pass0 {data['wifi0_password']}")
    if 'wifi0_timeout' in data and data['wifi0_timeout']:
        commands.append(f"set wifi[0].connectTimeoutMs {data['wifi0_timeout']}")
    if 'wifi0_static_enabled' in data:
        enabled_str = 'true' if bool(data['wifi0_static_enabled']) else 'false'
        commands.append(f"set wifi[0].staticIpEnabled {enabled_str}")
    if 'wifi0_static_ip' in data and data['wifi0_static_ip']:
        commands.append(f"set ip0 {data['wifi0_static_ip']}")
    if 'wifi0_subnet' in data and data['wifi0_subnet']:
        commands.append(f"set subnet0 {data['wifi0_subnet']}")
    if 'wifi0_gateway' in data and data['wifi0_gateway']:
        commands.append(f"set gateway0 {data['wifi0_gateway']}")
    if 'wifi0_dns1' in data and data['wifi0_dns1']:
        commands.append(f"set dns10 {data['wifi0_dns1']}")
    if 'wifi0_dns2' in data and data['wifi0_dns2']:
        commands.append(f"set dns20 {data['wifi0_dns2']}")
    
    # WiFi settings - Network 1
    if 'wifi1_ssid' in data and data['wifi1_ssid']:
        commands.append(f"set ssid1 {data['wifi1_ssid']}")
    if 'wifi1_password' in data and data['wifi1_password']:
        commands.append(f"set pass1 {data['wifi1_password']}")
    
    # WiFi settings - Network 2
    if 'wifi2_ssid' in data and data['wifi2_ssid']:
        commands.append(f"set ssid2 {data['wifi2_ssid']}")
    if 'wifi2_password' in data and data['wifi2_password']:
        commands.append(f"set pass2 {data['wifi2_password']}")
    
    # Host/API settings - Endpoint 0
    if 'host0' in data and data['host0']:
        commands.append(f"set host0 {data['host0']}")
    if 'host0_port' in data and data['host0_port']:
        commands.append(f"set upload.apiPorts[0] {data['host0_port']}")
    if 'host0_enabled' in data:
        enabled_str = 'true' if bool(data['host0_enabled']) else 'false'
        commands.append(f"set upload.enabled[0] {enabled_str}")
    if 'host0_ssl' in data:
        ssl_str = 'true' if bool(data['host0_ssl']) else 'false'
        commands.append(f"set upload.audioUploadUseSSL {ssl_str}")
    if 'host0_mp3' in data:
        mp3_str = 'true' if bool(data['host0_mp3']) else 'false'
        commands.append(f"set upload.convertToMp3PerEndpoint[0] {mp3_str}")
    
    # Host/API settings - Endpoint 1
    if 'host1' in data and data['host1']:
        commands.append(f"set host1 {data['host1']}")
    if 'host1_port' in data and data['host1_port']:
        commands.append(f"set upload.apiPorts[1] {data['host1_port']}")
    if 'host1_enabled' in data:
        enabled_str = 'true' if bool(data['host1_enabled']) else 'false'
        commands.append(f"set upload.enabled[1] {enabled_str}")
    if 'host1_mp3' in data:
        mp3_str = 'true' if bool(data['host1_mp3']) else 'false'
        commands.append(f"set upload.convertToMp3PerEndpoint[1] {mp3_str}")
    
    # Host/API settings - Endpoint 2
    if 'host2' in data and data['host2']:
        commands.append(f"set host2 {data['host2']}")
    if 'host2_port' in data and data['host2_port']:
        commands.append(f"set upload.apiPorts[2] {data['host2_port']}")
    if 'host2_enabled' in data:
        enabled_str = 'true' if bool(data['host2_enabled']) else 'false'
        commands.append(f"set upload.enabled[2] {enabled_str}")
    if 'host2_mp3' in data:
        mp3_str = 'true' if bool(data['host2_mp3']) else 'false'
        commands.append(f"set upload.convertToMp3PerEndpoint[2] {mp3_str}")
    
    # Upload queue settings
    if 'queue_depth' in data and data['queue_depth']:
        commands.append(f"set upload.queueDepth {data['queue_depth']}")
    
    # Other settings
    if 'timezone_offset' in data and data['timezone_offset'] is not None:
        commands.append(f"set timezone.offsetHours {data['timezone_offset']}")
    if 'wifi_tx_power' in data and data['wifi_tx_power']:
        commands.append(f"set txpower {data['wifi_tx_power']}")
    
    if not commands:
        return jsonify({'error': 'No settings provided'}), 400
    
    result = serial_service.send_commands_to_mac(mac, commands)
    status_code = 200 if result.get('success') else 500
    return jsonify({'commands': commands, **result}), status_code

@app.route('/api/serial/device/<mac>/reboot', methods=['POST'])
def reboot_device(mac):
    """Send reboot command to device."""
    mac = normalize_mac(mac)
    result = serial_service.send_commands_to_mac(mac, ['reboot'])
    status_code = 200 if result.get('success') else 500
    return jsonify(result), status_code

@app.route('/api/serial/device/<mac>/refresh', methods=['POST'])
def refresh_device_health(mac):
    """Request health update from device."""
    mac = normalize_mac(mac)
    result = serial_service.send_commands_to_mac(mac, ['health ?'])
    status_code = 200 if result.get('success') else 500
    return jsonify(result), status_code

@app.route('/api/serial/device/<mac>/command', methods=['POST'])
def device_command(mac):
    """Send a raw CLI command to device."""
    mac = normalize_mac(mac)
    data = request.json or {}
    command = data.get('command')
    commands = data.get('commands')
    
    if not command and not commands:
        return jsonify({'error': 'Command or commands list required'}), 400
    
    if command:
        commands_to_send = [command]
    else:
        commands_to_send = commands
    
    result = serial_service.send_commands_to_mac(mac, commands_to_send)
    status_code = 200 if result.get('success') else 500
    return jsonify({'commands': commands_to_send, **result}), status_code

@app.route('/api/serial/sessions/clear-all', methods=['POST'])
def clear_all_sessions():
    """Clear all sessions (in-memory and persisted)."""
    from log_summary_service import log_summary_service
    result = log_summary_service.clear_all_sessions()
    status = 200 if result.get('success') else 500
    return jsonify(result), status

@app.route('/api/serial/sessions/<mac>', methods=['GET'])
def get_sessions(mac):
    mac = normalize_mac(mac)
    page = request.args.get('page', 0, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    data = serial_service.get_sessions(mac, page, per_page)
    return jsonify(data)

@app.route('/api/serial/sessions/all', methods=['GET'])
def get_all_sessions():
    """Get all sessions from all devices with device aliases, including active sessions."""
    from log_summary_service import log_summary_service
    
    # Get all devices with history
    devices_with_history = serial_service.get_all_devices_with_history()
    
    # Get currently connected devices
    device_data = serial_service.get_device_data()
    
    # Combine all device MACs (from history and currently connected)
    all_macs = set()
    for device in devices_with_history:
        mac = device['mac']
        # Normalize MAC address
        if mac:
            mac = mac.replace(':', '').replace('-', '').upper()
            all_macs.add(mac)
    
    # Add MACs from currently connected devices
    for key, device in device_data.items():
        mac = device.get('mac', '')
        if mac:
            mac = mac.replace(':', '').replace('-', '').upper()
            all_macs.add(mac)
        elif key and len(key) == 12 and all(c in '0123456789ABCDEFabcdef' for c in key):
            # Key is a MAC address (12 hex chars)
            all_macs.add(key.upper())
    
    # Get device aliases (already returns a dict: {mac: name})
    alias_map = DeviceAlias.get_all()
    
    # Get all active sessions
    active_sessions_list = log_summary_service.get_all_active_sessions()
    active_sessions_by_mac = {}  # mac -> list of active sessions
    for session in active_sessions_list:
        mac = session.get('mac', '')
        if mac:
            if mac not in active_sessions_by_mac:
                active_sessions_by_mac[mac] = []
            active_sessions_by_mac[mac].append(session)
            # Add MAC to all_macs if not already there
            all_macs.add(mac)
    
    # Build a set of active session IDs by MAC for quick lookup
    active_session_ids_by_mac = {}  # mac -> set of active session_ids
    for mac, sessions in active_sessions_by_mac.items():
        active_session_ids_by_mac[mac] = {s.get('session_id') for s in sessions if s.get('session_id')}
    
    # Collect all sessions
    all_sessions = []
    for mac in all_macs:
        device_name = alias_map.get(mac, mac)
        
        # Get completed sessions from summary files
        completed_sessions = log_summary_service.get_sessions(mac)
        for session in completed_sessions:
            session_id = session.get('session_id')
            session_end = session.get('end')
            
            # Determine if this session is active:
            # Check if session_id is in the active sessions for this MAC
            is_active = False
            if session_id and mac in active_session_ids_by_mac:
                is_active = session_id in active_session_ids_by_mac[mac]
            
            all_sessions.append({
                'device_mac': mac,
                'device_name': device_name,
                'firmware': session.get('firmware', 'Unknown'),
                'start': session.get('start'),
                'end': session_end,
                'uptime': session.get('uptime', 0),
                'recordings': session.get('recordings', 0),
                'uploads': session.get('uploads', 0),
                'recordings_duration': session.get('recordings_duration', 0),  # in milliseconds
                'is_active': is_active,
                'session_id': session_id
            })
        
        # Add active sessions that haven't been added yet
        if mac in active_sessions_by_mac:
            for active_session in active_sessions_by_mac[mac]:
                session_id = active_session.get('session_id')
                # Check if we already added this session from completed_sessions (by session_id)
                already_added = any(
                    s.get('device_mac') == mac and s.get('session_id') == session_id
                    for s in all_sessions
                )
                
                if not already_added:
                    all_sessions.append({
                        'device_mac': mac,
                        'device_name': device_name,
                        'firmware': active_session.get('firmware', 'Unknown'),
                        'start': active_session.get('start'),
                        'end': active_session.get('end'),  # May be set but session is still active
                        'uptime': active_session.get('uptime', 0),
                        'recordings': active_session.get('recordings', 0),
                        'uploads': active_session.get('uploads', 0),
                        'recordings_duration': active_session.get('recordings_duration', 0),  # in milliseconds
                        'is_active': True,
                        'session_id': session_id
                    })
    
    # Sort: active sessions first, then by start time (most recent first)
    # Use a tuple where first element is 0 for active (sorts first), 1 for inactive
    # Second element is negative timestamp for descending order (newest first)
    def sort_key(session):
        is_active = session.get('is_active', False)
        start_time = session.get('start', '')
        # Convert to sortable value: 0 for active (sorts first), 1 for inactive
        # For timestamp, use negative for descending (newest first), but handle empty strings
        try:
            if start_time:
                # Use negative timestamp for descending order (newest first)
                timestamp_value = -int(datetime.fromisoformat(start_time.replace('Z', '+00:00')).timestamp())
            else:
                timestamp_value = 0
        except:
            timestamp_value = 0
        return (0 if is_active else 1, timestamp_value)
    
    all_sessions.sort(key=sort_key)
    
    return jsonify({'sessions': all_sessions})

@app.route('/api/serial/history', methods=['GET'])
def get_all_history_devices():
    devices = serial_service.get_all_devices_with_history()
    return jsonify(devices)

@app.route('/api/serial/history/clear-all', methods=['POST'])
def clear_all_history():
    """Clear all serial history for all devices."""
    result = serial_service.clear_all_history()
    status = 200 if result.get('success') else 500
    return jsonify(result), status

@app.route('/api/serial/history/<mac>/dates', methods=['GET'])
def get_history_dates(mac):
    mac = normalize_mac(mac)
    dates = serial_service.get_history_dates(mac)
    return jsonify(dates)

@app.route('/api/serial/history/<mac>/<date_str>', methods=['GET'])
def get_history(mac, date_str):
    mac = normalize_mac(mac)
    offset = request.args.get('offset', 0, type=int)
    limit_param = request.args.get('limit')
    # If limit is 'all' or not provided, use None to get all messages
    if limit_param == 'all' or limit_param is None:
        limit = None
    else:
        limit = int(limit_param)
        if limit == 0:
            limit = None
    data = serial_service.get_history(mac, date_str, offset, limit)
    return jsonify(data)

@app.route('/api/serial/history/multiple', methods=['POST'])
def get_history_multiple():
    """Get history from multiple devices."""
    data = request.json or {}
    macs = data.get('macs', [])
    date_str = data.get('date')
    offset = data.get('offset', 0)
    limit = data.get('limit')
    
    if not macs or not date_str:
        return jsonify({'error': 'macs and date are required'}), 400
    
    # Normalize MAC addresses
    macs = [normalize_mac(mac) for mac in macs]
    
    # If limit is 'all' or 0, use None to get all messages
    if limit == 'all' or limit == 0:
        limit = None
    
    result = serial_service.get_history_multiple_devices(macs, date_str, offset, limit)
    return jsonify(result)

# API Routes - Device Aliases
@app.route('/api/device-aliases', methods=['GET'])
def get_device_aliases():
    aliases = DeviceAlias.get_all()
    return jsonify(aliases)

@app.route('/api/device-aliases/<mac>', methods=['PUT'])
def set_device_alias(mac):
    mac = normalize_mac(mac)
    data = request.json
    name = data.get('name', '')
    if name:
        DeviceAlias.set(mac, name)
    else:
        DeviceAlias.delete(mac)
    return jsonify({'success': True})

@app.route('/api/device-aliases/<mac>', methods=['DELETE'])
def delete_device_alias(mac):
    mac = normalize_mac(mac)
    DeviceAlias.delete(mac)
    return jsonify({'success': True})

@app.route('/api/serial/device/<mac>', methods=['DELETE'])
def delete_device(mac):
    mac = normalize_mac(mac)
    import shutil
    # Delete alias
    DeviceAlias.delete(mac)
    # Delete history folder
    history_folder = os.path.join(os.path.dirname(__file__), 'serial_history', mac)
    if os.path.exists(history_folder):
        shutil.rmtree(history_folder)
    # Remove from sessions
    if mac in serial_service.sessions:
        del serial_service.sessions[mac]
    if mac in serial_service.current_sessions:
        del serial_service.current_sessions[mac]
    if mac in serial_service.last_uptime:
        del serial_service.last_uptime[mac]
    serial_service._save_sessions()
    return jsonify({'success': True})

# API Routes - LLM Analysis
@app.route('/api/llm/config', methods=['GET'])
def get_llm_config():
    return jsonify({
        'url': Config.OLLAMA_URL,
        'model': Config.OLLAMA_MODEL
    })

@app.route('/api/llm/analyze', methods=['POST'])
def analyze_logs():
    import requests
    data = request.json
    logs = data.get('logs', '')
    prompt = data.get('prompt', 'Analyze these serial logs and identify any issues or patterns:')
    model = data.get('model', Config.OLLAMA_MODEL)
    
    try:
        response = requests.post(
            f"{Config.OLLAMA_URL}/api/generate",
            json={
                'model': model,
                'prompt': f"{prompt}\n\n{logs}",
                'stream': False
            },
            timeout=120
        )
        response.raise_for_status()
        result = response.json()
        return jsonify({'response': result.get('response', '')})
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/llm/models', methods=['GET'])
def get_llm_models():
    import requests
    try:
        response = requests.get(f"{Config.OLLAMA_URL}/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        models = [m['name'] for m in data.get('models', [])]
        return jsonify(models)
    except requests.exceptions.RequestException as e:
        return jsonify({'error': str(e)}), 500

# API Routes - Firmware
@app.route('/api/firmwares', methods=['GET'])
def get_firmwares():
    firmwares = Firmware.get_all()
    return jsonify(firmwares)

@app.route('/api/firmwares', methods=['POST'])
def create_firmware():
    if 'firmware' not in request.files and 'bootloader' not in request.files and 'partition' not in request.files:
        return jsonify({'error': 'At least one file (firmware, bootloader, or partition) is required'}), 400
    
    name = request.form.get('name', 'Unnamed Firmware')
    if not name:
        return jsonify({'error': 'Firmware name is required'}), 400
    
    firmware_filename = None
    bootloader_filename = None
    partition_filename = None

    # Process in order: 1. Bootloader, 2. Firmware, 3. Partitions. Validate exact filenames.
    for file_key, required_name in [('bootloader', 'bootloader.bin'), ('firmware', 'firmware.bin'), ('partition', 'partitions.bin')]:
        if file_key not in request.files:
            continue
        f = request.files[file_key]
        if not f.filename:
            continue
        if f.filename.lower() != required_name:
            return jsonify({'error': f'File must be named exactly "{required_name}" (got "{f.filename}")'}), 400
        fn = f"{uuid.uuid4()}.bin"
        path = os.path.join(Config.FIRMWARE_FOLDER, fn)
        f.save(path)
        if file_key == 'bootloader':
            bootloader_filename = fn
        elif file_key == 'firmware':
            firmware_filename = fn
        else:
            partition_filename = fn

    firmware_id = Firmware.create(name, firmware_filename, bootloader_filename, partition_filename)
    return jsonify({
        'id': firmware_id,
        'name': name,
        'firmware_filename': firmware_filename,
        'bootloader_filename': bootloader_filename,
        'partition_filename': partition_filename
    })

@app.route('/api/firmwares/<int:firmware_id>', methods=['DELETE'])
def delete_firmware(firmware_id):
    Firmware.delete(firmware_id)
    return jsonify({'success': True})

@app.route('/api/firmwares/<int:firmware_id>/download/<file_type>', methods=['GET'])
def download_firmware_file(firmware_id, file_type):
    """Download bootloader.bin, firmware.bin, or partitions.bin for a firmware."""
    if file_type not in ('bootloader', 'firmware', 'partition'):
        return jsonify({'error': 'Invalid file type'}), 400
    firmware = Firmware.get(firmware_id)
    if not firmware:
        return jsonify({'error': 'Firmware not found'}), 404
    key = 'bootloader_filename' if file_type == 'bootloader' else 'firmware_filename' if file_type == 'firmware' else 'partition_filename'
    stored_name = firmware.get(key)
    if not stored_name:
        return jsonify({'error': f'No {file_type} file for this firmware'}), 404
    path = os.path.join(Config.FIRMWARE_FOLDER, stored_name)
    if not os.path.isfile(path):
        return jsonify({'error': 'File not found on server'}), 404
    download_name = 'bootloader.bin' if file_type == 'bootloader' else 'firmware.bin' if file_type == 'firmware' else 'partitions.bin'
    return send_file(path, as_attachment=True, download_name=download_name)

@app.route('/api/firmwares/<int:firmware_id>/flash', methods=['POST'])
def flash_firmware(firmware_id):
    """Start firmware flashing in background thread."""
    data = request.json
    port = data.get('port')
    
    if not port:
        return jsonify({'error': 'Port is required'}), 400
    
    firmware = Firmware.get(firmware_id)
    if not firmware:
        return jsonify({'error': 'Firmware not found'}), 404
    
    # Check if already flashing
    if firmware_service.is_flashing(port):
        return jsonify({'error': 'Device is already being flashed'}), 400
    
    # Build file paths
    firmware_path = None
    bootloader_path = None
    partition_path = None
    
    if firmware['firmware_filename']:
        firmware_path = os.path.join(Config.FIRMWARE_FOLDER, firmware['firmware_filename'])
    if firmware['bootloader_filename']:
        bootloader_path = os.path.join(Config.FIRMWARE_FOLDER, firmware['bootloader_filename'])
    if firmware['partition_filename']:
        partition_path = os.path.join(Config.FIRMWARE_FOLDER, firmware['partition_filename'])
    
    # Start flashing in background thread
    def flash_thread():
        firmware_service.flash_firmware(port, firmware_id, firmware_path, bootloader_path, partition_path)
    
    thread = threading.Thread(target=flash_thread, daemon=True)
    thread.start()
    
    return jsonify({'success': True, 'message': 'Flash started'})

@app.route('/api/firmwares/erase', methods=['POST'])
def erase_flash():
    data = request.json
    port = data.get('port')
    
    if not port:
        return jsonify({'error': 'Port is required'}), 400
    
    result = firmware_service.erase_flash(port)
    
    status_code = 200 if result.get('success') else 500
    return jsonify(result), status_code

@app.route('/api/firmwares/flash/stream', methods=['GET'])
def stream_flash_output():
    """Stream flash output using Server-Sent Events."""
    port = request.args.get('port')
    if not port:
        return jsonify({'error': 'Port is required'}), 400
    
    def generate():
        output_queue = firmware_service.get_output_queue(port)
        if not output_queue:
            yield f"data: {json.dumps({'error': 'No flash operation in progress'})}\n\n"
            return
        
        while True:
            try:
                # Get output from queue (with timeout)
                try:
                    msg_type, content, is_stderr = output_queue.get(timeout=0.5)
                    
                    if msg_type == 'line':
                        yield f"data: {json.dumps({'type': 'line', 'line': content, 'is_stderr': is_stderr})}\n\n"
                    elif msg_type == 'status':
                        yield f"data: {json.dumps({'type': 'status', 'message': content})}\n\n"
                    elif msg_type == 'error':
                        yield f"data: {json.dumps({'type': 'error', 'error': content})}\n\n"
                    elif msg_type == 'done':
                        success, returncode = content
                        yield f"data: {json.dumps({'type': 'done', 'success': success, 'returncode': returncode})}\n\n"
                        break
                except queue.Empty:
                    # Check if still flashing
                    if not firmware_service.is_flashing(port):
                        yield f"data: {json.dumps({'type': 'done', 'success': False, 'message': 'Flash operation ended'})}\n\n"
                        break
                    continue
                    
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
                break
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })

@app.route('/api/firmwares/flash-all', methods=['POST'])
def flash_all_firmware():
    """Start firmware flashing for multiple devices in parallel."""
    data = request.json
    firmware_id = data.get('firmware_id')
    ports = data.get('ports', [])
    
    if not firmware_id:
        return jsonify({'error': 'firmware_id is required'}), 400
    
    if not ports or not isinstance(ports, list):
        return jsonify({'error': 'ports must be a non-empty list'}), 400
    
    firmware = Firmware.get(firmware_id)
    if not firmware:
        return jsonify({'error': 'Firmware not found'}), 404
    
    # Check if any devices are already being flashed
    already_flashing = [port for port in ports if firmware_service.is_flashing(port)]
    if already_flashing:
        return jsonify({
            'error': f'Devices already being flashed: {", ".join(already_flashing)}'
        }), 400
    
    # Build file paths
    firmware_path = None
    bootloader_path = None
    partition_path = None
    
    if firmware['firmware_filename']:
        firmware_path = os.path.join(Config.FIRMWARE_FOLDER, firmware['firmware_filename'])
    if firmware['bootloader_filename']:
        bootloader_path = os.path.join(Config.FIRMWARE_FOLDER, firmware['bootloader_filename'])
    if firmware['partition_filename']:
        partition_path = os.path.join(Config.FIRMWARE_FOLDER, firmware['partition_filename'])
    
    erase_before_flash = data.get('erase_before_flash', False)
    
    # Start flashing each device in a separate thread
    for port in ports:
        def flash_thread(device_port, do_erase):
            firmware_service.flash_firmware(
                device_port,
                firmware_id,
                firmware_path,
                bootloader_path,
                partition_path,
                erase_before_flash=do_erase
            )
        thread = threading.Thread(target=flash_thread, args=(port, erase_before_flash), daemon=True)
        thread.start()
    
    return jsonify({
        'success': True, 
        'message': f'Flash started for {len(ports)} device(s)',
        'ports': ports
    })

@app.route('/api/firmwares/flash-all/stream', methods=['GET'])
def stream_flash_all_output():
    """Stream flash output from multiple devices using Server-Sent Events."""
    ports_param = request.args.get('ports')
    if not ports_param:
        return jsonify({'error': 'ports parameter is required'}), 400
    
    ports = [p.strip() for p in ports_param.split(',') if p.strip()]
    if not ports:
        return jsonify({'error': 'At least one port is required'}), 400
    
    def generate():
        # Create a mapping of port -> output queue
        port_queues = {}
        for port in ports:
            queue_obj = firmware_service.get_output_queue(port)
            if queue_obj:
                port_queues[port] = queue_obj
        
        if not port_queues:
            yield f"data: {json.dumps({'type': 'error', 'error': 'No flash operations in progress'})}\n\n"
            return
        
        # Track which ports are done
        done_ports = set()
        
        while len(done_ports) < len(ports):
            for port in ports:
                if port in done_ports:
                    continue
                
                # Get queue for this port
                output_queue = port_queues.get(port)
                if not output_queue:
                    # Check if still flashing
                    if not firmware_service.is_flashing(port):
                        done_ports.add(port)
                        yield f"data: {json.dumps({'type': 'done', 'port': port, 'success': False, 'message': 'Flash operation ended'})}\n\n"
                    continue
                
                try:
                    # Try to get output from queue (non-blocking)
                    try:
                        msg_type, content, is_stderr = output_queue.get(timeout=0.1)
                        
                        if msg_type == 'line':
                            yield f"data: {json.dumps({'type': 'line', 'port': port, 'line': content, 'is_stderr': is_stderr})}\n\n"
                        elif msg_type == 'status':
                            yield f"data: {json.dumps({'type': 'status', 'port': port, 'message': content})}\n\n"
                        elif msg_type == 'error':
                            yield f"data: {json.dumps({'type': 'error', 'port': port, 'error': content})}\n\n"
                        elif msg_type == 'done':
                            success, returncode = content
                            done_ports.add(port)
                            yield f"data: {json.dumps({'type': 'done', 'port': port, 'success': success, 'returncode': returncode})}\n\n"
                    except queue.Empty:
                        # Check if still flashing
                        if not firmware_service.is_flashing(port):
                            done_ports.add(port)
                            yield f"data: {json.dumps({'type': 'done', 'port': port, 'success': False, 'message': 'Flash operation ended'})}\n\n"
                        continue
                        
                except Exception as e:
                    done_ports.add(port)
                    yield f"data: {json.dumps({'type': 'error', 'port': port, 'error': str(e)})}\n\n"
            
            # Small sleep to prevent busy waiting
            time.sleep(0.05)
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })

if __name__ == '__main__':
    use_reload = os.environ.get('RELOAD', '').lower() in ('1', 'true', 'yes') or '--reload' in sys.argv
    if use_reload:
        print(f"Starting with reload (watching Python files) on http://{Config.HOST}:{Config.PORT}")
        app.run(host=Config.HOST, port=Config.PORT, debug=False, use_reloader=True)
    else:
        from waitress import serve
        print(f"Starting Boondock 4 Channel Player on http://{Config.HOST}:{Config.PORT}")
        serve(app, host=Config.HOST, port=Config.PORT)
