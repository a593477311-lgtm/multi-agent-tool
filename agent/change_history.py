from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
import json
from config import get_work_dir


@dataclass
class ChangeRecord:
    change_type: str
    file_path: str
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        result = {
            "change_type": self.change_type,
            "file_path": self.file_path,
            "old_content": self.old_content,
            "new_content": self.new_content,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ChangeRecord":
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()
        
        return cls(
            change_type=data.get("change_type", "modify"),
            file_path=data.get("file_path", ""),
            old_content=data.get("old_content"),
            new_content=data.get("new_content"),
            timestamp=timestamp
        )


class ChangeHistory:
    history_file: Path
    history: List[ChangeRecord]
    current_index: int

    def __init__(self, history_file: Optional[str] = None):
        if history_file:
            self.history_file = Path(history_file)
        else:
            self.history_file = get_work_dir() / ".agent_data" / "history.json"
        
        self.history: List[ChangeRecord] = []
        self.current_index: int = -1
        self._load()

    def record(
        self,
        change_type: str,
        file_path: str,
        old_content: Optional[str] = None,
        new_content: Optional[str] = None
    ) -> None:
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]
        
        record = ChangeRecord(
            change_type=change_type,
            file_path=file_path,
            old_content=old_content,
            new_content=new_content
        )
        self.history.append(record)
        self.current_index = len(self.history) - 1
        self._save()

    def undo(self) -> Optional[ChangeRecord]:
        if not self.can_undo():
            return None
        
        record = self.history[self.current_index]
        self.current_index -= 1
        self._save()
        return record

    def redo(self) -> Optional[ChangeRecord]:
        if not self.can_redo():
            return None
        
        self.current_index += 1
        record = self.history[self.current_index]
        self._save()
        return record

    def can_undo(self) -> bool:
        return self.current_index >= 0

    def can_redo(self) -> bool:
        return self.current_index < len(self.history) - 1

    def get_recent(self, n: int = 10) -> List[Dict]:
        if not self.history:
            return []
        
        start_idx = max(0, len(self.history) - n)
        return [record.to_dict() for record in self.history[start_idx:]]

    def get_undo_count(self) -> int:
        return self.current_index + 1

    def get_redo_count(self) -> int:
        return len(self.history) - self.current_index - 1

    def clear(self) -> None:
        self.history = []
        self.current_index = -1
        self._save()

    def _save(self) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "history": [record.to_dict() for record in self.history],
            "current_index": self.current_index
        }
        
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        if not self.history_file.exists():
            self.history = []
            self.current_index = -1
            return
        
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                self.history = [ChangeRecord.from_dict(r) for r in data.get("history", [])]
                self.current_index = data.get("current_index", -1)
            elif isinstance(data, list):
                self.history = [ChangeRecord.from_dict(r) for r in data]
                self.current_index = len(self.history) - 1
            else:
                self.history = []
                self.current_index = -1
            
            if self.current_index >= len(self.history):
                self.current_index = len(self.history) - 1
            if self.current_index < -1:
                self.current_index = -1
                
        except (json.JSONDecodeError, IOError, KeyError):
            self.history = []
            self.current_index = -1
