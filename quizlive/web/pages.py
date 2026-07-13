# File: quizlive/web/pages.py
"""Les trois vues, HTML/CSS/JS vanilla inline. Zero build, zero CDN.

Pattern reseau commun, eprouve par la sonde : le WebSocket sert de sonnette
({type:update} declenche un GET de l'etat), HTTP est la source de verite.
Reconnexion automatique 2 s, ping client 25 s, refetch sur visibilitychange.
Un gel reseau ne perd rien : au reveil, refetch complet.
"""
from __future__ import annotations

_BASE_CSS = """
  :root { --bg:#20262e; --panel:#161b21; --ink:#e6e9ee; --mut:#8ba0b3;
          --acc:#8bb2c2; --ok:#37b24d; --ko:#e03131; --warn:#c9a227; }
  * { box-sizing:border-box; }
  body { font-family:system-ui,sans-serif; margin:0; background:var(--bg);
         color:var(--ink); min-height:100vh; }
  .wrap { max-width:640px; margin:0 auto; padding:1rem; }
  h1 { font-size:1.15rem; margin:.2rem 0 1rem; color:var(--acc); }
  .panel { background:var(--panel); border-radius:.6rem; padding:1rem; margin:.7rem 0; }
  .mut { color:var(--mut); }
  .big { font-size:1.6rem; font-weight:700; }
  .ok { color:var(--ok); } .ko { color:var(--ko); } .warn { color:var(--warn); }
  button { font:inherit; border:0; border-radius:.6rem; padding:1rem;
           background:#0d3b53; color:var(--ink); width:100%; margin:.35rem 0;
           font-size:1.25rem; font-weight:700; cursor:pointer; }
  button:disabled { opacity:.45; cursor:default; }
  button.sel { outline:3px solid var(--acc); }
  input[type=text] { font:inherit; width:100%; padding:.8rem; border-radius:.5rem;
           border:1px solid #3a4654; background:#10151b; color:var(--ink); }
  .dotline { display:flex; align-items:center; gap:.45rem; font-size:.85rem;
             color:var(--mut); margin-top:.6rem; }
  #dot { width:.7rem; height:.7rem; border-radius:50%; background:#888; }
  #dot.on { background:var(--ok); } #dot.off { background:var(--ko); }
  .bar { font-family:ui-monospace,monospace; white-space:pre; font-size:1.05rem; }
  table { border-collapse:collapse; width:100%; }
  td, th { text-align:left; padding:.3rem .5rem; border-bottom:1px solid #2c3540; }
  .r { text-align:right; }
"""

_WS_JS = """
  var ws=null, wsRole=ROLE, pingT=null;
  function wsConnect(){
    var proto = location.protocol==="https:" ? "wss" : "ws";
    ws = new WebSocket(proto+"://"+location.host+"/ws/"+wsRole);
    ws.onopen = function(){ setDot(true); refresh(); 
      pingT=setInterval(function(){ try{ws.send("ping");}catch(e){} },25000); };
    ws.onmessage = function(ev){
      var m; try{ m=JSON.parse(ev.data);}catch(e){ return; }
      if(m.type==="update"){ refresh(); }
      if(m.type==="votes" && window.onVotes){ window.onVotes(m); }
    };
    ws.onclose = function(){ setDot(false); clearInterval(pingT);
      setTimeout(wsConnect, 2000); };
    ws.onerror = function(){};
  }
  function setDot(on){ var d=document.getElementById("dot");
    if(d){ d.className = on ? "on" : "off"; } }
  document.addEventListener("visibilitychange", function(){
    if(!document.hidden){ refresh(); } });
  wsConnect();
"""


def play_page() -> str:
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>XTra Game</title><style>{_BASE_CSS}</style></head>
<body><div class="wrap">
<h1>XTra Game . Quiz</h1>
<div id="app" class="panel">Chargement...</div>
<div class="dotline"><span id="dot"></span><span>connexion temps reel</span></div>
</div>
<script>
var ROLE="player";
var myVote=null, countdownT=null;

function esc(s){{ return String(s).replace(/[&<>"']/g, function(c){{
  return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]; }}); }}

async function refresh(){{
  try {{
    var r = await fetch("/api/state", {{cache:"no-store"}});
    var s = await r.json();
    render(s);
  }} catch(e) {{ /* reseau HS, la sonnette retentera */ }}
}}

