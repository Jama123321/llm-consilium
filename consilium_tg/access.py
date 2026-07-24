from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class AccessStore:
    def __init__(self, path, owner_id: int | None = None) -> None:
        self._path = str(path)
        self._owner = owner_id

    def _load(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        d.setdefault("allowed", [])
        d.setdefault("pending", {})
        return d

    def _save(self, d: dict) -> None:
        try:
            parent = Path(self._path).parent
            parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(parent), prefix=".tgacc-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f)
            os.replace(tmp, self._path)
        except OSError:
            pass

    def owner_id(self) -> int | None:
        return self._owner

    def is_owner(self, uid) -> bool:
        return self._owner is not None and int(uid) == int(self._owner)

    def is_allowed(self, uid) -> bool:
        return self.is_owner(uid) or int(uid) in self._load().get("allowed", [])

    def request_access(self, uid, username: str) -> None:
        d = self._load()
        d["pending"][str(int(uid))] = username or ""
        self._save(d)

    def list_pending(self) -> dict:
        return dict(self._load().get("pending", {}))

    def approve(self, uid) -> bool:
        d = self._load()
        d["pending"].pop(str(int(uid)), None)
        if int(uid) not in d["allowed"]:
            d["allowed"].append(int(uid))
        self._save(d)
        return True

    def deny(self, uid) -> bool:
        d = self._load()
        d["pending"].pop(str(int(uid)), None)
        self._save(d)
        return True
