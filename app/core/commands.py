"""具体撤销命令：所有会改变条目数据的操作在此封装。"""
from __future__ import annotations

from .database import Database
from .models import Entry
from .undostack import Command


class CreateEntryCommand(Command):
    """新建条目。undo 移除，redo 重新插回。"""

    def __init__(self, db: Database, entry: Entry):
        super().__init__(f"新建「{entry.title or '未命名'}」")
        self._db = db
        self._entry = entry

    def undo(self):
        self._db.remove(self._entry.id)

    def redo(self):
        self._db.insert(self._entry)


class SaveEntryCommand(Command):
    """保存条目（含恢复历史版本，label 由调用方定制）。"""

    def __init__(self, db: Database, old_entry: Entry, new_entry: Entry, label: str | None = None):
        super().__init__(label or f"保存「{new_entry.title or '未命名'}」")
        self._db = db
        self._old = old_entry        # 保存前完整深拷贝（含当时的 history）
        self._new = new_entry

    def undo(self):
        self._db.replace(self._old)

    def redo(self):
        self._db.replace(self._new)


class SoftDeleteCommand(Command):
    def __init__(self, db: Database, entry_id: str, title: str):
        super().__init__(f"删除「{title or '未命名'}」")
        self._db = db
        self._id = entry_id

    def undo(self):
        self._db.undelete(self._id)

    def redo(self):
        self._db.soft_delete(self._id)


class UndeleteCommand(Command):
    def __init__(self, db: Database, entry_id: str, title: str):
        super().__init__(f"恢复「{title or '未命名'}」")
        self._db = db
        self._id = entry_id

    def undo(self):
        self._db.soft_delete(self._id)

    def redo(self):
        self._db.undelete(self._id)


class PurgeCommand(Command):
    """彻底删除（单个 / 清空回收站）。"""

    def __init__(self, db: Database, ids: list[str], label: str):
        super().__init__(label)
        self._db = db
        self._ids = list(ids)
        # 构造时数据已被移除，捕获返回的恢复材料
        self._removed = db.purge(ids)

    def undo(self):
        self._db.restore_purged(self._removed)

    def redo(self):
        self._removed = self._db.purge(self._ids)
