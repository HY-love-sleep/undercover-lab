from __future__ import annotations

import json
import random
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .adapters import ActionContext, Adapter, build_adapter, detect_repetition, detect_violations, extract_vote
from .models import Event, GameConfig, GameResult, PlayerConfig, PlayerState


class UndercoverGame:
    def __init__(
        self,
        game_config: GameConfig,
        player_configs: List[PlayerConfig],
        seed: Optional[int] = None,
        undercover_count: int = 1,
    ) -> None:
        if len(player_configs) < 3:
            raise ValueError("至少需要 3 名玩家")
        if len({player.id for player in player_configs}) != len(player_configs):
            raise ValueError("玩家 id 必须唯一")
        if undercover_count < 1:
            raise ValueError("卧底人数必须大于 0")
        if undercover_count >= len(player_configs):
            raise ValueError("卧底人数必须少于玩家总数，否则没有平民")
        self.game_config = game_config
        self.undercover_count = undercover_count
        self.seed = seed if seed is not None else random.randrange(2**32)
        self.rng = random.Random(self.seed)
        undercover_configs = self.rng.sample(player_configs, undercover_count)
        undercover_config_ids = {config.id for config in undercover_configs}
        self.players = [
            PlayerState(
                config=config,
                role="undercover" if config.id in undercover_config_ids else "civilian",
                word=(
                    game_config.undercover_word
                    if config.id in undercover_config_ids
                    else game_config.civilian_word
                ),
            )
            for config in player_configs
        ]
        self.adapters: Dict[str, Adapter] = {
            player.id: build_adapter(player.config, self.rng) for player in self.players
        }
        self.events: List[Event] = []
        self.round_no = 0
        self.started_at = datetime.now(timezone.utc).isoformat()

    @property
    def alive(self) -> List[PlayerState]:
        return [player for player in self.players if player.alive]

    def _context(self, player: PlayerState) -> ActionContext:
        speeches = []
        for event in self.events:
            if event.kind == "speech" and event.round_no == self.round_no:
                speeches.append(
                    {
                        "id": event.actor_id or "",
                        "name": self.player(event.actor_id or "").config.name,
                        "text": str(event.payload["text"]),
                    }
                )
        return ActionContext(
            round_no=self.round_no,
            player=player,
            alive_players=self.alive,
            speeches=speeches,
            events=[self._event_dict(event) for event in self.events],
        )

    def player(self, player_id: str) -> PlayerState:
        for player in self.players:
            if player.id == player_id:
                return player
        raise KeyError("未知玩家: %s" % player_id)

    def _add_event(
        self,
        kind: str,
        actor_id: Optional[str],
        payload: Dict[str, Any],
        prompt: Optional[str] = None,
        raw_response: Optional[str] = None,
        error: Optional[str] = None,
        elapsed_ms: Optional[int] = None,
    ) -> None:
        event_payload = dict(payload)
        if prompt is not None:
            event_payload["prompt"] = prompt
        if raw_response is not None:
            event_payload["raw_response"] = raw_response
        if error is not None:
            event_payload["error"] = error
        if elapsed_ms is not None:
            event_payload["elapsed_ms"] = elapsed_ms
        self.events.append(Event(kind=kind, round_no=self.round_no, actor_id=actor_id, payload=event_payload))

    def _event_dict(self, event: Event) -> Dict[str, Any]:
        return {
            "kind": event.kind,
            "round": event.round_no,
            "actor_id": event.actor_id,
            "payload": event.payload,
        }

    def _prompt_snapshot(self, player: PlayerState, action: str) -> str:
        context = self._context(player)
        public = json.dumps(
            {
                "round": context.round_no,
                "speeches": context.speeches,
                "alive": [p.id for p in context.alive_players],
                "action": action,
                # Deliberately record the private prompt snapshot in logs. The
                # HTML viewer can hide it, but replay/debugging must be exact.
                "private": {"role": player.role, "word": player.word},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return public

    def play(self) -> GameResult:
        self._add_event("game_started", None, {"seed": self.seed, "player_count": len(self.players)})
        for round_no in range(1, self.game_config.max_rounds + 1):
            self.round_no = round_no
            self._add_event("round_started", None, {"alive": [p.id for p in self.alive]})
            self._speech_phase()
            result = self._vote_phase()
            if result is not None:
                self._add_event("game_finished", None, result.to_dict())
                return result
        result = GameResult(
            winner="undercover",
            reason="达到最大轮数，卧底仍未被投出",
            undercover_ids=self.undercover_ids,
            eliminated_ids=[p.id for p in self.players if not p.alive],
            rounds_played=self.round_no,
        )
        self._add_event("game_finished", None, result.to_dict())
        return result

    @property
    def undercover_ids(self) -> List[str]:
        return [player.id for player in self.players if player.role == "undercover"]

    @property
    def undercover_id(self) -> str:
        """Backward-compatible accessor for single-undercover games."""
        return self.undercover_ids[0]

    def _is_undercover_win(self, civilians_alive: int, undercover_alive: int) -> bool:
        """Undercover side wins once it reaches parity with civilians.

        Covers both single- and multi-undercover configurations: e.g. 1
        undercover vs 1 civilian, or 2 undercover vs 2 civilians.
        """
        return undercover_alive > 0 and undercover_alive >= civilians_alive

    def _all_speeches_so_far(self) -> List[str]:
        return [
            str(event.payload["text"])
            for event in self.events
            if event.kind == "speech" and "text" in event.payload
        ]

    def _speech_phase(self) -> None:
        other_words = [self.game_config.civilian_word, self.game_config.undercover_word]
        for player in list(self.alive):
            adapter = self.adapters[player.id]
            prompt = self._prompt_snapshot(player, "speak")
            started = time.monotonic()
            try:
                text = adapter.speak(self._context(player)).strip()
                if not text:
                    raise ValueError("模型返回空发言")
                elapsed = int((time.monotonic() - started) * 1000)
                # Check repetition against every earlier speech in this game
                # (any player, any round) before recording this one.
                is_repeat = detect_repetition(text, self._all_speeches_so_far())
                player.speeches.append(text)
                violations = detect_violations(player, text, other_words)
                if is_repeat:
                    violations.append("repeated_speech")
                payload = {"text": text}
                if violations:
                    payload["violations"] = violations
                self._add_event(
                    "speech",
                    player.id,
                    payload,
                    prompt=prompt,
                    raw_response=text,
                    elapsed_ms=elapsed,
                )
            except Exception as exc:  # one bad player should not erase the experiment
                elapsed = int((time.monotonic() - started) * 1000)
                fallback = "我觉得这个东西很常见。"
                player.speeches.append(fallback)
                self._add_event(
                    "speech",
                    player.id,
                    {"text": fallback, "fallback": True},
                    prompt=prompt,
                    error=repr(exc),
                    elapsed_ms=elapsed,
                )

    def _vote_phase(self) -> Optional[GameResult]:
        other_words = [self.game_config.civilian_word, self.game_config.undercover_word]
        votes: Dict[str, str] = {}
        alive = list(self.alive)
        for player in alive:
            adapter = self.adapters[player.id]
            prompt = self._prompt_snapshot(player, "vote")
            started = time.monotonic()
            raw = ""
            error: Optional[str] = None
            try:
                raw = adapter.vote(self._context(player))
                target = extract_vote(raw, [candidate.id for candidate in alive], player.id)
                if target is None:
                    raise ValueError("未能从响应中解析出合法投票目标")
            except Exception as exc:
                error = repr(exc)
                candidates = [candidate.id for candidate in alive if candidate.id != player.id]
                target = self.rng.choice(candidates)
            elapsed = int((time.monotonic() - started) * 1000)
            votes[player.id] = target
            player.votes.append(target)
            violations = detect_violations(player, raw, other_words) if raw else []
            payload = {"target_id": target, "parsed": error is None}
            if violations:
                payload["violations"] = violations
            self._add_event(
                "vote",
                player.id,
                payload,
                prompt=prompt,
                raw_response=raw,
                error=error,
                elapsed_ms=elapsed,
            )

        counts = Counter(votes.values())
        max_votes = max(counts.values())
        leaders = sorted(player_id for player_id, count in counts.items() if count == max_votes)
        self._add_event("vote_result", None, {"votes": votes, "counts": dict(counts), "leaders": leaders})
        if len(leaders) != 1:
            return None
        eliminated = self.player(leaders[0])
        eliminated.alive = False
        eliminated.eliminated_round = self.round_no
        self._add_event(
            "eliminated",
            eliminated.id,
            {"name": eliminated.config.name, "was_undercover": eliminated.role == "undercover"},
        )
        civilians_alive = sum(1 for p in self.alive if p.role == "civilian")
        undercover_alive = sum(1 for p in self.alive if p.role == "undercover")
        if undercover_alive == 0:
            return GameResult(
                winner="civilian",
                reason="所有卧底均已被投出",
                undercover_ids=self.undercover_ids,
                eliminated_ids=[p.id for p in self.players if not p.alive],
                rounds_played=self.round_no,
            )
        if self._is_undercover_win(civilians_alive, undercover_alive):
            return GameResult(
                winner="undercover",
                reason="卧底人数达到与平民持平，卧底阵营获胜",
                undercover_ids=self.undercover_ids,
                eliminated_ids=[p.id for p in self.players if not p.alive],
                rounds_played=self.round_no,
            )
        return None

    def to_dict(self, result: Optional[GameResult] = None) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "started_at": self.started_at,
            "seed": self.seed,
            "game": asdict(self.game_config),
            "players": [
                {
                    "id": player.id,
                    "name": player.config.name,
                    "adapter": player.config.adapter,
                    "model": player.config.model,
                    "role": player.role,
                    "word": player.word,
                    "alive": player.alive,
                    "eliminated_round": player.eliminated_round,
                }
                for player in self.players
            ],
            "events": [self._event_dict(event) for event in self.events],
            "result": result.to_dict() if result else None,
        }

    def save(self, output_dir: Path, result: GameResult) -> Tuple[Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = output_dir / ("game-%s-%s" % (stamp, self.seed))
        json_path = stem.with_suffix(".json")
        html_path = stem.with_suffix(".html")
        json_path.write_text(json.dumps(self.to_dict(result), ensure_ascii=False, indent=2), encoding="utf-8")
        from .replay import render_html

        html_path.write_text(render_html(self.to_dict(result)), encoding="utf-8")
        return json_path, html_path
