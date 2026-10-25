// The post-match review pack: every VAR check in a match, from the stored case files, and the
// Key Match Incidents panel's votes on each published decision.
import { get, params, post } from "./api.js";
import { CATEGORY, DECISION, REVIEW, esc, total } from "./labels.js";

const seed = Number(params.get("seed") || 5001);
const SEAT_INITIALS = { "Former striker": "ST", "Former defender": "DF", "Former coach": "CO", "League representative": "LG", "Referees' representative": "RF" };

function deskSeconds(c) {
  return c.steps.filter((s) => s.agent !== "approval").reduce((sum, s) => sum + s.seconds, 0);
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b), mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function panelChip(p) {
  if (!p) return '<span class="muted">–</span>';
  const upheld = p.verdict === "decision upheld";
  return `<span class="chip ${upheld ? "stands" : "overturn"}">${esc(p.decision_correct)} ${upheld ? "upheld" : "questioned"}</span>`;
}

function panelCard(c) {
  const p = c.panel, v = c.verdict;
  const seats = p.members.map((m) => {
    const dissent = p.dissent.includes(m.seat);
    return `<li class="${dissent ? "dissent" : ""}"><span class="seat-badge" aria-hidden="true">${SEAT_INITIALS[m.seat] ?? "?"}</span>
      <div><div class="seat-line"><b>${esc(m.seat)}</b>${dissent ? '<span class="small" style="color:var(--accent)">dissent</span>' : ""}
        <span class="vote ${m.decision_correct ? "yes" : "no"}">${m.decision_correct ? "Decision right" : "Decision wrong"}</span>
        <span class="vote ${m.var_right ? "yes" : "no"}">${m.var_right ? "VAR right" : "VAR wrong"}</span></div>
        <p class="small" style="margin:4px 0 0;color:var(--soft)">${m.reason ? esc(m.reason) : '<span class="muted">Reason withheld: it cited a figure that is not in the record.</span>'}</p></div></li>`;
  }).join("");
  return `<article class="kmi-card"><div class="kmi-head"><span class="mono muted">${esc(c.clock)}</span><b>${esc(CATEGORY[c.category])}</b>
      <span class="muted">Final: ${esc(DECISION[v.final_decision])}</span>${panelChip(p)}<span class="small muted">VAR right ${esc(p.var_right)}</span></div>
    <ul class="kmi-seats">${seats}</ul></article>`;
}

function render(match, rows) {
  const done = rows.filter((r) => r.c?.verdict);
  const interventions = done.filter((r) => r.c.verdict.review !== "check_complete").length;
  const right = done.filter((r) => r.c.verdict.final_decision === r.c.on_field).length;
  const mid = median(done.map((r) => deskSeconds(r.c)));
  const reviewed = done.filter((r) => r.c.panel);
  const questioned = reviewed.filter((r) => r.c.panel.verdict !== "decision upheld").length;
  const tile = (label, value, note = "") =>
    `<div class="panel tile"><div class="label">${label}</div><div style="font-size:30px;font-weight:700;margin-top:4px">${value}</div>${note ? `<div class="small muted">${note}</div>` : ""}</div>`;
  document.getElementById("tiles").innerHTML = [
    tile("VAR checks", `${done.length} of ${match.incidents.length}`, "checked by the desk so far"),
    tile("Interventions", interventions),
    tile("On-field calls right", done.length ? `${right} of ${done.length}` : "–"),
    tile("Median desk time", mid === null ? "–" : `<span class="mono">${mid.toFixed(1)} s</span>`, "from the check to checked messages"),
    tile("Panel", reviewed.length ? `${reviewed.length - questioned} upheld` : "–", reviewed.length ? `${questioned} questioned, of ${reviewed.length} reviewed` : "not convened yet"),
  ].join("");

  document.getElementById("rows").innerHTML = rows.map(({ incident, c }) => {
    if (!c?.verdict) {
      return `<tr><td class="mono">${esc(incident.clock)}</td><td><b>${esc(CATEGORY[incident.category])}</b></td><td>${esc(DECISION[incident.on_field] ?? incident.on_field)}</td>
        <td colspan="7" class="muted">Not checked yet. <a href="index.html?seed=${seed}">Run it from the desk</a>.</td></tr>`;
    }
    const v = c.verdict, chip = v.review === "check_complete" ? "stands" : "overturn";
    return `<tr><td class="mono">${esc(c.clock)}</td><td><b>${esc(CATEGORY[c.category])}</b></td><td>${esc(DECISION[c.on_field] ?? c.on_field)}</td>
      <td><span class="chip ${chip}">${esc(REVIEW[v.review])}</span></td><td><b>${esc(c.status === "held" ? "Held" : DECISION[v.final_decision])}</b></td>
      <td>${esc(c.law?.id)}</td><td style="color:var(--soft)">${esc(c.evidence?.facts?.[0] ?? "")}</td>
      <td>${c.precedent ? `${c.precedent.agreeing} of ${total(c.precedent.finals)}` : "–"}</td><td>${panelChip(c.panel)}</td><td class="mono">${deskSeconds(c).toFixed(1)} s</td></tr>`;
  }).join("");

  document.getElementById("panel-cards").innerHTML = reviewed.map(({ c }) => panelCard(c)).join("");
  const waiting = done.filter((r) => r.c.status === "published" && !r.c.panel).length;
  const button = document.getElementById("convene");
  button.disabled = !waiting || button.dataset.busy === "1";
  if (button.dataset.busy !== "1") {
    document.getElementById("panel-note").textContent = reviewed.length || waiting
      ? (waiting ? `${waiting} published decision${waiting > 1 ? "s" : ""} waiting for the panel.` : "")
      : "No published decisions to review yet.";
  }
}

