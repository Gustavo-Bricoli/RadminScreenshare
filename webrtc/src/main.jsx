import React from "react";
import { createRoot } from "react-dom/client";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  VideoTrack,
  useRoomContext,
  useTracks
} from "@livekit/components-react";
import {
  createLocalScreenTracks,
  Room,
  RoomEvent,
  Track
} from "livekit-client";
import "@livekit/components-styles";
import "./styles.css";

function RoomContent() {
  const room = useRoomContext();
  const stageRef = React.useRef(null);
  const [isFullscreen, setIsFullscreen] = React.useState(false);
  const tracks = useTracks([
    { source: Track.Source.ScreenShare, withPlaceholder: false }
  ]);
  const screenTrack = tracks[0];

  React.useEffect(() => {
    console.info("[WEBRTC] Viewer room state", {
      state: room.state,
      room: room.name,
      remoteParticipants: Array.from(
        room.remoteParticipants.values(),
        (participant) => participant.identity
      )
    });

    const onConnected = () => {
      console.info("[WEBRTC] Connected to LiveKit", {
        room: room.name,
        remoteParticipants: room.remoteParticipants.size
      });
    };
    const onDisconnected = (reason) => {
      console.warn("[WEBRTC] Disconnected from LiveKit", { reason });
    };
    const onConnectionStateChanged = (state) => {
      console.info("[WEBRTC] LiveKit connection state", { state });
    };
    const onParticipantConnected = (participant) => {
      console.info("[WEBRTC] Remote participant connected", {
        identity: participant.identity
      });
    };
    const onParticipantDisconnected = (participant) => {
      console.warn("[WEBRTC] Remote participant disconnected", {
        identity: participant.identity
      });
    };
    const onTrackSubscribed = (track, publication, participant) => {
      console.info("[WEBRTC] Remote track subscribed", {
        identity: participant.identity,
        kind: track.kind,
        source: publication.source,
        trackSid: publication.trackSid
      });
    };
    const onTrackPublished = (publication, participant) => {
      console.info("[WEBRTC] Remote track published", {
        identity: participant.identity,
        kind: publication.kind,
        source: publication.source,
        trackSid: publication.trackSid
      });
    };
    const onTrackSubscriptionFailed = (trackSid, participant) => {
      console.error("[WEBRTC] Remote track subscription failed", {
        identity: participant.identity,
        trackSid
      });
    };

    room.on(RoomEvent.Connected, onConnected);
    room.on(RoomEvent.Disconnected, onDisconnected);
    room.on(RoomEvent.ConnectionStateChanged, onConnectionStateChanged);
    room.on(RoomEvent.ParticipantConnected, onParticipantConnected);
    room.on(RoomEvent.ParticipantDisconnected, onParticipantDisconnected);
    room.on(RoomEvent.TrackPublished, onTrackPublished);
    room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
    room.on(RoomEvent.TrackSubscriptionFailed, onTrackSubscriptionFailed);

    return () => {
      room.off(RoomEvent.Connected, onConnected);
      room.off(RoomEvent.Disconnected, onDisconnected);
      room.off(RoomEvent.ConnectionStateChanged, onConnectionStateChanged);
      room.off(RoomEvent.ParticipantConnected, onParticipantConnected);
      room.off(RoomEvent.ParticipantDisconnected, onParticipantDisconnected);
      room.off(RoomEvent.TrackPublished, onTrackPublished);
      room.off(RoomEvent.TrackSubscribed, onTrackSubscribed);
      room.off(RoomEvent.TrackSubscriptionFailed, onTrackSubscriptionFailed);
    };
  }, [room]);

  React.useEffect(() => {
    if (screenTrack) {
      console.info("[WEBRTC] Screen track available to viewer", {
        identity: screenTrack.participant.identity,
        trackSid: screenTrack.publication.trackSid
      });
    }
  }, [screenTrack]);

  React.useEffect(() => {
    const stage = stageRef.current;
    const updateFullscreen = () => {
      if (document.fullscreenEnabled) {
        setIsFullscreen(document.fullscreenElement === stage);
      }
    };

    document.addEventListener("fullscreenchange", updateFullscreen);
    return () => {
      document.removeEventListener("fullscreenchange", updateFullscreen);
    };
  }, []);

  React.useEffect(() => {
    if (!isFullscreen || document.fullscreenElement) return;

    const exitOnEscape = (event) => {
      if (event.key === "Escape") setIsFullscreen(false);
    };
    document.addEventListener("keydown", exitOnEscape);
    return () => document.removeEventListener("keydown", exitOnEscape);
  }, [isFullscreen]);

  async function toggleFullscreen() {
    const stage = stageRef.current;
    if (!stage) return;

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (stage.requestFullscreen) {
        await stage.requestFullscreen();
      } else {
        setIsFullscreen((fullscreen) => !fullscreen);
      }
    } catch (fullscreenError) {
      console.warn("[WEBRTC] Fullscreen request failed; using page fullscreen", fullscreenError);
      setIsFullscreen((fullscreen) => !fullscreen);
    }
  }

  return (
    <main className={`room${isFullscreen ? " is-fullscreen" : ""}`}>
      <header className="room-header">
        <span className="live-dot" />
        <span>Live screen</span>
      </header>
      <section className="screen-stage" ref={stageRef}>
        {screenTrack ? (
          <>
            <VideoTrack trackRef={screenTrack} className="screen-video" />
            <button
              className="fullscreen-button"
              type="button"
              onClick={toggleFullscreen}
              aria-label={isFullscreen ? "Sair da tela cheia" : "Abrir tela cheia"}
              title={isFullscreen ? "Sair da tela cheia" : "Tela cheia"}
            >
              {isFullscreen ? "Sair da tela cheia" : "Tela cheia"}
            </button>
          </>
        ) : (
          <div className="empty-state">Waiting for the sender...</div>
        )}
      </section>
    </main>
  );
}

