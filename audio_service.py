"""Audio playback service with multi-channel support."""
import sys
import numpy as np
import sounddevice as sd
import threading
import os
import wave
import time
from scipy import signal
from config import Config
from models import AudioFile, AudioStream, OutputChannel, NoiseProfile

# pydub requires the audioop module (removed in Python 3.13). Install audioop-lts on 3.13+.
_AudioSegment = None
try:
    from pydub import AudioSegment as _AudioSegment
except ImportError:
    pass  # WAV-only conversion fallback used in convert_audio when pydub is unavailable

# Preset noise types for two-way radio simulation
PRESET_NOISES = {
    'white': {
        'name': 'White Noise',
        'description': 'Constant broadband noise'
    },
    'pink': {
        'name': 'Pink Noise',
        'description': 'Natural sounding noise (1/f spectrum)'
    },
    'radio_static': {
        'name': 'Radio Static',
        'description': 'Classic AM/FM static'
    },
    'hf_radio': {
        'name': 'HF Radio Noise',
        'description': 'Shortwave/HF band atmospheric noise'
    },
    'vhf_squelch': {
        'name': 'VHF Squelch Noise',
        'description': 'Open squelch hiss on VHF/UHF'
    },
    'motor_interference': {
        'name': 'Motor Interference',
        'description': 'Engine/motor ignition noise'
    },
    'electrical_hum': {
        'name': 'Electrical Hum',
        'description': '60Hz power line hum with harmonics'
    },
    'digital_artifacts': {
        'name': 'Digital Artifacts',
        'description': 'Digital radio compression artifacts'
    },
    'multipath_fading': {
        'name': 'Multipath Fading',
        'description': 'Signal fading simulation'
    },
    'atmospheric': {
        'name': 'Atmospheric/QRN',
        'description': 'Lightning and atmospheric interference'
    }
}


