// Words shared by every page of the desk.

export const CATEGORY = {
  offside: "Offside, goal", penalty_claim: "Penalty claim", handball: "Handball",
  handball_goal: "Handball before a goal", red_card: "Possible red card",
};
export const DECISION = {
  goal: "Goal stands", no_goal: "Goal disallowed", penalty: "Penalty", free_kick: "Free kick",
  no_foul: "No foul", red: "Red card", yellow: "Yellow card", no_card: "No card",
};
export const REVIEW = { check_complete: "Check complete", var_overturn: "VAR overturn", on_field_review: "On-field review" };
export const DRILL = {
  tracking_dropout: "Tracking drops out", player_missing: "A player vanishes from tracking",
  model_timeout: "The model times out", wrong_draft: "The writer states the wrong decision",
};

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const total = (finals) => Object.values(finals ?? {}).reduce((a, b) => a + b, 0);
