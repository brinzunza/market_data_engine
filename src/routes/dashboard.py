"""
Dashboard route — serves the live monitoring UI at GET /monitor.

Single self-contained HTML page.  No build step, no static files, no extra
packages.  Connects to the existing /ws WebSocket, subscribes to
__METRICS__, and renders four live-updating Chart.js line charts with a
user-controllable sliding window.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #111;
  color: #aaa;
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 13px;
  min-height: 100vh;
  padding: 32px 28px;
}

/* ---- top bar ---- */
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
  flex-wrap: wrap;
  gap: 12px;
}
.top h1 {
  font-size: 18px;
  font-weight: 500;
  color: #fff;
  letter-spacing: -0.4px;
}
.top-right { display: flex; align-items: center; gap: 16px; }

/* status dot */
.status { display: flex; align-items: center; gap: 7px; font-size: 12px; color: #666; }
.status .dot {
  width: 7px; height: 7px; border-radius: 50%; background: #555;
  transition: background .4s;
}
.status .dot.live { background: #4ade80; box-shadow: 0 0 6px #4ade8066; }

/* window pills */
.pills { display: flex; gap: 4px; }
.pills button {
  background: none;
  border: 1px solid #2a2a2a;
  color: #666;
  padding: 4px 11px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
  transition: all .15s;
}
.pills button:hover         { border-color: #444; color: #aaa; }
.pills button.active        { border-color: #fff; color: #fff; background: #1e1e1e; }

/* ---- cards row ---- */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 10px;
  margin-bottom: 28px;
}
.card {
  background: #161616;
  border: 1px solid #222;
  border-radius: 8px;
  padding: 14px 16px;
}
.card-label { font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 5px; }
.card-val   { font-size: 20px; font-weight: 600; color: #fff; }
.card-val .unit { font-size: 11px; font-weight: 400; color: #555; margin-left: 2px; }

/* ---- charts ---- */
.charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
@media (max-width: 720px) { .charts { grid-template-columns: 1fr; } }

.chart-box {
  background: #161616;
  border: 1px solid #222;
  border-radius: 8px;
  padding: 18px 18px 12px;
}
.chart-box h3 {
  font-size: 12px;
  font-weight: 500;
  color: #777;
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chart-box h3 .legend { display: flex; gap: 12px; }
.chart-box h3 .legend span {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: #555;
}
.chart-box h3 .legend .ln { width: 18px; height: 2px; border-radius: 1px; }

.chart-wrap { position: relative; height: 150px; }

/* ---- alerts ---- */
.alerts {
  margin-top: 20px;
  background: #161616;
  border: 1px solid #222;
  border-radius: 8px;
  padding: 16px 18px;
}
.alerts h3 { font-size: 12px; font-weight: 500; color: #777; margin-bottom: 10px; }
.alert-list { max-height: 160px; overflow-y: auto; display: flex; flex-direction: column; gap: 5px; }
.alert-list::-webkit-scrollbar { width: 4px; }
.alert-list::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }

.alert-row {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 8px 10px;
  border-radius: 6px;
  background: #1c1c1c;
  border-left: 3px solid #eab308;
}
.alert-row.critical { border-left-color: #ef4444; }
.alert-row .a-msg { color: #ccc; font-size: 13px; }
.alert-row .a-meta { font-size: 11px; color: #555; margin-top: 2px; }
.alert-row .a-tag {
  display: inline-block; padding: 1px 6px; border-radius: 8px;
  font-size: 10px; font-weight: 700; text-transform: uppercase; margin-right: 4px;
}
.a-tag.warning  { background: #eab30822; color: #eab308; }
.a-tag.critical { background: #ef444422; color: #ef4444; }

.no-alert { color: #444; font-size: 12px; }
</style>
</head>
<body>

<!-- top bar -->
<div class="top">
  <h1>Monitor</h1>
  <div class="top-right">
    <div class="status"><span class="dot" id="dot"></span><span id="statusTxt">connecting</span></div>
    <div class="pills" id="pills">
      <button data-w="30">30s</button>
      <button data-w="60" class="active">60s</button>
      <button data-w="120">2m</button>
      <button data-w="300">5m</button>
    </div>
  </div>
</div>

<!-- cards -->
<div class="cards">
  <div class="card" id="c-uptime">  <div class="card-label">Uptime</div>  <div class="card-val">—<span class="unit">s</span></div></div>
  <div class="card" id="c-gen">     <div class="card-label">Gen Rate</div><div class="card-val">—<span class="unit">ticks/s</span></div></div>
  <div class="card" id="c-proc">    <div class="card-label">Proc Rate</div><div class="card-val">—<span class="unit">ticks/s</span></div></div>
  <div class="card" id="c-buf">     <div class="card-label">Buffer</div>  <div class="card-val">—<span class="unit">pending</span></div></div>
  <div class="card" id="c-api">     <div class="card-label">API Req</div> <div class="card-val">—<span class="unit">req/s</span></div></div>
  <div class="card" id="c-ws">      <div class="card-label">WS Clients</div><div class="card-val">—</div></div>
</div>

<!-- four charts -->
<div class="charts">
  <!-- throughput -->
  <div class="chart-box">
    <h3>Throughput
      <span class="legend">
        <span><span class="ln" style="background:#4ade80"></span>Produced</span>
        <span><span class="ln" style="background:#60a5fa"></span>Consumed</span>
      </span>
    </h3>
    <div class="chart-wrap"><canvas id="chThroughput"></canvas></div>
  </div>

  <!-- latency -->
  <div class="chart-box">
    <h3>Latency
      <span class="legend">
        <span><span class="ln" style="background:#60a5fa"></span>Produce</span>
        <span><span class="ln" style="background:#fb923c"></span>Flush</span>
      </span>
    </h3>
    <div class="chart-wrap"><canvas id="chLatency"></canvas></div>
  </div>

  <!-- buffer + errors -->
  <div class="chart-box">
    <h3>Buffer Depth
      <span class="legend">
        <span><span class="ln" style="background:#a78bfa"></span>Pending</span>
      </span>
    </h3>
    <div class="chart-wrap"><canvas id="chBuffer"></canvas></div>
  </div>

  <!-- API -->
  <div class="chart-box">
    <h3>API
      <span class="legend">
        <span><span class="ln" style="background:#fff"></span>Requests</span>
        <span><span class="ln" style="background:#ef4444"></span>Errors</span>
      </span>
    </h3>
    <div class="chart-wrap"><canvas id="chApi"></canvas></div>
  </div>
</div>

<!-- alerts -->
<div class="alerts">
  <h3>Alerts</h3>
  <div class="alert-list" id="alertList"><div class="no-alert">No alerts.</div></div>
</div>

<script>
(function(){
"use strict";

// ---- config ----
const WS = (location.protocol==="https:"?"wss:":"ws:")+"//"+location.host+"/ws";
let MAX = 60;

// ---- ring buffer ----
class Buf {
  constructor(){ this.d=[]; }
  push(v){ this.d.push(v); while(this.d.length>MAX) this.d.shift(); }
  trim(){ while(this.d.length>MAX) this.d.shift(); }
}

// ---- shared buffers ----
const L   = new Buf();                          // time labels
const gen = new Buf(), proc = new Buf();        // throughput
const pLat= new Buf(), fLat = new Buf();        // latencies (p99)
const buf = new Buf();                          // buffer depth
const req = new Buf(), err  = new Buf();        // API

// ---- chart factory ----
function line(id, datasets){
  return new Chart(document.getElementById(id), {
    type:"line",
    data:{
      labels: L.d,
      datasets: datasets.map(d=>({
        data: d.buf.d,
        borderColor: d.color,
        backgroundColor: "transparent",
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
      }))
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      animation:false,
      plugins:{ legend:{ display:false } },
      scales:{
        x:{ ticks:{ color:"#555", maxTicksLimit:6, maxRotation:0, font:{size:10} }, grid:{ color:"#222" } },
        y:{ ticks:{ color:"#555", font:{size:10} }, grid:{ color:"#222" }, beginAtZero:true }
      }
    }
  });
}

// ---- create charts ----
const chTh  = line("chThroughput", [{buf:gen, color:"#4ade80"}, {buf:proc, color:"#60a5fa"}]);
const chLat = line("chLatency",    [{buf:pLat, color:"#60a5fa"}, {buf:fLat, color:"#fb923c"}]);
const chBuf = line("chBuffer",     [{buf:buf,  color:"#a78bfa"}]);
const chApi = line("chApi",        [{buf:req,  color:"#fff"}, {buf:err, color:"#ef4444"}]);
const allCharts = [chTh, chLat, chBuf, chApi];

// ---- time label ----
function fmt(ts){
  const d=new Date(ts*1000);
  return [d.getHours(),d.getMinutes(),d.getSeconds()]
    .map(n=>String(n).padStart(2,"0")).join(":");
}

// ---- card updater ----
function card(id, val, unit){
  document.querySelector("#"+id+" .card-val").innerHTML = val+'<span class="unit">'+(unit||"")+"</span>";
}

// ---- process snapshot ----
function onSnap(s){
  const c=s.counters||{}, g=s.gauges||{}, h=s.histograms||{};

  L.push(fmt(s.timestamp));

  gen.push( (c["generator.ticks_produced"] ||{}).rate_per_sec ||0 );
  proc.push((c["processor.ticks_consumed"] ||{}).rate_per_sec ||0 );

  pLat.push((h["generator.produce_latency_ms"]||{}).p99 ||0);
  fLat.push((h["processor.flush_latency_ms"]   ||{}).p99 ||0);

  buf.push( (g["processor.buffer_depth"]        ||{}).value ||0 );

  req.push( (c["api.requests"]                  ||{}).rate_per_sec ||0 );
  err.push( (c["api.errors"]                    ||{}).rate_per_sec ||0 );

  // update cards
  card("c-uptime", s.uptime_seconds!==undefined? s.uptime_seconds:"—");
  card("c-gen",  gen.d[gen.d.length-1],  "ticks/s");
  card("c-proc", proc.d[proc.d.length-1],"ticks/s");
  card("c-buf",  buf.d[buf.d.length-1],  "pending");
  card("c-api",  req.d[req.d.length-1],  "req/s");
  card("c-ws",   (g["websocket.active_connections"]||{}).value||0);

  // update chart data references (labels are shared object, already mutated)
  allCharts.forEach(ch=>{ ch.data.labels=L.d; ch.update(); });
}

// ---- alerts ----
const seen = new Set();
function onAlerts(alerts){
  if(!alerts||!alerts.length) return;
  const list = document.getElementById("alertList");
  alerts.forEach(a=>{
    const key = a.id+":"+a.fired_at;
    if(seen.has(key)) return;
    seen.add(key);

    const el = list.querySelector(".no-alert");
    if(el) el.remove();

    const row = document.createElement("div");
    row.className = "alert-row"+(a.severity==="critical"?" critical":"");
    row.innerHTML =
      '<div><div class="a-msg">'+esc(a.message)+'</div>'+
      '<div class="a-meta"><span class="a-tag '+a.severity+'">'+a.severity+'</span>'+
      esc(a.metric)+' '+a.stat+' = '+a.actual+' · '+fmt(a.fired_at)+'</div></div>';
    list.insertBefore(row, list.firstChild);

    // keep max 20
    const rows = list.querySelectorAll(".alert-row");
    if(rows.length>20) rows[rows.length-1].remove();
  });
}

function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

// ---- WebSocket ----
let ws, delay=1000;
function connect(){
  setStatus(false,"connecting");
  ws = new WebSocket(WS);
  ws.onopen = ()=>{
    delay=1000;
    setStatus(true,"live");
    ws.send(JSON.stringify({type:"subscribe", tickers:["__METRICS__"]}));
  };
  ws.onmessage = ev=>{
    try {
      const m = JSON.parse(ev.data);
      if(m.type==="metrics"){
        setStatus(true,"live");
        onSnap(m.data);
        onAlerts(m.data.alerts||[]);
      }
    } catch(e){}
  };
  ws.onclose = ()=>{
    setStatus(false,"reconnecting…");
    setTimeout(connect, delay);
    delay = Math.min(delay*2, 8000);
  };
  ws.onerror = ()=>{};
}

function setStatus(ok, txt){
  document.getElementById("dot").className = "dot"+(ok?" live":"");
  document.getElementById("statusTxt").textContent = txt;
}

// ---- window picker ----
document.querySelectorAll(".pills button").forEach(btn=>{
  btn.addEventListener("click", ()=>{
    document.querySelectorAll(".pills button").forEach(b=>b.classList.remove("active"));
    btn.classList.add("active");
    MAX = parseInt(btn.dataset.w);
    [L,gen,proc,pLat,fLat,buf,req,err].forEach(b=>b.trim());
    allCharts.forEach(ch=>{ ch.data.labels=L.d; ch.update(); });
  });
});

// ---- boot ----
connect();
})();
</script>
</body>
</html>
"""


@router.get("/monitor", response_class=HTMLResponse)
async def dashboard():
    """Serve the live monitoring dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)
