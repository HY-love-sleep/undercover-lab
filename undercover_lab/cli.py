from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from .batch import run_batch, save_batch_summary
from .engine import UndercoverGame
from .models import GameConfig, PlayerConfig


def _default_demo_players(count: int) -> List[PlayerConfig]:
    names = ["Claude", "GPT", "DeepSeek", "Gemini", "Mistral", "Qwen"]
    return [
        PlayerConfig(
            id="p%d" % (index + 1),
            name=names[index % len(names)],
            adapter="mock",
            model="mock-v1",
            personality="谨慎而有点多疑",
        )
        for index in range(count)
    ]


def load_config(
    path: Path, max_rounds_override: "int | None" = None
) -> "tuple[GameConfig, List[PlayerConfig], str | None]":
    data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    game_data = data.get("game", {})
    config_max_rounds = int(game_data.get("max_rounds", 3))
    warning = None
    max_rounds = config_max_rounds
    if max_rounds_override is not None and max_rounds_override != config_max_rounds:
        warning = (
            "已用命令行参数覆盖配置文件的 max_rounds：配置文件为 %d，命令行为 %d，"
            "本次以命令行参数为准。"
        ) % (config_max_rounds, max_rounds_override)
        max_rounds = max_rounds_override
    game = GameConfig(
        civilian_word=str(game_data.get("civilian_word", "咖啡")),
        undercover_word=str(game_data.get("undercover_word", "奶茶")),
        max_rounds=max_rounds,
    )
    players = [PlayerConfig.from_dict(item) for item in data.get("players", [])]
    return game, players, warning


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多模型谁是卧底实验室")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="使用内置模拟玩家")
    source.add_argument("--config", type=Path, help="真实模型 JSON 配置")
    parser.add_argument("--seed", type=int, help="固定随机种子")
    parser.add_argument("--output-dir", type=Path, default=Path("runs"))
    parser.add_argument("--players", type=int, default=5, help="demo 玩家数量")
    parser.add_argument(
        "--max-rounds", type=int, default=None,
        help="最大轮数。demo 模式默认 3；--config 模式默认取配置文件的值，"
             "显式传入本参数会覆盖配置文件并打印提示",
    )
    parser.add_argument("--batch", type=int, metavar="N", help="批量运行 N 局")
    parser.add_argument("--save-games", action="store_true", help="批量模式保存每局 JSON/HTML")
    parser.add_argument("--undercover-count", type=int, default=1, help="卧底人数，默认 1")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_warning = None
    try:
        if args.config:
            game_config, players, config_warning = load_config(
                args.config, max_rounds_override=args.max_rounds
            )
        else:
            game_config = GameConfig(max_rounds=args.max_rounds if args.max_rounds is not None else 3)
            players = _default_demo_players(args.players)
        if args.batch:
            summary = run_batch(
                game_config,
                players,
                count=args.batch,
                seed=args.seed if args.seed is not None else 0,
                output_dir=args.output_dir,
                save_games=args.save_games,
                undercover_count=args.undercover_count,
            )
            summary_path = save_batch_summary(summary, args.output_dir)
        else:
            game = UndercoverGame(
                game_config, players, seed=args.seed, undercover_count=args.undercover_count
            )
            result = game.play()
            json_path, html_path = game.save(args.output_dir, result)
    except Exception as exc:
        print("启动失败：%s" % exc, file=sys.stderr)
        return 1

    if config_warning:
        print("提示：%s" % config_warning, file=sys.stderr)

    if not args.quiet:
        if args.batch:
            print("\n=== 谁是卧底 · 批量实验 ===")
            print("完成：%d/%d 局（每局卧底人数：%d）" % (
                summary["games_completed"], summary["games_requested"], summary["undercover_count"]
            ))
            print("胜负：平民 %d；卧底 %d" % (summary["wins"]["civilian"], summary["wins"]["undercover"]))
            print("轮数分布：%s" % summary["rounds"])
            print("违规行为总数：%d" % summary["total_violations"])
            for model, stat in summary["model_stats"].items():
                print(
                    "%s | 卧底胜率 %.1f%% | 被抓率 %.1f%% | 投票命中率 %.1f%% | 平均响应 %.0fms | 违规 %d"
                    % (
                        model,
                        stat["undercover_win_rate"] * 100,
                        stat["undercover_detection_rate"] * 100,
                        stat["vote_accuracy"] * 100,
                        stat["avg_response_ms"],
                        stat["violations"],
                    )
                )
            print("汇总：%s" % summary_path)
        else:
            print("\n=== 谁是卧底 · 模型社会实验室 ===")
            print("seed: %s" % game.seed)
            print("玩家：%s" % "、".join(player.config.name for player in game.players))
            print("卧底：%s（观众视角可见，玩家 prompt 不会收到）" % "、".join(game.undercover_ids))
            print("结果：%s；%s" % (result.winner, result.reason))
            print("轮数：%d" % result.rounds_played)
            print("JSON：%s" % json_path)
            print("HTML：%s" % html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
