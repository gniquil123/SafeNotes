"""启动选择器测试：解锁上次 / 打开其他 / 新建（mock 文件对话框）。"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.ui.launcher_dialog import LauncherDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_unlock_last(qapp, tmp_path):
    p = tmp_path / "v.vault"
    p.write_bytes(b"x")
    d = LauncherDialog(p)
    assert d.b_last.isEnabled()
    d._unlock_last()
    assert d.choice == (p, "unlock")


def test_unlock_last_missing_disabled(qapp, tmp_path):
    d = LauncherDialog(tmp_path / "gone.vault")
    assert not d.b_last.isEnabled()
    assert d.choice is None


def test_open_other(qapp, tmp_path, monkeypatch):
    other = tmp_path / "other.vault"
    other.write_bytes(b"x")
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(other), "")))
    d = LauncherDialog(tmp_path / "last.vault")
    d._open_other()
    assert d.choice == (other, "unlock")


def test_open_other_cancel(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    d = LauncherDialog(tmp_path / "last.vault")
    d._open_other()
    assert d.choice is None


def test_create_new(qapp, tmp_path, monkeypatch):
    new = tmp_path / "new.vault"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(new), "")))
    d = LauncherDialog(None)
    d._create_new()
    assert d.choice == (new, "create")


def test_create_new_refuse_overwrite_then_cancel(qapp, tmp_path, monkeypatch):
    """已存在文件 + 拒绝覆盖 → 重新弹选文件；再取消 → choice 为 None。"""
    existing = tmp_path / "exist.vault"
    existing.write_bytes(b"x")
    answers = [str(existing), ""]           # 第一次选中已存在文件，第二次取消
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (answers.pop(0), "")))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.No))
    d = LauncherDialog(None)
    d._create_new()
    assert d.choice is None
