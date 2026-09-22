from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlayerConfig:
    id: str
    name: str
    adapter: str = "mock"
    model: str = "mock-v1"
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    personality: str = "自然、简洁地发言"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlayerConfig":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            adapter=str(data.get("adapter", "mock")),
            model=str(data.get("model", "mock-v1")),
            base_url=data.get("base_url"),
            api_key_env=data.get("api_key_env"),
            personality=str(data.get("personality", "自然、简洁地发言")),
        )


@dataclass
class PlayerState:
    config: PlayerConfig
    role: str
    word: str
    alive: bool = True
    eliminated_round: Optional[int] = None
    speeches: List[str] = field(default_factory=list)
    votes: List[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.config.id


@dataclass
class GameConfig:
    civilian_word: str = "咖啡"
    undercover_word: str = "奶茶"
    max_rounds: int = 3


@dataclass
class Event:
    kind: str
    round_no: int
    actor_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GameResult:
    winner: str
    reason: str
    undercover_ids: List[str]
    eliminated_ids: List[str]
    rounds_played: int

    @property
    def undercover_id(self) -> str:
        """Backward-compatible accessor for single-undercover games."""
        return self.undercover_ids[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "winner": self.winner,
            "reason": self.reason,
            "undercover_ids": self.undercover_ids,
            "eliminated_ids": self.eliminated_ids,
            "rounds_played": self.rounds_played,
        }
