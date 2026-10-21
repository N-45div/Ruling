// Pitch drawings in SVG. Coordinates are metres on a 105 x 68 pitch (x left to right,
// y from the near touchline), as served by the API.

const NS = "http://www.w3.org/2000/svg";
const LENGTH = 105, WIDTH = 68;
const AREA = { depth: 16.5, low: 13.84, high: 54.16 };
const GOAL_AREA = { depth: 5.5, low: 24.84, high: 43.16 };
export const COLOURS = { home: "#E14D5F", away: "#3BA3D9", onside: "#5AA9FF", offside: "#FF6B6B", accent: "#F5B544" };

function el(name, attrs = {}, parent) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (parent) parent.appendChild(node);
  return node;
}

function clear(svg) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
}

// Pitch markings drawn through a mapping from metres to screen units.
function markings(svg, map, strokeWidth) {
  const g = el("g", { fill: "none", stroke: "rgba(255,255,255,0.55)", "stroke-width": strokeWidth }, svg);
  const line = (x1, y1, x2, y2) => {
    const [a, b] = map(x1, y1), [c, d] = map(x2, y2);
    el("line", { x1: a, y1: b, x2: c, y2: d }, g);
  };
  const box = (x1, y1, x2, y2) => { line(x1, y1, x2, y1); line(x2, y1, x2, y2); line(x2, y2, x1, y2); line(x1, y2, x1, y1); };
  box(0, 0, LENGTH, WIDTH);
  line(LENGTH / 2, 0, LENGTH / 2, WIDTH);
  box(0, AREA.low, AREA.depth, AREA.high);
  box(LENGTH - AREA.depth, AREA.low, LENGTH, AREA.high);
  box(0, GOAL_AREA.low, GOAL_AREA.depth, GOAL_AREA.high);
  box(LENGTH - GOAL_AREA.depth, GOAL_AREA.low, LENGTH, GOAL_AREA.high);
  const [cx, cy] = map(LENGTH / 2, WIDTH / 2), [ex] = map(LENGTH / 2 + 9.15, WIDTH / 2);
  el("circle", { cx, cy, r: Math.abs(ex - cx) }, g);
}

function player(svg, x, y, r, team, shirt, ring) {
  const fill = team === "home" ? COLOURS.home : COLOURS.away;
  el("circle", { cx: x, cy: y, r, fill, stroke: ring || "#FFFFFF", "stroke-width": ring ? 3 : 1.5 }, svg);
  const text = el("text", {
    x, y: y + r * 0.36, fill: team === "home" ? "#FFFFFF" : "#0B1220", "text-anchor": "middle",
    "font-family": "IBM Plex Mono, monospace", "font-size": r * 1.05, "font-weight": 600,
  }, svg);
  text.textContent = shirt;
}

// The whole pitch with every player at one event.
export function drawPitch(svg, frame, homeCode, offsideLineX = null) {
  clear(svg);
  const s = 6;
  const map = (x, y) => [x * s, (WIDTH - y) * s];
  el("rect", { x: -12, y: -12, width: 654, height: 432, rx: 10, fill: "#17402B" }, svg);
  markings(svg, map, 1.5);
  if (offsideLineX !== null) {
    const [x] = map(offsideLineX, 0);
    el("line", { x1: x, y1: 0, x2: x, y2: WIDTH * s, stroke: COLOURS.offside, "stroke-width": 2, "stroke-dasharray": "6 4" }, svg);
  }
  if (!frame) return;
  for (const p of frame.players) {
    const [x, y] = map(p.x, p.y);
    player(svg, x, y, 8, p.team === homeCode ? "home" : "away", p.shirt);
  }
  const [bx, by] = map(frame.ball[0], frame.ball[1]);
  el("circle", { cx: bx + 6, cy: by - 6, r: 4, fill: "#FFFFFF", stroke: "#0B1220", "stroke-width": 1 }, svg);
}

function torso(body) {
  return body.parts.torso;
}

// A zoomed freeze-frame around the decisive point of a check.
export function drawFreezeFrame(svg, packet, caseFile, homeCode) {
  clear(svg);
  const facts = packet.facts;
  const W = 400, H = 300, s = 20; // 20 m x 15 m window
  const focus = packet.category === "offside"
    ? [caseFile.evidence?.offside_line_x ?? torso(facts.bodies.find((b) => b.player === facts.attacker))[0],
       torso(facts.bodies.find((b) => b.player === facts.attacker))[1]]
    : facts.point;
  const x0 = Math.min(Math.max(focus[0] - 10, 0), LENGTH - W / s);
  const y0 = Math.min(Math.max(focus[1] - 7.5, 0), WIDTH - H / s);
  const map = (x, y) => [(x - x0) * s, (y0 + H / s - y) * s];
  el("rect", { x: 0, y: 0, width: W, height: H, rx: 8, fill: "#17402B" }, svg);
  markings(svg, map, 1.5);

  const team = (b) => (b.team === homeCode ? "home" : "away");
  for (const body of facts.bodies) {
    const [x, y] = map(...torso(body));
    if (x < -20 || x > W + 20 || y < -20 || y > H + 20) continue;
    const key = body.player === facts.attacker || body.player === facts.offender || body.player === facts.victim;
    player(svg, x, y, key ? 11 : 9, team(body), body.shirt, key ? COLOURS.accent : null);
  }
  if (packet.category === "offside" && caseFile.evidence?.offside_line_x != null) {
    const line = caseFile.evidence.offside_line_x;
    const margin = caseFile.evidence.numbers.margin_m ?? 0;
    const front = facts.attacks_right ? line + margin : line - margin;
    const [lx] = map(line, 0), [fx] = map(front, 0);
    el("line", { x1: lx, y1: 0, x2: lx, y2: H, stroke: COLOURS.onside, "stroke-width": 2 }, svg);
    el("line", { x1: fx, y1: 0, x2: fx, y2: H, stroke: margin > 0 ? COLOURS.offside : COLOURS.onside, "stroke-width": 2 }, svg);
    inset(svg, margin);
  } else if (facts.point) {
    const [px, py] = map(...facts.point);
    el("path", { d: `M${px - 7} ${py - 7}L${px + 7} ${py + 7}M${px + 7} ${py - 7}L${px - 7} ${py + 7}`, stroke: COLOURS.accent, "stroke-width": 3 }, svg);
  }
}

// Magnifies a gap of a few centimetres so it can be read.
function inset(svg, margin) {
  const cm = Math.round(Math.abs(margin) * 100);
  el("rect", { x: 12, y: 200, width: 150, height: 86, rx: 8, fill: "#0B1220", stroke: "#2C3B57" }, svg);
  const gap = Math.max(6, Math.min(cm, 60));
  const left = 50 - gap / 2, right = 50 + gap / 2;  // the label sits clear of the lines
  el("line", { x1: left, y1: 212, x2: left, y2: 276, stroke: COLOURS.onside, "stroke-width": 2 }, svg);
  el("line", { x1: right, y1: 212, x2: right, y2: 276, stroke: margin > 0 ? COLOURS.offside : COLOURS.onside, "stroke-width": 2 }, svg);
  const label = el("text", { x: right + 12, y: 248, fill: "#E8ECF3", "text-anchor": "start", "font-family": "IBM Plex Mono, monospace", "font-size": 12, "font-weight": 600 }, svg);
  label.textContent = cm === 0 ? "level" : `${cm} cm`;
}
