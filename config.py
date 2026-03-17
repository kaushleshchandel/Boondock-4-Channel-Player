"""Configuration for the Boondock Monitor application."""
import os

class Config:
    # Server settings
    HOST = os.environ.get('AUDIO_PLAYER_HOST', '0.0.0.0')
    PORT = int(os.environ.get('AUDIO_PLAYER_PORT', 5001))
    DEBUG = os.environ.get('AUDIO_PLAYER_DEBUG', 'false').lower() == 'true'
    
    # LLM/Ollama settings
    OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://10.0.2.47:11435')
    OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:14b-instruct')
    
    # Audio settings
    OUTPUT_SAMPLE_RATE = 44100
    INPUT_SAMPLE_RATE = 8000
    CHANNELS_PER_DEVICE = 2
    NUM_PLAYBACK_CHANNELS = 4  # 2 devices x 2 channels each
    BLOCK_SIZE = 2048
    TARGET_BITRATE = int(os.environ.get('AUDIO_TARGET_BITRATE', '192'))  # kbps for compressed formats
    TARGET_BIT_DEPTH = 16  # bits per sample for WAV files
    
    # Storage
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    STREAMS_FOLDER = os.path.join(os.path.dirname(__file__), 'streams')
    NOISE_FOLDER = os.path.join(os.path.dirname(__file__), 'noise')
    FIRMWARE_FOLDER = os.path.join(os.path.dirname(__file__), 'firmwares')
    DATABASE_FILE = os.path.join(os.path.dirname(__file__), 'audio_player.db')
    
    # Ensure directories exist
    @classmethod
    def init_folders(cls):
        os.makedirs(cls.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(cls.STREAMS_FOLDER, exist_ok=True)
        os.makedirs(cls.NOISE_FOLDER, exist_ok=True)
        os.makedirs(cls.FIRMWARE_FOLDER, exist_ok=True)

Config.init_folders()

