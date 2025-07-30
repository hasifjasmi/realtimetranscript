from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json
import threading
import pyaudio
import time
from websockets.sync.client import connect

app = FastAPI()

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
                "enable_speaker_diarization": True,  # Already enabled
                # Optional: for speaker names if available
                "enable_speaker_identification": True,
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
                        time.sleep(0.01)
                except Exception:
                    pass

            threading.Thread(target=record_audio, daemon=True).start()

            while is_recording:
                try:
                    message = ws.recv(timeout=2)
                    result = json.loads(message)

                    if result.get("error_code"):
                        yield f"event: error\ndata: {result['error_message']}\n\n"
                        break

                    # Only process final tokens for clean output
                    final_tokens = [
                        token for token in result.get("tokens", [])
                        if token.get("is_final")
                    ]

                    if final_tokens:
                        # Group consecutive tokens by speaker
                        speaker_segments = []
                        current_speaker = None
                        current_text = []

                        for token in final_tokens:
                            speaker = token.get("speaker", "Unknown")

                            if speaker != current_speaker:
                                # New speaker detected, save previous segment
                                if current_speaker is not None and current_text:
                                    speaker_segments.append({
                                        "speaker": current_speaker,
                                        "text": "".join(current_text).strip()
                                    })

                                # Start new segment
                                current_speaker = speaker
                                current_text = [token["text"]]
                            else:
                                # Same speaker, continue accumulating text
                                current_text.append(token["text"])

                        # Don't forget the last segment
                        if current_speaker is not None and current_text:
                            speaker_segments.append({
                                "speaker": current_speaker,
                                "text": "".join(current_text).strip()
                            })

                        # Output each speaker segment in clean format
                        for segment in speaker_segments:
                            if segment["text"]:
                                formatted_output = f"Speaker {segment['speaker']}: {segment['text']}"
                                yield f"data: {formatted_output}\n\n"

                except TimeoutError:
                    continue
                except Exception as e:
                    yield f"event: error\ndata: Error processing message: {str(e)}\n\n"
                    break

            stream.stop_stream()
            stream.close()
            ws.send(b"")
            p.terminate()

    except Exception as e:
        yield f"event: error\ndata: {str(e)}\n\n"


@app.get("/transcribe")
def stream_transcription():
    return StreamingResponse(generate_transcription(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
