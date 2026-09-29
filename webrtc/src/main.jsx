import React from "react";
import { createRoot } from "react-dom/client";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  VideoTrack,
  useTracks
} from "@livekit/components-react";
import { Track } from "livekit-client";
import "@livekit/components-styles";
import "./styles.css";

function RoomContent() {
  const tracks = useTracks([
    { source: Track.Source.ScreenShare, withPlaceholder: false }
  ]);
  const screenTrack = tracks[0];

  return (
    <main className="room">
      <header className="room-header">
        <span className="live-dot" />
        <span>Live screen</span>
      </header>
      <section className="screen-stage">
        {screenTrack ? (
          <VideoTrack
            trackRef={screenTrack}
            className="screen-video"
          />
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

function App() {
  const [room, setRoom] = React.useState("screen-share");
  const [identity, setIdentity] = React.useState("mobile-viewer");
  const [session, setSession] = React.useState(null);
  const [error, setError] = React.useState("");

  async function joinRoom(event) {
    event.preventDefault();
    setError("");

    try {
      const query = new URLSearchParams({ room, identity });
      const response = await fetch(`/api/token?${query}`);
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Unable to join");
      setSession(body);
    } catch (joinError) {
      setError(joinError.message);
    }
  }

  if (session) {
    return <MediaRoom token={session.token} url={session.url} />;
  }

  return (
    <main className="join-page">
      <section className="join-panel">
        <p className="eyebrow">WebRTC / SFU</p>
        <h1>Screen share</h1>
        <p className="muted">Join a private room to watch the live desktop.</p>
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