import "dotenv/config";
import cors from "cors";
import express from "express";
import { AccessToken } from "livekit-server-sdk";

const app = express();
const port = Number(process.env.PORT || 8787);
const livekitUrl = process.env.LIVEKIT_URL || "ws://localhost:7880";
const apiKey = process.env.LIVEKIT_API_KEY || "devkey";
const apiSecret = process.env.LIVEKIT_API_SECRET || "secret";

app.use(cors());
app.use(express.json());

app.get("/api/health", (_request, response) => {
  response.json({ ok: true, livekitUrl });
});

app.get("/api/token", async (request, response) => {
  const room = String(request.query.room || "screen-share").trim();
  const identity = String(
    request.query.identity || `viewer-${Date.now()}`
  ).trim();
  const role = String(request.query.role || "viewer").trim();

  if (!room || !identity) {
    response.status(400).json({ error: "room and identity are required" });
    return;
  }

  const token = new AccessToken(apiKey, apiSecret, {
    identity,
    name: identity,
    ttl: "2h"
  });

  token.addGrant({
    room,
    roomJoin: true,
    canSubscribe: true,
    canPublish: role === "publisher"
  });

  response.json({
    token: await token.toJwt(),
    url: livekitUrl,
    room,
    identity
  });
});

app.listen(port, "0.0.0.0", () => {
  console.log(`[WEBRTC] Token server listening on http://0.0.0.0:${port}`);
});