function MediaRoom({ token, url }) {
  return (
    <LiveKitRoom
      token={token}
      serverUrl={url}
      connect
      audio={false}
      video={false}
      data-lk-theme="default"
    >
      <RoomContent />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

function BrowserPublisher({ token, url, onExit }) {
  const videoRef = React.useRef(null);
  const roomRef = React.useRef(null);
  const tracksRef = React.useRef([]);
  const [status, setStatus] = React.useState("Starting screen capture...");
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;

    async function startPublisher() {
      try {
        const room = new Room();
        roomRef.current = room;
        const tracks = await createLocalScreenTracks({
          audio: true,
          resolution: {
            width: 1920,
            height: 1080,
            frameRate: 30
          }
        });
        if (cancelled) {
          tracks.forEach((track) => track.stop());
          return;
        }

        tracksRef.current = tracks;
        await room.connect(url, token);
        for (const track of tracks) {
          await room.localParticipant.publishTrack(track, {
            source: track.source,
            name: track.kind === "video" ? "screen" : "system-audio"
          });
        }

        const videoTrack = tracks.find((track) => track.kind === "video");
        if (videoTrack && videoRef.current) {
          videoTrack.attach(videoRef.current);
        }
        setStatus("Browser publisher is live");
        room.on(RoomEvent.Disconnected, () => {
          if (!cancelled) setStatus("Publisher disconnected");
        });
      } catch (publisherError) {
        if (!cancelled) {
          setError(publisherError.message || "Unable to publish screen");
          setStatus("");
        }
      }
    }

    startPublisher();
    return () => {
      cancelled = true;
      if (videoRef.current) {
        tracksRef.current.forEach((track) => track.detach(videoRef.current));
      }
      tracksRef.current.forEach((track) => track.stop());
      roomRef.current?.disconnect();
    };
  }, [token, url]);

  function stopPublisher() {
    roomRef.current?.disconnect();
    onExit();
  }

  return (
    <main className="publisher-page">
      <section className="publisher-panel">
        <p className="eyebrow">WebRTC / Publisher</p>
        <h1>Browser sender</h1>
        <p className="muted">{status || error}</p>
        <video ref={videoRef} autoPlay muted playsInline className="publisher-preview" />
        <button type="button" onClick={stopPublisher}>Stop sharing</button>
      </section>
    </main>
  );
}

function PythonPublisherInfo({ onExit }) {
  return (
    <main className="join-page">
      <section className="join-panel">
        <p className="eyebrow">WebRTC / Publisher</p>
        <h1>Python sender</h1>
        <p className="muted">
          Keep this page open and start the existing publisher in a terminal.
        </p>
        <pre className="command">cd webrtc{"\n"}python publisher.py</pre>
        <button type="button" onClick={onExit}>Back</button>
      </section>
    </main>
  );
}

function App() {
  const [room, setRoom] = React.useState("screen-share");
  const [identity, setIdentity] = React.useState("mobile-viewer");
  const [session, setSession] = React.useState(null);
  const [error, setError] = React.useState("");
  const [mode, setMode] = React.useState("viewer");

  function selectMode(nextMode) {
    setMode(nextMode);
    if (nextMode === "browser-publisher") {
      setIdentity("browser-sender");
    } else if (nextMode === "viewer") {
      setIdentity("mobile-viewer");
    }
  }

  async function joinRoom(event) {
    event.preventDefault();
    setError("");
    console.info("[WEBRTC] Requesting viewer token", {
      origin: window.location.origin,
      room,
      identity
    });

    try {
      const role = mode === "viewer" ? "viewer" : "publisher";
      const query = new URLSearchParams({ room, identity, role });
      const response = await fetch(`/api/token?${query}`);
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Unable to join");
      console.info("[WEBRTC] Viewer token received", {
        room: body.room,
        identity: body.identity,
        livekitUrl: body.url
      });
      setSession(body);
    } catch (joinError) {
      console.error("[WEBRTC] Viewer token request failed", joinError);
      setError(joinError.message);
    }
  }

  if (session && mode === "browser-publisher") {
    return (
      <BrowserPublisher
        token={session.token}
        url={session.url}
        onExit={() => {
          setSession(null);
          setMode("viewer");
        }}
      />
    );
  }

  if (mode === "python-publisher") {
    return <PythonPublisherInfo onExit={() => setMode("viewer")} />;
  }

  if (session) {
    return <MediaRoom token={session.token} url={session.url} />;
  }

  return (
    <main className="join-page">
      <section className="join-panel">
        <p className="eyebrow">WebRTC / SFU</p>
        <h1>Screen share</h1>
        <p className="muted">Choose how this computer should connect to the room.</p>
        <div className="mode-grid">
          <button type="button" onClick={() => selectMode("viewer")}>
            Watch stream
          </button>
          <button type="button" onClick={() => selectMode("browser-publisher")}>
            Publish from browser
          </button>
          <button type="button" onClick={() => selectMode("python-publisher")}>
            Use Python publisher
          </button>
        </div>
        <form onSubmit={joinRoom}>
          <label>
            Room
            <input value={room} onChange={(event) => setRoom(event.target.value)} />
          </label>
          <label>
            Name
            <input value={identity} onChange={(event) => setIdentity(event.target.value)} />
          </label>
          <button type="submit">Join room</button>
        </form>
        {error && <p className="error">{error}</p>}
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);