class NoiseGenerator:
    """Generates various noise types in real-time."""
    
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.phase = 0
        self.pink_state = np.zeros(7)  # For pink noise filter
        self.crackle_timer = 0
        self.fade_phase = 0
    
    def generate(self, noise_type, frames):
        if noise_type == 'white':
            return self._white_noise(frames)
        elif noise_type == 'pink':
            return self._pink_noise(frames)
        elif noise_type == 'radio_static':
            return self._radio_static(frames)
        elif noise_type == 'hf_radio':
            return self._hf_radio(frames)
        elif noise_type == 'vhf_squelch':
            return self._vhf_squelch(frames)
        elif noise_type == 'motor_interference':
            return self._motor_interference(frames)
        elif noise_type == 'electrical_hum':
            return self._electrical_hum(frames)
        elif noise_type == 'digital_artifacts':
            return self._digital_artifacts(frames)
        elif noise_type == 'multipath_fading':
            return self._multipath_fading(frames)
        elif noise_type == 'atmospheric':
            return self._atmospheric(frames)
        else:
            return np.zeros(frames, dtype=np.float32)
    
    def _white_noise(self, frames):
        return np.random.randn(frames).astype(np.float32) * 0.5
    
    def _pink_noise(self, frames):
        """Generate pink noise using Voss-McCartney algorithm."""
        white = np.random.randn(frames).astype(np.float32)
        pink = np.zeros(frames, dtype=np.float32)
        
        b = [0.99886, 0.99332, 0.96900, 0.86650, 0.55000, -0.7616]
        for i in range(frames):
            white_sample = white[i]
            self.pink_state[0] = 0.99886 * self.pink_state[0] + white_sample * 0.0555179
            self.pink_state[1] = 0.99332 * self.pink_state[1] + white_sample * 0.0750759
            self.pink_state[2] = 0.96900 * self.pink_state[2] + white_sample * 0.1538520
            self.pink_state[3] = 0.86650 * self.pink_state[3] + white_sample * 0.3104856
            self.pink_state[4] = 0.55000 * self.pink_state[4] + white_sample * 0.5329522
            self.pink_state[5] = -0.7616 * self.pink_state[5] - white_sample * 0.0168980
            pink[i] = (self.pink_state[0] + self.pink_state[1] + self.pink_state[2] + 
                      self.pink_state[3] + self.pink_state[4] + self.pink_state[5] + 
                      white_sample * 0.5362) * 0.2
        return pink
    
    def _radio_static(self, frames):
        """Classic AM/FM radio static with crackles."""
        noise = self._pink_noise(frames) * 0.6
        
        # Add random crackles
        for i in range(frames):
            if np.random.random() < 0.001:
                burst_len = min(int(np.random.exponential(50)), frames - i)
                noise[i:i+burst_len] += np.random.randn(burst_len).astype(np.float32) * 0.8
        
        return noise
    
    def _hf_radio(self, frames):
        """HF/Shortwave atmospheric noise with fading."""
        base = self._pink_noise(frames) * 0.4
        
        # Add slow fading
        t = np.arange(frames) / self.sample_rate + self.fade_phase
        fade = 0.5 + 0.5 * np.sin(2 * np.pi * 0.3 * t)  # Slow fade
        self.fade_phase += frames / self.sample_rate
        
        # Add atmospheric crashes
        crashes = np.zeros(frames, dtype=np.float32)
        for i in range(frames):
            if np.random.random() < 0.0005:
                crash_len = min(int(np.random.exponential(200)), frames - i)
                crash = np.exp(-np.arange(crash_len) / 50) * np.random.randn(crash_len)
                crashes[i:i+crash_len] += crash.astype(np.float32) * 1.5
        
        return (base * fade + crashes).astype(np.float32)
    
    def _vhf_squelch(self, frames):
        """VHF/UHF open squelch hiss."""
        # High-frequency biased noise
        white = np.random.randn(frames).astype(np.float32)
        
        # Simple high-pass effect
        hiss = np.zeros(frames, dtype=np.float32)
        prev = 0
        alpha = 0.95
        for i in range(frames):
            hiss[i] = alpha * (hiss[i-1] if i > 0 else 0) + alpha * (white[i] - prev)
            prev = white[i]
        
        return hiss * 0.5
    
    def _motor_interference(self, frames):
        """Engine/motor ignition interference."""
        t = np.arange(frames) / self.sample_rate + self.phase
        self.phase += frames / self.sample_rate
        
        # Base ignition frequency (simulating engine RPM)
        rpm_freq = 25  # ~1500 RPM / 60
        
        # Create impulse train
        impulses = np.zeros(frames, dtype=np.float32)
        period = int(self.sample_rate / rpm_freq)
        
        for i in range(0, frames, period):
            if i < frames:
                # Add impulse with some jitter
                jitter = int(np.random.randn() * 5)
                idx = max(0, min(frames - 1, i + jitter))
                impulse_len = min(100, frames - idx)
                impulses[idx:idx+impulse_len] += np.exp(-np.arange(impulse_len) / 10).astype(np.float32) * 0.8
        
        # Add broadband noise component
        noise = self._white_noise(frames) * 0.2
        
        return impulses + noise
    
    def _electrical_hum(self, frames):
        """60Hz power line hum with harmonics."""
        t = np.arange(frames) / self.sample_rate + self.phase
        self.phase += frames / self.sample_rate
        
        hum = np.zeros(frames, dtype=np.float32)
        # Fundamental + harmonics
        for harmonic in [1, 2, 3, 4, 5]:
            freq = 60 * harmonic
            amplitude = 0.4 / harmonic
            hum += amplitude * np.sin(2 * np.pi * freq * t)
        
        # Add slight noise
        hum += self._white_noise(frames) * 0.05
        
        return hum.astype(np.float32)
    
    def _digital_artifacts(self, frames):
        """Digital radio compression/dropout artifacts."""
        base = self._white_noise(frames) * 0.1
        
        # Add random digital "glitches"
        glitch = np.zeros(frames, dtype=np.float32)
        i = 0
        while i < frames:
            if np.random.random() < 0.002:
                # Create a "stuck sample" or quantization noise
                glitch_len = min(int(np.random.exponential(100)), frames - i)
                glitch_type = np.random.choice(['stuck', 'quantized', 'burst'])
                
                if glitch_type == 'stuck':
                    glitch[i:i+glitch_len] = np.random.randn() * 0.3
                elif glitch_type == 'quantized':
                    glitch[i:i+glitch_len] = np.round(np.random.randn(glitch_len) * 4) / 4 * 0.3
                else:
                    glitch[i:i+glitch_len] = np.random.randn(glitch_len).astype(np.float32) * 0.5
                
                i += glitch_len
            else:
                i += 1
        
        return base + glitch
    
    def _multipath_fading(self, frames):
        """Signal fading/flutter simulation."""
        t = np.arange(frames) / self.sample_rate + self.fade_phase
        self.fade_phase += frames / self.sample_rate
        
        # Multiple fading components at different rates
        fade1 = 0.5 + 0.3 * np.sin(2 * np.pi * 0.5 * t)
        fade2 = 0.5 + 0.2 * np.sin(2 * np.pi * 1.7 * t)
        fade3 = 0.5 + 0.15 * np.sin(2 * np.pi * 4.3 * t)  # Flutter
        
        combined_fade = fade1 * fade2 * fade3
        
        # Apply to pink noise base
        base = self._pink_noise(frames)
        return (base * combined_fade).astype(np.float32)
    
    def _atmospheric(self, frames):
        """Lightning crashes and atmospheric QRN."""
        base = self._pink_noise(frames) * 0.3
        
        crashes = np.zeros(frames, dtype=np.float32)
        i = 0
        while i < frames:
            if np.random.random() < 0.0003:
                # Lightning crash
                crash_len = min(int(np.random.exponential(500) + 100), frames - i)
                envelope = np.exp(-np.arange(crash_len) / 100)
                crash = envelope * np.random.randn(crash_len) * 2.0
                crashes[i:i+crash_len] += crash.astype(np.float32)
                i += crash_len
            else:
                i += 1
        
        return base + crashes


