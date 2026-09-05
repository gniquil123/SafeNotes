"""撤销 / 重做测试：50 步上限、redo 清空规则、命令往返一致性。"""
from app.core.commands import (
    CreateEntryCommand, PurgeCommand, SaveEntryCommand,
    SoftDeleteCommand, UndeleteCommand,
)
from app.core.database import Database
from app.core.models import Entry
from app.core.undostack import UNDO_LIMIT, UndoManager


def mk_entry(title, pw="x"):
    e = Entry.new("password")
    e.title = title
    e.fields["password"] = pw
    return e


def test_undo_limit_50():
    db = Database.empty()
    mgr = UndoManager()
    for i in range(60):
        e = mk_entry(f"t{i}")
        db.insert(e)
        mgr.push(CreateEntryCommand(db, e))
    assert mgr.can_undo
    for _ in range(UNDO_LIMIT):
        assert mgr.undo() is not None
    assert not mgr.can_undo
    assert len(db.entries) == 10          # 前 10 条超出撤销范围


def test_redo_cleared_on_new_push():
    db = Database.empty()
    mgr = UndoManager()
    e1 = mk_entry("a"); db.insert(e1); mgr.push(CreateEntryCommand(db, e1))
    e2 = mk_entry("b"); db.insert(e2); mgr.push(CreateEntryCommand(db, e2))
    assert mgr.undo()
    assert mgr.can_redo
    e3 = mk_entry("c"); db.insert(e3); mgr.push(CreateEntryCommand(db, e3))
    assert not mgr.can_redo            # 新命令清空 redo 栈
    assert mgr.undo() and mgr.undo()
    assert len(db.entries) == 0        # 两次 undo 把 b、a 都撤掉
    assert mgr.redo() and mgr.redo()   # b 的撤销命令已被清空，仅能重做 a、c
    assert [e.title for e in db.entries] == ["c", "a"]


def test_save_undo_restores_including_history():
    db = Database.empty()
    e = mk_entry("v1", pw="旧密码")
    db.insert(e)
    mgr = UndoManager()

    old = e.deep_copy()
    ne = e.deep_copy()
    ne.title = "v2"; ne.fields["password"] = "新密码"
    ne.history = db.push_history(e, "编辑保存")
    ne.updated_at = "2099-01-01T00:00:00"
    db.replace(ne)
    mgr.push(SaveEntryCommand(db, old, ne))

    assert db.get(e.id).fields["password"] == "新密码"
    assert len(db.get(e.id).history) == 1
    mgr.undo()
    restored = db.get(e.id)
    assert restored.fields["password"] == "旧密码"
    assert restored.history == []          # 撤销连 history 一起还原
    mgr.redo()
    assert db.get(e.id).fields["password"] == "新密码"


def test_soft_delete_undo():
    db = Database.empty()
    e = mk_entry("a"); db.insert(e)
    mgr = UndoManager()
    db.soft_delete(e.id)
    mgr.push(SoftDeleteCommand(db, e.id, e.title))
    assert db.get(e.id).deleted
    mgr.undo()
    assert not db.get(e.id).deleted
    mgr.redo()
    assert db.get(e.id).deleted
    mgr.undo()
    # UndeleteCommand 的 undo 会重新软删
    db.undelete(e.id)
    mgr.push(UndeleteCommand(db, e.id, e.title))
    mgr.undo()
    assert db.get(e.id).deleted


def test_purge_undo_restores_position_and_data():
    db = Database.empty()
    a, b, c = mk_entry("a"), mk_entry("b"), mk_entry("c")
    for e in (a, b, c):
        db.insert(e)
    # Database.insert 为头插：初始顺序 [c, b, a]
    mgr = UndoManager()
    cmd = PurgeCommand(db, [a.id, c.id], "清空回收站")
    mgr.push(cmd)
    assert [e.title for e in db.entries] == ["b"]
    mgr.undo()
    assert [e.title for e in db.entries] == ["c", "b", "a"]     # 原位置恢复
    mgr.redo()
    assert [e.title for e in db.entries] == ["b"]
    mgr.undo()
    assert db.get(a.id).title == "a"


def test_clear():
    db = Database.empty()
    mgr = UndoManager()
    e = mk_entry("a"); db.insert(e); mgr.push(CreateEntryCommand(db, e))
    mgr.clear()
    assert not mgr.can_undo and not mgr.can_redo
