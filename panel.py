"""Admin panel. Single-file page, token kept in localStorage."""

PAGE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FF Like API</title>
<style>
  :root{--bg:#0b0f14;--card:#141b24;--line:#1f2a36;--txt:#d7e2ee;--dim:#7c8b9c;--acc:#00c2ff;--ok:#2ecc71;--bad:#ff5c5c}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
  .wrap{max-width:960px;margin:0 auto;padding:24px}
  h1{font-size:16px;letter-spacing:2px;color:var(--acc);margin:0 0 20px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:16px;margin-bottom:16px}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  label{display:block;color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
  input,select{background:#0d141c;border:1px solid var(--line);color:var(--txt);padding:8px;border-radius:6px;font:inherit;width:100%}
  button{background:var(--acc);border:0;color:#04121a;font-weight:700;padding:8px 14px;border-radius:6px;cursor:pointer;font:inherit}
  button.ghost{background:transparent;color:var(--txt);border:1px solid var(--line)}
  table{width:100%;border-collapse:collapse;font-size:12px}
  th,td{text-align:left;padding:6px;border-bottom:1px solid var(--line)}
  th{color:var(--dim);font-weight:400;text-transform:uppercase;font-size:10px}
  .stat{flex:1;min-width:110px}
  .stat b{display:block;font-size:20px;color:var(--acc)}
  .muted{color:var(--dim);font-size:12px}
  .ok{color:var(--ok)}.bad{color:var(--bad)}
  .hide{display:none}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
</style>
</head>
<body>
<div class="wrap">
  <h1>FF LIKE API — CONTROL</h1>

  <div id="login" class="card">
    <label>Admin token</label>
    <div class="row">
      <input id="pw" type="password" placeholder="ADMIN_TOKEN" style="flex:1">
      <button onclick="login()">Enter</button>
    </div>
    <p id="loginErr" class="bad"></p>
  </div>

  <div id="app" class="hide">
    <div class="card">
      <div class="row" style="justify-content:space-between">
        <div class="muted">session active</div>
        <button class="ghost" onclick="logout()">Log out</button>
      </div>
    </div>

    <div class="card">
      <label>Overview</label>
      <div class="row" id="stats"></div>
      <div class="row" id="pool" style="margin-top:12px"></div>
    </div>

    <div class="card">
      <label>Settings</label>
      <div class="grid">
        <div><label>API enabled</label><select id="s_api"><option value="1">ON</option><option value="0">OFF</option></select></div>
        <div><label>Cost per command</label><input id="s_cmd" type="number"></div>
        <div><label>Cost per extra like</label><input id="s_like" type="number"></div>
        <div><label>Daily limit</label><input id="s_daily" type="number"></div>
        <div><label>Max amount</label><input id="s_max" type="number"></div>
        <div><label>Maintenance message</label><input id="s_msg"></div>
      </div>
      <div class="row" style="margin-top:12px">
        <button onclick="saveSettings()">Save</button>
        <button class="ghost" onclick="refill()">Refill pool</button>
        <button class="ghost" onclick="purge()">Purge dead</button>
      </div>
      <p id="setMsg" class="muted"></p>
    </div>

    <div class="card">
      <label>Credits</label>
      <div class="row">
        <input id="c_id" placeholder="discord id" style="flex:2">
        <input id="c_amt" type="number" placeholder="delta (negative = remove)" style="flex:1">
        <button onclick="addCredits()">Apply</button>
      </div>
      <p id="cMsg" class="muted"></p>
    </div>

    <div class="card">
      <label>Users</label>
      <table><thead><tr><th>id</th><th>credits</th><th>total</th><th>today</th><th>state</th><th></th></tr></thead><tbody id="users"></tbody></table>
    </div>

    <div class="card">
      <label>Guests</label>
      <table><thead><tr><th>id</th><th>uid</th><th>region</th><th>status</th><th>today</th><th>fails</th></tr></thead><tbody id="guests"></tbody></table>
    </div>

    <div class="card">
      <label>Recent logs</label>
      <table><thead><tr><th>user</th><th>target</th><th>ok</th><th>note</th><th>time</th></tr></thead><tbody id="logs"></tbody></table>
    </div>
  </div>
</div>

<script>
let token = localStorage.getItem("ff_token") || "";

function q(id){return document.getElementById(id);}
function esc(s){return String(s==null?"":s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

async function api(path, opts){
  opts = opts || {};
  opts.headers = Object.assign({"Content-Type":"application/json"}, opts.headers || {});
  if (token) opts.headers["Authorization"] = "Bearer " + token;
  const r = await fetch(path, opts);
  if (r.status === 401) { logout(); throw new Error("unauthorized"); }
  const t = await r.text();
  let d = null;
  try { d = JSON.parse(t); } catch(e) { d = t; }
  if (!r.ok) throw new Error(typeof d === "string" ? d : JSON.stringify(d));
  return d;
}

async function login(){
  try{
    const r = await fetch("/admin/login", {method:"POST",headers:{"Content-Type":"application/json"},
      body: JSON.stringify({password: q("pw").value})});
    if (!r.ok) throw new Error("wrong password");
    const d = await r.json();
    token = d.token;
    localStorage.setItem("ff_token", token);
    q("loginErr").textContent = "";
    show();
  }catch(e){ q("loginErr").textContent = e.message; }
}

function logout(){
  token = "";
  localStorage.removeItem("ff_token");
  q("app").classList.add("hide");
  q("login").classList.remove("hide");
}

function show(){
  q("login").classList.add("hide");
  q("app").classList.remove("hide");
  refresh();
}

async function refresh(){
  let d;
  try { d = await api("/admin/overview"); } catch(e) { return; }
  const s = d.stats, p = d.pool;
  q("stats").innerHTML =
    '<div class="stat"><label>users</label><b>'+s.users+'</b></div>'+
    '<div class="stat"><label>total likes</label><b>'+s.total_likes+'</b></div>'+
    '<div class="stat"><label>today</label><b>'+s.today_likes+'</b></div>';
  q("pool").innerHTML =
    '<div class="stat"><label>ready</label><b>'+(p.ready||0)+'</b></div>'+
    '<div class="stat"><label>busy</label><b>'+(p.busy||0)+'</b></div>'+
    '<div class="stat"><label>dead</label><b>'+(p.dead||0)+'</b></div>';
  const st = d.settings;
  q("s_api").value = st.api_enabled ? "1" : "0";
  q("s_cmd").value = st.cost_per_cmd;
  q("s_like").value = st.cost_per_like;
  q("s_daily").value = st.daily_limit;
  q("s_max").value = st.max_amount;
  q("s_msg").value = st.maintenance_msg || "";
  q("guests").innerHTML = (d.guests||[]).map(g=>
    "<tr><td>"+g.id+"</td><td>"+esc(g.uid)+"</td><td>"+esc(g.region)+"</td><td>"+esc(g.status)+"</td><td>"+(g.likes_today||0)+"</td><td>"+(g.fails||0)+"</td></tr>").join("");
  q("logs").innerHTML = (d.logs||[]).map(l=>
    "<tr><td>"+esc(l.user_id)+"</td><td>"+esc(l.target)+"</td><td class='"+(l.ok?"ok":"bad")+"'>"+(l.ok?1:0)+"</td><td>"+esc(l.note)+"</td><td>"+esc(l.created)+"</td></tr>").join("");
  loadUsers();
}

async function loadUsers(){
  let d;
  try { d = await api("/admin/users"); } catch(e) { return; }
  q("users").innerHTML = d.map(u=>
    "<tr><td>"+u.discord_id+"</td><td>"+u.credits+"</td><td>"+u.total_likes+"</td><td>"+u.today+"</td>"+
    "<td class='"+(u.banned?"bad":"ok")+"'>"+(u.banned?"banned":"active")+"</td>"+
    "<td><button class='ghost' onclick=\\"ban("+u.discord_id+","+(u.banned?0:1)+")\\">"+(u.banned?"unban":"ban")+"</button></td></tr>").join("");
}

async function saveSettings(){
  try{
    await api("/admin/settings", {method:"POST", body: JSON.stringify({
      api_enabled: q("s_api").value === "1",
      cost_per_cmd: +q("s_cmd").value,
      cost_per_like: +q("s_like").value,
      daily_limit: +q("s_daily").value,
      max_amount: +q("s_max").value,
      maintenance_msg: q("s_msg").value
    })});
    q("setMsg").textContent = "saved";
    refresh();
  }catch(e){ q("setMsg").textContent = e.message; }
}

async function addCredits(){
  try{
    const d = await api("/admin/credits", {method:"POST", body: JSON.stringify({
      discord_id: +q("c_id").value, delta: +q("c_amt").value })});
    q("cMsg").textContent = "balance now " + d.credits;
    loadUsers();
  }catch(e){ q("cMsg").textContent = e.message; }
}

async function ban(id, state){
  try{
    await api("/admin/ban?discord_id="+id+"&banned="+(state?"true":"false"), {method:"POST"});
    loadUsers();
  }catch(e){}
}

async function refill(){
  try{ await api("/admin/pool/refill", {method:"POST", body: JSON.stringify({count: 3})}); refresh(); }catch(e){}
}

async function purge(){
  try{ await api("/admin/pool/purge", {method:"POST"}); refresh(); }catch(e){}
}

if (token) show();
</script>
</body>
</html>
'''