class NoisePlayer:
    """Plays noise profile or preset in a loop."""
    
    def __init__(self):
        self.audio = None
        self.position = 0
        self.profile_id = None
        self.preset_type = None
        self.generator = NoiseGenerator(Config.OUTPUT_SAMPLE_RATE)
    
    def load(self, profile_id):
        """Load a custom noise profile from file."""
        self.preset_type = None  # Clear preset
        
        if profile_id == self.profile_id and self.audio is not None:
            return
        
        self.profile_id = profile_id
        profile = NoiseProfile.get(profile_id)
        if not profile:
            self.audio = None
            return
        
        filepath = os.path.join(Config.NOISE_FOLDER, profile['filename'])
        if os.path.exists(filepath):
            try:
                with wave.open(filepath, 'rb') as wf:
                    frames = wf.readframes(wf.getnframes())
                    self.audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                    self.position = 0
            except Exception as e:
                print(f"Error loading noise: {e}")
                self.audio = None
    
    def set_preset(self, preset_type):
        """Set a preset noise type."""
        self.preset_type = preset_type
        self.profile_id = None
        self.audio = None
    
    def get_chunk(self, frames):
        # If using preset, generate noise in real-time
        if self.preset_type and self.preset_type in PRESET_NOISES:
            return self.generator.generate(self.preset_type, frames)
        
        # Otherwise use loaded audio file
        if self.audio is None or len(self.audio) == 0:
            return np.zeros(frames, dtype=np.float32)
        
        chunk = np.zeros(frames, dtype=np.float32)
        chunk_pos = 0
        
        while chunk_pos < frames:
            remaining = len(self.audio) - self.position
            needed = frames - chunk_pos
            
            if remaining <= 0:
                self.position = 0
                continue
            
            copy_len = min(remaining, needed)
            chunk[chunk_pos:chunk_pos + copy_len] = self.audio[self.position:self.position + copy_len]
            self.position += copy_len
            chunk_pos += copy_len
        
        return chunk