function render(s){{
  clearInterval(countdownT);
  var el = document.getElementById("app");
  if(!s.registered){{ el.innerHTML = joinForm(s); return; }}

  var head = '<div class="mut">'+esc(s.me.nickname)+' . equipe '+esc(s.me.team)+
             ' . total <b>'+s.me.total+'</b></div>';

  if(s.phase==="LOBBY"){{
    el.innerHTML = head + '<p class="big">Bien recu.</p>' +
      '<p>Regarde l\\'ecran. Le quiz demarre bientot.</p>';
    return;
  }}
  if(s.phase==="OPEN"){{
    if(myVote!==null && !s.voted) myVote=null;
    var q = s.question;
    var html = head + '<p>Question <b>'+(q.index+1)+'/'+q.count+'</b>' +
      ' . <span id="cd" class="warn"></span></p>';
    if(s.voted){{
      html += '<p class="big ok">Vote enregistre.</p><p class="mut">Reponse verrouillee. Regarde l\\'ecran.</p>';
    }} else {{
      html += q.labels.map(function(l,i){{
        return '<button onclick="vote('+i+')" id="opt'+i+'">'+esc(l)+'</button>';
      }}).join("");
    }}
    el.innerHTML = html;
    startCountdown(q.remaining_s);
    return;
  }}
  if(s.phase==="CLOSED" || s.phase==="FINISHED"){{
    var html = head;
    if(s.result){{
      if(!s.result.voted){{
        html += '<p class="big warn">Pas de vote.</p>';
      }} else if(s.result.correct){{
        html += '<p class="big ok">Correct. +'+s.result.score+'</p>';
      }} else {{
        html += '<p class="big ko">Rate.</p>';
      }}
      html += '<p>Bonne reponse : <b>'+esc(s.result.correct_label)+'</b></p>';
    }}
    if(s.leaderboard){{
      html += '<div class="panel"><b>Classement</b>' + lbTable(s.leaderboard) + '</div>';
    }}
    if(s.phase==="FINISHED"){{ html += '<p class="big">Termine. Merci.</p>'; }}
    else {{ html += '<p class="mut">Prochaine question a l\\'ecran.</p>'; }}
    el.innerHTML = html;
    return;
  }}
}}

function lbTable(lb){{
  return '<table>'+lb.map(function(t,i){{
    return '<tr><td>'+(i+1)+'</td><td>'+esc(t.name)+'</td>'+
      '<td class="r"><b>'+t.avg+'</b></td><td class="r mut">'+t.members+' pers.</td></tr>';
  }}).join("")+'</table>';
}}

function startCountdown(remaining){{
  var cd = document.getElementById("cd");
  if(!cd || remaining===null) return;
  var end = Date.now() + remaining*1000;
  function tick(){{
    var left = Math.max(0, (end-Date.now())/1000);
    cd.textContent = Math.ceil(left)+" s";
    if(left<=0){{
      clearInterval(countdownT);
      cd.textContent = "temps ecoule";
      for(var i=0;i<8;i++){{ var b=document.getElementById("opt"+i); if(b) b.disabled=true; }}
    }}
  }}
  tick(); countdownT = setInterval(tick, 250);
}}

async function vote(i){{
  myVote=i;
  for(var k=0;k<8;k++){{ var b=document.getElementById("opt"+k); if(b) b.disabled=true; }}
  var sel=document.getElementById("opt"+i); if(sel) sel.classList.add("sel");
  try {{
    var r = await fetch("/api/vote", {{method:"POST",
      headers:{{"Content-Type":"application/json"}},
      body: JSON.stringify({{option:i}})}});
    var d = await r.json();
    if(d.status==="ok" || d.status==="already"){{ refresh(); }}
    else if(d.status==="closed"){{ refresh(); }}
    else {{ refresh(); }}
  }} catch(e) {{
    // reseau gele : on retente une fois apres 2 s, le serveur est idempotent
    setTimeout(function(){{ vote(i); }}, 2000);
  }}
}}

function joinForm(s){{
  var teams = s.teams.map(function(t){{
    return '<button onclick="pick(\\''+t.id+'\\', this)" data-t="'+t.id+'">'+esc(t.name)+'</button>';
  }}).join("");
  return '<p><b>Rejoindre le quiz</b></p>' +
    '<p><input type="text" id="nick" maxlength="20" placeholder="Ton prenom ou pseudo"></p>' +
    '<p class="mut">Choisis ton equipe :</p>' + teams +
    '<div class="panel" style="font-size:.85rem">' +
    'En rejoignant, un cookie strictement necessaire est depose sur ce navigateur. ' +
    'Raison : retrouver ta session si la connexion coupe (wifi instable, veille du telephone). ' +
    'Aucun suivi, aucune publicite, duree 12 h.</div>' +
    '<button class="ok" id="go" onclick="join()" disabled>Rejoindre</button>';
}}

var pickedTeam=null;
function pick(tid, btn){{
  pickedTeam=tid;
  document.querySelectorAll("button[data-t]").forEach(function(b){{ b.classList.remove("sel"); }});
  btn.classList.add("sel");
  maybeEnable();
}}
document.addEventListener("input", maybeEnable);
function maybeEnable(){{
  var n=document.getElementById("nick"); var g=document.getElementById("go");
  if(n && g) g.disabled = !(n.value.trim().length>=2 && pickedTeam);
}}

async function join(){{
  var nick=document.getElementById("nick").value.trim();
  try {{
    var r = await fetch("/api/join", {{method:"POST",
      headers:{{"Content-Type":"application/json"}},
      body: JSON.stringify({{nickname:nick, team_id:pickedTeam}})}});
    if(r.ok){{ refresh(); }}
    else {{ var d=await r.json(); alert(d.detail || "Erreur"); }}
  }} catch(e) {{ alert("Reseau indisponible, reessaie."); }}
}}

{_WS_JS}
</script></body></html>"""


def present_page() -> str:
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>XTra Game . Ecran</title><style>{_BASE_CSS}
  body {{ font-size:1.35rem; }}
  .wrap {{ max-width:1100px; }}
  .huge {{ font-size:3rem; font-weight:800; }}
  #qr img {{ width:340px; height:340px; background:#fff; padding:12px; border-radius:8px; }}
  .cols {{ display:flex; gap:2rem; flex-wrap:wrap; }}
  .cols > div {{ flex:1; min-width:320px; }}
</style></head>
<body><div class="wrap">
<div id="app">Chargement...</div>
<div class="dotline"><span id="dot"></span><span>temps reel</span></div>
</div>
<script>
var ROLE="present";
function esc(s){{ return String(s).replace(/[&<>"']/g, function(c){{
  return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]; }}); }}

window.onVotes = function(m){{
  var v = document.getElementById("votesLine");
  if(v) v.innerHTML = 'Votes : <b class="huge">'+m.votes+'</b> / '+m.participants;
}};

async function refresh(){{
  try {{
    var r = await fetch("/api/present-state", {{cache:"no-store"}});
    render(await r.json());
  }} catch(e) {{}}
}}

function bars(counts, labels, correctLabel){{
  var total = counts.reduce(function(a,b){{return a+b;}},0) || 1;
  var maxw = 30;
  return counts.map(function(c,i){{
    var w = Math.round(maxw * c / total);
    var mark = (labels[i]===correctLabel) ? "  <= bonne reponse" : "";
    return esc(labels[i]).padEnd(8) + " " +
      "&#9608;".repeat(w) + " " + c + mark;
  }}).join("\\n");
}}

function lbTable(lb){{
  return '<table>'+lb.map(function(t,i){{
    return '<tr><td>'+(i+1)+'</td><td>'+esc(t.name)+'</td>'+
      '<td class="r"><b>'+t.avg+'</b></td><td class="r mut">'+t.members+' pers.</td></tr>';
  }}).join("")+'</table>';
}}

function render(s){{
  var el=document.getElementById("app");
  if(s.phase==="LOBBY"){{
    var teams = s.teams.map(function(t){{
      return '<tr><td>'+esc(t.name)+'</td><td class="r">'+t.members+'</td></tr>';
    }}).join("");
    el.innerHTML =
      '<h1>XTra Game 2026 . Test de Turing inverse</h1>' +
      '<div class="cols"><div>' +
      '<p class="big">Scannez pour rejoindre :</p>' +
      '<div id="qr"><img src="/api/qr.svg" alt="QR"></div>' +
      '<p class="mut">'+esc(s.join_url)+'</p>' +
      '</div><div>' +
      '<p>Participants : <b class="huge">'+s.participants+'</b></p>' +
      '<table>'+teams+'</table>' +
      '</div></div>';
    return;
  }}
  if(s.phase==="OPEN"){{
    var q=s.question;
    el.innerHTML =
      '<h1>Question '+(q.index+1)+' / '+q.count+'</h1>' +
      '<p class="mut">Repondez sur vos telephones.</p>' +
      '<p id="votesLine">Votes : <b class="huge">'+s.votes+'</b> / '+s.participants+'</p>';
    return;
  }}
  if(s.phase==="CLOSED" || s.phase==="FINISHED"){{
    var html='';
    if(s.question && s.stats){{
      html += '<h1>Question '+(s.question.index+1)+' . resultat</h1>' +
        '<div class="cols"><div>' +
        '<div class="panel bar">'+bars(s.stats.counts, s.question.labels, s.correct_label)+'</div>' +
        '<p>Bonne reponse : <b class="ok">'+esc(s.correct_label)+'</b>' +
        ' . corrects : '+s.stats.correct+' / '+s.stats.total+'</p>' +
        '<div class="panel"><b>Par equipe (% corrects)</b><table>' +
        s.stats_by_team.map(function(t){{
          return '<tr><td>'+esc(t.name)+'</td><td class="r">'+t.correct+'/'+t.total+
                 '</td><td class="r"><b>'+t.pct+' %</b></td></tr>';
        }}).join("") + '</table></div>' +
        '</div><div>' +
        '<div class="panel"><b>Classement</b>'+lbTable(s.leaderboard)+'</div>' +
        '</div></div>';
    }}
    if(s.phase==="FINISHED"){{
      html += '<h1>Classement final</h1>' +
        '<div class="panel">'+lbTable(s.leaderboard)+'</div>' +
        '<div class="panel"><b>Corrects par question (%)</b><table>' +
        '<tr><th>Q</th><th class="r">global</th>' +
        Object.keys(s.per_question[0].teams).map(function(n){{
          return '<th class="r">'+esc(n)+'</th>'; }}).join("") + '</tr>' +
        s.per_question.map(function(row){{
          return '<tr><td>Q'+row.index+'</td><td class="r"><b>'+row.pct+'</b></td>' +
            Object.values(row.teams).map(function(p){{
              return '<td class="r">'+p+'</td>'; }}).join("") + '</tr>';
        }}).join("") + '</table></div>';
    }}
    el.innerHTML = html;
    return;
  }}
}}
{_WS_JS}
</script></body></html>"""


def host_page() -> str:
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>XTra Game . Controle</title><style>{_BASE_CSS}</style></head>
<body><div class="wrap">
<h1>Controle du quiz</h1>
<div id="app" class="panel">Chargement...</div>
<div class="panel">
  <button id="bOpen" onclick="act('open')">Ouvrir la question suivante</button>
  <button id="bClose" onclick="act('close')">Fermer le vote et reveler</button>
  <button id="bFinish" onclick="act('finish')">Terminer le quiz</button>
  <p class="mut" id="msg"></p>
</div>
<div class="panel">
  <button id="bReset" style="background:#5a1e1e" onclick="doReset()">Recommencer a zero</button>
  <p class="mut">Efface participants et scores, retour au lobby. Demande confirmation.</p>
</div>
<div class="dotline"><span id="dot"></span><span>temps reel</span></div>
</div>
<script>
var ROLE="host";
var KEY = new URLSearchParams(location.search).get("key") || "";
function esc(s){{ return String(s).replace(/[&<>"']/g, function(c){{
  return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]; }}); }}

