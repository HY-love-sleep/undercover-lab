from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .engine import UndercoverGame
from .models import GameConfig, PlayerConfig


def _model_stat() -> Dict[str, Any]:
    return {
        "games": 0,
        "undercover_games": 0,
        "undercover_wins": 0,
        "caught_as_undercover": 0,
        "civilian_games": 0,
        "civilian_wins": 0,
        "votes_cast": 0,
        "votes_for_undercover": 0,
        "speeches": 0,
        "fallbacks": 0,
        "vote_parse_failures": 0,
        "response_ms_total": 0,
        "violations": 0,
        "violation_types": Counter(),
    }


def _update_model_stats(summary: Dict[str, Any], game: UndercoverGame, result: Any) -> None:
    players = {player.id: player for player in game.players}
    undercover_ids = set(game.undercover_ids)
    for player in game.players:
        model = player.config.model
        stat = summary["model_stats"].setdefault(model, _model_stat())
        stat["games"] += 1
        if player.role == "undercover":
            stat["undercover_games"] += 1
            # Whether this specific player "won" is ambiguous once multiple
            # undercover players exist and some get caught before the game
            # ends; use the player's own survival, not just the team result.
            if result.winner == "undercover" and player.alive:
                stat["undercover_wins"] += 1
            if not player.alive:
                stat["caught_as_undercover"] += 1
        else:
            stat["civilian_games"] += 1
            if result.winner == "civilian":
                stat["civilian_wins"] += 1

    for event in game.events:
        if not event.actor_id:
            continue
        stat = summary["model_stats"][players[event.actor_id].config.model]
        elapsed = event.payload.get("elapsed_ms")
        if elapsed is not None:
            stat["response_ms_total"] += int(elapsed)
        violations = event.payload.get("violations") or []
        if violations:
            stat["violations"] += len(violations)
            stat["violation_types"].update(violations)
        if event.kind == "speech":
            stat["speeches"] += 1
            stat["fallbacks"] += int(bool(event.payload.get("fallback")))
        elif event.kind == "vote":
            stat["votes_cast"] += 1
            stat["votes_for_undercover"] += int(event.payload.get("target_id") in undercover_ids)
            stat["vote_parse_failures"] += int(event.payload.get("parsed") is False)


def finalize_stats(summary: Dict[str, Any]) -> Dict[str, Any]:
    for stat in summary["model_stats"].values():
        stat["undercover_win_rate"] = round(
            stat["undercover_wins"] / max(stat["undercover_games"], 1), 4
        )
        stat["civilian_win_rate"] = round(
            stat["civilian_wins"] / max(stat["civilian_games"], 1), 4
        )
        stat["undercover_detection_rate"] = round(
            stat["caught_as_undercover"] / max(stat["undercover_games"], 1), 4
        )
        stat["vote_accuracy"] = round(
            stat["votes_for_undercover"] / max(stat["votes_cast"], 1), 4
        )
        stat["avg_response_ms"] = round(
            stat["response_ms_total"] / max(stat["speeches"] + stat["votes_cast"], 1), 1
        )
        stat["violation_types"] = dict(stat["violation_types"])
    return summary


def run_batch(
    game_config: GameConfig,
    player_configs: List[PlayerConfig],
    count: int,
    seed: int,
    output_dir: Optional[Path] = None,
    save_games: bool = False,
    undercover_count: int = 1,
) -> Dict[str, Any]:
    if count < 1:
        raise ValueError("批量实验次数必须大于 0")
    summary: Dict[str, Any] = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "games_requested": count,
        "games_completed": 0,
        "seed_start": seed,
        "undercover_count": undercover_count,
        "wins": {"civilian": 0, "undercover": 0},
        "rounds": Counter(),
        "total_violations": 0,
        "model_stats": {},
        "games": [],
    }
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        game = UndercoverGame(
            game_config, player_configs, seed=seed + index, undercover_count=undercover_count
        )
        result = game.play()
        summary["games_completed"] += 1
        summary["wins"][result.winner] += 1
        summary["rounds"][str(result.rounds_played)] += 1
        _update_model_stats(summary, game, result)
        game_violations = sum(
            len(event.payload.get("violations") or []) for event in game.events
        )
        summary["total_violations"] += game_violations
        summary["games"].append({
            "index": index + 1,
            "seed": game.seed,
            "winner": result.winner,
            "reason": result.reason,
            "rounds": result.rounds_played,
            "undercover_ids": result.undercover_ids,
            "undercover_models": [
                game.player(pid).config.model for pid in result.undercover_ids
            ],
            "violations": game_violations,
        })
        if output_dir and save_games:
            game.save(output_dir / "games", result)
    summary["rounds"] = dict(summary["rounds"])
    return finalize_stats(summary)


def save_batch_summary(summary: Dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = output_dir / ("batch-%s-%s.json" % (stamp, summary["seed_start"]))
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