class ChannelPlayer:
    """Manages playback for a single output channel."""
    
    def __init__(self, channel_id):
        self.channel_id = channel_id
        self.stream_id = None
        self.device_id = None
        self.audio_files = []
        self.current_file_index = 0
        self.current_audio = None
        self.current_position = 0
        self.is_playing = False
        self.is_paused = False
        self.volume = 1.0
        self.noise_enabled = False
        self.noise_volume = 0.3
        self.noise_player = NoisePlayer()
        self.noise_preset = None
        self.file_delay = 0  # Delay in seconds between files
        self.noise_during_delay = False
        self.delay_samples_remaining = 0  # Samples left in current delay
        self.in_delay = False
        self.play_start_time = None  # Track when playback started
        self.lock = threading.RLock()
    
    def configure(self, device_id, stream_id, volume=1.0, noise_enabled=False, noise_profile_id=None, noise_volume=0.3, noise_preset=None, file_delay=0, noise_during_delay=False):
        with self.lock:
            self.device_id = device_id
            self.stream_id = stream_id
            self.volume = volume
            self.noise_enabled = noise_enabled
            self.noise_volume = noise_volume
            self.noise_preset = noise_preset
            self.file_delay = file_delay
            self.noise_during_delay = noise_during_delay
            
            if noise_enabled:
                if noise_preset:
                    self.noise_player.set_preset(noise_preset)
                elif noise_profile_id:
                    self.noise_player.load(noise_profile_id)
            
            if stream_id:
                self._load_files()
            else:
                self.audio_files = []
                self.current_audio = None
    
    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, volume))
    
    def set_noise(self, enabled, profile_id=None, noise_volume=None, preset=None):
        self.noise_enabled = enabled
        if noise_volume is not None:
            self.noise_volume = max(0.0, min(1.0, noise_volume))
        
        if enabled:
            if preset:
                self.noise_preset = preset
                self.noise_player.set_preset(preset)
            elif profile_id:
                self.noise_preset = None
                self.noise_player.load(profile_id)
    
    def set_delay(self, delay, noise_during_delay):
        self.file_delay = delay
        self.noise_during_delay = noise_during_delay
    
    def _load_files(self):
        if not self.stream_id:
            self.audio_files = []
            self.current_audio = None
            return
        self.audio_files = AudioFile.get_by_stream(self.stream_id)
        self.current_file_index = 0
        self.current_audio = None
        self.current_position = 0
        self._load_current_file()
    
    def reload_files(self):
        with self.lock:
            self._load_files()
    
    def _load_current_file(self):
        if not self.audio_files or not self.stream_id:
            self.current_audio = None
            return
        
        file_info = self.audio_files[self.current_file_index]
        filepath = os.path.join(Config.STREAMS_FOLDER, str(self.stream_id), file_info['filename'])
        
        if os.path.exists(filepath):
            try:
                with wave.open(filepath, 'rb') as wf:
                    frames = wf.readframes(wf.getnframes())
                    self.current_audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                    self.current_position = 0
            except Exception as e:
                print(f"Error loading file {filepath}: {e}")
                self.current_audio = None
    
    def get_next_chunk(self, frames):
        if not self.is_playing or self.is_paused or self.current_audio is None:
            if self.noise_enabled and self.is_playing and not self.is_paused:
                return self.noise_player.get_chunk(frames) * self.noise_volume
            return np.zeros(frames, dtype=np.float32)
        
        chunk = np.zeros(frames, dtype=np.float32)
        chunk_pos = 0
        
        while chunk_pos < frames:
            # Handle delay period between files
            if self.in_delay:
                delay_frames = min(self.delay_samples_remaining, frames - chunk_pos)
                
                # During delay, optionally play noise
                if self.noise_during_delay and self.noise_enabled:
                    noise_chunk = self.noise_player.get_chunk(delay_frames) * self.noise_volume
                    chunk[chunk_pos:chunk_pos + delay_frames] = noise_chunk
                # else: chunk stays silent (zeros)
                
                self.delay_samples_remaining -= delay_frames
                chunk_pos += delay_frames
                
                if self.delay_samples_remaining <= 0:
                    self.in_delay = False
                continue
            
            if self.current_audio is None or len(self.current_audio) == 0:
                break
                
            remaining_in_file = len(self.current_audio) - self.current_position
            remaining_in_chunk = frames - chunk_pos
            
            if remaining_in_file <= 0:
                # File finished - start delay if configured
                if self.file_delay > 0:
                    self.in_delay = True
                    self.delay_samples_remaining = int(self.file_delay * Config.OUTPUT_SAMPLE_RATE)
                
                # Move to next file
                if len(self.audio_files) > 0:
                    self.current_file_index = (self.current_file_index + 1) % len(self.audio_files)
                    self._load_current_file()
                if self.current_audio is None:
                    break
                continue
            
            copy_len = min(remaining_in_file, remaining_in_chunk)
            chunk[chunk_pos:chunk_pos + copy_len] = self.current_audio[self.current_position:self.current_position + copy_len]
            self.current_position += copy_len
            chunk_pos += copy_len
        
        chunk *= self.volume
        
        # Mix in noise if enabled (and not in delay period - handled above)
        if self.noise_enabled and not self.in_delay:
            noise = self.noise_player.get_chunk(frames) * self.noise_volume
            chunk += noise
        
        return chunk
    
    def play(self):
        with self.lock:
            if not self.stream_id or not self.audio_files:
                return False
            self.is_playing = True
            self.is_paused = False
            if self.play_start_time is None:
                self.play_start_time = time.time()
            return True
    
    def pause(self):
        with self.lock:
            self.is_paused = True
    
    def resume(self):
        with self.lock:
            self.is_paused = False
    
    def stop(self):
        with self.lock:
            self.is_playing = False
            self.is_paused = False
            self.current_position = 0
            self.current_file_index = 0
            self.play_start_time = None
            self.in_delay = False
            self.delay_samples_remaining = 0
            if self.stream_id:
                self._load_current_file()
    
    def get_status(self):
        current_file = None
        if self.audio_files and self.current_file_index < len(self.audio_files):
            current_file = self.audio_files[self.current_file_index].get('original_filename')
        
        play_duration = 0
        if self.play_start_time and self.is_playing:
            play_duration = int(time.time() - self.play_start_time)
        
        return {
            'channel_id': self.channel_id,
            'stream_id': self.stream_id,
            'device_id': self.device_id,
            'is_playing': self.is_playing,
            'is_paused': self.is_paused,
            'current_file': current_file,
            'file_index': self.current_file_index,
            'total_files': len(self.audio_files),
            'volume': self.volume,
            'noise_enabled': self.noise_enabled,
            'noise_volume': self.noise_volume,
            'noise_preset': self.noise_preset,
            'file_delay': self.file_delay,
            'noise_during_delay': self.noise_during_delay,
            'in_delay': self.in_delay,
            'play_duration': play_duration
        }


