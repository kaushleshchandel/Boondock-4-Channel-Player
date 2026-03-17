# Boondock 4 Channel Player

A web-based monitoring application that supports device management, audio playback, and serial communication.

## Features

- Create and manage audio streams with multiple audio files (MP3, WAV, M4A, FLAC, OGG, AAC, etc.)
- Automatic conversion to target sample rate (44100Hz) and bitrate
- Support for multiple audio formats with automatic format conversion
- 4 independent playback channels (2 stereo devices)
- Play, pause, resume, stop controls per channel
- Test tone for each channel
- USB audio device detection
- Responsive Bootstrap UI

## Installation

```bash
cd audio-player
pip install -r requirements.txt
```

**Note:** For MP3 and other compressed audio formats, you need to install `ffmpeg` on your system:
- **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt-get install ffmpeg` (Debian/Ubuntu) or `sudo yum install ffmpeg` (RHEL/CentOS)

## Configuration

Edit `config.py` to change:
- `HOST` - Server host (default: 0.0.0.0)
- `PORT` - Server port (default: 5001)
- `OUTPUT_SAMPLE_RATE` - Playback sample rate (default: 44100)
- `TARGET_BITRATE` - Target bitrate in kbps for audio conversion (default: 192)
- `TARGET_BIT_DEPTH` - Bit depth for WAV files (default: 16)

Or use environment variables:
- `AUDIO_PLAYER_HOST`
- `AUDIO_PLAYER_PORT`
- `AUDIO_PLAYER_DEBUG`
- `AUDIO_TARGET_BITRATE` - Target bitrate in kbps (default: 192)

## Usage

```bash
python app.py
```

Open http://localhost:5001 in your browser.

## API Endpoints

### Streams
- `GET /api/streams` - List all streams
- `POST /api/streams` - Create stream
- `GET /api/streams/<id>` - Get stream
- `PUT /api/streams/<id>` - Update stream
- `DELETE /api/streams/<id>` - Delete stream
- `POST /api/streams/<id>/upload` - Upload audio file (MP3, WAV, M4A, FLAC, OGG, AAC, etc.)

### Channels
- `GET /api/channels` - Get all channel status
- `POST /api/channels/<id>/load` - Load stream to channel
- `POST /api/channels/<id>/play` - Start playback
- `POST /api/channels/<id>/pause` - Pause playback
- `POST /api/channels/<id>/resume` - Resume playback
- `POST /api/channels/<id>/stop` - Stop playback
- `POST /api/channels/<id>/test` - Play test tone

### Devices
- `GET /api/devices` - List audio devices