window.onVotes = function(m){{
  var v=document.getElementById("votesLine");
  if(v) v.textContent = "Votes : "+m.votes+" / "+m.participants;
}};

async function refresh(){{
  try {{
    var r = await fetch("/api/present-state", {{cache:"no-store"}});
    render(await r.json());
  }} catch(e) {{}}
}}

function render(s){{
  var el=document.getElementById("app");
  var q = s.question ? ('Question '+(s.question.index+1)+' / '+s.question.count) : 'Aucune question ouverte';
  el.innerHTML =
    '<p>Phase : <b>'+s.phase+'</b></p>' +
    '<p>'+q+'</p>' +
    '<p id="votesLine">'+(s.votes!==undefined ? 'Votes : '+s.votes+' / '+s.participants
                          : 'Participants : '+s.participants)+'</p>' +
    '<p class="mut">Suivez votre PowerPoint. Ouvrez a la slide question, fermez avant la slide revelation.</p>';
  document.getElementById("bOpen").disabled  = !(s.phase==="LOBBY" || (s.phase==="CLOSED" && !s.is_last));
  document.getElementById("bClose").disabled = !(s.phase==="OPEN");
  document.getElementById("bFinish").disabled= !(s.phase==="CLOSED");
}}

async function act(a){{
  var m=document.getElementById("msg"); m.textContent="";
  try {{
    var r = await fetch("/api/host/"+a+"?key="+encodeURIComponent(KEY), {{method:"POST"}});
    var d = await r.json();
    if(!r.ok){{ m.textContent = d.detail || "refuse"; }}
  }} catch(e) {{ m.textContent = "reseau indisponible"; }}
}}

async function doReset(){{
  if(!confirm("Tout effacer et revenir au lobby ? Participants et scores seront perdus.")) return;
  var m=document.getElementById("msg"); m.textContent="";
  try {{
    var r = await fetch("/api/host/reset?key="+encodeURIComponent(KEY), {{method:"POST"}});
    var d = await r.json();
    if(!r.ok){{ m.textContent = d.detail || "refuse"; }}
    else {{ m.textContent = "Quiz remis a zero."; }}
  }} catch(e) {{ m.textContent = "reseau indisponible"; }}
}}
{_WS_JS}
</script></body></html>"""
