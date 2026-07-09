# File: probe.py
"""Sonde reseau. But unique : verifier depuis LTS qu'un hote donne est
joignable en HTTPS ET en WebSocket, et que le proxy ne coupe pas les
connexions inactives.

Trois routes :
  GET  /healthz  -> 200 JSON. Test de joignabilite HTTP et TLS.
  GET  /         -> page de test autonome. Ouvre un WS, envoie un ping toutes
                    les 3 s, recoit un heartbeat serveur toutes les 5 s,
                    affiche l'etat, la latence, le compteur de duree, et le
                    code de fermeture si ca coupe. Reconnexion automatique.
  WS   /ws       -> echo des messages + heartbeat serveur. Teste les deux sens.

Aucune dependance hors FastAPI et uvicorn[standard]. Rien de metier ici, c'est
un instrument de mesure jetable.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

HEARTBEAT_EVERY_S = 5.0

PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sonde WebSocket LTS</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; padding: 1.2rem; background:#20262e; color:#e6e9ee; }
  h1 { font-size: 1.1rem; margin: 0 0 .8rem; }
  #dot { display:inline-block; width:.9rem; height:.9rem; border-radius:50%; background:#888; vertical-align:middle; margin-right:.4rem; }
  .ok { background:#37b24d !important; }
  .ko { background:#e03131 !important; }
  .row { margin:.35rem 0; font-variant-numeric: tabular-nums; }
  .k { color:#8bb2c2; }
  #log { margin-top:.9rem; background:#161b21; border-radius:.4rem; padding:.6rem; height:44vh; overflow:auto; font-family:ui-monospace,monospace; font-size:.8rem; white-space:pre-wrap; }
  .rx { color:#8bd5a0; } .tx { color:#9ab4ff; } .err { color:#ff9aa2; } .sys { color:#c9a227; }
</style>
</head>
<body>
<h1><span id="dot"></span><span id="status">connexion...</span></h1>
<div class="row"><span class="k">connecte depuis :</span> <span id="uptime">-</span></div>
<div class="row"><span class="k">latence aller-retour :</span> <span id="rtt">-</span></div>
<div class="row"><span class="k">reconnexions :</span> <span id="recon">0</span></div>
<div class="row"><span class="k">dernier code de fermeture :</span> <span id="close">-</span></div>
<div id="log"></div>
<script>
  var url = (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host + "/ws";
  var dot = document.getElementById("dot");
  var statusEl = document.getElementById("status");
  var logEl = document.getElementById("log");
  var uptimeEl = document.getElementById("uptime");
  var rttEl = document.getElementById("rtt");
  var reconEl = document.getElementById("recon");
  var closeEl = document.getElementById("close");
  var recon = 0, connectedAt = null, pingTimer = null, uptimeTimer = null, ws = null;

  function log(cls, msg) {
    var t = new Date().toISOString().substr(11, 12);
    var line = document.createElement("div");
    line.className = cls;
    line.textContent = t + "  " + msg;
    logEl.appendChild(line);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function tickUptime() {
    if (!connectedAt) return;
    var s = Math.floor((Date.now() - connectedAt) / 1000);
    uptimeEl.textContent = s + " s";
  }

  function connect() {
    log("sys", "ouverture vers " + url);
    ws = new WebSocket(url);

    ws.onopen = function () {
      dot.className = "ok"; statusEl.textContent = "connecte";
      connectedAt = Date.now();
      uptimeTimer = setInterval(tickUptime, 1000);
      pingTimer = setInterval(function () {
        var payload = JSON.stringify({ t: "ping", ts: Date.now() });
        ws.send(payload);
        log("tx", "ping envoye");
      }, 3000);
      log("sys", "connexion etablie");
    };

    ws.onmessage = function (ev) {
      var m;
      try { m = JSON.parse(ev.data); } catch (e) { log("rx", "recu : " + ev.data); return; }
      if (m.t === "echo" && m.ts) {
        var rtt = Date.now() - m.ts;
        rttEl.textContent = rtt + " ms";
        log("rx", "echo recu, aller-retour " + rtt + " ms");
      } else if (m.t === "heartbeat") {
        log("rx", "heartbeat serveur recu");
      } else {
        log("rx", "recu : " + ev.data);
      }
    };

    ws.onclose = function (ev) {
      dot.className = "ko"; statusEl.textContent = "coupe";
      closeEl.textContent = "code " + ev.code + (ev.reason ? " (" + ev.reason + ")" : "");
      log("err", "fermeture, code " + ev.code + " apres " +
        (connectedAt ? Math.floor((Date.now() - connectedAt) / 1000) + " s" : "?"));
      clearInterval(pingTimer); clearInterval(uptimeTimer);
      connectedAt = null;
      recon += 1; reconEl.textContent = recon;
      setTimeout(connect, 2000);
    };

    ws.onerror = function () { log("err", "erreur de socket"); };
  }

  connect();
</script>
</body>
</html>
"""


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "utc": datetime.now(timezone.utc).isoformat()})


@app.get("/")
async def index() -> HTMLResponse:
    return HTMLResponse(PAGE)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    async def echo() -> None:
        while True:
            data = await ws.receive_text()
            try:
                import json

                msg = json.loads(data)
                ts = msg.get("ts")
            except Exception:
                ts = None
            await ws.send_json({"t": "echo", "ts": ts})

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_EVERY_S)
            await ws.send_json({"t": "heartbeat", "utc": datetime.now(timezone.utc).isoformat()})

    try:
        await asyncio.gather(echo(), heartbeat())
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
