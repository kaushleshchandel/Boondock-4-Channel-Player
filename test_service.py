"""Test service for device testing."""
import time
import threading
import json
from datetime import datetime
from serial_service import serial_service

class TestService:
    def __init__(self):
        self.test_jobs = {}  # job_id -> test job data
        self.lock = threading.Lock()
    
    def get_test_cases(self):
        """Get all available test cases organized by category."""
        return {
            'settings': [
                {
                    'id': 'test_min_recording',
                    'name': 'Test Minimum Recording (ms)',
                    'description': 'Test setting and reading minimum recording duration',
                    'category': 'settings',
                    'setting': 'min',
                    'test_values': [1000, 2000, 5000]
                },
                {
                    'id': 'test_max_recording',
                    'name': 'Test Maximum Recording (ms)',
                    'description': 'Test setting and reading maximum recording duration',
                    'category': 'settings',
                    'setting': 'max',
                    'test_values': [10000, 30000, 60000]
                },
                {
                    'id': 'test_silence_threshold',
                    'name': 'Test Silence Threshold (ms)',
                    'description': 'Test setting and reading silence threshold',
                    'category': 'settings',
                    'setting': 'silence',
                    'test_values': [1000, 2000, 5000]
                },
                {
                    'id': 'test_sensitivity',
                    'name': 'Test Sensitivity (0-100)',
                    'description': 'Test setting and reading recording sensitivity',
                    'category': 'settings',
                    'setting': 'sense',
                    'test_values': [30, 50, 70]
                },
                {
                    'id': 'test_pre_buffer',
                    'name': 'Test Pre-Buffer (ms)',
                    'description': 'Test setting and reading pre-buffer duration',
                    'category': 'settings',
                    'setting': 'pre',
                    'test_values': [100, 200, 500]
                },
                {
                    'id': 'test_codec_gain',
                    'name': 'Test Codec Gain (dB)',
                    'description': 'Test setting and reading codec gain (-96 to +24 dB)',
                    'category': 'settings',
                    'setting': 'gain',
                    'test_values': [-6, 0, 6]
                },
                {
                    'id': 'test_sample_rate',
                    'name': 'Test Sample Rate',
                    'description': 'Test setting and reading audio sample rate',
                    'category': 'settings',
                    'setting': 'audio.sampleRate',
                    'test_values': [8000, 16000, 44100]
                },
                {
                    'id': 'test_buffer_samples',
                    'name': 'Test Buffer Samples',
                    'description': 'Test setting and reading buffer samples (512-4096)',
                    'category': 'settings',
                    'setting': 'audio.bufferSamples',
                    'test_values': [512, 1024, 2048]
                },
                {
                    'id': 'test_discard_enabled',
                    'name': 'Test Discard Small Files (Enabled)',
                    'description': 'Test enabling/disabling discard small files',
                    'category': 'settings',
                    'setting': 'audio.discardSmallFilesEnabled',
                    'test_values': ['true', 'false']
                },
                {
                    'id': 'test_discard_min_ms',
                    'name': 'Test Discard Minimum (ms)',
                    'description': 'Test setting and reading discard minimum duration',
                    'category': 'settings',
                    'setting': 'audio.discardSmallFilesMinMs',
                    'test_values': [500, 1000, 2000]
                }
            ],
            'recording': [
                {
                    'id': 'test_record_5s',
                    'name': 'Test 5 Second Recording',
                    'description': 'Set sensitivity to 100 and record a 5 second file',
                    'category': 'recording',
                    'duration': 5
                },
                {
                    'id': 'test_record_10s',
                    'name': 'Test 10 Second Recording',
                    'description': 'Set sensitivity to 100 and record a 10 second file',
                    'category': 'recording',
                    'duration': 10
                },
                {
                    'id': 'test_record_30s',
                    'name': 'Test 30 Second Recording',
                    'description': 'Set sensitivity to 100 and record a 30 second file',
                    'category': 'recording',
                    'duration': 30
                }
            ],
            'functions': [
                {
                    'id': 'test_export',
                    'name': 'Test Export Command',
                    'description': 'Test reading all device settings via export',
                    'category': 'functions'
                },
                {
                    'id': 'test_health',
                    'name': 'Test Health Command',
                    'description': 'Test reading device health status (health ?)',
                    'category': 'functions'
                },
                {
                    'id': 'test_status',
                    'name': 'Test Status Command',
                    'description': 'Test reading comprehensive device status',
                    'category': 'functions'
                },
                {
                    'id': 'test_status_short',
                    'name': 'Test Status Short Command',
                    'description': 'Test reading condensed device status',
                    'category': 'functions'
                },
                {
                    'id': 'test_time',
                    'name': 'Test Time Command',
                    'description': 'Test reading device time and uptime',
                    'category': 'functions'
                },
                {
                    'id': 'test_recordings_summary',
                    'name': 'Test Recordings Summary',
                    'description': 'Test reading recordings statistics',
                    'category': 'functions'
                },
                {
                    'id': 'test_audio_level',
                    'name': 'Test Audio Level Statistics',
                    'description': 'Test reading audio level statistics',
                    'category': 'functions'
                },
                {
                    'id': 'test_reboot',
                    'name': 'Test Reboot Command',
                    'description': 'Test device reboot functionality',
                    'category': 'functions'
                },
                {
                    'id': 'test_save',
                    'name': 'Test Save Command',
                    'description': 'Test saving device settings',
                    'category': 'functions'
                },
                {
                    'id': 'test_sample_recording',
                    'name': 'Test Sample Recording',
                    'description': 'Test sample recording command (bypasses threshold)',
                    'category': 'functions'
                }
            ],
            'advanced': [
                {
                    'id': 'test_wifi_settings',
                    'name': 'Test WiFi Settings',
                    'description': 'Test reading and setting WiFi configuration',
                    'category': 'advanced'
                },
                {
                    'id': 'test_api_server_settings',
                    'name': 'Test API Server Settings',
                    'description': 'Test reading and setting API server configuration',
                    'category': 'advanced'
                },
                {
                    'id': 'test_storage_info',
                    'name': 'Test Storage Information',
                    'description': 'Test reading storage information from health',
                    'category': 'advanced'
                },
                {
                    'id': 'test_uptime_tracking',
                    'name': 'Test Uptime Tracking',
                    'description': 'Verify device uptime is tracked correctly',
                    'category': 'advanced'
                },
                {
                    'id': 'test_ip_mac',
                    'name': 'Test IP and MAC Address',
                    'description': 'Test reading device IP and MAC address',
                    'category': 'advanced'
                },
                {
                    'id': 'test_config_csv',
                    'name': 'Test Config CSV',
                    'description': 'Test reading configuration in CSV format',
                    'category': 'advanced'
                },
                {
                    'id': 'test_recent_errors',
                    'name': 'Test Recent Errors',
                    'description': 'Test reading recent error messages',
                    'category': 'advanced'
                }
            ]
        }
    
    def _get_setting_command(self, setting, value):
        """Convert setting name to CLI command."""
        if setting == 'min':
            return f'set min {value}'
        elif setting == 'max':
            return f'set max {value}'
        elif setting == 'silence':
            return f'set silence {value}'
        elif setting == 'sense':
            return f'set sense {value}'
        elif setting == 'pre':
            return f'set pre {value}'
        elif setting == 'gain':
            return f'set gain {value}'
        elif setting == 'audio.sampleRate':
            return f'set audio.sampleRate {value}'
        elif setting == 'audio.bufferSamples':
            return f'set audio.bufferSamples {value}'
        elif setting == 'audio.discardSmallFilesEnabled':
            return f'set audio.discardSmallFilesEnabled {value}'
        elif setting == 'audio.discardSmallFilesMinMs':
            return f'set audio.discardSmallFilesMinMs {value}'
        return None
    
    def _get_setting_from_config(self, config, setting):
        """Extract setting value from device config."""
        if setting == 'min':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('mrm') or audio.get('minRecordingMs')
        elif setting == 'max':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('xrm') or audio.get('maxRecordingMs')
        elif setting == 'silence':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('stm') or audio.get('silenceThresholdMs')
        elif setting == 'sense':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('ath') or audio.get('audioThreshold')
        elif setting == 'pre':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('prm') or audio.get('preRecordingMs')
        elif setting == 'gain':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('cg') or audio.get('codecGain')
        elif setting == 'audio.sampleRate':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('sr') or audio.get('sampleRate')
        elif setting == 'audio.bufferSamples':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('bs') or audio.get('bufferSamples')
        elif setting == 'audio.discardSmallFilesEnabled':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('dsf') or audio.get('discardSmallFilesEnabled')
        elif setting == 'audio.discardSmallFilesMinMs':
            audio = config.get('a') or config.get('audio', {})
            return audio.get('dmm') or audio.get('discardSmallFilesMinMs')
        return None
    
    def _wait_for_response(self, mac, timeout=5):
        """Wait for device response by checking messages."""
        start_time = time.time()
        initial_count = len(serial_service.messages)
        
        while time.time() - start_time < timeout:
            if len(serial_service.messages) > initial_count:
                # Check if we got a response from this device
                port = serial_service.get_port_for_mac(mac)
                if port:
                    with serial_service.lock:
                        device_data = serial_service.device_data.get(port, {})
                        if device_data.get('last_update'):
                            return True
            time.sleep(0.1)
        return False
    
    def _get_device_config(self, mac):
        """Get current device configuration."""
        port = serial_service.get_port_for_mac(mac)
        if not port:
            return None
        
        with serial_service.lock:
            device_data = serial_service.device_data.get(port, {})
            return device_data.get('full_config') or device_data.get('config', {})
    
    def run_test_job(self, job_id, mac, test_case_ids):
        """Run a test job in background thread."""
        with self.lock:
            self.test_jobs[job_id] = {
                'status': 'running',
                'progress': 0,
                'total_tests': len(test_case_ids),
                'completed_tests': 0,
                'results': [],
                'original_settings': {},
                'start_time': datetime.now().isoformat(),
                'end_time': None,
                'error': None
            }
        
        try:
            job = self.test_jobs[job_id]
            
            # Step 1: Read all original settings
            job['status'] = 'reading_settings'
            job['progress'] = 5
            job['results'].append({
                'step': 'Reading original settings',
                'status': 'running',
                'message': 'Sending export command...'
            })
            
            # Request export
            result = serial_service.send_commands_to_mac(mac, ['export'])
            if not result.get('success'):
                raise Exception('Failed to send export command')
            
            # Wait for export response
            time.sleep(2)
            original_config = self._get_device_config(mac)
            if not original_config:
                # Try again
                time.sleep(1)
                original_config = self._get_device_config(mac)
            
            if original_config:
                job['original_settings'] = original_config.copy()
                job['results'][-1]['status'] = 'success'
                job['results'][-1]['message'] = 'Original settings read successfully'
            else:
                job['results'][-1]['status'] = 'warning'
                job['results'][-1]['message'] = 'Could not read all settings, continuing anyway'
            
            # Get all test cases
            all_test_cases = {}
            for category, cases in self.get_test_cases().items():
                for case in cases:
                    all_test_cases[case['id']] = case
            
            # Step 2: Run each test case
            for idx, test_id in enumerate(test_case_ids):
                if test_id not in all_test_cases:
                    job['results'].append({
                        'step': f'Test: {test_id}',
                        'status': 'error',
                        'message': 'Test case not found'
                    })
                    job['completed_tests'] += 1
                    continue
                
                test_case = all_test_cases[test_id]
                job['progress'] = 10 + (idx * 80 // len(test_case_ids))
                
                # Run the test
                result = self._run_single_test(mac, test_case, job)
                job['results'].append(result)
                job['completed_tests'] += 1
            
            # Step 3: Restore original settings
            job['status'] = 'restoring_settings'
            job['progress'] = 90
            job['results'].append({
                'step': 'Restoring original settings',
                'status': 'running',
                'message': 'Restoring settings...'
            })
            
            if job['original_settings']:
                restore_commands = []
                original = job['original_settings']
                audio = original.get('a') or original.get('audio', {})
                
                # Restore audio settings
                if 'mrm' in audio or 'minRecordingMs' in audio:
                    val = audio.get('mrm') or audio.get('minRecordingMs')
                    if val is not None:
                        restore_commands.append(f'set min {val}')
                if 'xrm' in audio or 'maxRecordingMs' in audio:
                    val = audio.get('xrm') or audio.get('maxRecordingMs')
                    if val is not None:
                        restore_commands.append(f'set max {val}')
                if 'stm' in audio or 'silenceThresholdMs' in audio:
                    val = audio.get('stm') or audio.get('silenceThresholdMs')
                    if val is not None:
                        restore_commands.append(f'set silence {val}')
                if 'ath' in audio or 'audioThreshold' in audio:
                    val = audio.get('ath') or audio.get('audioThreshold')
                    if val is not None:
                        restore_commands.append(f'set sense {val}')
                if 'prm' in audio or 'preRecordingMs' in audio:
                    val = audio.get('prm') or audio.get('preRecordingMs')
                    if val is not None:
                        restore_commands.append(f'set pre {val}')
                if 'cg' in audio or 'codecGain' in audio:
                    val = audio.get('cg') or audio.get('codecGain')
                    if val is not None:
                        restore_commands.append(f'set gain {val}')
                if 'dsf' in audio or 'discardSmallFilesEnabled' in audio:
                    val = audio.get('dsf') or audio.get('discardSmallFilesEnabled')
                    if val is not None:
                        restore_commands.append(f'set audio.discardSmallFilesEnabled {str(val).lower()}')
                if 'dmm' in audio or 'discardSmallFilesMinMs' in audio:
                    val = audio.get('dmm') or audio.get('discardSmallFilesMinMs')
                    if val is not None:
                        restore_commands.append(f'set audio.discardSmallFilesMinMs {val}')
                
                if restore_commands:
                    restore_commands.append('save')
                    result = serial_service.send_commands_to_mac(mac, restore_commands)
                    if result.get('success'):
                        job['results'][-1]['status'] = 'success'
                        job['results'][-1]['message'] = 'Settings restored successfully'
                    else:
                        job['results'][-1]['status'] = 'warning'
                        job['results'][-1]['message'] = 'Some settings may not have been restored'
                else:
                    job['results'][-1]['status'] = 'warning'
                    job['results'][-1]['message'] = 'No settings to restore'
            else:
                job['results'][-1]['status'] = 'warning'
                job['results'][-1]['message'] = 'No original settings saved, skipping restore'
            
            job['status'] = 'complete'
            job['progress'] = 100
            job['end_time'] = datetime.now().isoformat()
            
        except Exception as e:
            with self.lock:
                job['status'] = 'error'
                job['error'] = str(e)
                job['end_time'] = datetime.now().isoformat()
                job['results'].append({
                    'step': 'Error',
                    'status': 'error',
                    'message': f'Test job failed: {str(e)}'
                })
    
    def _run_single_test(self, mac, test_case, job):
        """Run a single test case."""
        test_id = test_case['id']
        category = test_case['category']
        
        result = {
            'test_id': test_id,
            'test_name': test_case['name'],
            'step': test_case['name'],
            'status': 'running',
            'message': '',
            'details': {}
        }
        
        try:
            if category == 'settings':
                # Settings test: get, set, save, get again, verify
                setting = test_case['setting']
                test_values = test_case.get('test_values', [])
                
                if not test_values:
                    result['status'] = 'error'
                    result['message'] = 'No test values defined'
                    return result
                
                # Get original value
                config = self._get_device_config(mac)
                if not config:
                    result['status'] = 'error'
                    result['message'] = 'Could not read device config'
                    return result
                
                original_value = self._get_setting_from_config(config, setting)
                result['details']['original_value'] = original_value
                
                # Test each value
                for test_value in test_values:
                    # Set value
                    cmd = self._get_setting_command(setting, test_value)
                    if not cmd:
                        result['status'] = 'error'
                        result['message'] = f'Unknown setting: {setting}'
                        return result
                    
                    serial_service.send_commands_to_mac(mac, [cmd, 'save'])
                    time.sleep(1)
                    
                    # Get value back
                    serial_service.send_commands_to_mac(mac, ['export'])
                    time.sleep(1.5)
                    
                    config = self._get_device_config(mac)
                    if not config:
                        result['status'] = 'error'
                        result['message'] = 'Could not read config after setting'
                        return result
                    
                    read_value = self._get_setting_from_config(config, setting)
                    
                    # Verify
                    if read_value == test_value:
                        result['details'][f'test_{test_value}'] = 'passed'
                    else:
                        result['details'][f'test_{test_value}'] = f'failed (expected {test_value}, got {read_value})'
                        result['status'] = 'error'
                
                if result['status'] != 'error':
                    result['status'] = 'success'
                    result['message'] = f'All test values verified successfully'
            
            elif category == 'recording':
                # Recording test: set sensitivity to 100, set min/max, wait for recording
                duration = test_case.get('duration', 5)
                
                # Get original settings
                config = self._get_device_config(mac)
                original_sense = None
                original_min = None
                original_max = None
                
                if config:
                    audio = config.get('a') or config.get('audio', {})
                    original_sense = audio.get('ath') or audio.get('audioThreshold')
                    original_min = audio.get('mrm') or audio.get('minRecordingMs')
                    original_max = audio.get('xrm') or audio.get('maxRecordingMs')
                
                # Set sensitivity to 100 (force continuous recording)
                serial_service.send_commands_to_mac(mac, ['set sense 100'])
                time.sleep(0.5)
                
                # Set min and max to target duration
                min_ms = max(100, duration * 1000 - 500)  # Slightly less than target
                max_ms = duration * 1000 + 1000  # Slightly more than target
                serial_service.send_commands_to_mac(mac, [
                    f'set min {min_ms}',
                    f'set max {max_ms}',
                    'save'
                ])
                time.sleep(1)
                
                # Get initial recording count
                port = serial_service.get_port_for_mac(mac)
                initial_count = 0
                if port:
                    with serial_service.lock:
                        device_data = serial_service.device_data.get(port, {})
                        initial_count = device_data.get('total_recordings', 0)
                
                # Wait for recording to complete (duration + buffer)
                wait_time = duration + 3
                result['message'] = f'Waiting {wait_time} seconds for {duration}s recording...'
                
                start_time = time.time()
                while time.time() - start_time < wait_time:
                    time.sleep(0.5)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            new_count = device_data.get('total_recordings', 0)
                            if new_count > initial_count:
                                result['status'] = 'success'
                                result['message'] = f'Recording completed successfully (duration: {duration}s)'
                                result['details']['recordings_before'] = initial_count
                                result['details']['recordings_after'] = new_count
                                break
                
                if result['status'] != 'success':
                    result['status'] = 'warning'
                    result['message'] = f'Recording may not have completed within timeout'
                
                # Restore original sensitivity (will be fully restored later)
                if original_sense is not None:
                    serial_service.send_commands_to_mac(mac, [f'set sense {original_sense}'])
            
            elif category == 'functions':
                # Function tests
                if test_id == 'test_export':
                    serial_service.send_commands_to_mac(mac, ['export'])
                    time.sleep(2)
                    config = self._get_device_config(mac)
                    if config:
                        result['status'] = 'success'
                        result['message'] = 'Export command successful'
                        result['details']['config_keys'] = list(config.keys())
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Export command failed or timed out'
                
                elif test_id == 'test_health':
                    serial_service.send_commands_to_mac(mac, ['health ?'])
                    time.sleep(1.5)
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            health = device_data.get('health', {})
                            if health:
                                result['status'] = 'success'
                                result['message'] = 'Health command successful'
                                result['details']['health_keys'] = list(health.keys())
                            else:
                                result['status'] = 'warning'
                                result['message'] = 'Health data not yet available'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_status':
                    serial_service.send_commands_to_mac(mac, ['status'])
                    time.sleep(2)
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            if device_data:
                                result['status'] = 'success'
                                result['message'] = 'Status command successful'
                                result['details']['has_data'] = True
                            else:
                                result['status'] = 'warning'
                                result['message'] = 'Status data not yet available'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_status_short':
                    serial_service.send_commands_to_mac(mac, ['statusshort'])
                    time.sleep(1.5)
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            if device_data:
                                result['status'] = 'success'
                                result['message'] = 'Status short command successful'
                            else:
                                result['status'] = 'warning'
                                result['message'] = 'Status data not yet available'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_time':
                    serial_service.send_commands_to_mac(mac, ['time'])
                    time.sleep(1)
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            uptime = device_data.get('uptime', 0)
                            if uptime >= 0:
                                result['status'] = 'success'
                                result['message'] = 'Time command successful'
                                result['details']['uptime'] = uptime
                            else:
                                result['status'] = 'warning'
                                result['message'] = 'Time data not yet available'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_recordings_summary':
                    serial_service.send_commands_to_mac(mac, ['recordings'])
                    time.sleep(1)
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            recordings = device_data.get('total_recordings', 0)
                            result['status'] = 'success'
                            result['message'] = 'Recordings summary command successful'
                            result['details']['total_recordings'] = recordings
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_audio_level':
                    serial_service.send_commands_to_mac(mac, ['audiolevel'])
                    time.sleep(1)
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            current_db = device_data.get('current_db', 0)
                            result['status'] = 'success'
                            result['message'] = 'Audio level command successful'
                            result['details']['current_db'] = current_db
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_reboot':
                    result['message'] = 'Sending reboot command (device will disconnect)...'
                    serial_service.send_commands_to_mac(mac, ['reboot'])
                    time.sleep(2)
                    result['status'] = 'success'
                    result['message'] = 'Reboot command sent successfully'
                    result['details']['note'] = 'Device should reboot and reconnect shortly'
                
                elif test_id == 'test_save':
                    # Just test that save command works
                    serial_service.send_commands_to_mac(mac, ['save'])
                    time.sleep(0.5)
                    result['status'] = 'success'
                    result['message'] = 'Save command sent successfully'
                
                elif test_id == 'test_sample_recording':
                    # Test sample recording command
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            initial_count = device_data.get('total_recordings', 0)
                            is_recording = device_data.get('recording', False)
                        
                        if is_recording:
                            result['status'] = 'warning'
                            result['message'] = 'Recording already in progress, skipping test'
                        else:
                            serial_service.send_commands_to_mac(mac, ['sample'])
                            result['message'] = 'Sample recording command sent'
                            result['status'] = 'success'
                            result['details']['note'] = 'Recording should start and use configured min/max duration'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
            
            elif category == 'advanced':
                if test_id == 'test_wifi_settings':
                    config = self._get_device_config(mac)
                    if config:
                        wifi = config.get('w') or config.get('wifi', {})
                        if wifi:
                            result['status'] = 'success'
                            result['message'] = 'WiFi settings read successfully'
                            result['details']['wifi_aps'] = len([k for k in wifi.keys() if 'ssid' in str(k).lower()])
                        else:
                            result['status'] = 'warning'
                            result['message'] = 'No WiFi settings found in config'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Could not read device config'
                
                elif test_id == 'test_storage_info':
                    serial_service.send_commands_to_mac(mac, ['health ?'])
                    time.sleep(1.5)
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            storage_mode = device_data.get('storage_mode')
                            storage_size = device_data.get('storage_size')
                            if storage_mode or storage_size:
                                result['status'] = 'success'
                                result['message'] = 'Storage information retrieved'
                                result['details'] = {
                                    'mode': storage_mode,
                                    'size': storage_size,
                                    'used': device_data.get('storage_used'),
                                    'percent': device_data.get('storage_percent')
                                }
                            else:
                                result['status'] = 'warning'
                                result['message'] = 'Storage information not available'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_uptime_tracking':
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            uptime = device_data.get('uptime', 0)
                            if uptime > 0:
                                result['status'] = 'success'
                                result['message'] = 'Uptime tracking working'
                                result['details']['uptime_seconds'] = uptime
                            else:
                                result['status'] = 'warning'
                                result['message'] = 'Uptime not yet available'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_api_server_settings':
                    config = self._get_device_config(mac)
                    if config:
                        upload = config.get('u') or config.get('upload', {})
                        if upload:
                            result['status'] = 'success'
                            result['message'] = 'API server settings read successfully'
                            hosts = upload.get('apiHosts', [])
                            ports = upload.get('apiPorts', [])
                            result['details'] = {
                                'hosts_count': len(hosts) if isinstance(hosts, list) else 0,
                                'ports_count': len(ports) if isinstance(ports, list) else 0
                            }
                        else:
                            result['status'] = 'warning'
                            result['message'] = 'No API server settings found in config'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Could not read device config'
                
                elif test_id == 'test_ip_mac':
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            ip = device_data.get('ip', '')
                            mac_addr = device_data.get('mac', '')
                            if ip or mac_addr:
                                result['status'] = 'success'
                                result['message'] = 'IP and MAC address retrieved'
                                result['details'] = {
                                    'ip': ip or 'Not connected',
                                    'mac': mac_addr or 'Unknown'
                                }
                            else:
                                result['status'] = 'warning'
                                result['message'] = 'IP/MAC not yet available'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
                
                elif test_id == 'test_config_csv':
                    serial_service.send_commands_to_mac(mac, ['config'])
                    time.sleep(1)
                    result['status'] = 'success'
                    result['message'] = 'Config CSV command sent successfully'
                    result['details']['note'] = 'Check terminal output for CSV format response'
                
                elif test_id == 'test_recent_errors':
                    serial_service.send_commands_to_mac(mac, ['errors'])
                    time.sleep(1)
                    port = serial_service.get_port_for_mac(mac)
                    if port:
                        with serial_service.lock:
                            device_data = serial_service.device_data.get(port, {})
                            event_counts = device_data.get('event_counts', {})
                            error_count = event_counts.get('error', 0)
                            result['status'] = 'success'
                            result['message'] = 'Errors command sent successfully'
                            result['details']['error_count'] = error_count
                            result['details']['note'] = 'Check terminal output for detailed error messages'
                    else:
                        result['status'] = 'error'
                        result['message'] = 'Device not connected'
            
            if result['status'] == 'running':
                result['status'] = 'success'
                result['message'] = 'Test completed'
        
        except Exception as e:
            result['status'] = 'error'
            result['message'] = f'Test failed: {str(e)}'
        
        return result
    
    def get_job_status(self, job_id):
        """Get status of a test job."""
        with self.lock:
            return self.test_jobs.get(job_id)
    
    def cancel_job(self, job_id):
        """Cancel a running test job."""
        with self.lock:
            if job_id in self.test_jobs:
                job = self.test_jobs[job_id]
                if job['status'] == 'running':
                    job['status'] = 'cancelled'
                    job['end_time'] = datetime.now().isoformat()
                    return True
        return False

# Global instance
test_service = TestService()

