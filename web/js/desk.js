// The Match Centre desk: live feed, pitch, VAR checks and the approval step.
import { follow, get, params, post } from "./api.js";
import { drawFreezeFrame, drawPitch } from "./pitch.js";
import { CATEGORY, DECISION, DRILL, REVIEW, esc, total } from "./labels.js";

const AGENTS = ["intake", "evidence", "laws", "assessor", "precedent", "communicator", "checker", "approval"];
const TABS = [["match_centre", "Match Centre"], ["stadium", "Stadium"], ["broadcaster", "Broadcaster"], ["fan", "Fan card"]];
const NOTABLE = new Set(["shot", "card", "foul", "offside", "penalty", "var_check", "var_decision", "substitution", "kickoff", "period_start", "period_end"]);

const $ = (id) => document.getElementById(id);

const state = {
  match: null, checks: new Map(), byIncident: new Map(), active: null, tab: "match_centre",
  stopCheck: null, packets: new Map(), frameWanted: null, frameDrawn: null, ticker: [],
};

// ---- match ---------------------------------------------------------------------------

async function loadMatches() {
  const matches = await get("/api/matches");
  const select = $("match");
  for (const m of matches) {
    const option = new Option(`${m.home.name} v ${m.away.name} (${m.incidents} checks)`, m.seed);
    select.appendChild(option);
  }
  select.value = params.get("seed") || matches[0].seed;
  select.onchange = () => selectMatch(Number(select.value));
  await selectMatch(Number(select.value));
}

async function selectMatch(seed) {
  state.match = await get(`/api/matches/${seed}`);
  state.ticker = [];
  const { home, away } = state.match;
  for (const [id, club] of [["home", home], ["away", away]]) {
    $(`${id}-name`).textContent = club.name;
    $(`legend-${id}-name`).textContent = club.name;
    $(`${id}-dot`).style.background = id === "home" ? "#E14D5F" : "#3BA3D9";
    $(`legend-${id}`).style.background = id === "home" ? "#E14D5F" : "#3BA3D9";
  }
  $("score").textContent = "0 – 0";
  $("clock").textContent = "00:00";
  $("review-link").href = `review.html?seed=${seed}`;
  $("ticker").innerHTML = '<div class="muted">Start the live feed to replay this match.</div>';
  // Checks already finished (before a reload, or on another screen) open from the store.
  for (const c of await get(`/api/cases?match_id=${encodeURIComponent(state.match.id)}`)) {
    if (!c.check_id || state.byIncident.has(c.incident_id)) continue;
    state.checks.set(c.check_id, { id: c.check_id, incident: c.incident_id, case: c, waiting: false, done: true });
    state.byIncident.set(c.incident_id, c.check_id);
  }
  renderChecks();
  state.frameWanted = 0;
}

// ---- live feed -----------------------------------------------------------------------

function onFeed(event) {
  if (!state.match || event.match_id !== state.match.id) return;
  if (event.type === "match_event") {
    const e = event.event;
    $("clock").textContent = e.clock;
    $("score").textContent = `${event.score[0]} – ${event.score[1]}`;
    $("pitch-note").textContent = `Positions at ${e.clock}`;
    state.frameWanted = e.i;
    if (NOTABLE.has(e.type)) addTicker(e);
  } else if (event.type === "check_started") {
    state.checks.set(event.check_id, { id: event.check_id, incident: event.incident_id, case: null, waiting: false, done: false });
    state.byIncident.set(event.incident_id, event.check_id);
    renderChecks();
    if (!state.active || state.checks.get(state.active)?.done) openCheck(event.check_id);
    else pollInBackground(state.checks.get(event.check_id));
  } else if (event.type === "feed_stale") {
    setLive("stale", event.seconds);
    note(`Feed stale: no data for ${event.seconds} s. Checks already running carry on.`);
  } else if (event.type === "feed_resumed") {
    setLive("live");
    note(`Feed back after ${event.gap} s without data.`);
  } else if (event.type === "feed_drill") {
    note(`Drill: the upstream feed freezes for ${event.seconds} s.`);
  } else if (event.type === "feed_ended") {
    setLive("idle");
  }
}

