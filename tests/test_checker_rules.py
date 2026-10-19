from ruling.desk.assessor import Verdict
from ruling.desk.checker import rule_issues, style_issues
from ruling.desk.communicator import Drafts
from ruling.desk.evidence import Evidence
from ruling.desk.packet import CheckPacket

EVIDENCE = Evidence("offside", "no_goal", "11.2", "interfering_with_play", "no_card",
                    ("At the moment of the pass, AGA No.9 Kofi Lunanek's right foot was 4 cm beyond the offside line.",))
PACKET = CheckPacket("i", "offside", "m", "AGA", "BRC", (0, 0), 1, "35:10", "AGA", "goal", {}, (), {}, {})
VERDICT = Verdict("no_goal", "no_card", "var_overturn", "11.2", announced=False)


def drafts(**kw) -> Drafts:
    base = dict(match_centre="#AGABRC – 35' VAR OVERTURN: the goal is disallowed for offside.", stadium="",
                broadcaster=["Goal disallowed.", "Right foot 4 cm beyond the line.", "Law 11.2."],
                fan="The goal is disallowed: Kofi Lunanek's right foot was 4 cm beyond the offside line.")
    base.update(kw)
    return Drafts(**base)


def test_a_clean_draft_passes_the_rules():
    assert rule_issues(drafts(), PACKET, EVIDENCE, VERDICT) == []


def test_video_claims_and_invented_figures_block_and_pronouns_are_style():
    bad = drafts(fan="Replays show his foot was 9 cm beyond the line, so the goal is disallowed.")
    issues = " | ".join(rule_issues(bad, PACKET, EVIDENCE, VERDICT))
    assert "video" in issues and "0.09 m is not in the evidence" in issues
    assert "pronoun" not in issues
    assert any("pronoun" in s for s in style_issues(bad))


def test_the_fan_card_must_state_the_decision():
    issues = rule_issues(drafts(fan="Kofi Lunanek's right foot was 4 cm beyond the offside line."),
                         PACKET, EVIDENCE, VERDICT)
    assert any("does not state the final decision" in i for i in issues)


def test_stadium_announcements_only_when_due():
    assert any("no announcement is due" in i for i in rule_issues(
        drafts(stadium='REF: "Final decision is offside."'), PACKET, EVIDENCE, VERDICT))
    due = Verdict("no_goal", "no_card", "on_field_review", "11.2", announced=True)
    assert any("must read REF" in i for i in rule_issues(drafts(), PACKET, EVIDENCE, due))


def test_speeds_in_metres_per_second_are_not_read_as_distances():
    fine = drafts(broadcaster=["Goal disallowed.", "Right foot 4 cm beyond the line at 6.5 m/s.", "Law 11.2."])
    assert rule_issues(fine, PACKET, EVIDENCE, VERDICT) == []
