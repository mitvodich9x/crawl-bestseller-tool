import io
import os
import sys
import traceback
from datetime import datetime


class _NullWriter(io.TextIOBase):
    def write(self, s):
        return len(s)


# windowed/pythonw builds have no console streams; Vietnamese logs need utf-8 otherwise
for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name, None)
    if _stream is None:
        setattr(sys, _name, _NullWriter())
    else:
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

if getattr(sys, "frozen", False):
    # autostart launches with CWD=System32
    os.chdir(os.path.dirname(sys.executable))

from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

from app import config
from app.app_version import APP_ID, APP_NAME
from app.db.database import Database
from app.logging_setup import setup_logging
from app.paths import logs_dir
from app.ui.main_window import MainWindow
from app.ui.style import STYLESHEET, app_icon


def _install_excepthook() -> None:
    """Log unhandled exceptions and keep the app alive (PyQt6 aborts on exceptions in slots by default)."""

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(logs_dir() / "error.log", "a", encoding="utf-8") as f:
                f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n{text}\n")
        except OSError:
            pass
        try:
            QMessageBox.critical(None, "Đã xảy ra lỗi (app vẫn chạy tiếp)",
                                 f"{exc_type.__name__}: {exc}\n\nChi tiết ở data/logs/error.log")
        except Exception:
            pass

    sys.excepthook = hook


def _notify_running_instance() -> bool:
    """True if another instance is running; it is asked to show its window."""
    socket = QLocalSocket()
    socket.connectToServer(APP_ID)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True
    return False


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(STYLESHEET)
    app.setQuitOnLastWindowClosed(False)
    _install_excepthook()

    if _notify_running_instance():
        return 0

    server = QLocalServer()
    QLocalServer.removeServer(APP_ID)
    server.listen(APP_ID)

    window = MainWindow(Database(), config.load())

    def on_connection():
        conn = server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(window.show_normal)

    server.newConnection.connect(on_connection)

    if "--minimized" in sys.argv:
        window.hide()
    else:
        window.show()
        QTimer.singleShot(0, window.raise_)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