function note(text) {
  state.ticker.unshift(`<div><span class="mono">${esc($("clock").textContent)}</span><span class="warn">${esc(text)}</span></div>`);
  state.ticker = state.ticker.slice(0, 14);
  $("ticker").innerHTML = state.ticker.join("");
}

function addTicker(e) {
  const team = e.team === state.match.home.code ? state.match.home.name : e.team === state.match.away.code ? state.match.away.name : "";
  const player = state.match.players[e.player]?.name ?? "";
  const what = { var_check: "VAR check", var_decision: `VAR decision: ${DECISION[e.result] ?? e.result}` }[e.type]
    ?? `${e.type.replace("_", " ")}${e.result && e.result !== "success" ? `: ${e.result.replace("_", " ")}` : ""}`;
  state.ticker.unshift(`<div><span class="mono">${esc(e.clock)}</span><span>${esc(what)}${player ? ` · ${esc(player)}` : team ? ` · ${esc(team)}` : ""}</span></div>`);
  state.ticker = state.ticker.slice(0, 14);
  $("ticker").innerHTML = state.ticker.join("");
}

function setLive(mode, seconds) {
  const chip = $("live-chip");
  chip.className = { live: "live-chip", stale: "live-chip stale", idle: "live-chip idle" }[mode];
  const stale = seconds ? `Feed stale · no data for ${seconds} s` : "Feed stale";
  chip.textContent = { live: "Live · Event Hubs", stale, idle: "Feed idle" }[mode];
  const freeze = $("drill-freeze");
  if (freeze) freeze.disabled = mode !== "live";
}

async function startFeed() {
  await post("/api/live", { seed: state.match.seed, speed: Number($("speed").value), from_minute: 0 });
  state.ticker = [];
  $("ticker").innerHTML = "";
  setLive("live");
}

// ---- failure drills ------------------------------------------------------------------

async function loadDrills() {
  const drills = await get("/api/drills");
  $("drills").innerHTML = drills.map((d) => `<button type="button" class="btn small" data-drill="${esc(d.id)}" title="${esc(d.label)}">${esc(DRILL[d.id] ?? d.label)}</button>`).join("")
    + '<button type="button" class="btn small" id="drill-freeze" title="The upstream feed stops sending for 15 seconds" disabled>The feed freezes for 15 s</button>';
  for (const button of $("drills").querySelectorAll("[data-drill]")) button.onclick = () => runDrill(button.dataset.drill);
  $("drill-freeze").onclick = () => post("/api/live/stall", { seconds: 15 });
  const live = await get("/api/live");
  if (live.running && live.match_id === state.match.id) setLive(live.stale ? "stale" : "live");
}

async function runDrill(drill) {
  const incidentId = state.checks.get(state.active)?.incident ?? state.match.incidents[0]?.id;
  if (!incidentId) return;
  const { check_id } = await post("/api/checks", { incident_id: incidentId, drill });
  state.checks.set(check_id, { id: check_id, incident: incidentId, case: null, waiting: false, done: false, drill });
  openCheck(check_id);  // drills never take over the row of the real check
}

async function pumpFrames() {
  if (state.match && state.frameWanted !== null && state.frameWanted !== state.frameDrawn) {
    const index = state.frameWanted;
    state.frameDrawn = index;
    try {
      const frame = await get(`/api/matches/${state.match.seed}/frames/${index}`);
      const active = state.checks.get(state.active);
      drawPitch($("pitch"), frame, state.match.home.code, active?.case?.evidence?.offside_line_x ?? null);
    } catch { /* a missed frame is redrawn on the next tick */ }
  }
  setTimeout(pumpFrames, 700);
}

// ---- checks --------------------------------------------------------------------------

function chipFor(check) {
  if (!check) return '<span class="chip idle">Not checked</span>';
  const c = check.case;
  if (check.waiting) return '<span class="chip waiting">Awaiting approval</span>';
  if (!check.done) return '<span class="chip idle">Desk working</span>';
  if (c?.status === "held") return '<span class="chip held">Held</span>';
  return c?.verdict?.review === "check_complete"
    ? '<span class="chip stands">Check complete</span>' : '<span class="chip overturn">Overturned</span>';
}

