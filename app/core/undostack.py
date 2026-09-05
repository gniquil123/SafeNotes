"""条目级撤销 / 重做管理（上限 50 步）。

与浏览器 demo 一致的双层撤销模型：
- 输入框内部：Qt 控件自带文本撤销（Ctrl+Z 在输入控件内由 UI 层转发）；
- 条目级：本模块，覆盖 保存 / 新建 / 删除 / 恢复 / 彻底删除 等命令，
  每个命令持有旧值完整深拷贝，撤销即原样还原（含历史版本列表）。

约定与 demo 相同：调用方先自行应用变更，再 push 命令（命令的 redo
仅用于「撤销后重做」的再次应用）。
"""
from __future__ import annotations

from typing import Callable

UNDO_LIMIT = 50


class Command:
    def __init__(self, label: str):
        self.label = label

    def undo(self) -> None:      # pragma: no cover - 接口定义
        raise NotImplementedError

    def redo(self) -> None:      # pragma: no cover - 接口定义
        raise NotImplementedError


class UndoManager:
    def __init__(self, limit: int = UNDO_LIMIT):
        self.limit = limit
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self.on_change: Callable[[], None] | None = None   # UI 刷新回调

    def _notify(self):
        if self.on_change:
            self.on_change()

    def push(self, cmd: Command) -> None:
        self._undo.append(cmd)
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()
        self._notify()

    def undo(self) -> str | None:
        if not self._undo:
            return None
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        self._notify()
        return cmd.label

    def redo(self) -> str | None:
        if not self._redo:
            return None
        cmd = self._redo.pop()
        cmd.redo()
        self._undo.append(cmd)
        self._notify()
        return cmd.label

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str | None:
        return self._undo[-1].label if self._undo else None

    @property
    def redo_label(self) -> str | None:
        return self._redo[-1].label if self._redo else None

    def clear(self) -> None:
        """锁定 / 数据重置时清空（撤销栈内含明文副本，必须一并丢弃）。"""
        self._undo.clear()
        self._redo.clear()
        self._notify()
