import json
from pathlib import Path

from .config import DATA_DIR, HISTORY_LIMIT, PROJECTS_DIR


class Storage:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.state_file = data_dir / "state.json"
        self._state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        self.state_file.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))

    def _user(self, user_id: int) -> dict:
        key = str(user_id)
        if key not in self._state:
            self._state[key] = {"cwd": None, "history": []}
        return self._state[key]

    def get_cwd(self, user_id: int) -> Path | None:
        cwd = self._user(user_id).get("cwd")
        if cwd is None:
            return None
        path = Path(cwd)
        return path if path.exists() else None

    def set_cwd(self, user_id: int, path: Path) -> None:
        self._user(user_id)["cwd"] = str(path)
        self._save()

    def get_history(self, user_id: int) -> list[dict]:
        return list(self._user(user_id).get("history", []))

    def append_history(self, user_id: int, message: dict) -> None:
        history = self._user(user_id).setdefault("history", [])
        history.append(message)
        if len(history) > HISTORY_LIMIT * 2:
            del history[: len(history) - HISTORY_LIMIT * 2]
        self._save()

    def clear_history(self, user_id: int) -> None:
        self._user(user_id)["history"] = []
        self._save()

    def list_projects(self) -> list[str]:
        if not PROJECTS_DIR.exists():
            return []
        return sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir())


storage = Storage()