function renderChecks() {
  const rows = state.match.incidents.map((incident) => {
    const check = state.checks.get(state.byIncident.get(incident.id));
    const v = check?.case?.verdict;
    const outcome = v ? `${DECISION[incident.on_field] ?? incident.on_field} → ${DECISION[v.final_decision]}` : `On-field: ${DECISION[incident.on_field] ?? incident.on_field}`;
    const current = check && check.id === state.active ? ' aria-current="true"' : "";
    return `<button type="button" class="check-row" data-incident="${esc(incident.id)}"${current}>
      <span class="time">${esc(incident.clock)}</span><span class="what">${esc(CATEGORY[incident.category])}</span>
      <span class="muted">${esc(outcome)}</span>${chipFor(check)}</button>`;
  });
  $("checks").innerHTML = rows.join("") || '<div class="muted">No VAR checks in this match.</div>';
  for (const row of $("checks").querySelectorAll(".check-row")) {
    row.onclick = () => runOrOpen(row.dataset.incident);
  }
}

async function runOrOpen(incidentId) {
  const existing = state.byIncident.get(incidentId);
  if (existing) return openCheck(existing);
  const { check_id } = await post("/api/checks", { incident_id: incidentId });
  state.checks.set(check_id, { id: check_id, incident: incidentId, case: null, waiting: false, done: false });
  state.byIncident.set(incidentId, check_id);
  openCheck(check_id);
}

// A check that is not on screen keeps its row up to date by polling, so the browser never holds
// more than one check stream (it allows only a few connections per host).
function pollInBackground(check) {
  if (!check || check.done || check.poll) return;
  check.poll = setInterval(async () => {
    try {
      const s = await get(`/api/checks/${check.id}`);
      if (s.case) check.case = s.case;
      check.waiting = s.awaiting_approval;
      check.done = s.done;
      if (check.done) { clearInterval(check.poll); check.poll = null; }
      renderChecks();
    } catch { /* try again on the next tick */ }
  }, 2000);
}

async function openCheck(checkId) {
  if (state.stopCheck) state.stopCheck();
  state.stopCheck = null;
  if (state.active !== checkId) pollInBackground(state.checks.get(state.active));
  state.active = checkId;
  state.tab = "match_centre";
  const check = state.checks.get(checkId);
  if (check.poll) { clearInterval(check.poll); check.poll = null; }
  if (!state.packets.has(check.incident)) state.packets.set(check.incident, (await get(`/api/incidents/${check.incident}`)).packet);
  renderChecks();
  renderCheck();
  showIncident(check);
  if (check.done) return;
  const stop = follow(`/api/checks/${checkId}/events`, (event) => {
    if (event.case) check.case = event.case;
    if (event.type === "awaiting_approval") check.waiting = true;
    if (event.type === "final" || event.type === "error") {
      check.waiting = false; check.done = true; check.error = event.message;
      stop();  // otherwise the browser reconnects and replays the finished check
    }
    renderChecks();
    if (state.active === checkId) { renderCheck(); showIncident(check); }
  });
  state.stopCheck = stop;
}

// With the feed idle, the pitch shows the moment of the open check, with its offside line.
function showIncident(check) {
  if (!$("live-chip").classList.contains("idle")) return;
  const incident = state.match.incidents.find((i) => i.id === check.incident);
  if (!incident) return;
  $("pitch-note").textContent = `Positions at ${incident.clock}`;
  state.frameWanted = incident.event_index;
  state.frameDrawn = null;
}

async function decide(decision) {
  const check = state.checks.get(state.active);
  check.waiting = false;
  renderCheck();
  await post(`/api/checks/${state.active}/decision`, { decision });
}

// ---- the active check ----------------------------------------------------------------

