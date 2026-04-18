from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class PromptManager:
    base_dir: Path
    _cache: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "PromptManager":
        base_dir = Path(__file__).parent.parent / "prompts" / "subagents"
        return cls(base_dir=base_dir)

    def load_prompt(self, filename: str) -> str:
        if filename in self._cache:
            return self._cache[filename]

        path = self.base_dir / filename
        content = path.read_text(encoding="utf-8")
        self._cache[filename] = content
        return content

    def try_load_prompt(self, filename: str) -> Optional[str]:
        try:
            return self.load_prompt(filename)
        except Exception:
            return None

