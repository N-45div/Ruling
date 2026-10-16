import json

import pytest

from ruling.sim.cli import SETS, main
from ruling.sim.events import read_events


def test_seed_sets_match_the_eval_plan_and_never_overlap():
    assert SETS["dev"] == range(5001, 5021)
    assert SETS["archive"] == range(1, 121)
    assert SETS["held-out"] == range(9001, 9021)
    seeds = [s for r in SETS.values() for s in r]
    assert len(seeds) == len(set(seeds))


def test_held_out_set_needs_explicit_confirmation(tmp_path):
    with pytest.raises(SystemExit):
        main(["generate", "held-out", "--out", str(tmp_path)])


def test_generate_writes_events_and_metadata(tmp_path):
    main(["generate", "dev", "--out", str(tmp_path)])
    folders = sorted((tmp_path / "dev").iterdir())
    assert len(folders) == 20
    meta = json.loads((folders[0] / "match.json").read_text(encoding="utf-8"))
    events = list(read_events(folders[0] / "events.jsonl"))
    assert meta["events"] == len(events) and meta["seed"] in SETS["dev"]
    incidents = (folders[0] / "incidents.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(incidents) == meta["incidents"]
