// The post-match review pack: every VAR check in a match, from the stored case files.
import { get, params } from "./api.js";
import { CATEGORY, DECISION, REVIEW, esc, total } from "./labels.js";

const seed = Number(params.get("seed") || 5001);

function deskSeconds(c) {
  return c.steps.filter((s) => s.agent !== "approval").reduce((sum, s) => sum + s.seconds, 0);
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b), mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

async function main() {
  const match = await get(`/api/matches/${seed}`);
  const cases = await get(`/api/cases?match_id=${encodeURIComponent(match.id)}`);
  const byIncident = new Map(cases.map((c) => [c.incident_id, c]));
  document.getElementById("title").textContent = `${match.home.name} ${match.score[0]} – ${match.score[1]} ${match.away.name}`;
  document.getElementById("back").href = `index.html?seed=${seed}`;

  const rows = match.incidents.map((incident) => ({ incident, c: byIncident.get(incident.id) }));
  const done = rows.filter((r) => r.c?.verdict);
  const interventions = done.filter((r) => r.c.verdict.review !== "check_complete").length;
  const right = done.filter((r) => r.c.verdict.final_decision === r.c.on_field).length;
  const mid = median(done.map((r) => deskSeconds(r.c)));
  const tile = (label, value, note = "") =>
    `<div class="panel tile"><div class="label">${label}</div><div style="font-size:30px;font-weight:700;margin-top:4px">${value}</div>${note ? `<div class="small muted">${note}</div>` : ""}</div>`;
  document.getElementById("tiles").innerHTML = [
    tile("VAR checks", `${done.length} of ${match.incidents.length}`, "checked by the desk so far"),
    tile("Interventions", interventions),
    tile("On-field calls right", done.length ? `${right} of ${done.length}` : "–"),
    tile("Median desk time", mid === null ? "–" : `<span class="mono">${mid.toFixed(1)} s</span>`, "from the check to checked messages"),
  ].join("");

  document.getElementById("rows").innerHTML = rows.map(({ incident, c }) => {
    if (!c?.verdict) {
      return `<tr><td class="mono">${esc(incident.clock)}</td><td><b>${esc(CATEGORY[incident.category])}</b></td><td>${esc(DECISION[incident.on_field] ?? incident.on_field)}</td>
        <td colspan="6" class="muted">Not checked yet. <a href="index.html?seed=${seed}">Run it from the desk</a>.</td></tr>`;
    }
    const v = c.verdict, chip = v.review === "check_complete" ? "stands" : "overturn";
    return `<tr><td class="mono">${esc(c.clock)}</td><td><b>${esc(CATEGORY[c.category])}</b></td><td>${esc(DECISION[c.on_field] ?? c.on_field)}</td>
      <td><span class="chip ${chip}">${esc(REVIEW[v.review])}</span></td><td><b>${esc(c.status === "held" ? "Held" : DECISION[v.final_decision])}</b></td>
      <td>${esc(c.law?.id)}</td><td style="color:var(--soft)">${esc(c.evidence?.facts?.[0] ?? "")}</td>
      <td>${c.precedent ? `${c.precedent.agreeing} of ${total(c.precedent.finals)}` : "–"}</td><td class="mono">${deskSeconds(c).toFixed(1)} s</td></tr>`;
  }).join("");

  document.getElementById("csv").onclick = () => {
    const header = ["time", "type", "on_field", "review", "final", "law", "evidence", "precedent", "desk_seconds"];
    const lines = [header.join(",")].concat(done.map(({ c }) => [c.clock, c.category, c.on_field, c.verdict.review, c.verdict.final_decision,
      c.law?.id ?? "", `"${(c.evidence?.facts?.[0] ?? "").replace(/"/g, '""')}"`,
      c.precedent ? `${c.precedent.agreeing}/${total(c.precedent.finals)}` : "", deskSeconds(c).toFixed(1)].join(",")));
    const link = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })), download: `${match.id}-review.csv`,
    });
    link.click();
  };
  document.getElementById("print").onclick = () => window.print();
}

main().catch(() => {
  document.getElementById("title").textContent = "This match could not be loaded";
  document.getElementById("rows").innerHTML = '<tr><td colspan="9" class="muted">Only the demo matches have a review pack. Pick one from the desk.</td></tr>';
});
