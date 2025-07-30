# Hasif Transcriber Backend

Real-time audio transcription backend using FastAPI and Soniox API for speech-to-text processing with speaker diarization and enhanced features.

## Features

- Real-time audio transcription via WebSocket
- Speaker diarization and identification
- Custom vocabulary support for "Titian System Solution" terms
- Confidence scores and timestamps
- Endpoint detection
- CORS support for web frontend integration

## Prerequisites

### System Dependencies

The project requires system-level audio libraries. Install them first:

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y python3-dev portaudio19-dev
```

**macOS:**
```bash
brew install portaudio
```

**Windows:**
```bash
# PyAudio wheels are usually available, but if building from source:
# Install Microsoft Visual C++ Build Tools
```

## Setup

### Option 1: Using uv (Recommended)

1. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```

2. Run the server:
   ```bash
   uv run python server.py
   ```

### Option 2: Using pip

1. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the server:
   ```bash
   python server.py
   ```

## API Endpoints

- `GET /transcribe` - Start real-time transcription stream (Server-Sent Events)
- `GET /health` - Health check endpoint

The server runs on `http://0.0.0.0:8000` by default.

## Configuration

The application is configured for:
- **Audio Format**: 16kHz, 16-bit, mono
- **Audio Device**: Index 1 (modify `DEVICE_INDEX` in server.py if needed)
- **CORS Origins**: `localhost:3000` and `127.0.0.1:3000`
- **Soniox Model**: `stt-rt-preview` with Malay and English language hints

## Common Problems and Solutions

### 1. PyAudio Installation Failed

**Error:**
```
fatal error: Python.h: No such file or directory
error: command 'gcc' failed with exit code 1
```

**Solution:**
Install system development packages:
```bash
# Ubuntu/Debian
sudo apt install python3-dev portaudio19-dev

# macOS
brew install portaudio

# Or try pre-built wheel
uv pip install --find-links https://www.lfd.uci.edu/~gohlke/pythonlibs/ PyAudio
```

### 2. Audio Device Not Found

**Error:**
```
OSError: [Errno -9996] Invalid input device (no default output device)
```

**Solution:**
- Check available audio devices and update `DEVICE_INDEX` in server.py
- Ensure your microphone is connected and working
- On Linux, you might need to install `alsa-utils`: `sudo apt install alsa-utils`

### 3. WebSocket Connection Failed

**Error:**
```
websockets.exceptions.InvalidStatusCode: server rejected WebSocket connection: HTTP 401
```

**Solution:**
- Verify your Soniox API key is valid
- Check your internet connection
- Ensure the API key has sufficient credits/permissions

### 4. Permission Denied for Audio Device

**Error:**
```
OSError: [Errno -9988] Stream closed
```

**Solution:**
- On Linux, add your user to the audio group: `sudo usermod -a -G audio $USER`
- Restart your session after adding to the group
- Check microphone permissions in system settings

### 5. CORS Issues

**Error:**
```
Access to fetch at 'http://localhost:8000/transcribe' has been blocked by CORS policy
```

**Solution:**
- Update the `allow_origins` list in server.py to include your frontend URL
- For development, you can temporarily use `allow_origins=["*"]`

### 6. High CPU Usage

**Problem:**
Server consuming too much CPU during transcription.

**Solution:**
- Increase the sleep time in the `record_audio()` function (line 133)
- Adjust `CHUNK` size (larger chunks = less frequent processing)
- Consider running on a more powerful machine

## Development

### Audio Device Testing

To list available audio devices:
```python
import pyaudio
p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f"Device {i}: {info['name']} - Inputs: {info['maxInputChannels']}")
```

### Testing the API

1. Start the server:
   ```bash
   uv run python server.py
   ```

2. Test health endpoint:
   ```bash
   curl http://localhost:8000/health
   ```

3. Test transcription stream:
   ```bash
   curl -N http://localhost:8000/transcribe
   ```

## Dependencies

- **FastAPI**: Web framework for building APIs
- **Uvicorn**: ASGI server for FastAPI
- **PyAudio**: Audio I/O library for microphone access
- **WebSockets**: WebSocket client for Soniox API communication

## License

This project is for internal use at Titian System Solution.