// Convene the panel on every published decision it has not reviewed, two at a time.
async function convene(match, rows) {
  const button = document.getElementById("convene"), note = document.getElementById("panel-note");
  const queue = rows.filter((r) => r.c?.verdict && r.c.status === "published" && !r.c.panel);
  button.dataset.busy = "1";
  button.disabled = true;
  let finished = 0;
  note.textContent = `The panel is sitting: 0 of ${queue.length} reviewed…`;
  async function worker() {
    while (queue.length) {
      const row = queue.shift();
      try {
        row.c.panel = await post(`/api/checks/${row.c.check_id}/panel`);
      } catch (err) {
        const detail = String(err?.message ?? err).match(/"detail":"([^"]+)"/);
        note.textContent = detail ? detail[1] : "The panel could not sit; try again in a moment.";
        queue.length = 0;
        break;
      }
      finished += 1;
      note.textContent = `The panel is sitting: ${finished} reviewed…`;
      render(match, rows);
    }
  }
  await Promise.all([worker(), worker()]);
  button.dataset.busy = "";
  render(match, rows);
}

async function main() {
  const match = await get(`/api/matches/${seed}`);
  const cases = await get(`/api/cases?match_id=${encodeURIComponent(match.id)}`);
  const byIncident = new Map(cases.map((c) => [c.incident_id, c]));
  document.getElementById("title").textContent = `${match.home.name} ${match.score[0]} – ${match.score[1]} ${match.away.name}`;
  document.getElementById("back").href = `index.html?seed=${seed}`;
  const rows = match.incidents.map((incident) => ({ incident, c: byIncident.get(incident.id) }));
  render(match, rows);
  document.getElementById("convene").onclick = () => convene(match, rows);

  document.getElementById("csv").onclick = () => {
    const done = rows.filter((r) => r.c?.verdict);
    const header = ["time", "type", "on_field", "review", "final", "law", "evidence", "precedent", "panel_decision_correct", "panel_var_right", "desk_seconds"];
    const lines = [header.join(",")].concat(done.map(({ c }) => [c.clock, c.category, c.on_field, c.verdict.review, c.verdict.final_decision,
      c.law?.id ?? "", `"${(c.evidence?.facts?.[0] ?? "").replace(/"/g, '""')}"`,
      c.precedent ? `${c.precedent.agreeing}/${total(c.precedent.finals)}` : "", c.panel?.decision_correct ?? "", c.panel?.var_right ?? "",
      deskSeconds(c).toFixed(1)].join(",")));
    const link = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })), download: `${match.id}-review.csv`,
    });
    link.click();
  };
  document.getElementById("print").onclick = () => window.print();
}

main().catch(() => {
  document.getElementById("title").textContent = "This match could not be loaded";
  document.getElementById("rows").innerHTML = '<tr><td colspan="10" class="muted">Only the demo matches have a review pack. Pick one from the desk.</td></tr>';
});
