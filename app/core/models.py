"""条目数据模型。

与 demo 一致的结构，序列化为 JSON 后整体进入加密 payload：
- 密码条目 fields: {username, password, url, notes}
- 笔记条目 fields: {content}
- history: 每次保存前的旧内容快照（防存错丢密码的核心机制）
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class ImageItem:
    name: str
    data: str          # base64 编码的图片字节

    def to_dict(self) -> dict:
        return {"name": self.name, "data": self.data}

    @staticmethod
    def from_dict(d: dict) -> "ImageItem":
        return ImageItem(name=d.get("name", ""), data=d.get("data", ""))


@dataclass
class HistoryItem:
    saved_at: str
    reason: str
    snap: dict           # {title, category, fields, images} 的快照

    def to_dict(self) -> dict:
        return {"saved_at": self.saved_at, "reason": self.reason, "snap": self.snap}

    @staticmethod
    def from_dict(d: dict) -> "HistoryItem":
        return HistoryItem(saved_at=d.get("saved_at", ""), reason=d.get("reason", ""),
                           snap=d.get("snap", {}))


def _empty_fields(entry_type: str) -> dict:
    if entry_type == "password":
        return {"username": "", "password": "", "url": "", "notes": ""}
    if entry_type == "note":
        return {"content": ""}
    raise ValueError(f"未知条目类型: {entry_type}")


@dataclass
class Entry:
    id: str
    type: str                                   # "password" | "note"
    title: str
    category: str
    fields: dict
    images: list[ImageItem] = field(default_factory=list)
    deleted: bool = False
    deleted_at: str | None = None
    history: list[HistoryItem] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    # ---------- 构造 ----------
    @staticmethod
    def new(entry_type: str, category: str = "默认") -> "Entry":
        return Entry(id=new_id(), type=entry_type, title="", category=category,
                     fields=_empty_fields(entry_type))

    # ---------- 快照（历史版本） ----------
    def content_snapshot(self) -> dict:
        return {
            "title": self.title,
            "category": self.category,
            "fields": copy.deepcopy(self.fields),
            "images": [im.to_dict() for im in self.images],
        }

    def deep_copy(self) -> "Entry":
        """完整深拷贝（含 history），用于撤销命令保存旧状态。"""
        return copy.deepcopy(self)

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "title": self.title,
            "category": self.category, "fields": self.fields,
            "images": [im.to_dict() for im in self.images],
            "deleted": self.deleted, "deleted_at": self.deleted_at,
            "history": [h.to_dict() for h in self.history],
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "Entry":
        etype = d.get("type", "note")
        fields = d.get("fields") or {}
        # 兼容缺字段的数据
        for k, v in _empty_fields(etype).items():
            fields.setdefault(k, v)
        return Entry(
            id=d.get("id") or new_id(),
            type=etype,
            title=d.get("title", ""),
            category=d.get("category", "默认") or "默认",
            fields=fields,
            images=[ImageItem.from_dict(im) for im in d.get("images", [])],
            deleted=bool(d.get("deleted", False)),
            deleted_at=d.get("deleted_at"),
            history=[HistoryItem.from_dict(h) for h in d.get("history", [])],
            created_at=d.get("created_at") or now_iso(),
            updated_at=d.get("updated_at") or now_iso(),
        )
