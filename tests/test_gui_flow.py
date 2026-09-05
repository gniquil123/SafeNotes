"""GUI 业务流测试：离屏（offscreen）驱动主窗口完整链路。

覆盖：新建草稿保存 → 编辑保存产生历史 → 撤销/重做 → 恢复历史版本 →
软删除（mock 确认框）→ 磁盘密文校验 → 锁定清零。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["SAFENOTES_LOW_KDF"] = "1"

import pytest

psqt = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.database import Database
from app.crypto.vault import WrongPasswordError, create_vault, open_vault
from app.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    # 所有确认框自动答「是」
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    vault, db_dict = create_vault(tmp_path / "t.vault", "主密码123", Database.empty().to_dict())
    w = MainWindow(vault, db_dict)
    yield w, tmp_path / "t.vault"
    if w.vault:
        w.vault.wipe()


def _fill_password_form(w, title, pw, category="工作"):
    w.start_draft("password")
    ed = w.editor
    ed.title_edit.setText(title)
    ed.category_edit.setCurrentText(category)
    ed.username_edit.setText("user@test.com")
    ed.password_edit.setText(pw)
    ed.url_edit.setText("https://example.com")
    ed._on_save()          # 触发 save_requested


def test_full_flow(win):
    w, vault_path = win

    # 1. 新建并保存
    _fill_password_form(w, "GitHub", "OldPass#123")
    e = w.db.visible()[0]
    assert e.title == "GitHub" and e.fields["password"] == "OldPass#123"
    eid = e.id

    # 2. 编辑保存 → 产生历史
    w.editor.password_edit.setText("NewPass#456")
    w.editor._on_save()
    e = w.db.get(eid)
    assert e.fields["password"] == "NewPass#456"
    assert len(e.history) == 1
    assert e.history[0].snap["fields"]["password"] == "OldPass#123"

    # 3. 撤销保存 → 回旧密码；重做 → 新密码
    w.do_undo()
    assert w.db.get(eid).fields["password"] == "OldPass#123"
    w.do_redo()
    assert w.db.get(eid).fields["password"] == "NewPass#456"

    # 4. 恢复历史版本（恢复前自动快照）
    w.on_restore_history(eid, 0)
    e = w.db.get(eid)
    assert e.fields["password"] == "OldPass#123"
    assert len(e.history) == 2                       # 新快照 + 原有 1 条
    assert e.history[0].snap["fields"]["password"] == "NewPass#456"
    w.do_undo()                                      # 撤销恢复
    assert w.db.get(eid).fields["password"] == "NewPass#456"

    # 5. 软删除 → 撤销删除
    w.view["sel"] = {"id": eid}
    w.on_delete_entry()
    assert w.db.get(eid).deleted
    assert len(w.db.visible("trash")) == 1
    w.do_undo()
    assert not w.db.get(eid).deleted

    # 6. 磁盘上只有密文
    raw = vault_path.read_bytes()
    assert b"GitHub" not in raw
    assert b"OldPass" not in raw and b"NewPass" not in raw
    assert b"user@test.com" not in raw

    # 7. 持久化数据可用主密码重新打开
    v2, db2 = open_vault(vault_path, "主密码123")
    try:
        assert db2["entries"][0]["title"] == "GitHub"
    finally:
        v2.wipe()

    # 8. 搜索与分类渲染
    w.render_all()
    assert w.db.visible(search="github")
    assert "工作" in w.db.categories()

    # 9. 锁定：密钥清零、数据丢弃
    w.lock("测试锁定")
    assert w.vault is None and w.db is None
    assert not w.undo_mgr.can_undo


def test_duplicate_entry(win):
    """复制条目：保留分类/密码/账号，标题加（副本），走新建草稿流程可撤销。"""
    w, vault_path = win
    _fill_password_form(w, "GitHub", "SamePw#123")
    src = w.db.visible()[0]
    w.view["sel"] = {"id": src.id}

    w.on_duplicate_entry()
    assert w.editor.is_draft
    ed = w.editor
    assert ed.title_edit.text() == "GitHub（副本）"
    assert ed.password_edit.text() == "SamePw#123"
    assert ed.username_edit.text() == "user@test.com"
    assert ed.category_edit.currentText() == "工作"

    ed.title_edit.setText("淘宝")          # 只改标题和账号
    ed.username_edit.setText("tao_bao_88")
    ed._on_save()

    assert len(w.db.visible()) == 2
    dup = [e for e in w.db.visible() if e.id != src.id][0]
    assert dup.title == "淘宝"
    assert dup.fields["password"] == "SamePw#123"
    assert dup.category == "工作"
    assert dup.history == []                # 新条目不继承历史

    w.do_undo()                             # 撤销新建
    assert len(w.db.visible()) == 1

    # 取消复制：不产生数据
    w.view["sel"] = {"id": src.id}
    w.on_duplicate_entry()
    w.on_cancel_edit()
    assert len(w.db.visible()) == 1


def test_share_text():
    from app.core.models import Entry, ImageItem
    from app.ui.main_window import entry_share_text
    e = Entry.new("password")
    e.title = "GitHub"
    e.fields.update(username="u@x.com", password="Pw#123", url="https://g", notes="n")
    e.images.append(ImageItem(name="a.png", data=""))
    t = entry_share_text(e)
    assert "【GitHub】" in t and "账号：u@x.com" in t and "密码：Pw#123" in t
    assert "1 张图片" in t
    n = Entry.new("note")
    n.title = "笔记"
    n.fields["content"] = "第一行\n第二行"
    t2 = entry_share_text(n)
    assert "第一行\n第二行" in t2


def test_wrong_password_after_lock(win):
    w, vault_path = win
    _fill_password_form(w, "条目", "pw#12345")
    w.lock()
    with pytest.raises(WrongPasswordError):
        open_vault(vault_path, "错误密码")
