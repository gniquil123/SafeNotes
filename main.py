"""加密记事本（SafeNotes）入口。

流程：单实例检查 → 解锁 / 创建保险库 → 主窗口。
支持 --smoke：使用临时文件与轻量 KDF 参数自动走一遍「创建 → 解锁 → 打开主窗口」，
3 秒后自动退出，用于无人工介入的冒烟验证。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ORG = "SafeNotes"
APP = "SafeNotes"
INSTANCE_KEY = "safenotes-single-instance"


def ensure_single_instance() -> bool:
    """已有实例在运行时返回 False（并尝试把已有窗口置前）。"""
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.disconnectFromServer()
        return False
    return True


def listen_single_instance(app) -> None:
    from PySide6.QtNetwork import QLocalServer
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)
    app._sn_instance_server = server     # 挂引用防回收


def default_vault_path() -> Path:
    from PySide6.QtCore import QStandardPaths
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return Path(docs) / "加密记事本.vault"


def run() -> int:
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName(ORG)
    app.setApplicationDisplayName("加密记事本")

    from app.utils.resources import resource_path
    icon_path = resource_path("assets/icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    smoke = "--smoke" in sys.argv
    if smoke:
        os.environ["SAFENOTES_LOW_KDF"] = "1"

    if not smoke and not ensure_single_instance():
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None, "加密记事本", "程序已在运行中。")
        return 0
    listen_single_instance(app)

    settings = QSettings()
    last_path = settings.value("last_vault_path", "")

    from app.ui.style import build_qss
    from app.ui.unlock_dialog import UnlockDialog
    from app.ui.main_window import MainWindow
    from app.core.database import Database

    def boot(vault_path: Path, mode: str):
        dlg = UnlockDialog(mode, vault_path)
        if dlg.exec() != UnlockDialog.Accepted:
            app.quit()
            return None
        settings.setValue("last_vault_path", str(vault_path))
        win = MainWindow(dlg.result_vault, dlg.result_db)
        mw_settings = win.db.settings
        app.setStyleSheet(build_qss(mw_settings.get("theme", "light")))

        def relock():
            dlg2 = UnlockDialog("unlock", vault_path)
            if dlg2.exec() == UnlockDialog.Accepted:
                win.vault = dlg2.result_vault
                win.db = Database.from_dict(dlg2.result_db)
                win._session_saved = False
                win._touch()
                win.render_all()
                win.show()
            else:
                win.close()
                app.quit()

        win.locked.connect(relock)
        win.show()
        return win

    if smoke:
        # 冒烟：程序化创建临时保险库并直接进入主窗口，3 秒后自动退出
        from app.core.database import Database
        from app.crypto.vault import create_vault
        tmp = Path(tempfile.mkdtemp(prefix="safenotes-smoke-")) / "smoke.vault"
        vault, db_dict = create_vault(tmp, "smoke-test-password", Database.empty().to_dict())
        win = MainWindow(vault, db_dict)
        app.setStyleSheet(build_qss(win.db.settings.get("theme", "light")))
        win.show()
        QTimer.singleShot(3000, app.quit)
        return app.exec()

    # 正常启动：先弹启动选择器（解锁上次 / 打开其他文件 / 新建）
    from app.ui.launcher_dialog import LauncherDialog
    last = Path(last_path) if last_path else None
    launcher = LauncherDialog(last)
    if launcher.exec() != LauncherDialog.Accepted or launcher.choice is None:
        return 0
    vault_path, mode = launcher.choice
    win = boot(vault_path, mode)
    if win is None:
        return 0
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