function stepsHtml(c) {
  const seen = new Map();
  for (const s of c?.steps ?? []) seen.set(s.agent, s);
  const finished = c?.status === "held" || c?.status === "published";
  const next = finished ? null : AGENTS.find((a) => !seen.has(a));
  const rows = AGENTS.map((agent) => {
    const s = seen.get(agent);
    const cls = s ? "done" : agent === next ? "active" : "";
    const seconds = s && (s.seconds < 0.01 ? "< 0.01 s" : `${s.seconds.toFixed(2)} s`);
    const working = agent === "approval" ? "your call" : "working";
    const time = s ? (agent === "approval" ? s.note : seconds) : agent === next ? working : finished ? "skipped" : "";
    return `<li class="${cls}"><span class="dot"></span><span>${agent[0].toUpperCase() + agent.slice(1)}</span><span class="mono muted small">${esc(time)}</span></li>`;
  });
  if (seen.has("fail-safe")) rows.push('<li class="done"><span class="dot" style="background:#FF9A9A"></span><span>Fail-safe</span><span class="mono muted small">holding line</span></li>');
  return rows.join("");
}

function draftHtml(c) {
  const d = c.drafts;
  if (state.tab === "broadcaster") return `<ul>${d.broadcaster.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`;
  if (state.tab === "stadium") return esc(d.stadium || "No stadium announcement is due for this decision.");
  return esc(d[state.tab]);
}

// What the checker sent back on each draft, so a caught mistake stays visible after the rewrite.
function caughtHtml(c, open) {
  const rounds = (c.check_history ?? []).map((issues, n) => [n + 1, issues]).filter(([, issues]) => issues.length);
  if (!rounds.length) return "";
  const items = rounds.flatMap(([n, issues]) => issues.map((i) => `<li><span class="mono muted">draft ${n}</span> ${esc(i)}</li>`));
  return `<details class="caught" style="margin-top:12px"${open ? " open" : ""}><summary>What the checker sent back (${items.length})</summary><ul>${items.join("")}</ul></details>`;
}

