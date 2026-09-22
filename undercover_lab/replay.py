from __future__ import annotations

import html
import json
from typing import Any, Dict, List


def render_html(game: Dict[str, Any]) -> str:
    players = game["players"]
    events = game["events"]
    result = game.get("result") or {}
    names = {player["id"]: player["name"] for player in players}
    role_text = {
        "civilian": "平民",
        "undercover": "卧底",
    }
    player_rows = []
    for player in players:
        state = "存活" if player["alive"] else "出局"
        role = role_text.get(player["role"], player["role"])
        player_rows.append(
            "<tr><td>{id}</td><td>{name}</td><td>{model}</td><td>{role}</td><td>{word}</td><td>{state}</td></tr>".format(
                id=html.escape(player["id"]),
                name=html.escape(player["name"]),
                model=html.escape(player["model"]),
                role=html.escape(role),
                word=html.escape(player["word"]),
                state=html.escape(state),
            )
        )

    timeline: List[str] = []
    for event in events:
        payload = event.get("payload", {})
        kind = event.get("kind")
        actor = names.get(event.get("actor_id"), "主持人")
        round_no = event.get("round", 0)
        violation_badge = ""
        violations = payload.get("violations") or []
        if violations:
            violation_badge = ' <span class="violation">⚠️ 违规：{}</span>'.format(
                html.escape("、".join(violations))
            )
        if kind == "speech":
            line = "<b>{}</b>：{}{}".format(
                html.escape(actor), html.escape(str(payload.get("text", ""))), violation_badge
            )
        elif kind == "vote":
            target = names.get(payload.get("target_id"), payload.get("target_id", "?"))
            line = "<b>{}</b> 投给 <b>{}</b>{}{}".format(
                html.escape(actor), html.escape(str(target)),
                " <small>（fallback）</small>" if payload.get("parsed") is False else "",
                violation_badge,
            )
        elif kind == "eliminated":
            line = "淘汰：<b>{}</b>".format(html.escape(actor))
        elif kind == "vote_result":
            counts = payload.get("counts", {})
            formatted = "、".join(
                "{} {} 票".format(html.escape(names.get(pid, pid)), count)
                for pid, count in counts.items()
            )
            line = "投票统计：{}".format(formatted)
        elif kind == "round_started":
            line = "第 {} 轮开始".format(round_no)
        elif kind == "game_finished":
            line = "游戏结束：{}（{}）".format(
                html.escape(str(result.get("winner", ""))),
                html.escape(str(result.get("reason", ""))),
            )
        else:
            continue
        timeline.append('<li><span class="round">R{}</span> {}</li>'.format(round_no, line))

    result_text = "{}：{}".format(result.get("winner", ""), result.get("reason", ""))
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>谁是卧底 · 模型社会实验室</title>
<style>
:root {{ color-scheme: dark; --bg:#111827; --panel:#1f2937; --muted:#9ca3af; --accent:#f59e0b; }}
body {{ margin:0; background:var(--bg); color:#f3f4f6; font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:28px 18px 60px; }}
h1 {{ margin:0 0 6px; font-size:30px; }}
h2 {{ margin-top:30px; font-size:20px; }}
.muted {{ color:var(--muted); }}
.card {{ background:var(--panel); border-radius:14px; padding:18px; margin-top:16px; overflow:auto; }}
.badge {{ display:inline-block; background:#78350f; color:#fde68a; border-radius:999px; padding:2px 10px; margin-left:8px; }}
table {{ border-collapse:collapse; width:100%; }}
th,td {{ text-align:left; padding:9px 10px; border-bottom:1px solid #374151; white-space:nowrap; }}
th {{ color:#fbbf24; }}
ul {{ list-style:none; padding:0; margin:0; }}
li {{ padding:10px 0; border-bottom:1px solid #374151; }}
.round {{ color:var(--accent); font-variant-numeric:tabular-nums; display:inline-block; width:38px; }}
code {{ color:#fde68a; }}
.violation {{ color:#fca5a5; background:#450a0a; border-radius:6px; padding:1px 8px; font-size:13px; margin-left:6px; }}
</style>
</head>
<body><main>
<h1>谁是卧底 <span class="badge">模型社会实验室</span></h1>
<p class="muted">seed: <code>{seed}</code> · schema: <code>{schema}</code></p>
<div class="card"><strong>结果：</strong>{result}</div>
<h2>玩家</h2>
<div class="card"><table><thead><tr><th>ID</th><th>玩家</th><th>模型</th><th>身份</th><th>词语</th><th>状态</th></tr></thead><tbody>{players}</tbody></table></div>
<h2>回放时间线</h2>
<div class="card"><ul>{timeline}</ul></div>
<p class="muted">提示：这是观众视角回放。实验日志 JSON 同时保存了私密身份、prompt 快照和原始响应，适合复盘信息隔离是否正确。</p>
</main></body></html>""".format(
        seed=html.escape(str(game.get("seed", ""))),
        schema=html.escape(str(game.get("schema_version", ""))),
        result=html.escape(result_text),
        players="".join(player_rows),
        timeline="".join(timeline),
    )
