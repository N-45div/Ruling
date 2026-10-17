"""Possession-chain match engine.

A match is a sequence of possessions. Each possession starts from a restart or a regain
and runs through on-ball actions (pass, carry, dribble, cross, shot) until it ends in a
turnover, a foul, an offside, the ball going out of play, or a goal. Probabilities depend
on the zone, the players' attributes and both teams' styles. All tunable constants live
in `Params`, calibrated against public per-match aggregates (see scripts/calibrate.py).

The engine works in the attacking frame of the team in possession and converts every
event to absolute coordinates when it is recorded.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ..incidents.fouls import FoulPlanner
from ..incidents.offside import OffsidePlanner
from . import events as ev
from . import pitch
from .clubs import ROLE_DEF, ROLE_FWD, ROLE_GK, ROLE_MID, Club, Player
from .flow import DEAD_TIME as _DEAD_TIME
from .flow import Restart as _Restart
from .reviews import VarReviews

SUBSTITUTION = "substitution"


@dataclass(frozen=True)
class Params:
    """Tunable constants. Defaults are calibrated by scripts/calibrate.py (seeds 5001-5200)."""

    short_pass_length: float = 14.0
    long_pass_length: float = 32.0
    pass_success_base: float = 1.02  # before the penalties below; capped by the draw
    pass_length_penalty: float = 0.004  # per metre beyond 12 m
    final_third_penalty: float = 0.12
    pressing_penalty: float = 0.06
    dribble_success: float = 0.48
    cross_success: float = 0.24
    cross_cleared_for_corner: float = 0.44  # share of cleared crosses that go behind
    carry_loss: float = 0.10
    shot_appetite: float = 0.58  # multiplies xG to give the per-action shot weight
    long_shot_weight: float = 0.14  # baseline shot weight within 32 m of goal
    pass_preference: float = 1.7  # weight of a short pass relative to other actions
    cautioned_restraint: float = 0.3  # a cautioned player fouls, and is booked, less often
    foul_on_tackle: float = 0.60
    foul_in_box_factor: float = 0.12  # defenders foul far less inside their own area
    handball_share: float = 0.05
    reckless_share: float = 0.20  # fouls that earn a caution
    excessive_share: float = 0.003  # fouls that earn a straight red
    offside_rate: float = 0.04  # forward passes into the final third flagged offside
    stoppage_first: tuple[int, int] = (60, 300)
    stoppage_second: tuple[int, int] = (150, 480)
    # VAR-checked incidents (used only when incidents are on)
    penalty_claim_rate: float = 0.14  # duels near the area that become penalty claims
    red_check_rate: float = 0.007  # other duels that become possible sending-offs
    handball_block_rate: float = 0.045  # blocked shots that strike an arm
    handball_cross_rate: float = 0.012  # cleared crosses that strike an arm
    handball_goal_rate: float = 0.12  # goals with no real offside question that follow an attacker's touch


DEFAULT_PARAMS = Params()


@dataclass
class _Side:
    club: Club
    home: bool
    on_pitch: list[Player] = field(default_factory=list)
    bench: list[Player] = field(default_factory=list)
    cautioned: set[str] = field(default_factory=set)
    subs_made: int = 0

    def attacks_right(self, period: int) -> bool:
        return self.home == (period == 1)

    def pick(self, weights: dict[str, float], rng: random.Random, exclude: Player | None = None) -> Player:
        pool = [p for p in self.on_pitch if p is not exclude] or self.on_pitch
        w = [weights.get(p.role, 0.0) + 1e-3 for p in pool]
        return rng.choices(pool, weights=w)[0]


def expected_goals(x: float, y: float, header: bool = False) -> float:
    """A simple location model: chance of a shot from (x, y), attacking frame, scoring.

    The intercept absorbs the defensive pressure a location-only model cannot see.
    """
    d = pitch.distance_to_goal(x, y)
    angle = pitch.goal_angle(x, y)
    logit = -1.6 - 0.11 * d + 1.6 * angle - (0.9 if header else 0.0)
    return round(1 / (1 + math.exp(-logit)), 4)


class MatchEngine(VarReviews):
    def __init__(self, home: Club, away: Club, seed: int, params: Params = DEFAULT_PARAMS,
                 incidents: bool = True):
        self.rng = random.Random(seed)
        self.params = params
        # Incident planners and the triggers that call them have their own random streams.
        self.offside = OffsidePlanner(seed) if incidents else None
        self.fouls = FoulPlanner(seed) if incidents else None
        self.irng = random.Random(f"triggers:{seed}")
        self.match = ev.Match(id=f"{home.code}-{away.code}-{seed}", seed=seed, home=home.code, away=away.code)
        self.sides = (self._side(home, True), self._side(away, False))
        self.match.home_lineup = [p.id for p in home.starters]
        self.match.away_lineup = [p.id for p in away.starters]
        self.period = 1
        self.second = 0.0

    @staticmethod
    def _side(club: Club, home: bool) -> _Side:
        return _Side(club, home, list(club.starters), list(club.bench))

    # ---- recording -------------------------------------------------------------

    def _emit(self, team: int, player: Player | None, kind: str, result: str,
              start: tuple[float, float], end: tuple[float, float] | None = None, **extra) -> None:
        side = self.sides[team]
        right = side.attacks_right(self.period)
        sx, sy = pitch.to_absolute(*pitch.clamp_to_pitch(*start), right)
        ex, ey = pitch.to_absolute(*pitch.clamp_to_pitch(*(end or start)), right)
        self.match.events.append(ev.Event(
            match_id=self.match.id, index=len(self.match.events), period=self.period,
            second=round(self.second, 1), team=side.club.code, player=player.id if player else None,
            type=kind, result=result, start_x=round(sx, 2), start_y=round(sy, 2),
            end_x=round(ex, 2), end_y=round(ey, 2), **extra,
        ))

    def _tick(self, low: float, high: float) -> None:
        self.second += self.rng.uniform(low, high)

    # ---- match flow ------------------------------------------------------------

    def play(self) -> ev.Match:
        for period, stoppage in ((1, self.params.stoppage_first), (2, self.params.stoppage_second)):
            self.period, self.second = period, 0.0
            end = ev.PERIOD_SECONDS + self.rng.randint(*stoppage)
            kicker = 0 if period == 1 else 1
            self._emit(kicker, None, ev.PERIOD_START, ev.SUCCESS, (pitch.HALFWAY_X, pitch.CENTRE_Y))
            restart = _Restart(ev.KICKOFF, kicker, pitch.HALFWAY_X, pitch.CENTRE_Y)
            while self.second < end:
                if period == 2:
                    self._maybe_substitute()
                restart = self._possession(restart)
            self._emit(kicker, None, ev.PERIOD_END, ev.SUCCESS, (pitch.HALFWAY_X, pitch.CENTRE_Y))
        return self.match

    def _maybe_substitute(self) -> None:
        if self.second < 10 * 60:
            return
        for team, side in enumerate(self.sides):
            if side.subs_made >= 5 or not side.bench:
                continue
            due = 10 * 60 + side.subs_made * 7 * 60
            if self.second >= due and self.rng.random() < 0.02:
                outfield = [p for p in side.on_pitch if p.role != ROLE_GK]
                off = self.rng.choice(outfield)
                same_role = [p for p in side.bench if p.role == off.role] or [p for p in side.bench if p.role != ROLE_GK]
                if not same_role:
                    continue
                on = same_role[0]
                side.bench.remove(on)
                side.on_pitch[side.on_pitch.index(off)] = on
                side.subs_made += 1
                self._emit(team, on, SUBSTITUTION, ev.SUCCESS, (pitch.HALFWAY_X, 0.0), detail=f"off:{off.id}")

    def _possession(self, restart: _Restart) -> _Restart:
        team, x, y = restart.team, restart.x, restart.y
        side = self.sides[team]
        carrier = self._restart_taker(side, restart)
        if restart.kind != "regain":
            self._emit(team, carrier, restart.kind, ev.SUCCESS, (x, y), detail=restart.detail)
            if restart.kind == ev.PENALTY:
                return self._shot(team, carrier, pitch.LENGTH - pitch.PENALTY_SPOT_DISTANCE, pitch.CENTRE_Y,
                                  xg=0.78, detail="penalty")
            if restart.kind == ev.CORNER:
                return self._cross(team, carrier, x, y)
        for _ in range(60):
            action = self._choose_action(side, x, y)
            if action == "shot":
                return self._shot(team, carrier, x, y)
            if action == "cross":
                return self._cross(team, carrier, x, y)
            if action in ("pass", "long"):
                outcome = self._pass(team, carrier, x, y, long=(action == "long"))
            elif action == "dribble":
                outcome = self._dribble(team, carrier, x, y)
            else:
                outcome = self._carry(team, carrier, x, y)
            if isinstance(outcome, _Restart):
                return outcome
            carrier, x, y = outcome
            self._tick(0.1, 0.6)
        return _Restart("regain", 1 - team, *pitch.flip(x, y))

    def _restart_taker(self, side: _Side, restart: _Restart) -> Player:
        rng = self.rng
        if restart.kind == ev.GOAL_KICK:
            return side.pick({ROLE_GK: 1.0}, rng)
        if restart.kind == ev.KICKOFF:
            return side.pick({ROLE_FWD: 1.0, ROLE_MID: 0.3}, rng)
        if restart.kind in (ev.CORNER, ev.PENALTY):
            return side.pick({ROLE_MID: 1.0, ROLE_FWD: 1.0}, rng)
        if restart.kind == ev.THROW_IN:
            return side.pick({ROLE_DEF: 1.0, ROLE_MID: 0.4}, rng)
        if restart.x < pitch.LENGTH / 3:
            return side.pick({ROLE_DEF: 1.0, ROLE_GK: 0.3, ROLE_MID: 0.5}, rng)
        if restart.x < 2 * pitch.LENGTH / 3:
            return side.pick({ROLE_DEF: 0.6, ROLE_MID: 1.0, ROLE_FWD: 0.3}, rng)
        return side.pick({ROLE_DEF: 0.1, ROLE_MID: 0.8, ROLE_FWD: 1.0}, rng)

    # ---- actions ---------------------------------------------------------------

    def _choose_action(self, side: _Side, x: float, y: float) -> str:
        style = side.club.style
        zone = pitch.third(x)
        long_w = 0.06 + 0.22 * style.directness
        if zone == 0:
            weights = {"pass": 0.72, "long": long_w, "carry": 0.16, "dribble": 0.02}
        elif zone == 1:
            weights = {"pass": 0.64, "long": long_w * 0.7, "carry": 0.2, "dribble": 0.08}
        else:
            wide = y < 14 or y > pitch.WIDTH - 14
            weights = {"pass": 0.55, "carry": 0.12, "dribble": 0.14}
            if pitch.distance_to_goal(x, y) < 32:
                weights["shot"] = self.params.long_shot_weight + expected_goals(x, y) * self.params.shot_appetite
            if wide:
                weights["cross"] = 0.22 if x > pitch.LENGTH - 30 else 0.05
        weights["pass"] *= self.params.pass_preference + 0.4 * style.possession
        kinds = list(weights)
        return self.rng.choices(kinds, weights=[weights[k] for k in kinds])[0]

    def _receiver_weights(self, x: float) -> dict[str, float]:
        zone = pitch.third(x)
        if zone == 0:
            return {ROLE_GK: 0.15, ROLE_DEF: 1.0, ROLE_MID: 0.8}
        if zone == 1:
            return {ROLE_DEF: 0.5, ROLE_MID: 1.0, ROLE_FWD: 0.45}
        return {ROLE_DEF: 0.15, ROLE_MID: 0.7, ROLE_FWD: 1.0}

    def _defender(self, opp: _Side, x: float) -> Player:
        """The opponent most likely to contest the ball at x (attacking frame)."""
        zone = pitch.third(x)
        weights = ({ROLE_FWD: 1.0, ROLE_MID: 0.8}, {ROLE_MID: 1.0, ROLE_DEF: 0.5, ROLE_FWD: 0.3},
                   {ROLE_DEF: 1.0, ROLE_MID: 0.4})[zone]
        return opp.pick(weights, self.rng)

    def _pass(self, team: int, carrier: Player, x: float, y: float, long: bool):
        p, rng = self.params, self.rng
        side, opp = self.sides[team], self.sides[1 - team]
        mean = p.long_pass_length if long else p.short_pass_length
        length = max(4.0, rng.gauss(mean, mean * 0.35))
        forward = 0.35 + 0.4 * side.club.style.directness + (0.3 if long else 0.0)
        heading = rng.gauss(0.0, 1.0) if rng.random() > forward else rng.gauss(0.0, 0.45)
        tx, ty = x + length * math.cos(heading), y + length * math.sin(heading)
        receiver = side.pick(self._receiver_weights(tx), rng, exclude=carrier)
        self._tick(0.5 + length / 18, 1.0 + length / 14)
        out_of_play = not (0 <= ty <= pitch.WIDTH) or tx > pitch.LENGTH
        tx, ty = pitch.clamp_to_pitch(tx, ty)
        chance = (p.pass_success_base + 0.15 * (carrier.passing - 0.6)
                  - p.pass_length_penalty * max(0.0, length - 12)
                  - (p.final_third_penalty if pitch.third(tx) == 2 else 0.0)
                  - p.pressing_penalty * opp.club.style.pressing)
        if (tx > x + 8 and pitch.third(tx) == 2 and receiver.role == ROLE_FWD
                and rng.random() < p.offside_rate):
            self._emit(team, carrier, ev.PASS, ev.FAIL, (x, y), (tx, ty), receiver=receiver.id, detail="offside")
            self._emit(team, receiver, ev.OFFSIDE, ev.FAIL, (tx, ty))
            self._tick(*_DEAD_TIME[ev.OFFSIDE])
            return _Restart(ev.FREE_KICK, 1 - team, *pitch.flip(tx, ty), detail="offside")
        if not out_of_play and rng.random() < chance:
            self._emit(team, carrier, ev.PASS, ev.SUCCESS, (x, y), (tx, ty), receiver=receiver.id)
            return receiver, tx, ty
        self._emit(team, carrier, ev.PASS, ev.FAIL, (x, y), (tx, ty), receiver=receiver.id)
        if out_of_play:
            return self._out_of_play(team, tx, ty)
        interceptor = self._defender(opp, tx)
        self._emit(1 - team, interceptor, ev.INTERCEPTION, ev.SUCCESS, pitch.flip(tx, ty))
        return _Restart("regain", 1 - team, *pitch.flip(tx, ty))

    def _carry(self, team: int, carrier: Player, x: float, y: float):
        rng = self.rng
        tx = x + max(0.0, rng.gauss(6, 3))
        ty = y + rng.gauss(0, 3)
        tx, ty = pitch.clamp_to_pitch(min(tx, pitch.LENGTH - 2), ty)
        self._tick(1.5, 3.5)
        if rng.random() < self.params.carry_loss:
            return self._duel_lost(team, carrier, x, y)
        self._emit(team, carrier, ev.CARRY, ev.SUCCESS, (x, y), (tx, ty))
        return carrier, tx, ty

    def _dribble(self, team: int, carrier: Player, x: float, y: float):
        rng = self.rng
        self._tick(1.5, 3.0)
        chance = self.params.dribble_success + 0.25 * (carrier.pace - 0.6)
        if rng.random() < chance:
            tx, ty = pitch.clamp_to_pitch(min(x + rng.uniform(3, 8), pitch.LENGTH - 2), y + rng.gauss(0, 2))
            self._emit(team, carrier, ev.DRIBBLE, ev.SUCCESS, (x, y), (tx, ty))
            return carrier, tx, ty
        self._emit(team, carrier, ev.DRIBBLE, ev.FAIL, (x, y))
        return self._duel_lost(team, carrier, x, y)

    def _duel_lost(self, team: int, carrier: Player, x: float, y: float) -> _Restart:
        """The carrier is challenged: either a clean tackle or a foul."""
        rng, p = self.rng, self.params
        opp = self.sides[1 - team]
        defender = self._defender(opp, x)
        if self.fouls:
            if x >= 84 and abs(y - pitch.CENTRE_Y) <= 24:
                if self.irng.random() < p.penalty_claim_rate:
                    return self._penalty_claim(team, carrier, defender, x, y)
                # Every penalty is a VAR-checked claim; other duels by the area are clean tackles.
                self._emit(1 - team, defender, ev.TACKLE, ev.SUCCESS, pitch.flip(x, y))
                return _Restart("regain", 1 - team, *pitch.flip(x, y))
            if self.irng.random() < p.red_check_rate:
                return self._red_check(team, carrier, defender, x, y)
        foul_chance = p.foul_on_tackle * (0.6 + defender.aggression)
        if defender.id in opp.cautioned:
            foul_chance *= p.cautioned_restraint
        if pitch.in_penalty_area(x, y):
            foul_chance *= p.foul_in_box_factor
        if rng.random() < foul_chance:
            return self._foul(team, carrier, defender, x, y)
        self._emit(1 - team, defender, ev.TACKLE, ev.SUCCESS, pitch.flip(x, y))
        return _Restart("regain", 1 - team, *pitch.flip(x, y))

    def _foul(self, team: int, fouled: Player, offender: Player, x: float, y: float) -> _Restart:
        rng, p = self.rng, self.params
        kind = "handball" if rng.random() < p.handball_share else rng.choice(
            ("trip", "trip", "push", "holding", "tackle", "charge", "kick"))
        self._emit(1 - team, offender, ev.FOUL, ev.FAIL, pitch.flip(x, y), detail=kind, receiver=fouled.id)
        roll = rng.random()
        # With incidents on, every straight red goes through a VAR-checked red-card incident.
        excessive = 0.0 if self.fouls else p.excessive_share * (0.5 + offender.aggression)
        reckless = p.reckless_share * (0.5 + offender.aggression)
        if offender.id in self.sides[1 - team].cautioned:
            reckless *= p.cautioned_restraint
        if roll < excessive:
            self._card(1 - team, offender, ev.RED, "serious_foul_play", x, y)
        elif roll < excessive + reckless:
            self._card(1 - team, offender, ev.YELLOW, "reckless", x, y)
        if pitch.in_penalty_area(x, y):
            self._tick(*_DEAD_TIME[ev.PENALTY])
            spot = pitch.LENGTH - pitch.PENALTY_SPOT_DISTANCE
            return _Restart(ev.PENALTY, team, spot, pitch.CENTRE_Y, detail=kind)
        self._tick(*_DEAD_TIME[ev.FREE_KICK])
        return _Restart(ev.FREE_KICK, team, x, y, detail=kind)

    def _card(self, team: int, player: Player, colour: str, reason: str, x: float, y: float) -> None:
        side = self.sides[team]
        if colour == ev.YELLOW and player.id in side.cautioned:
            colour = ev.SECOND_YELLOW
        side.cautioned.add(player.id)
        self._emit(team, player, ev.CARD, colour, pitch.flip(x, y), detail=reason)
        self._tick(10, 25)
        if colour in (ev.RED, ev.SECOND_YELLOW) and player in side.on_pitch and len(side.on_pitch) > 7:
            side.on_pitch.remove(player)

    def _cross(self, team: int, carrier: Player, x: float, y: float) -> _Restart:
        rng = self.rng
        side, opp = self.sides[team], self.sides[1 - team]
        tx = rng.uniform(pitch.LENGTH - 14, pitch.LENGTH - 4)
        ty = rng.gauss(pitch.CENTRE_Y, 6)
        self._tick(1.5, 3.0)
        target = side.pick({ROLE_FWD: 1.0, ROLE_MID: 0.4, ROLE_DEF: 0.3}, rng, exclude=carrier)
        if rng.random() < self.params.cross_success:
            self._emit(team, carrier, ev.CROSS, ev.SUCCESS, (x, y), (tx, ty), receiver=target.id)
            return self._shot(team, target, tx, ty, header=rng.random() < 0.6)
        self._emit(team, carrier, ev.CROSS, ev.FAIL, (x, y), (tx, ty), receiver=target.id)
        if rng.random() < 0.25:
            keeper = opp.pick({ROLE_GK: 1.0}, rng)
            self._emit(1 - team, keeper, ev.CLAIM, ev.SUCCESS, pitch.flip(tx, ty))
            return _Restart("regain", 1 - team, *pitch.flip(tx, ty))
        clearer = opp.pick({ROLE_DEF: 1.0, ROLE_MID: 0.2}, rng)
        self._emit(1 - team, clearer, ev.CLEARANCE, ev.SUCCESS, pitch.flip(tx, ty))
        if rng.random() < self.params.cross_cleared_for_corner:
            corner_y = 0.0 if ty < pitch.CENTRE_Y else pitch.WIDTH
            self._tick(*_DEAD_TIME[ev.CORNER])
            otherwise = _Restart(ev.CORNER, team, pitch.LENGTH, corner_y)
        else:
            otherwise = _Restart("regain", 1 - team, *pitch.flip(rng.uniform(20, 45), rng.uniform(5, 63)))
        if self.fouls and self.irng.random() < self.params.handball_cross_rate:
            return self._handball_claim(team, clearer, tx, ty, otherwise)
        return otherwise

    def _shot(self, team: int, shooter: Player, x: float, y: float, header: bool = False,
              xg: float | None = None, detail: str | None = None) -> _Restart:
        rng = self.rng
        xg = xg if xg is not None else expected_goals(x, y, header)
        self._tick(0.5, 1.5)
        scored = rng.random() < min(0.95, xg * (0.75 + 0.5 * shooter.finishing))
        goal_mouth = (pitch.LENGTH, rng.uniform(pitch.CENTRE_Y - 3.6, pitch.CENTRE_Y + 3.6))
        part = "head" if header else "foot"
        if scored:
            plan = None
            if self.offside and detail != "penalty":
                plan = self.offside.plan(self.match, self.sides[team].club.code, shooter.id, (x, y))
            if plan and plan.pre_touch:
                defender_id, touch, position = plan.pre_touch
                defender = self.sides[1 - team].club.player(defender_id)
                frame_xy = pitch.to_absolute(*position, self.sides[1 - team].attacks_right(self.period))
                self._emit(1 - team, defender, ev.CLEARANCE, ev.FAIL, frame_xy, detail=touch)
            handball = None
            no_offside_question = plan is None or plan.scenario == "clear_onside"
            if (no_offside_question and self.fouls and detail != "penalty"
                    and self.irng.random() < self.params.handball_goal_rate):
                handball = self.fouls.handball_goal(self.match, self.sides[team].club.code, shooter.id, (x, y))
                plan = None  # the check that matters for this goal is the handball
            self._emit(team, shooter, ev.SHOT, ev.GOAL, (x, y), goal_mouth, xg=xg, body_part=part, detail=detail)
            if plan:
                return self._review_goal(team, plan)
            if handball:
                return self._review_handball_goal(team, shooter, handball)
            self._tick(*_DEAD_TIME[ev.KICKOFF])
            return _Restart(ev.KICKOFF, 1 - team, pitch.HALFWAY_X, pitch.CENTRE_Y)
        opp = self.sides[1 - team]
        roll = rng.random()
        if detail != "penalty" and roll < 0.28:
            blocker = opp.pick({ROLE_DEF: 1.0, ROLE_MID: 0.3}, rng)
            self._emit(team, shooter, ev.SHOT, ev.BLOCKED, (x, y), xg=xg, body_part=part, detail=detail)
            self._emit(1 - team, blocker, ev.CLEARANCE, ev.SUCCESS, pitch.flip(x, y), detail="block")
            if rng.random() < 0.4:
                self._tick(*_DEAD_TIME[ev.CORNER])
                otherwise = _Restart(ev.CORNER, team, pitch.LENGTH, rng.choice((0.0, pitch.WIDTH)))
            else:
                otherwise = _Restart("regain", 1 - team, *pitch.flip(x, y))
            if self.fouls and x >= 80 and self.irng.random() < self.params.handball_block_rate:
                block_xy = (x + (pitch.LENGTH - x) * 0.3, y + (pitch.CENTRE_Y - y) * 0.3)
                return self._handball_claim(team, blocker, *block_xy, otherwise)
            return otherwise
        if roll < 0.62:
            keeper = opp.pick({ROLE_GK: 1.0}, rng)
            self._emit(team, shooter, ev.SHOT, ev.SAVED, (x, y), goal_mouth, xg=xg, body_part=part, detail=detail)
            self._emit(1 - team, keeper, ev.SAVE, ev.SUCCESS, pitch.flip(*goal_mouth))
            if rng.random() < 0.3:
                self._tick(*_DEAD_TIME[ev.CORNER])
                return _Restart(ev.CORNER, team, pitch.LENGTH, rng.choice((0.0, pitch.WIDTH)))
            return _Restart("regain", 1 - team, 4.0, pitch.CENTRE_Y)
        wide = (pitch.LENGTH, rng.choice((rng.uniform(20, 30), rng.uniform(38, 48))))
        self._emit(team, shooter, ev.SHOT, ev.OFF_TARGET, (x, y), wide, xg=xg, body_part=part, detail=detail)
        self._tick(*_DEAD_TIME[ev.GOAL_KICK])
        return _Restart(ev.GOAL_KICK, 1 - team, 5.5, pitch.CENTRE_Y)

    def _out_of_play(self, team: int, x: float, y: float) -> _Restart:
        """Restart for the opponent after `team` put the ball out at (x, y), attacking frame."""
        self._emit(team, None, ev.BALL_OUT, ev.FAIL, (x, y))
        if x >= pitch.LENGTH:
            self._tick(*_DEAD_TIME[ev.GOAL_KICK])
            return _Restart(ev.GOAL_KICK, 1 - team, 5.5, pitch.CENTRE_Y)
        self._tick(*_DEAD_TIME[ev.THROW_IN])
        fx, fy = pitch.flip(x, y)
        return _Restart(ev.THROW_IN, 1 - team, fx, 0.0 if fy < pitch.CENTRE_Y else pitch.WIDTH)


def simulate(home: Club, away: Club, seed: int, params: Params = DEFAULT_PARAMS,
             incidents: bool = True) -> ev.Match:
    return MatchEngine(home, away, seed, params, incidents).play()
