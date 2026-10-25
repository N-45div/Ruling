// The fan card for one published VAR decision, with the explanation in the fan's language.
import { get, params, post } from "./api.js";
import { drawFreezeFrame } from "./pitch.js";
import { CATEGORY, DECISION, esc, total } from "./labels.js";

const LANGUAGES = [["en", "English"], ["es", "Español"], ["hi", "हिन्दी"], ["fr", "Français"], ["pt", "Português"], ["ar", "العربية"],
  ["id", "Indonesia"], ["zh", "中文"], ["de", "Deutsch"], ["ja", "日本語"], ["sw", "Kiswahili"]];
const RTL = new Set(["ar"]);
const checkId = params.get("check");
let current = "en";

async function main() {
  const card = document.getElementById("card");
  if (!checkId) { card.innerHTML = '<div class="empty">Open a fan card from the desk.</div>'; return; }
  let c;
  try {
    ({ case: c } = await get(`/api/checks/${checkId}`));
  } catch {
    card.innerHTML = '<div class="empty">This decision could not be found. Open the fan card again from the desk.</div>';
    return;
  }
  if (!c || c.status !== "published") { card.innerHTML = `<div class="empty">${esc(c?.holding ?? "This decision has not been published yet.")}</div>`; return; }
  const match = await get(`/api/matches/${Number(c.match_id.split("-").pop())}`);
  const { packet } = await get(`/api/incidents/${c.incident_id}`);
  const minute = c.clock.split(":")[0].replace(/^0/, "");
  card.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center"><b class="phone-title">Match Centre</b><span class="mono muted small">${esc(minute)}'</span></div>
    <div class="panel" style="display:flex;justify-content:space-between;align-items:center;gap:8px">
      <span class="team"><span class="dot" style="background:#E14D5F"></span>${esc(match.home.name)}</span>
      <span class="mono" style="font-size:20px;font-weight:600;white-space:nowrap">${c.score[0]} – ${c.score[1]}</span>
      <span class="team">${esc(match.away.name)}<span class="dot" style="background:#3BA3D9"></span></span>
    </div>
    <div class="panel" style="padding:0;overflow:hidden">
      <div style="padding:16px 16px 12px"><div class="kicker">VAR decision · ${esc(minute)}'</div>
        <div class="verdict-title" style="margin-top:4px">${esc(DECISION[c.verdict.final_decision])}</div>
        <div class="muted small">${esc(CATEGORY[c.category])}</div></div>
      <svg class="pitch" id="freeze" viewBox="0 0 400 300" role="img" aria-label="Freeze-frame of the incident"></svg>
      <p id="text" style="margin:0;padding:14px 16px 8px">${esc(c.drafts.fan)}</p>
      <div class="listen"><button type="button" class="btn small" id="listen" aria-describedby="listen-note">▶ Listen</button><span class="small muted" id="listen-note">Read aloud by Azure AI Speech</span></div>
    </div>
    <div class="lang" role="group" aria-label="Language">${LANGUAGES.map(([code, name]) => `<button type="button" data-lang="${code}" lang="${code}" aria-pressed="${code === current}">${name}</button>`).join("")}</div>
    <div class="panel" style="display:flex;flex-direction:column;gap:8px">
      <b class="phone-title">How this was decided</b>
      <span>Measured from tracking data at the decisive moment</span>
      <span>Law ${esc(c.law.id)}, ${esc(c.law.title.toLowerCase())}</span>
      ${c.precedent ? `<span>${c.precedent.agreeing} of ${total(c.precedent.finals)} similar past checks ended the same way</span>` : ""}
      <a href="${esc(c.law.url)}" target="_blank" rel="noopener">Read the Law (IFAB)</a>
    </div>
    <div class="small muted" style="text-align:center">Explained by Ruling · every claim checked before publishing</div>`;
  drawFreezeFrame(document.getElementById("freeze"), packet, c, match.home.code);
  for (const button of card.querySelectorAll(".lang button")) button.onclick = () => choose(button.dataset.lang, c);
  document.getElementById("listen").onclick = listen;
}

// The card read aloud in the language on screen; the audio is made once per language, then cached.
async function listen() {
  const button = document.getElementById("listen"), note = document.getElementById("listen-note");
  const language = current, name = LANGUAGES.find(([code]) => code === language)[1];
  button.disabled = true;
  note.textContent = "Getting the voice ready…";
  try {
    const res = await fetch(`/api/checks/${checkId}/listen?language=${language}`);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `${res.status}`);
    const audio = new Audio(URL.createObjectURL(await res.blob()));
    audio.onended = () => { button.disabled = false; note.textContent = "Read aloud by Azure AI Speech"; };
    await audio.play();
    note.textContent = `Playing · ${name}`;
  } catch (err) {
    button.disabled = false;
    note.textContent = String(err.message ?? err);
  }
}

async function choose(language, c) {
  current = language;
  for (const b of document.querySelectorAll(".lang button")) b.setAttribute("aria-pressed", String(b.dataset.lang === language));
  const text = document.getElementById("text");
  const show = (words, lang) => { text.textContent = words; text.lang = lang; text.dir = RTL.has(lang) ? "rtl" : "ltr"; };
  if (language === "en") { show(c.drafts.fan, "en"); return; }
  text.textContent = "Translating…";
  try {
    const result = await post(`/api/checks/${checkId}/translate`, { language });
    if (current !== language) return;  // the fan picked another language meanwhile
    show(result.text, result.verified ? language : "en");
  } catch {
    if (current !== language) return;
    show(c.drafts.fan, "en");
  }
}

main();
