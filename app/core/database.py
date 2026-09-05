"""内存数据库：条目 CRUD、搜索、分类、回收站、历史版本。

解锁时由加密 payload 反序列化而来，全部修改只发生在内存，
由 UI 层在合适时机调用 crypto.vault 写回磁盘（密文）。
"""
from __future__ import annotations

import copy
from datetime import datetime

from .models import Entry, HistoryItem, ImageItem, now_iso

DEFAULT_SETTINGS = {
    "auto_lock_min": 5,      # 闲置自动锁定分钟数（0 = 不锁定）
    "clip_sec": 20,          # 复制密码后剪贴板自动清除秒数（0 = 不清除）
    "history_keep": 20,      # 每条目保留的历史版本数
    "theme": "light",
}


class Database:
    def __init__(self, entries: list[Entry] | None = None, settings: dict | None = None):
        self.entries: list[Entry] = entries if entries is not None else []
        self.settings: dict = dict(DEFAULT_SETTINGS)
        if settings:
            self.settings.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        return {
            "format": {"version": 1},
            "settings": dict(self.settings),
            "entries": [e.to_dict() for e in self.entries],
        }

    @staticmethod
    def from_dict(d: dict) -> "Database":
        return Database(
            entries=[Entry.from_dict(e) for e in d.get("entries", [])],
            settings=d.get("settings"),
        )

    @staticmethod
    def empty() -> "Database":
        return Database()

    # ---------- 查询 ----------
    def get(self, entry_id: str) -> Entry | None:
        for e in self.entries:
            if e.id == entry_id:
                return e
        return None

    def index_of(self, entry_id: str) -> int:
        for i, e in enumerate(self.entries):
            if e.id == entry_id:
                return i
        return -1

    @staticmethod
    def _entry_text(e: Entry) -> str:
        f = e.fields
        return " ".join([e.title, e.category, f.get("username", ""),
                         f.get("url", ""), f.get("notes", ""),
                         f.get("content", "")]).lower()

    def visible(self, cat: str = "all", search: str = "") -> list[Entry]:
        """按视图筛选：cat 为 'all' / 'trash' / 分类名；search 大小写不敏感全文匹配。"""
        q = (search or "").strip().lower()
        out = []
        for e in self.entries:
            if cat == "trash":
                if not e.deleted:
                    continue
            else:
                if e.deleted:
                    continue
                if cat != "all" and e.category != cat:
                    continue
            if q and q not in self._entry_text(e):
                continue
            out.append(e)
        out.sort(key=lambda e: e.updated_at or "", reverse=True)
        return out

    def categories(self) -> list[str]:
        seen: dict[str, None] = {}
        for e in self.entries:
            if not e.deleted and e.category:
                seen.setdefault(e.category, None)
        return sorted(seen.keys())

    def counts(self) -> tuple[int, dict[str, int], int]:
        """返回 (未删除总数, {分类: 数量}, 回收站数量)。"""
        total, trash = 0, 0
        per: dict[str, int] = {}
        for e in self.entries:
            if e.deleted:
                trash += 1
            else:
                total += 1
                per[e.category] = per.get(e.category, 0) + 1
        return total, per, trash

    # ---------- 修改（由撤销命令调用，均不直接触发持久化） ----------
    def insert(self, entry: Entry) -> None:
        self.entries.insert(0, entry)

    def remove(self, entry_id: str) -> None:
        self.entries = [e for e in self.entries if e.id != entry_id]

    def replace(self, entry: Entry) -> None:
        i = self.index_of(entry.id)
        if i >= 0:
            self.entries[i] = entry

    def soft_delete(self, entry_id: str) -> None:
        e = self.get(entry_id)
        if e:
            e.deleted = True
            e.deleted_at = now_iso()

    def undelete(self, entry_id: str) -> None:
        e = self.get(entry_id)
        if e:
            e.deleted = False
            e.deleted_at = None

    def purge(self, ids: list[str]) -> list[tuple[int, Entry]]:
        """彻底删除（回收站）。返回 [(原索引, 条目深拷贝)] 供撤销恢复。"""
        idset = set(ids)
        removed: list[tuple[int, Entry]] = []
        kept: list[Entry] = []
        for i, e in enumerate(self.entries):
            if e.id in idset:
                removed.append((i, copy.deepcopy(e)))
            else:
                kept.append(e)
        self.entries = kept
        return removed

    def restore_purged(self, removed: list[tuple[int, Entry]]) -> None:
        """按原索引位置插回（用于撤销彻底删除）。"""
        for idx, entry in sorted(removed, key=lambda x: x[0]):
            self.entries.insert(min(idx, len(self.entries)), entry)

    # ---------- 历史版本 ----------
    def push_history(self, entry: Entry, reason: str) -> list[HistoryItem]:
        """把 entry 当前内容压入其历史（就地产出新的 history 列表）。"""
        keep = int(self.settings.get("history_keep", 20))
        snap = HistoryItem(saved_at=now_iso(), reason=reason, snap=entry.content_snapshot())
        return [snap, *entry.history][:max(keep, 1)]

    def restore_history(self, entry_id: str, hist_index: int) -> Entry | None:
        """构造「恢复到指定历史版本」的新条目（不动原数据，由调用方 replace）。"""
        cur = self.get(entry_id)
        if cur is None or hist_index < 0 or hist_index >= len(cur.history):
            return None
        total = len(cur.history)
        ver_no = total - hist_index        # 最初版为第 1 版
        h = cur.history[hist_index]
        ne = cur.deep_copy()
        snap = h.snap
        ne.title = snap.get("title", "")
        ne.category = snap.get("category", "") or "默认"
        ne.fields = copy.deepcopy(snap.get("fields", ne.fields))
        ne.images = [ImageItem.from_dict(im) for im in snap.get("images", [])]
        ne.history = self.push_history(cur, f"恢复第 {ver_no} 版前的自动快照")
        return ne
