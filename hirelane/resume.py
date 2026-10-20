"""The content of one tailored resume, before it becomes a PDF.

Every bullet carries its provenance so the record can be audited later: ``original`` is the approved text,
``variant`` is another approved wording, and ``rewrite`` is a reworded line that passed validation.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

PROVENANCE = ("original", "variant", "rewrite")


@dataclass
class BulletLine:
    text: str
    source_id: str               # id of the approved bullet this line comes from
    provenance: str = "original"


@dataclass
class Block:
    """One experience, project or school on the resume."""
    key: str
    kind: str
    name: str
    title: str = ""
    location: str = ""
    dates: str = ""
    detail: str = ""
    bullets: list[BulletLine] = field(default_factory=list)


@dataclass
class ResumeContent:
    name: str
    contact: list[str]
    skills: list[str]
    blocks: list[Block]
    track: str = ""
    job_key: str = ""

    def bullet_lines(self) -> list[BulletLine]:
        return [b for blk in self.blocks for b in blk.bullets]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> ResumeContent:
        raw: dict[str, Any] = json.loads(text)
        blocks = [Block(**{**b, "bullets": [BulletLine(**x) for x in b.get("bullets", [])]}) for b in raw["blocks"]]
        return cls(name=raw["name"], contact=raw["contact"], skills=raw["skills"], blocks=blocks,
                   track=raw.get("track", ""), job_key=raw.get("job_key", ""))