function renderCheck() {
  const check = state.checks.get(state.active);
  const c = check?.case;
  const packet = state.packets.get(check?.incident);
  const side = $("check");
  const drill = check?.drill ?? c?.drill;
  const kicker = `${drill ? "Drill · " : ""}VAR check`;
  const banner = drill ? `<div class="panel drill-banner"><div class="label" style="color:var(--accent)">Failure drill</div><p style="margin:6px 0 0">${esc(DRILL[drill] ?? drill)}. Real data and real models; nothing from a drill is saved.</p></div>` : "";
  if (!c) {
    side.innerHTML = banner + (check?.error
      ? `<div class="panel"><div class="kicker">${kicker}</div><div class="verdict-title" style="margin-top:8px">The check failed</div><p class="small warn" style="margin:8px 0 0">${esc(check.error)}</p><p class="small muted" style="margin:6px 0 0">Nothing was published.</p></div>`
      : `<div class="panel"><div class="kicker">${kicker}</div><div class="verdict-title" style="margin-top:8px">The desk is working…</div><ol class="steps" style="margin-top:14px">${stepsHtml(null)}</ol></div>`);
    return;
  }
  const v = c.verdict;
  const verdict = v
    ? `<div style="display:flex;align-items:baseline;gap:12px;margin-top:10px;flex-wrap:wrap"><div class="verdict-title">${esc(c.status === "held" && c.holding ? c.holding : DECISION[v.final_decision])}</div>
       <div class="small muted">${esc(REVIEW[v.review])}${v.announced ? " · announced in the stadium" : " · no stadium announcement"}</div></div>
       <div class="pills"><span class="pill">Law <b>${esc(c.law?.id)}</b> ${esc(c.law?.title)}</span>${c.precedent_line ? `<span class="pill">Precedent <b>${c.precedent?.agreeing} of ${total(c.precedent?.finals)}</b> agree</span>` : ""}${v.card !== "no_card" ? `<span class="pill">${esc(DECISION[v.card])}</span>` : ""}</div>`
    : `<div class="verdict-title" style="margin-top:10px">${esc(c.holding ?? "Working…")}</div>`;
  const drafts = c.drafts && c.status !== "held"
    ? `<div class="panel"><div class="panel-head"><h2>Messages, checked</h2><span class="small ${c.check?.passed ? "ok" : "warn"}">${c.check ? (c.check.passed ? `Checker: 0 issues · ${c.check.claims.length} claims backed` : `Checker: ${c.check.issues.length} issue(s)`) : "Checking…"}${c.revisions ? ` · after ${c.revisions} rewrite(s)` : ""}</span></div>
       <div class="tabs" role="tablist" aria-label="Channel">${TABS.map(([id, label]) => `<button type="button" role="tab" class="tab" data-tab="${id}" aria-selected="${state.tab === id}">${label}</button>`).join("")}</div>
       <div class="draft">${draftHtml(c)}</div>
       <div class="actions">
         <button type="button" class="btn primary" id="approve" ${check.waiting ? "" : "disabled"}>${c.status === "published" ? "Published" : "Approve and publish"}</button>
         <button type="button" class="btn" id="hold" ${check.waiting ? "" : "disabled"}>Hold</button>
         <span class="small muted">${c.status === "published" ? (drill ? "Approved. A drill publishes nothing." : `Published. <a href="fan.html?check=${esc(check.id)}" target="_blank" rel="noopener">Open the fan card</a>`) : check.waiting ? "Nothing is published until you approve." : "Waiting for the checker."}</span>
       </div>${caughtHtml(c, Boolean(drill))}</div>`
    : c.status === "held" ? `<div class="panel"><div class="label">Fail-safe</div><p style="margin:6px 0 0">Only the holding line goes out: <b>${esc(c.holding)}</b></p>${c.failure ? `<p class="small muted" style="margin:6px 0 0">Why: ${esc(c.failure)}</p>` : ""}${caughtHtml(c, Boolean(drill))}</div>` : "";
  side.innerHTML = `${banner}
    <div class="panel">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;align-items:center">
        <div class="kicker">${kicker} · ${esc(CATEGORY[c.category])} · ${esc(c.clock)}</div>
        <div class="small muted">On-field: <b style="color:var(--text)">${esc(DECISION[c.on_field] ?? c.on_field)}</b></div>
      </div>${verdict}
      ${c.consistency_flag ? `<p class="small warn" style="margin:10px 0 0">Internal: ${esc(c.consistency_flag)}</p>` : ""}
    </div>
    ${c.evidence ? `<div class="panel"><div class="panel-head"><h2>Freeze-frame</h2><span class="small muted">Tracking data at the decisive moment</span></div>
      <svg class="pitch" id="freeze" viewBox="0 0 400 300" role="img" aria-label="Zoomed freeze-frame of the incident"></svg>
      <ul class="facts">${c.evidence.facts.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
      ${c.evidence.borderline ? `<p class="small" style="margin:10px 0 0;color:var(--accent)">Close call: ${esc(c.evidence.borderline_reason)}.</p>` : ""}</div>` : ""}
    ${c.law ? `<div class="split"><div class="panel"><div class="label">The Law</div><div style="font-weight:600;margin-top:6px">Law ${esc(c.law.id)} · ${esc(c.law.title)}</div>
      <p style="margin:6px 0 8px;color:var(--soft)">${esc(c.law.summary)}</p><a href="${esc(c.law.url)}" target="_blank" rel="noopener">Official wording (IFAB)</a></div>
      <div class="panel"><div class="label">Precedent</div>${c.precedent_line ? `<div class="big-number">${c.precedent.agreeing} of ${total(c.precedent.finals)}</div><p style="margin:4px 0 0;color:var(--soft)">most similar past checks ended the same way.</p>` : '<p class="muted" style="margin:6px 0 0">Looking up similar past checks…</p>'}</div></div>` : ""}
    <div class="panel"><h2 style="margin-bottom:12px">The desk at work</h2><ol class="steps">${stepsHtml(c)}</ol></div>
    ${drafts}`;
  if (c.evidence && packet) drawFreezeFrame($("freeze"), packet, c, state.match.home.code);
  for (const tab of side.querySelectorAll(".tab")) tab.onclick = () => { state.tab = tab.dataset.tab; renderCheck(); };
  if ($("approve")) $("approve").onclick = () => decide("approve");
  if ($("hold")) $("hold").onclick = () => decide("hold");
}

// ---- start ---------------------------------------------------------------------------

$("start").onclick = startFeed;
follow("/api/live/events", onFeed);
loadMatches().then(() => { pumpFrames(); loadDrills(); });