class AudioService:
    """Main audio service managing all channels and devices."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.channel_players = {}
        self.device_streams = {}
        self.lock = threading.RLock()
        
        # Restore playback state on startup
        self._restore_playback_state()
    
    def _restore_playback_state(self):
        """Restore playback state from database on startup."""
        try:
            channels = OutputChannel.get_all()
            for ch in channels:
                if ch.get('is_playing') and ch.get('stream_id'):
                    print(f"Restoring playback for channel {ch['id']}: {ch['name']}")
                    self.play_channel(ch['id'])
        except Exception as e:
            print(f"Error restoring playback state: {e}")
    
    def get_preset_noises(self):
        """Return list of available preset noise types."""
        return [{'id': k, 'name': v['name'], 'description': v['description']} 
                for k, v in PRESET_NOISES.items()]
    
    def get_audio_devices(self):
        """Get list of available audio output devices. On Windows, all outputs are listed; on Linux, USB/sound card preferred."""
        devices = sd.query_devices()
        output_devices = []
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] <= 0:
                continue
            name = dev['name'].lower()
            # On Windows, list all output devices; on Linux list USB / sound card devices
            if sys.platform == 'win32':
                output_devices.append({
                    'id': i,
                    'name': dev['name'],
                    'channels': dev['max_output_channels'],
                    'sample_rate': dev['default_samplerate']
                })
            elif 'usb' in name or 'sound card' in name or 'audio device' in name:
                output_devices.append({
                    'id': i,
                    'name': dev['name'],
                    'channels': dev['max_output_channels'],
                    'sample_rate': dev['default_samplerate']
                })
        return output_devices
    
    def get_or_create_player(self, channel_id):
        if channel_id not in self.channel_players:
            self.channel_players[channel_id] = ChannelPlayer(channel_id)
        return self.channel_players[channel_id]
    
    def _audio_callback(self, device_id):
        def callback(outdata, frames, time_info, status):
            audio = np.zeros(frames, dtype=np.float32)
            
            for player in list(self.channel_players.values()):
                if player.device_id == device_id and player.is_playing:
                    chunk = player.get_next_chunk(frames)
                    audio += chunk
            
            clipped = np.clip(audio, -1.0, 1.0)
            outdata[:, 0] = clipped
            outdata[:, 1] = clipped
        
        return callback
    
    def start_device(self, device_id):
        if device_id in self.device_streams:
            return True
        
        try:
            stream = sd.OutputStream(
                samplerate=Config.OUTPUT_SAMPLE_RATE,
                device=device_id,
                channels=2,
                dtype='float32',
                blocksize=Config.BLOCK_SIZE,
                callback=self._audio_callback(device_id)
            )
            stream.start()
            self.device_streams[device_id] = stream
            return True
        except Exception as e:
            print(f"Error starting device {device_id}: {e}")
            return False
    
    def stop_device(self, device_id):
        if device_id in self.device_streams:
            try:
                self.device_streams[device_id].stop()
                self.device_streams[device_id].close()
            except:
                pass
            del self.device_streams[device_id]
    
    def set_channel_stream(self, channel_id, stream_id):
        output_channel = OutputChannel.get(channel_id)
        if not output_channel:
            return False
        
        OutputChannel.set_stream(channel_id, stream_id)
        
        player = self.get_or_create_player(channel_id)
        player.configure(
            output_channel['device_id'],
            stream_id,
            output_channel.get('volume', 1.0),
            output_channel.get('noise_enabled', False),
            output_channel.get('noise_profile_id'),
            output_channel.get('noise_volume', 0.3),
            output_channel.get('noise_preset')
        )
        return True
    
    def set_channel_volume(self, channel_id, volume):
        OutputChannel.set_volume(channel_id, volume)
        if channel_id in self.channel_players:
            self.channel_players[channel_id].set_volume(volume)
        return True
    
    def set_channel_noise(self, channel_id, enabled, profile_id=None, noise_volume=None, preset=None):
        OutputChannel.set_noise(channel_id, enabled, profile_id, noise_volume, preset)
        if channel_id in self.channel_players:
            self.channel_players[channel_id].set_noise(enabled, profile_id, noise_volume, preset)
        return True
    
    def set_channel_delay(self, channel_id, delay, noise_during_delay):
        OutputChannel.set_delay(channel_id, delay, noise_during_delay)
        if channel_id in self.channel_players:
            self.channel_players[channel_id].set_delay(delay, noise_during_delay)
        return True
    
    def play_channel(self, channel_id):
        output_channel = OutputChannel.get(channel_id)
        if not output_channel or not output_channel.get('stream_id'):
            return False
        
        player = self.get_or_create_player(channel_id)
        player.configure(
            output_channel['device_id'],
            output_channel['stream_id'],
            output_channel.get('volume', 1.0),
            output_channel.get('noise_enabled', False),
            output_channel.get('noise_profile_id'),
            output_channel.get('noise_volume', 0.3),
            output_channel.get('noise_preset'),
            output_channel.get('file_delay', 0),
            output_channel.get('noise_during_delay', False)
        )
        
        self.start_device(output_channel['device_id'])
        result = player.play()
        if result:
            OutputChannel.set_playback_state(channel_id, True)
        return result
    
    def pause_channel(self, channel_id):
        if channel_id in self.channel_players:
            self.channel_players[channel_id].pause()
            return True
        return False
    
    def resume_channel(self, channel_id):
        if channel_id in self.channel_players:
            self.channel_players[channel_id].resume()
            return True
        return False
    
    def stop_channel(self, channel_id):
        OutputChannel.set_playback_state(channel_id, False)
        if channel_id in self.channel_players:
            self.channel_players[channel_id].stop()
            return True
        return False
    
    def reload_channel_files(self, channel_id):
        if channel_id in self.channel_players:
            self.channel_players[channel_id].reload_files()
    
    def test_device(self, device_id, duration=1.0):
        try:
            # Query device to check channel count
            device_info = sd.query_devices(device_id)
            num_channels = min(device_info['max_output_channels'], 2)  # Use stereo if available
            
            t = np.linspace(0, duration, int(Config.OUTPUT_SAMPLE_RATE * duration), endpoint=False)
            tone = 0.3 * np.sin(2 * np.pi * 1000 * t).astype(np.float32)
            
            # Create stereo array: shape should be (n_samples, channels)
            if num_channels >= 2:
                stereo = np.column_stack([tone, tone]).astype(np.float32)
                # Ensure array is C-contiguous
                stereo = np.ascontiguousarray(stereo)
            else:
                # Mono device - use single channel
                stereo = tone.astype(np.float32)
            
            sd.play(stereo, Config.OUTPUT_SAMPLE_RATE, device=device_id)
            sd.wait()
            return True
        except Exception as e:
            print(f"Error testing device {device_id}: {e}")
            return False
    
    def get_channel_status(self, channel_id):
        if channel_id in self.channel_players:
            return self.channel_players[channel_id].get_status()
        
        output_channel = OutputChannel.get(channel_id)
        if output_channel:
            total_files = 0
            if output_channel.get('stream_id'):
                total_files = len(AudioFile.get_by_stream(output_channel['stream_id']))
            return {
                'channel_id': channel_id,
                'stream_id': output_channel.get('stream_id'),
                'device_id': output_channel['device_id'],
                'is_playing': False,
                'is_paused': False,
                'current_file': None,
                'file_index': 0,
                'total_files': total_files,
                'volume': output_channel.get('volume', 1.0),
                'noise_enabled': output_channel.get('noise_enabled', False),
                'noise_volume': output_channel.get('noise_volume', 0.3),
                'noise_preset': output_channel.get('noise_preset'),
                'file_delay': output_channel.get('file_delay', 0),
                'noise_during_delay': output_channel.get('noise_during_delay', False),
                'in_delay': False,
                'play_duration': 0
            }
        return None
    
    def get_all_channel_status(self):
        output_channels = OutputChannel.get_all()
        status = {}
        for ch in output_channels:
            channel_id = ch['id']
            if channel_id in self.channel_players:
                status[channel_id] = self.channel_players[channel_id].get_status()
            else:
                total_files = 0
                if ch.get('stream_id'):
                    total_files = len(AudioFile.get_by_stream(ch['stream_id']))
                status[channel_id] = {
                    'channel_id': channel_id,
                    'stream_id': ch.get('stream_id'),
                    'device_id': ch['device_id'],
                    'is_playing': False,
                    'is_paused': False,
                    'current_file': None,
                    'file_index': 0,
                    'total_files': total_files,
                    'volume': ch.get('volume', 1.0),
                    'noise_enabled': ch.get('noise_enabled', False),
                    'noise_volume': ch.get('noise_volume', 0.3),
                    'noise_preset': ch.get('noise_preset'),
                    'file_delay': ch.get('file_delay', 0),
                    'noise_during_delay': ch.get('noise_during_delay', False),
                    'in_delay': False,
                    'play_duration': 0
                }
        return status


def convert_audio(input_path, output_path, target_sr=None, target_bitrate=None):
    """
    Convert audio file to WAV format with target sample rate and bitrate.
    Supports multiple input formats: MP3, WAV, M4A, FLAC, OGG, etc.
    
    Args:
        input_path: Path to input audio file
        output_path: Path to output WAV file
        target_sr: Target sample rate in Hz (default: Config.OUTPUT_SAMPLE_RATE)
        target_bitrate: Target bitrate in kbps (default: Config.TARGET_BITRATE)
                       For WAV files, this determines bit depth:
                       - < 256 kbps: 16-bit
                       - >= 256 kbps: 24-bit
    
    Returns:
        True if successful
    """
    if target_sr is None:
        target_sr = Config.OUTPUT_SAMPLE_RATE
    if target_bitrate is None:
        target_bitrate = Config.TARGET_BITRATE
    
    is_wav = input_path.lower().endswith('.wav')

    # Use pydub when available (needs audioop; on Python 3.13 install audioop-lts)
    if _AudioSegment is not None:
        try:
            audio = _AudioSegment.from_file(input_path)
            if audio.channels > 1:
                audio = audio.set_channels(1)
            if audio.frame_rate != target_sr:
                audio = audio.set_frame_rate(target_sr)
            if target_bitrate >= 256:
                audio = audio.set_sample_width(3)
            else:
                audio = audio.set_sample_width(2)
            audio.export(output_path, format="wav")
            return True
        except Exception as e:
            if not is_wav:
                raise Exception(f"Failed to convert audio: {str(e)}")
            # Fall through to WAV-only fallback
    elif not is_wav:
        raise Exception(
            "Converting non-WAV formats requires pydub. On Python 3.13+, run: pip install audioop-lts"
        )

    # WAV-only path (no pydub, or pydub failed for this file; is_wav is True here)
    try:
        with wave.open(input_path, 'rb') as wf:
            original_sr = wf.getframerate()
            n_channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)
            if n_channels > 1:
                audio = audio[::n_channels]
        num_samples = int(len(audio) * target_sr / original_sr)
        resampled = signal.resample(audio, num_samples).astype(np.int16)
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(target_sr)
            wf.writeframes(resampled.tobytes())
        return True
    except Exception as e2:
        raise Exception(f"Failed to convert WAV: {str(e2)}")


def resample_audio(input_path, output_path, target_sr=44100):
    """
    Legacy function for backward compatibility.
    Use convert_audio() for new code.
    """
    return convert_audio(input_path, output_path, target_sr=target_sr)


audio_service = AudioService()
