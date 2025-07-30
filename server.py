from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import threading
import pyaudio
import time
from websockets.sync.client import connect
from datetime import datetime

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Your Soniox API key
api_key = "e2a6b6253d4175f8d992e2b63913d982daf8892951a97f55d461325fe294f0a3"
websocket_url = "wss://stt-rt.soniox.com/transcribe-websocket"

CHUNK = 4096
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
DEVICE_INDEX = 1


def generate_transcription():
    p = pyaudio.PyAudio()
    is_recording = True

    try:
        with connect(websocket_url, close_timeout=2) as ws:
            config = {
                "api_key": api_key,
                "audio_format": "auto",
                "model": "stt-rt-preview",
                "language_hints": ["ms", "en"],
                "enable_dictation": True,
                "enable_punctuation": True,
                "enable_speaker_diarization": True,
                "enable_speaker_identification": True,

                # Enhanced features
                "include_nonfinal": True,  # Include non-final tokens for real-time display
                "enable_global_speaker_diarization": True,  # Better speaker tracking
                "enable_streaming_speaker_diarization": True,

                # Real-time latency control (max 1 second delay)
                "speech_context": {
                    "max_alternatives": 1,
                    "enable_automatic_punctuation": True,
                    "enable_word_time_offsets": True,  # Enable timestamps
                    "enable_word_confidence": True,    # Enable confidence scores
                    "speech_adaptation": {
                        "phrase_sets": [
                            {
                                "name": "custom_terms",
                                "phrases": [
                                    {"value": "Titian System Solution", "boost": 20},
                                    {"value": "Titian", "boost": 15},
                                    {"value": "SI", "boost": 10},
                                    {"value": "API", "boost": 10},
                                    {"value": "system", "boost": 5},
                                    {"value": "solution", "boost": 5}
                                ]
                            }
                        ]
                    }
                },

                # Endpoint detection
                "enable_endpoint_detection": True,
                "endpoint_detection_config": {
                    # 2 seconds before considering speech started
                    "start_of_speech_timeout_ms": 2000,
                    # 1 second of silence before considering speech ended
                    "end_of_speech_timeout_ms": 1000,
                    "max_speech_timeout_ms": 30000       # Max 30 seconds of continuous speech
                },

                # Custom vocabulary for better recognition
                "custom_vocabulary": [
                    "Titian System Solution",
                    "Titian",
                    "SI",
                    "sistem",
                    "penyelesaian",
                    "API",
                    "websocket",
                    "real-time",
                    "latency"
                ]
            }

            ws.send(json.dumps(config))
            response = ws.recv(timeout=5)
            data = json.loads(response)
            if data.get("error_code"):
                yield f"event: error\ndata: {data['error_message']}\n\n"
                return

            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=DEVICE_INDEX,
                frames_per_buffer=CHUNK
            )

            wav_header = (
                b'RIFF' + (36).to_bytes(4, 'little') + b'WAVEfmt ' +
                (16).to_bytes(4, 'little') + (1).to_bytes(2, 'little') +
                CHANNELS.to_bytes(2, 'little') + RATE.to_bytes(4, 'little') +
                (RATE * CHANNELS * 2).to_bytes(4, 'little') +
                (CHANNELS * 2).to_bytes(2, 'little') +
                (16).to_bytes(2, 'little') + b'data' +
                (0).to_bytes(4, 'little')
            )
            ws.send(wav_header)

            def record_audio():
                try:
                    while is_recording:
                        data = stream.read(CHUNK, exception_on_overflow=False)
                        ws.send(data)
                        time.sleep(0.01)  # Small delay to control latency
                except Exception:
                    pass

            threading.Thread(target=record_audio, daemon=True).start()

            # Track partial transcripts for real-time updates
            partial_transcripts = {}

            while is_recording:
                try:
                    message = ws.recv(timeout=2)
                    result = json.loads(message)

                    if result.get("error_code"):
                        yield f"event: error\ndata: {result['error_message']}\n\n"
                        break

                    # Handle endpoint detection events
                    if result.get("event_type") == "endpoint_detected":
                        endpoint_info = {
                            "type": "endpoint",
                            "event": result.get("endpoint_type", "unknown"),
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(endpoint_info)}\n\n"
                        continue

                    tokens = result.get("tokens", [])

                    if tokens:
                        # Process both final and non-final tokens
                        for token in tokens:
                            speaker = token.get("speaker", "Unknown")
                            text = token.get("text", "")
                            is_final = token.get("is_final", False)
                            confidence = token.get("confidence", 0.0)
                            # Convert to seconds
                            start_time = token.get("start_time_ms", 0) / 1000.0
                            end_time = token.get("end_time_ms", 0) / 1000.0

                            # Create enhanced transcript object
                            transcript_data = {
                                "type": "transcript",
                                "speaker": speaker,
                                "text": text,
                                "is_final": is_final,
                                "confidence": round(confidence, 3),
                                "start_time": round(start_time, 2),
                                "end_time": round(end_time, 2),
                                "duration": round(end_time - start_time, 2),
                                "timestamp": datetime.now().isoformat(),
                                "token_id": token.get("token_id", "")
                            }

                            # For real-time display, we'll send both partial and final
                            if is_final:
                                # Final token - send complete transcript
                                transcript_data["status"] = "final"
                                # Clear any partial transcript for this speaker
                                if speaker in partial_transcripts:
                                    del partial_transcripts[speaker]
                            else:
                                # Non-final token - accumulate for real-time display
                                transcript_data["status"] = "partial"
                                if speaker not in partial_transcripts:
                                    partial_transcripts[speaker] = []
                                partial_transcripts[speaker].append(text)
                                transcript_data["partial_text"] = "".join(
                                    partial_transcripts[speaker])

                            # Only send if confidence is above threshold (optional filter)
                            if confidence > 0.3 or is_final:  # Lower threshold for partial, require higher for final
                                yield f"data: {json.dumps(transcript_data)}\n\n"

                        # Send aggregated final transcripts (grouped by speaker)
                        final_tokens = [
                            token for token in tokens if token.get("is_final")]
                        if final_tokens:
                            # Group by speaker for cleaner output
                            speaker_segments = {}
                            for token in final_tokens:
                                speaker = token.get("speaker", "Unknown")
                                if speaker not in speaker_segments:
                                    speaker_segments[speaker] = {
                                        "texts": [],
                                        "confidences": [],
                                        "start_times": [],
                                        "end_times": []
                                    }

                                speaker_segments[speaker]["texts"].append(
                                    token.get("text", ""))
                                speaker_segments[speaker]["confidences"].append(
                                    token.get("confidence", 0.0))
                                speaker_segments[speaker]["start_times"].append(
                                    token.get("start_time_ms", 0) / 1000.0)
                                speaker_segments[speaker]["end_times"].append(
                                    token.get("end_time_ms", 0) / 1000.0)

                            # Send aggregated segments
                            for speaker, segment_data in speaker_segments.items():
                                if segment_data["texts"]:
                                    combined_text = "".join(
                                        segment_data["texts"]).strip()
                                    avg_confidence = sum(
                                        segment_data["confidences"]) / len(segment_data["confidences"])
                                    start_time = min(
                                        segment_data["start_times"])
                                    end_time = max(segment_data["end_times"])

                                    aggregated_data = {
                                        "type": "segment",
                                        "speaker": speaker,
                                        "text": combined_text,
                                        "is_final": True,
                                        "confidence": round(avg_confidence, 3),
                                        "start_time": round(start_time, 2),
                                        "end_time": round(end_time, 2),
                                        "duration": round(end_time - start_time, 2),
                                        "timestamp": datetime.now().isoformat(),
                                        "word_count": len(combined_text.split())
                                    }

                                    yield f"data: {json.dumps(aggregated_data)}\n\n"

                except TimeoutError:
                    # Send heartbeat to keep connection alive
                    heartbeat = {
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat(),
                        "status": "listening"
                    }
                    yield f"data: {json.dumps(heartbeat)}\n\n"
                    continue
                except Exception as e:
                    error_data = {
                        "type": "error",
                        "message": f"Error processing message: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    break

            stream.stop_stream()
            stream.close()
            ws.send(b"")  # Send empty message to close websocket
            p.terminate()

    except Exception as e:
        error_data = {
            "type": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }
        yield f"data: {json.dumps(error_data)}\n\n"


@app.get("/transcribe")
def stream_transcription():
    """
    Stream real-time transcription with enhanced features:
    - Timestamps and confidence scores
    - Final vs non-final tokens
    - Real-time latency control (~1s max delay)
    - Endpoint detection
    - Custom vocabulary for "Titian System Solution" and related terms
    """
    return StreamingResponse(
        generate_transcription(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
