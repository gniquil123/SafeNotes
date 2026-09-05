"""应用主题（QSS），观感与浏览器 demo 一致：浅/深双主题。"""
from __future__ import annotations

_LIGHT = {
    "bg": "#eef1f6", "panel": "#ffffff", "panel2": "#f8fafc",
    "border": "#e2e8f0", "border2": "#cbd5e1",
    "text": "#1e293b", "muted": "#64748b",
    "accent": "#2563eb", "accent_h": "#1d4ed8", "accent_weak": "#dbeafe",
    "danger": "#dc2626", "danger_weak": "#fee2e2",
    "sel": "#eff6ff",
}

_DARK = {
    "bg": "#0d1220", "panel": "#161e30", "panel2": "#1b2438",
    "border": "#28324a", "border2": "#3a4a6b",
    "text": "#e2e8f0", "muted": "#8b9bb4",
    "accent": "#3b82f6", "accent_h": "#60a5fa", "accent_weak": "#1e3a5f",
    "danger": "#f87171", "danger_weak": "#3f1d24",
    "sel": "#1c2a44",
}

_QSS = """
* {{
    font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
    color: {text};
}}
QMainWindow, QDialog {{ background: {bg}; }}
QWidget#topbar, QWidget#sidePanel, QWidget#listPanel {{
    background: {panel}; border: none;
}}
QLabel {{ background: transparent; border: none; }}
QLabel#brand {{ font-size: 15px; font-weight: 700; }}
QLabel#brandIcon {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {accent}, stop:2 #7c3aed);
    border-radius: 8px; padding: 3px 6px; font-size: 16px;
}}
QLabel#muted, QLabel#subtle {{ color: {muted}; }}
QLabel#demoBadge {{
    background: {accent_weak}; color: {accent};
    border-radius: 9px; padding: 1px 8px; font-size: 10px; font-weight: 700;
}}
QLabel#listHead {{ font-weight: 700; font-size: 13px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {panel}; border: 1px solid {border2};
    border-radius: 8px; padding: 6px 9px; selection-background-color: {accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {accent};
}}
QLineEdit[error=true] {{ border: 1px solid {danger}; }}
QPushButton {{
    background: {panel}; color: {text};
    border: 1px solid {border2}; border-radius: 8px;
    padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {accent}; color: {accent}; }}
QPushButton:disabled {{ color: {muted}; border-color: {border}; background: {panel2}; }}
QPushButton[primary=true] {{
    background: {accent}; color: #ffffff; border: 1px solid {accent}; font-weight: 600;
}}
QPushButton[primary=true]:hover {{ background: {accent_h}; color: #ffffff; }}
QPushButton[danger=true] {{
    background: {danger}; color: #ffffff; border: 1px solid {danger}; font-weight: 600;
}}
QPushButton[danger=true]:hover {{ color: #ffffff; opacity: 0.9; }}
QPushButton[flat=true] {{ background: transparent; border: none; }}
QPushButton[flat=true]:hover {{ background: {accent_weak}; border: none; }}
QToolButton {{
    background: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 5px 8px; font-size: 14px;
}}
QToolButton:hover {{ border-color: {accent}; }}
QToolButton:disabled {{ color: {muted}; }}
QListWidget {{
    background: transparent; border: none; outline: none;
}}
QListWidget::item {{
    border-radius: 8px; padding: 7px 10px; margin: 2px 4px;
}}
QListWidget::item:hover {{ background: {panel2}; }}
QListWidget::item:selected {{ background: {accent_weak}; color: {accent}; }}
QListWidget#catList::item {{ margin: 1px 6px; }}
QListWidget#entryList {{
    background: {panel2}; border: none;
}}
QListWidget#entryList::item {{
    background: {panel}; border: 1px solid transparent;
    border-radius: 10px; margin: 3px 8px; padding: 8px;
}}
QListWidget#entryList::item:hover {{ border-color: {accent}; }}
QListWidget#entryList::item:selected {{ border-color: {accent}; background: {sel}; }}
QListWidget#histList::item:selected {{ background: {sel}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {border2}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; }}
QScrollBar::handle:horizontal {{ background: {border2}; border-radius: 4px; min-width: 30px; }}
QSplitter::handle {{ background: {border}; }}
QSplitter::handle:hover {{ background: {accent}; }}
QFrame[card=true] {{
    background: {panel}; border: 1px solid {border};
    border-radius: 12px;
}}
QFrame[hline=true] {{ background: {border}; border: none; max-height: 1px; }}
QFrame#thumbCard {{
    background: {panel2}; border: 1px solid {border};
    border-radius: 10px;
}}
QLabel#thumbLabel {{ border-radius: 8px; background: {panel2}; }}
QLabel#imgName {{
    color: {muted}; font-size: 10px;
    background: transparent; max-height: 16px;
}}
QCheckBox {{ spacing: 7px; background: transparent; }}
QComboBox QAbstractItemView {{
    background: {panel}; border: 1px solid {border2};
    selection-background-color: {accent_weak}; selection-color: {accent};
    outline: none;
}}
QComboBox QLineEdit {{
    border: none; background: transparent; padding: 0;
}}
QToolTip {{
    background: {panel}; color: {text}; border: 1px solid {border2};
    padding: 5px 8px; border-radius: 6px;
}}
QStatusBar {{ background: {panel}; border-top: 1px solid {border}; color: {muted}; }}
QMessageBox {{ background: {panel}; }}
QSlider::groove:horizontal {{
    height: 5px; background: {border2}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {panel}; border: 2px solid {accent};
    width: 15px; margin: -6px 0; border-radius: 8px;
}}
"""


def build_qss(theme: str) -> str:
    v = _DARK if theme == "dark" else _LIGHT
    return _QSS.format(**{k: v[k] for k in v})
