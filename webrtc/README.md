# WebRTC/SFU experimental version

This directory is independent from the legacy Python sender and viewer.
The legacy commands remain unchanged:

```powershell
python ..\screenshot_audioopus_sender.py
python ..\screenshot_audioopus_viewer.py
```

## Current pieces

- `docker-compose.yml`: local LiveKit SFU.
- `server.mjs`: Node token/health server.
- `src/`: React browser viewer.
- `publisher.py`: separate Python LiveKit publisher for screen and system audio.
- `video_sender.py` and `audio_sender.py` in the parent directory remain legacy modules and are not imported here.

The React viewer is subscribe-only. `publisher.py` captures the desktop/audio and publishes one WebRTC connection to LiveKit.

## Local start

From this directory:

```powershell
Copy-Item .env.example .env
docker compose up -d
npm run dev

python publisher.py
```

Install the publisher dependencies once:

```powershell
python -m pip install -r requirements.txt
```

The publisher defaults to 1280x720 at 15 FPS to reduce CPU and RAM use. You can
override these values with `LIVEKIT_VIDEO_MAX_WIDTH`, `LIVEKIT_VIDEO_MAX_HEIGHT`
and `LIVEKIT_VIDEO_FPS`.

Open `http://localhost:5173` on the PC. For a phone on the same Wi-Fi, set `LIVEKIT_URL` in `.env` to the PC's LAN address, for example:

```text
LIVEKIT_URL=ws://192.168.1.50:7880
```

Then open `http://192.168.1.50:5173` on the phone and allow TCP `5173`, TCP `17880`, TCP `17881`, and UDP `17882` through the PC firewall as needed. Update `livekit.yaml` when the host LAN IP changes.

This local setup uses LiveKit development credentials only. It is not an internet-facing deployment and does not yet include user authentication.