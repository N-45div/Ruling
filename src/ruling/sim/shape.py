"""Freeze-frames: where all players stand at the moment of an event.

The engine records on-ball events only. A frame places every player on the pitch from
their formation slot, shifted with the ball:
- the team in possession steps up and spreads wide behind the ball;
- the team out of possession holds a compact block between the ball and its own goal,
  with its line height set by the club's style.
Attackers are kept level with or behind the second-last defender unless the event is
an offside, so an ordinary frame never shows a false offside. Positions carry seeded
jitter, so a frame is deterministic for a given match and event.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from . import events as ev
from . import pitch
from .clubs import FORMATIONS, ROLE_GK, Club, league

_DEFENSIVE = frozenset({ev.TACKLE, ev.INTERCEPTION, ev.CLEARANCE, ev.SAVE, ev.CLAIM, ev.FOUL, ev.CARD})
_JITTER = 1.4  # metres


@dataclass(frozen=True, slots=True)
class PlayerSpot:
    player: str
    team: str
    shirt: int
    role: str
    x: float  # absolute coordinates
    y: float


@dataclass(frozen=True, slots=True)
class Frame:
    match_id: str
    event_index: int
    period: int
    second: float
    ball_x: float
    ball_y: float
    possession: str  # club code of the team in possession
    players: tuple[PlayerSpot, ...]

    def team(self, code: str) -> list[PlayerSpot]:
        return [p for p in self.players if p.team == code]


def lineups_at(match: ev.Match, index: int) -> dict[str, dict[str, tuple[float, float]]]:
    """Players on the pitch just before event `index`, each with their formation slot."""
    clubs = league()
    on: dict[str, dict[str, tuple[float, float]]] = {}
    for code, lineup in ((match.home, match.home_lineup), (match.away, match.away_lineup)):
        slots = FORMATIONS[clubs[code].formation]
        on[code] = {pid: (x, y) for pid, (_, x, y) in zip(lineup, slots)}
    for e in match.events[:index]:
        if e.type == "substitution" and e.detail and e.detail.startswith("off:"):
            off = e.detail[4:]
            team = on[e.team]
            if off in team:
                team[e.player] = team.pop(off)
        elif e.type == ev.CARD and e.result in (ev.RED, ev.SECOND_YELLOW):
            on[e.team].pop(e.player, None)
    return on


def _possession(match: ev.Match, event: ev.Event) -> str:
    if event.type in _DEFENSIVE:
        return match.away if event.team == match.home else match.home
    return event.team


def frame_at(match: ev.Match, index: int) -> Frame:
    event = match.events[index]
    clubs = league()
    attackers = _possession(match, event)
    defenders = match.away if attackers == match.home else match.home
    on = lineups_at(match, index)
    rng = random.Random(f"frame:{match.seed}:{index}")
    a_right = match.attacks_right(attackers, event.period)
    # Ball in the attacking frame of the team in possession.
    bx, by = pitch.to_absolute(event.start_x, event.start_y, a_right)

    attack = _attacking_shape(on[attackers], clubs[attackers], bx, by, rng)
    defence = _defensive_shape(on[defenders], clubs[defenders], *pitch.flip(bx, by), rng)
    # Defenders in the attackers' frame, to find the offside line.
    defence_in_attack_frame = {pid: pitch.flip(x, y) for pid, (x, y) in defence.items()}
    line = _second_last_x(defence_in_attack_frame)
    offside_event = event.type == ev.OFFSIDE or event.detail == "offside"
    for pid, (x, y) in attack.items():
        if pid == event.player and event.type != ev.OFFSIDE:
            attack[pid] = (bx, by)
        elif x > max(line, bx) and not (offside_event and pid in (event.receiver, event.player)):
            attack[pid] = (max(line, bx) - abs(rng.gauss(0.8, 0.5)), y)
    if event.player in defence and event.type in _DEFENSIVE:
        defence[event.player] = pitch.flip(bx, by)

    spots = []
    for code, positions, right in ((attackers, attack, a_right), (defenders, defence, not a_right)):
        club = clubs[code]
        for pid, (x, y) in positions.items():
            player = club.player(pid)
            ax, ay = pitch.to_absolute(*pitch.clamp_to_pitch(x, y), right)
            spots.append(PlayerSpot(pid, code, player.shirt, player.role, round(ax, 2), round(ay, 2)))
    return Frame(match.id, index, event.period, event.second, event.start_x, event.start_y, attackers, tuple(spots))


def _attacking_shape(players: dict[str, tuple[float, float]], club: Club, bx: float, by: float,
                     rng: random.Random) -> dict[str, tuple[float, float]]:
    shift = (bx - 45) * 0.75
    out = {}
    for pid, (sx, sy) in players.items():
        if club.player(pid).role == ROLE_GK:
            x = pitch.clamp(4 + max(0.0, bx - 60) * 0.25, 2, 25)
            out[pid] = (x + rng.gauss(0, 0.5), pitch.CENTRE_Y + rng.gauss(0, 1.5))
            continue
        x = sx + shift + rng.gauss(0, _JITTER)
        y = pitch.CENTRE_Y + (sy - pitch.CENTRE_Y) * 1.1 + (by - pitch.CENTRE_Y) * 0.3 + rng.gauss(0, _JITTER)
        out[pid] = (x, y)
    return out


def _defensive_shape(players: dict[str, tuple[float, float]], club: Club, bx: float, by: float,
                     rng: random.Random) -> dict[str, tuple[float, float]]:
    """Shape of the team without the ball, in its own attacking frame; (bx, by) is the ball."""
    line_x = pitch.clamp(bx - 22 + 10 * club.style.line_height, 7, 50)
    out = {}
    for pid, (sx, sy) in players.items():
        if club.player(pid).role == ROLE_GK:
            x = pitch.clamp(3 + max(0.0, line_x - 20) * 0.3, 1, 18)
            out[pid] = (x + rng.gauss(0, 0.5), pitch.CENTRE_Y + (by - pitch.CENTRE_Y) * 0.15)
            continue
        x = line_x + (sx - 24) * 0.7 + rng.gauss(0, _JITTER)
        y = pitch.CENTRE_Y + (sy - pitch.CENTRE_Y) * 0.8 + (by - pitch.CENTRE_Y) * 0.45 + rng.gauss(0, _JITTER)
        out[pid] = (x, y)
    return out


def _second_last_x(defenders: dict[str, tuple[float, float]]) -> float:
    """x of the second-last defender, in the attacking frame (larger x is nearer their goal)."""
    xs = sorted((x for x, _ in defenders.values()), reverse=True)
    return xs[1] if len(xs) > 1 else pitch.HALFWAY_X
