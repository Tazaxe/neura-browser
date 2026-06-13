import sys
import json
import os
import base64
import hashlib
import threading
import urllib.request
import urllib.error
import shutil
import subprocess
import tempfile
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFileDialog, QDialog,
    QFrame, QSizePolicy, QStackedWidget, QScrollArea, QMenu,
    QInputDialog, QToolTip, QProgressBar, QListWidget, QListWidgetItem,
    QTextEdit, QMessageBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineDownloadRequest
from PyQt6.QtCore import (
    QUrl, Qt, QSize, QTimer, QPoint, QMimeData, QByteArray, pyqtSignal,
    QObject, QPropertyAnimation, QEasingCurve, QAbstractAnimation
)
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QPixmap, QPainter,
    QBrush, QKeySequence, QShortcut, QDrag, QCursor
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect

try:
    from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
    HAVE_NETWORK = True
except Exception:
    HAVE_NETWORK = False

try:
    from cryptography.fernet import Fernet
    HAVE_CRYPTO = True
except Exception:
    HAVE_CRYPTO = False

BG       = "#000000"
BG2      = "#0e0e0e"
BG3      = "#131313"
PRIMARY  = "#b1c5ff"
TERTIARY = "#00e639"
OUTLINE  = "#424654"
TEXT_DIM = "#8c90a0"
TEXT_MID = "#c2c6d7"
TEXT_ON  = "#002c70"
RED      = "#ff5f57"
YELLOW   = "#febc2e"
GREEN    = "#28c840"

# ─────────────────────────────────────────────
#  Versión y configuración del auto-actualizador
#  CAMBIA ESTOS VALORES a los de tu repo de GitHub:
# ─────────────────────────────────────────────
VERSION        = "2.7.0"          # versión actual del archivo
GITHUB_USER    = "Tazaxe"     # tu usuario de GitHub
GITHUB_REPO    = "neura-browser"  # nombre del repositorio
GITHUB_BRANCH  = "main"           # rama principal
# El archivo debe subirse al repo con este nombre:
GITHUB_FILENAME = "neura_v3.py"

PROFILE_FILE  = os.path.join(os.path.expanduser("~"), ".neura_profile.json")
PASSWORDS_FILE = os.path.join(os.path.expanduser("~"), ".neura_passwords.enc")
PW_KEY_FILE    = os.path.join(os.path.expanduser("~"), ".neura_pwkey")
SETTINGS_FILE  = os.path.join(os.path.expanduser("~"), ".neura_settings.json")

def load_profile():
    try:
        with open(PROFILE_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_profile(data):
    with open(PROFILE_FILE, "w") as f:
        json.dump(data, f)

def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)

def _get_fernet_key():
    if os.path.exists(PW_KEY_FILE):
        with open(PW_KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(PW_KEY_FILE, "wb") as f:
        f.write(key)
    try:
        os.chmod(PW_KEY_FILE, 0o600)
    except Exception:
        pass
    return key

def load_passwords():
    if not HAVE_CRYPTO or not os.path.exists(PASSWORDS_FILE):
        return []
    try:
        f = Fernet(_get_fernet_key())
        with open(PASSWORDS_FILE, "rb") as fh:
            data = f.decrypt(fh.read())
        return json.loads(data.decode())
    except Exception:
        return []

def save_passwords(entries):
    if not HAVE_CRYPTO:
        return
    f = Fernet(_get_fernet_key())
    data = f.encrypt(json.dumps(entries).encode())
    with open(PASSWORDS_FILE, "wb") as fh:
        fh.write(data)
    try:
        os.chmod(PASSWORDS_FILE, 0o600)
    except Exception:
        pass

def mono(size=11, bold=False):
    f = QFont("Courier New", size)
    f.setBold(bold)
    return f

def space(size=9, bold=True):
    f = QFont("Courier New", size)
    f.setBold(bold)
    return f


# ─────────────────────────────────────────────
#  Auto-Actualizador
# ─────────────────────────────────────────────
def _parse_version(v):
    """Convierte '2.7.0' en (2, 7, 0) para comparar."""
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:
        return (0,)

def _fetch_remote_version():
    """
    Lee el archivo VERSION.txt del repo de GitHub.
    Crea ese archivo en tu repo con solo el número: 2.8.0
    """
    url = (
        f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}"
        f"/{GITHUB_BRANCH}/VERSION.txt"
    )
    try:
        with urllib.request.urlopen(url, timeout=6) as r:
            return r.read().decode().strip()
    except Exception:
        return None

def _download_update(dest_path, progress_cb=None):
    """
    Descarga el .py actualizado del repo y lo guarda en dest_path.
    progress_cb(porcentaje_int) se llama mientras baja.
    """
    url = (
        f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}"
        f"/{GITHUB_BRANCH}/{GITHUB_FILENAME}"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 8192
            with open(dest_path, "wb") as f:
                while True:
                    data = r.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    downloaded += len(data)
                    if total and progress_cb:
                        progress_cb(int(downloaded * 100 / total))
        return True
    except Exception:
        return False


class UpdateDialog(QDialog):
    """Diálogo que aparece cuando hay una versión nueva disponible."""

    # señales para comunicar el hilo de descarga con el UI
    progress_signal = pyqtSignal(int)
    done_signal     = pyqtSignal(bool)

    def __init__(self, remote_version, parent=None):
        super().__init__(parent)
        self.remote_version = remote_version
        self.setWindowTitle("NEURA // ACTUALIZACIÓN")
        self.setFixedSize(440, 260)
        self.setStyleSheet(f"QDialog{{background:{BG2};color:{PRIMARY};}}")

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(24, 24, 24, 24)

        title = QLabel("// ACTUALIZACIÓN_DISPONIBLE")
        title.setFont(mono(11, True))
        title.setStyleSheet(
            f"color:{PRIMARY};letter-spacing:2px;"
            f"border-bottom:1px solid {OUTLINE};padding-bottom:8px;"
        )
        lay.addWidget(title)

        info = QLabel(
            f"  VERSIÓN_ACTUAL :  {VERSION}\n"
            f"  VERSIÓN_NUEVA  :  {remote_version}"
        )
        info.setFont(mono(10))
        info.setStyleSheet(f"color:{TEXT_MID};")
        lay.addWidget(info)

        self.status_lbl = QLabel("¿Deseas actualizar ahora?")
        self.status_lbl.setFont(mono(9))
        self.status_lbl.setStyleSheet(f"color:{TERTIARY};")
        lay.addWidget(self.status_lbl)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        self.bar.setStyleSheet(
            f"QProgressBar{{background:{BG3};border:1px solid {OUTLINE};color:{PRIMARY};text-align:center;height:16px;}}"
            f"QProgressBar::chunk{{background:{PRIMARY};}}"
        )
        lay.addWidget(self.bar)

        btn_row = QHBoxLayout()
        self.update_btn = QPushButton("[ ACTUALIZAR_AHORA ]")
        self.update_btn.setFont(mono(9, True))
        self.update_btn.setFlat(True)
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{PRIMARY};border:1px solid {PRIMARY};"
            f"padding:10px;letter-spacing:2px;}}"
            f"QPushButton:hover{{background:{PRIMARY};color:{TEXT_ON};}}"
        )
        self.update_btn.clicked.connect(self._do_update)

        skip_btn = QPushButton("[ OMITIR ]")
        skip_btn.setFont(mono(9, True))
        skip_btn.setFlat(True)
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{TEXT_DIM};border:1px solid {OUTLINE};"
            f"padding:10px;letter-spacing:2px;}}"
            f"QPushButton:hover{{color:{PRIMARY};border-color:{PRIMARY};}}"
        )
        skip_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.update_btn)
        btn_row.addWidget(skip_btn)
        lay.addLayout(btn_row)

        self.progress_signal.connect(self._on_progress)
        self.done_signal.connect(self._on_done)

    def _do_update(self):
        self.update_btn.setEnabled(False)
        self.bar.setVisible(True)
        self.status_lbl.setText("// DESCARGANDO...")

        # descarga en hilo separado para no bloquear UI
        def worker():
            tmp = tempfile.mktemp(suffix=".py")
            ok = _download_update(tmp, lambda p: self.progress_signal.emit(p))
            if ok:
                # reemplaza el archivo actual
                try:
                    current = os.path.abspath(sys.argv[0])
                    shutil.move(tmp, current)
                    self.done_signal.emit(True)
                except Exception:
                    self.done_signal.emit(False)
            else:
                self.done_signal.emit(False)

        threading.Thread(target=worker, daemon=True).start()

    def _on_progress(self, val):
        self.bar.setValue(val)

    def _on_done(self, ok):
        if ok:
            self.status_lbl.setStyleSheet(f"color:{TERTIARY};")
            self.status_lbl.setText("// ACTUALIZACIÓN_COMPLETA ✓  Reiniciando...")
            self.bar.setValue(100)
            QTimer.singleShot(1200, self._restart)
        else:
            self.status_lbl.setStyleSheet("color:#ff5f57;")
            self.status_lbl.setText("// ERROR: no se pudo descargar. Revisa tu conexión.")
            self.update_btn.setEnabled(True)

    def _restart(self):
        """Reinicia el proceso con el archivo ya actualizado."""
        self.accept()
        python = sys.executable
        os.execv(python, [python] + sys.argv)


def check_for_updates_async(parent_window):
    """
    Llama esto al iniciar la app. Checa en background y,
    si hay versión nueva, muestra el diálogo de actualización.
    """
    def worker():
        remote = _fetch_remote_version()
        if remote is None:
            return  # sin internet o repo no configurado, silencio total
        if _parse_version(remote) > _parse_version(VERSION):
            # hay update: lo mostramos en el hilo principal
            QTimer.singleShot(0, lambda: _show_update_dialog(remote, parent_window))

    threading.Thread(target=worker, daemon=True).start()


def _show_update_dialog(remote_version, parent):
    dlg = UpdateDialog(remote_version, parent)
    dlg.exec()


# ─────────────────────────────────────────────
#  Settings Dialog
# ─────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SETTINGS")
        self.setFixedSize(420, 360)
        self.avatar_path = None
        self.setStyleSheet(f"QDialog{{background:{BG2};color:{PRIMARY};}}")

        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 20, 20, 20)

        title = QLabel("// SETTINGS_PANEL")
        title.setFont(mono(11, True))
        title.setStyleSheet(f"color:{PRIMARY};letter-spacing:2px;border-bottom:1px solid {OUTLINE};padding-bottom:8px;")
        lay.addWidget(title)

        av_row = QHBoxLayout()
        self.av_lbl = QLabel()
        self.av_lbl.setFixedSize(64, 64)
        self.av_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.av_lbl.setFont(mono(20, True))
        self.av_lbl.setStyleSheet(f"color:{PRIMARY};border:2px solid {OUTLINE};border-radius:32px;background:{BG3};")
        self.av_lbl.setText("?")
        av_row.addWidget(self.av_lbl)

        av_right = QVBoxLayout()
        av_lbl2 = QLabel("AVATAR_IMG")
        av_lbl2.setFont(mono(8, True))
        av_lbl2.setStyleSheet(f"color:{TEXT_DIM};letter-spacing:2px;")
        av_btn = QPushButton("[ UPLOAD_IMAGE ]")
        av_btn.setFont(mono(9, True))
        av_btn.setFlat(True)
        av_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        av_btn.setStyleSheet(f"QPushButton{{background:transparent;color:{TEXT_DIM};border:1px solid {OUTLINE};padding:6px 12px;}}QPushButton:hover{{color:{PRIMARY};border-color:{PRIMARY};}}")
        av_btn.clicked.connect(self._pick)
        av_right.addWidget(av_lbl2)
        av_right.addWidget(av_btn)
        av_right.addStretch()
        av_row.addLayout(av_right)
        lay.addLayout(av_row)

        nl = QLabel("USERNAME")
        nl.setFont(mono(8, True))
        nl.setStyleSheet(f"color:{TEXT_DIM};letter-spacing:2px;")
        lay.addWidget(nl)

        self.name_in = QLineEdit()
        self.name_in.setPlaceholderText("ENTER_USERNAME...")
        self.name_in.setFont(mono(13))
        self.name_in.setStyleSheet(f"QLineEdit{{background:{BG3};color:{PRIMARY};border:1px solid {OUTLINE};padding:8px 12px;}}QLineEdit:focus{{border-color:{PRIMARY};}}")
        lay.addWidget(self.name_in)

        self.status = QLabel("")
        self.status.setFont(mono(9))
        self.status.setStyleSheet(f"color:{TERTIARY};")
        lay.addWidget(self.status)

        save = QPushButton("[ SAVE_PROFILE ]")
        save.setFont(mono(10, True))
        save.setFlat(True)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.setStyleSheet(f"QPushButton{{background:transparent;color:{PRIMARY};border:1px solid {PRIMARY};padding:10px;letter-spacing:2px;}}QPushButton:hover{{background:{PRIMARY};color:{TEXT_ON};}}")
        save.clicked.connect(self._save)
        lay.addWidget(save)

        p = load_profile()
        if p.get("name"):
            self.name_in.setText(p["name"])
            self._set_initials(p["name"])
        if p.get("avatar") and os.path.exists(p["avatar"]):
            self.avatar_path = p["avatar"]
            self._show_av(p["avatar"])

    def _set_initials(self, name):
        ini = "".join(w[0] for w in name.split() if w).upper()[:2] or "?"
        self.av_lbl.setPixmap(QPixmap())
        self.av_lbl.setText(ini)
        self.av_lbl.setStyleSheet(f"color:{PRIMARY};border:2px solid {OUTLINE};border-radius:32px;background:{BG3};")

    def _show_av(self, path):
        pix = QPixmap(path)
        if pix.isNull(): return
        pix = pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        result = QPixmap(64, 64)
        result.fill(Qt.GlobalColor.transparent)
        p = QPainter(result)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(pix))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 64, 64)
        p.end()
        self.av_lbl.setPixmap(result)
        self.av_lbl.setText("")
        self.av_lbl.setStyleSheet("border-radius:32px;")

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "Imagen", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.avatar_path = path
            self._show_av(path)

    def _save(self):
        name = self.name_in.text().strip()
        if not name:
            self.status.setStyleSheet("color:#ffb4ab;")
            self.status.setText("// ERROR: USERNAME_REQUIRED")
            return
        save_profile({"name": name, "avatar": self.avatar_path or ""})
        self.status.setStyleSheet(f"color:{TERTIARY};")
        self.status.setText("// PROFILE_SAVED ✓")
        QTimer.singleShot(700, self.accept)


# ─────────────────────────────────────────────
#  Password Manager Dialog
# ─────────────────────────────────────────────
class PasswordManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PASSWORD_MANAGER")
        self.setFixedSize(480, 420)
        self.setStyleSheet(f"QDialog{{background:{BG2};color:{PRIMARY};}}")
        self.entries = load_passwords()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(20, 20, 20, 20)

        title = QLabel("// PASSWORD_MANAGER" + ("" if HAVE_CRYPTO else "  (NO_ENCRYPTION_LIB)"))
        title.setFont(mono(11, True))
        title.setStyleSheet(f"color:{PRIMARY};letter-spacing:2px;border-bottom:1px solid {OUTLINE};padding-bottom:8px;")
        lay.addWidget(title)

        self.list = QListWidget()
        self.list.setFont(mono(10))
        self.list.setStyleSheet(f"QListWidget{{background:{BG3};color:{TEXT_MID};border:1px solid {OUTLINE};}}QListWidget::item{{padding:6px;}}QListWidget::item:selected{{background:{PRIMARY};color:{TEXT_ON};}}")
        lay.addWidget(self.list, 1)

        form = QHBoxLayout()
        self.site_in = QLineEdit(); self.site_in.setPlaceholderText("SITE (e.g. github.com)")
        self.user_in = QLineEdit(); self.user_in.setPlaceholderText("USERNAME")
        self.pass_in = QLineEdit(); self.pass_in.setPlaceholderText("PASSWORD")
        self.pass_in.setEchoMode(QLineEdit.EchoMode.Password)
        for w in (self.site_in, self.user_in, self.pass_in):
            w.setFont(mono(9))
            w.setStyleSheet(f"QLineEdit{{background:{BG3};color:{PRIMARY};border:1px solid {OUTLINE};padding:6px;}}QLineEdit:focus{{border-color:{PRIMARY};}}")
            form.addWidget(w)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("[ ADD/UPDATE ]")
        del_btn = QPushButton("[ DELETE ]")
        show_btn = QPushButton("[ SHOW/HIDE ]")
        for b in (add_btn, del_btn, show_btn):
            b.setFont(mono(9, True))
            b.setFlat(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:transparent;color:{PRIMARY};border:1px solid {OUTLINE};padding:8px;letter-spacing:1px;}}QPushButton:hover{{background:{PRIMARY};color:{TEXT_ON};}}")
        add_btn.clicked.connect(self._add)
        del_btn.clicked.connect(self._delete)
        show_btn.clicked.connect(self._toggle_show)
        btn_row.addWidget(add_btn); btn_row.addWidget(del_btn); btn_row.addWidget(show_btn)
        lay.addLayout(btn_row)

        self._showing = False
        self._refresh()
        self.list.itemClicked.connect(self._on_pick)

    def _refresh(self):
        self.list.clear()
        for e in self.entries:
            pw = e["password"] if self._showing else "•" * 8
            self.list.addItem(f"{e['site']}  |  {e['username']}  |  {pw}")

    def _on_pick(self, item):
        idx = self.list.row(item)
        e = self.entries[idx]
        self.site_in.setText(e["site"])
        self.user_in.setText(e["username"])
        self.pass_in.setText(e["password"])

    def _add(self):
        site = self.site_in.text().strip()
        user = self.user_in.text().strip()
        pwd  = self.pass_in.text()
        if not site or not user or not pwd:
            QMessageBox.warning(self, "ERROR", "Completa SITE, USERNAME y PASSWORD")
            return
        for e in self.entries:
            if e["site"] == site and e["username"] == user:
                e["password"] = pwd
                break
        else:
            self.entries.append({"site": site, "username": user, "password": pwd})
        save_passwords(self.entries)
        self._refresh()

    def _delete(self):
        row = self.list.currentRow()
        if row < 0: return
        del self.entries[row]
        save_passwords(self.entries)
        self._refresh()

    def _toggle_show(self):
        self._showing = not self._showing
        self._refresh()


# ─────────────────────────────────────────────
#  AI Side Panel (Ollama local / Gemini opcional)
# ─────────────────────────────────────────────
class AIPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{BG2};border-left:1px solid {PRIMARY};")
        self.nam = QNetworkAccessManager(self) if HAVE_NETWORK else None
        self._reply = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("⬡ NEURA_AI // OLLAMA")
        title.setFont(mono(10, True))
        title.setStyleSheet(f"color:{PRIMARY};letter-spacing:2px;")
        head.addWidget(title)
        head.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFlat(True)
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"QPushButton{{color:{TEXT_DIM};background:transparent;border:none;}}QPushButton:hover{{color:#ff4444;}}")
        close_btn.clicked.connect(self._close)
        head.addWidget(close_btn)
        lay.addLayout(head)

        key_row = QHBoxLayout()
        self.model_in = QLineEdit()
        self.model_in.setPlaceholderText("MODELO_OLLAMA (ej: llama3.2)")
        self.model_in.setFont(mono(8))
        self.model_in.setStyleSheet(f"QLineEdit{{background:{BG3};color:{PRIMARY};border:1px solid {OUTLINE};padding:5px;}}QLineEdit:focus{{border-color:{PRIMARY};}}")
        save_key_btn = QPushButton("SAVE")
        save_key_btn.setFont(mono(8, True))
        save_key_btn.setFlat(True)
        save_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_key_btn.setStyleSheet(f"QPushButton{{color:{PRIMARY};background:transparent;border:1px solid {OUTLINE};padding:5px 8px;}}QPushButton:hover{{background:{PRIMARY};color:{TEXT_ON};}}")
        save_key_btn.clicked.connect(self._save_key)
        key_row.addWidget(self.model_in, 1)
        key_row.addWidget(save_key_btn)
        lay.addLayout(key_row)

        s = load_settings()
        self.model_in.setText(s.get("ollama_model", "llama3.2"))

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setFont(mono(9))
        self.chat.setStyleSheet(f"QTextEdit{{background:{BG3};color:{TEXT_MID};border:1px solid {OUTLINE};}}")
        self.chat.append("// Requiere Ollama corriendo en localhost:11434")
        self.chat.append("// Descarga: https://ollama.com  |  ej: ollama run llama3.2")
        lay.addWidget(self.chat, 1)

        in_row = QHBoxLayout()
        self.prompt_in = QLineEdit()
        self.prompt_in.setPlaceholderText("PREGUNTA_A_LA_IA...")
        self.prompt_in.setFont(mono(9))
        self.prompt_in.setStyleSheet(f"QLineEdit{{background:{BG3};color:{PRIMARY};border:1px solid {OUTLINE};padding:6px;}}QLineEdit:focus{{border-color:{PRIMARY};}}")
        self.prompt_in.returnPressed.connect(self._send)
        send_btn = QPushButton("➤")
        send_btn.setFixedSize(30, 30)
        send_btn.setFlat(True)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(f"QPushButton{{color:{PRIMARY};background:transparent;border:1px solid {OUTLINE};}}QPushButton:hover{{background:{PRIMARY};color:{TEXT_ON};}}")
        send_btn.clicked.connect(self._send)
        in_row.addWidget(self.prompt_in, 1)
        in_row.addWidget(send_btn)
        lay.addLayout(in_row)

    def _save_key(self):
        s = load_settings()
        s["ollama_model"] = self.model_in.text().strip() or "llama3.2"
        save_settings(s)
        self.chat.append(f"// Modelo guardado: {s['ollama_model']} ✓")

    def _close(self):
        self.setVisible(False)

    def _send(self):
        prompt = self.prompt_in.text().strip()
        if not prompt: return
        if not HAVE_NETWORK:
            self.chat.append("// ERROR: módulo QtNetwork no disponible")
            return
        model = self.model_in.text().strip() or "llama3.2"
        self.chat.append(f"\n> {prompt}")
        self.chat.append("// pensando...")
        self.prompt_in.clear()

        url = QUrl("http://127.0.0.1:11434/api/generate")
        req = QNetworkRequest(url)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
        reply = self.nam.post(req, body)
        self._reply = reply
        reply.finished.connect(lambda: self._on_reply(reply))

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: reply.isFinished() or reply.abort())
        timer.start(60000)

    def _on_reply(self, reply):
        # remove "// pensando..." placeholder line
        doc = self.chat.document()
        last_block = doc.lastBlock()
        if last_block.text().strip() == "// pensando...":
            cursor = self.chat.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            cursor.select(cursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deletePreviousChar()

        data = bytes(reply.readAll())
        err = reply.error()

        if err != QNetworkReply.NetworkError.NoError:
            self.chat.append(
                f"// ERROR: no se pudo conectar con Ollama ({err}). "
                f"¿Está corriendo? Instala desde https://ollama.com y ejecuta "
                f"'ollama run {self.model_in.text().strip() or 'llama3.2'}'"
            )
            reply.deleteLater()
            return

        try:
            obj = json.loads(data.decode())
            text = obj.get("response", "").strip() or f"// ERROR: respuesta vacía: {data.decode(errors='ignore')[:300]}"
        except Exception:
            text = f"// ERROR: respuesta inesperada: {data.decode(errors='ignore')[:300]}"
        self.chat.append(text)
        reply.deleteLater()



class TabBtn(QWidget):
    on_close  = None
    on_select = None
    drag_requested = None   # callable(from_index)

    def __init__(self, title="NEW_TAB", index=0, parent=None):
        super().__init__(parent)
        self.active = False
        self.index  = index
        self._drag_start = None
        self.setFixedHeight(30)
        self.setMinimumWidth(100)
        self.setMaximumWidth(220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 6, 0)
        lay.setSpacing(4)

        self.favicon = QLabel()
        self.favicon.setFixedSize(16, 16)
        self.favicon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.favicon.setStyleSheet("border:none;background:transparent;")
        self._set_default_favicon()
        lay.addWidget(self.favicon)

        self.title_lbl = QLabel(title)
        self.title_lbl.setFont(mono(8, True))
        self.title_lbl.setStyleSheet(f"color:{TEXT_DIM};letter-spacing:1px;border:none;background:transparent;")
        self.title_lbl.setMaximumWidth(140)
        lay.addWidget(self.title_lbl, 1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFont(QFont("Arial", 8))
        self.close_btn.setFixedSize(14, 14)
        self.close_btn.setFlat(True)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(f"QPushButton{{color:{TEXT_DIM};background:transparent;border:none;}}QPushButton:hover{{color:#ff4444;}}")
        lay.addWidget(self.close_btn)

        self._refresh_style()

    def set_title(self, t):
        short = (t[:16] + "…") if len(t) > 16 else t
        self.title_lbl.setText(short.upper())

    def _set_default_favicon(self):
        self.favicon.setText("○")
        self.favicon.setFont(mono(8))
        self.favicon.setStyleSheet(f"color:{TEXT_DIM};border:none;background:transparent;")
        self.favicon.setPixmap(QPixmap())

    def set_favicon(self, icon):
        if icon and not icon.isNull():
            pix = icon.pixmap(16, 16)
            if not pix.isNull():
                self.favicon.setFont(QFont())
                self.favicon.setPixmap(pix)
                self.favicon.setStyleSheet("border:none;background:transparent;")
                return
        self._set_default_favicon()

    def set_loading(self, loading):
        if loading:
            self.favicon.setPixmap(QPixmap())
            self.favicon.setFont(mono(8))
            self.favicon.setText("◌")
            self.favicon.setStyleSheet(f"color:{TEXT_DIM};border:none;background:transparent;")
        # when not loading, favicon will be set via set_favicon or stays as-is

    def set_active(self, active):
        self.active = active
        self._refresh_style()

    def _refresh_style(self):
        if self.active:
            self.setStyleSheet(f"QWidget{{background:{BG2};border-top:2px solid {PRIMARY};border-right:1px solid {OUTLINE};border-left:1px solid {OUTLINE};}}")
            self.title_lbl.setStyleSheet(f"color:{PRIMARY};letter-spacing:1px;border:none;background:transparent;")
            self.favicon.setStyleSheet(f"color:{PRIMARY};border:none;background:transparent;")
        else:
            self.setStyleSheet(f"QWidget{{background:{BG3};border-top:2px solid transparent;border-right:1px solid {OUTLINE};}}")
            self.title_lbl.setStyleSheet(f"color:{TEXT_DIM};letter-spacing:1px;border:none;background:transparent;")
            self.favicon.setStyleSheet(f"color:{TEXT_DIM};border:none;background:transparent;")

    # ── Mouse events ──
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            if self.on_close: self.on_close()
        elif e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.pos()
            if self.on_select: self.on_select()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and self._drag_start:
            if (e.pos() - self._drag_start).manhattanLength() > 8:
                if self.drag_requested:
                    self.drag_requested(self.index)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_start = None
        super().mouseReleaseEvent(e)

    # Right-click context menu on tab
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{BG2};color:{PRIMARY};border:1px solid {OUTLINE};font-family:'Courier New';font-size:11px;}}QMenu::item:selected{{background:{PRIMARY};color:{TEXT_ON};}}")
        menu.addAction("New Tab",       lambda: self._parent_app()._add_tab())
        menu.addAction("Reload Tab",    lambda: self._parent_app()._reload_current())
        menu.addAction("Duplicate Tab", lambda: self._parent_app()._duplicate_tab(self.index))
        menu.addSeparator()
        menu.addAction("Close Tab",     lambda: self.on_close() if self.on_close else None)
        menu.addAction("Close Others",  lambda: self._parent_app()._close_others(self.index))
        menu.exec(e.globalPos())

    def _parent_app(self):
        w = self.parent()
        while w and not isinstance(w, NeuraApp):
            w = w.parent()
        return w


# ─────────────────────────────────────────────
#  Tab bar (handles drop reordering)
# ─────────────────────────────────────────────
class TabBar(QWidget):
    tab_moved = pyqtSignal(int, int)   # from_idx, to_idx

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_from = -1

    def start_drag(self, from_idx):
        self._drag_from = from_idx
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/neura-tab", QByteArray(str(from_idx).encode()))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat("application/neura-tab"):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        if e.mimeData().hasFormat("application/neura-tab"):
            from_idx = int(e.mimeData().data("application/neura-tab").data().decode())
            # Find drop position
            drop_x = e.position().x()
            to_idx = self._index_at(drop_x)
            if to_idx >= 0 and to_idx != from_idx:
                self.tab_moved.emit(from_idx, to_idx)
            e.acceptProposedAction()

    def _index_at(self, x):
        layout = self.layout()
        if not layout: return -1
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.x() <= x <= w.x() + w.width():
                    return i
        return layout.count() - 2  # last real tab


# ─────────────────────────────────────────────
#  Custom WebPage — opens new tabs in app
# ─────────────────────────────────────────────
class NeuraPage(QWebEnginePage):
    new_tab_requested = pyqtSignal(QUrl)

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)

    def createWindow(self, _type):
        fake = NeuraPage(self.profile(), self)
        fake.urlChanged.connect(lambda u: self.new_tab_requested.emit(u))
        return fake


# ─────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────
class NeuraApp(QMainWindow):
    def __init__(self, incognito=False):
        super().__init__()
        self.is_incognito = incognito
        self.setWindowTitle("NEURA // CMD_INTERFACE" + ("  [INCOGNITO]" if incognito else ""))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(900, 600)
        self.resize(1280, 800)
        self._drag_pos  = None
        self._drag_zone = False
        self.tabs        = []
        self.current_tab = -1

        if incognito:
            self._profile = QWebEngineProfile()  # off-the-record, in-memory
            self._profile.downloadRequested.connect(self._on_download)
            self._incognito_profile = self._profile
        else:
            self._profile = QWebEngineProfile("neura_session")
            data_path = os.path.join(os.path.expanduser("~"), ".neura_browser")
            os.makedirs(data_path, exist_ok=True)
            self._profile.setPersistentStoragePath(data_path)
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
            )
            self._profile.downloadRequested.connect(self._on_download)

            self._incognito_profile = QWebEngineProfile()  # off-the-record
            self._incognito_profile.downloadRequested.connect(self._on_download)
        self._incognito_windows = []

        self._apply_palette()
        self._build_ui()
        self._load_chip()
        self._add_tab()
        self._setup_shortcuts()

    def _apply_palette(self):
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window,     QColor(BG))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(PRIMARY))
        pal.setColor(QPalette.ColorRole.Base,       QColor(BG2))
        pal.setColor(QPalette.ColorRole.Text,       QColor(PRIMARY))
        self.setPalette(pal)
        self.setStyleSheet(f"QMainWindow{{background:{BG};}}")
        if self.is_incognito:
            self._accent = "#a370f7"
        else:
            self._accent = PRIMARY

    # ──────────────────────────────────────────
    #  UI build
    # ──────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ═══ HEADER (drag zone) ═══
        self.header = QWidget()
        self.header.setFixedHeight(38)
        self.header.setObjectName("header")
        self.header.setStyleSheet(f"#header{{background:{BG3};border-bottom:1px solid {self._accent};}}")
        h = QHBoxLayout(self.header)
        h.setContentsMargins(10, 0, 10, 0)
        h.setSpacing(4)

        logo = QLabel("⬡  NEURA" + ("  🕶" if self.is_incognito else ""))
        logo.setFont(mono(13, True))
        logo.setStyleSheet(f"color:{self._accent};letter-spacing:3px;")
        h.addWidget(logo)
        h.addStretch()

        for name, url in [
            ("YOUTUBE",   "https://youtube.com"),
            ("DISCORD",   "https://discord.com"),
            ("ROBLOX",    "https://roblox.com"),
            ("SPOTIFY",   "https://open.spotify.com"),
            ("CHATGPT",   "https://chatgpt.com"),
            ("CLAUDE",    "https://claude.ai"),
            ("TIKTOK",    "https://tiktok.com"),
            ("INSTAGRAM", "https://instagram.com"),
        ]:
            b = QPushButton(name)
            b.setFont(mono(7, True))
            b.setFlat(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{color:{TEXT_MID};background:transparent;border:none;padding:2px 6px;letter-spacing:1px;}}QPushButton:hover{{background:{PRIMARY};color:{TEXT_ON};}}")
            # Left click → current tab, Middle click → new tab
            def make_handler(u):
                def handler(e):
                    if e.button() == Qt.MouseButton.LeftButton:
                        br = self._current_browser()
                        if br: br.setUrl(QUrl(u))
                    elif e.button() == Qt.MouseButton.MiddleButton:
                        self._open_url_new_tab(u)
                return handler
            b.mousePressEvent = make_handler(url)
            h.addWidget(b)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(18)
        sep.setStyleSheet(f"color:{OUTLINE};")
        h.addWidget(sep)

        # User chip
        self.chip = QWidget()
        self.chip.setVisible(False)
        self.chip.setFixedHeight(26)
        self.chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip.setStyleSheet(f"border:1px solid {OUTLINE};background:transparent;")
        cl = QHBoxLayout(self.chip)
        cl.setContentsMargins(3, 0, 8, 0)
        cl.setSpacing(5)
        self.chip_av = QLabel()
        self.chip_av.setFixedSize(20, 20)
        self.chip_av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chip_name = QLabel()
        self.chip_name.setFont(mono(7, True))
        self.chip_name.setStyleSheet(f"color:{PRIMARY};letter-spacing:1px;border:none;background:transparent;")
        cl.addWidget(self.chip_av)
        cl.addWidget(self.chip_name)
        self.chip.mousePressEvent = lambda e: self._open_settings()
        h.addWidget(self.chip)

        gear = QPushButton("⚙")
        gear.setFont(QFont("Arial", 13))
        gear.setFlat(True)
        gear.setFixedSize(26, 26)
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.setStyleSheet(f"QPushButton{{color:{TEXT_DIM};background:transparent;border:none;}}QPushButton:hover{{color:{PRIMARY};}}")
        gear.clicked.connect(self._open_settings)
        h.addWidget(gear)

        h.addSpacing(8)

        # macOS buttons
        for color, hover, slot in [
            (YELLOW, "#f0a500", self.showMinimized),
            (GREEN,  "#1aab30", lambda: self.showNormal() if self.isMaximized() else self.showMaximized()),
            (RED,    "#ff3b30", self.close),
        ]:
            btn = QPushButton()
            btn.setFixedSize(13, 13)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"QPushButton{{background:{color};border-radius:6px;border:none;}}QPushButton:hover{{background:{hover};}}")
            btn.clicked.connect(slot)
            h.addWidget(btn)

        root.addWidget(self.header)

        # ═══ TAB BAR ═══
        tab_bar_wrap = QWidget()
        tab_bar_wrap.setFixedHeight(34)
        tab_bar_wrap.setStyleSheet(f"background:{BG3};border-bottom:1px solid {OUTLINE};")
        tbo = QHBoxLayout(tab_bar_wrap)
        tbo.setContentsMargins(6, 2, 6, 0)
        tbo.setSpacing(0)

        self.tab_scroll = QScrollArea()
        self.tab_scroll.setFixedHeight(32)
        self.tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tab_scroll.setWidgetResizable(True)
        self.tab_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        self.tab_container = TabBar()
        self.tab_container.setStyleSheet("background:transparent;")
        self.tab_layout = QHBoxLayout(self.tab_container)
        self.tab_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_layout.setSpacing(2)
        self.tab_layout.addStretch()
        self.tab_container.tab_moved.connect(self._move_tab)
        self.tab_scroll.setWidget(self.tab_container)
        self.tab_scroll.wheelEvent = self._tab_bar_wheel
        tbo.addWidget(self.tab_scroll, 1)

        new_tab_btn = QPushButton("＋")
        new_tab_btn.setFont(QFont("Arial", 14))
        new_tab_btn.setFixedSize(28, 28)
        new_tab_btn.setFlat(True)
        new_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_tab_btn.setStyleSheet(f"QPushButton{{color:{TEXT_DIM};background:transparent;border:1px solid {OUTLINE};}}QPushButton:hover{{color:{PRIMARY};border-color:{PRIMARY};}}")
        new_tab_btn.clicked.connect(self._add_tab)
        tbo.addWidget(new_tab_btn)

        root.addWidget(tab_bar_wrap)

        # ═══ URL / SEARCH BAR ═══
        url_bar_widget = QWidget()
        url_bar_widget.setFixedHeight(38)
        url_bar_widget.setStyleSheet(f"background:{BG2};border-bottom:1px solid {OUTLINE};")
        ub = QHBoxLayout(url_bar_widget)
        ub.setContentsMargins(8, 4, 8, 4)
        ub.setSpacing(4)

        # Nav buttons
        self.back_btn = self._nav_btn("◀", lambda: self._current_browser() and self._current_browser().back())
        self.fwd_btn  = self._nav_btn("▶", lambda: self._current_browser() and self._current_browser().forward())
        self.rel_btn  = self._nav_btn("↺", lambda: self._current_browser() and self._current_browser().reload())
        self.home_btn = self._nav_btn("⌂", self._go_home)
        for b in [self.back_btn, self.fwd_btn, self.rel_btn, self.home_btn]:
            ub.addWidget(b)

        # Lock icon
        self.lock_lbl = QLabel("🔒")
        self.lock_lbl.setFont(mono(9))
        self.lock_lbl.setStyleSheet("border:none;background:transparent;")
        ub.addWidget(self.lock_lbl)

        # URL bar
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("ENTER_QUERY or URL...")
        self.url_input.setFont(mono(10))
        self.url_input.setFixedHeight(26)
        self.url_input.setStyleSheet(f"QLineEdit{{background:{BG3};color:{PRIMARY};border:1px solid {OUTLINE};padding:2px 10px;}}QLineEdit:focus{{border-color:{PRIMARY};}}")
        self.url_input.returnPressed.connect(self._go)
        ub.addWidget(self.url_input, 1)

        # Zoom indicator
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setFont(mono(8))
        self.zoom_lbl.setStyleSheet(f"color:{TEXT_DIM};border:none;background:transparent;min-width:36px;")
        ub.addWidget(self.zoom_lbl)

        # Right-side buttons: bookmark, downloads, mute, zoom+/-, dev tools, passwords, incognito, AI
        for icon, tip, slot in [
            ("★",  "Bookmark (Ctrl+D)",     self._bookmark),
            ("⬇",  "Downloads (Ctrl+J)",    self._open_downloads),
            ("🔇", "Mute Tab",              self._toggle_mute),
            ("－", "Zoom out",              self._zoom_out),
            ("＋", "Zoom in",              self._zoom_in),
            ("⚒",  "DevTools (F12)",       self._devtools),
            ("🔑", "Password Manager",     self._open_passwords),
            ("🕶", "Incognito (Ctrl+Shift+N)", self._open_incognito),
            ("✦",  "Neura AI (Ctrl+Shift+A)", self._toggle_ai_panel),
        ]:
            b = QPushButton(icon)
            b.setFont(mono(9))
            b.setFixedSize(26, 26)
            b.setFlat(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tip)
            b.setStyleSheet(f"QPushButton{{color:{TEXT_DIM};background:transparent;border:none;padding:0;}}QPushButton:hover{{color:{PRIMARY};}}")
            b.clicked.connect(slot)
            ub.addWidget(b)

        root.addWidget(url_bar_widget)

        # ═══ PROGRESS BAR ═══
        self.progress = QProgressBar()
        self.progress.setFixedHeight(2)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(f"QProgressBar{{background:{BG2};border:none;}}QProgressBar::chunk{{background:{PRIMARY};}}")
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        # ═══ BROWSER STACK + AI PANEL ═══
        content_wrap = QWidget()
        content_layout = QHBoxLayout(content_wrap)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.browser_stack = QStackedWidget()
        self.browser_stack.setStyleSheet("background:#000;")
        content_layout.addWidget(self.browser_stack, 1)

        self.ai_panel = AIPanel()
        self.ai_panel.setMinimumWidth(0)
        self.ai_panel.setMaximumWidth(0)
        self.ai_panel.setVisible(False)
        content_layout.addWidget(self.ai_panel)

        root.addWidget(content_wrap, 1)

        # ═══ STATUS BAR ═══
        self.statusBar().setStyleSheet(f"background:{BG3};color:{TERTIARY};font-family:'Courier New';font-size:10px;border-top:1px dashed {OUTLINE};")
        self._tick_status()

    def _nav_btn(self, icon, slot):
        b = QPushButton(icon)
        b.setFont(QFont("Arial", 11))
        b.setFixedSize(26, 26)
        b.setFlat(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"QPushButton{{color:{TEXT_DIM};background:transparent;border:none;}}QPushButton:hover{{color:{PRIMARY};}}")
        b.clicked.connect(slot)
        return b

    # ──────────────────────────────────────────
    #  Drag to move window (only from header)
    # ──────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            # Only drag from header area
            if self.header.geometry().contains(e.pos()):
                self._drag_pos  = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self._drag_zone = True
            else:
                self._drag_zone = False

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and self._drag_zone and self._drag_pos:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos  = None
        self._drag_zone = False

    def mouseDoubleClickEvent(self, e):
        if self.header.geometry().contains(e.pos()):
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()

    # ──────────────────────────────────────────
    #  Shortcuts
    # ──────────────────────────────────────────
    def _setup_shortcuts(self):
        shortcuts = [
            ("Ctrl+T",           self._add_tab),
            ("Ctrl+W",           lambda: self._close_tab(self.current_tab)),
            ("Ctrl+Tab",         self._next_tab),
            ("Ctrl+Shift+Tab",   self._prev_tab),
            ("Ctrl+R",           self._reload_current),
            ("F5",               self._reload_current),
            ("Ctrl+Shift+R",     lambda: self._current_browser() and self._current_browser().reloadAndBypassCache()),
            ("Alt+Left",         lambda: self._current_browser() and self._current_browser().back()),
            ("Alt+Right",        lambda: self._current_browser() and self._current_browser().forward()),
            ("Ctrl+L",           lambda: (self.url_input.setFocus(), self.url_input.selectAll())),
            ("Ctrl+D",           self._bookmark),
            ("Ctrl+J",           self._open_downloads),
            ("Ctrl+Plus",        self._zoom_in),
            ("Ctrl+Minus",       self._zoom_out),
            ("Ctrl+0",           self._zoom_reset),
            ("F12",              self._devtools),
            ("F11",              lambda: self.showNormal() if self.isMaximized() else self.showMaximized()),
            ("Ctrl+Shift+N",     self._open_incognito),
            ("Ctrl+Shift+A",     self._toggle_ai_panel),
            ("Escape",           lambda: self._current_browser() and self._current_browser().stop()),
        ]
        for key, slot in shortcuts:
            QShortcut(QKeySequence(key), self).activated.connect(slot)
        for n in range(1, 9):
            QShortcut(QKeySequence(f"Ctrl+{n}"), self).activated.connect(
                lambda _, i=n-1: self._switch_tab(i)
            )
        QShortcut(QKeySequence("Ctrl+9"), self).activated.connect(
            lambda: self._switch_tab(len(self.tabs) - 1)
        )

    # ──────────────────────────────────────────
    #  Tab management
    # ──────────────────────────────────────────
    def _add_tab(self, url=None):
        page = NeuraPage(self._profile, self)
        page.new_tab_requested.connect(lambda u: self._add_tab(u.toString()))
        browser = QWebEngineView()
        browser.setPage(page)

        if url:
            browser.setUrl(QUrl(url))
        else:
            browser.setHtml(self._home_html(), QUrl("about:blank"))

        idx = len(self.tabs)
        tab_btn = TabBtn("NEW_TAB", index=idx)
        tab_btn.drag_requested = lambda i: self.tab_container.start_drag(i)
        self.tab_layout.insertWidget(self.tab_layout.count() - 1, tab_btn)

        self.tabs.append((tab_btn, browser))
        self.browser_stack.addWidget(browser)

        browser.urlChanged.connect(   lambda u, i=idx: self._on_url_changed(u, i))
        browser.titleChanged.connect( lambda t, i=idx: self._on_title_changed(t, i))
        browser.iconChanged.connect(  lambda icon, i=idx: self._on_icon_changed(icon, i))
        browser.loadStarted.connect(  lambda i=idx: self._on_load_start(i))
        browser.loadProgress.connect( lambda p, i=idx: self._on_load_progress(p, i))
        browser.loadFinished.connect( lambda ok, i=idx: self._on_load_finish(ok, i))

        tab_btn.on_select = lambda i=idx: self._switch_tab(self.tabs.index(self.tabs[i]))
        tab_btn.on_close  = lambda: self._close_tab(self.tabs.index((tab_btn, browser)))
        tab_btn.close_btn.clicked.connect(
            lambda: self._close_tab(self.tabs.index((tab_btn, browser)))
        )

        self._switch_tab(idx)

    def _switch_tab(self, idx):
        if idx < 0 or idx >= len(self.tabs): return
        for i, (tb, _) in enumerate(self.tabs):
            tb.set_active(i == idx)
        self.current_tab = idx
        new_widget = self.tabs[idx][1]
        self.browser_stack.setCurrentWidget(new_widget)

        overlay = QWidget(self.browser_stack)
        overlay.setStyleSheet(f"background:{BG};")
        overlay.setGeometry(self.browser_stack.rect())
        overlay.show()
        overlay.raise_()

        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutQuint)
        anim.finished.connect(overlay.deleteLater)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._tab_anim = anim

        u = self.tabs[idx][1].url().toString()
        self.url_input.setText(u if u not in ("about:blank", "") else "")
        self._update_lock(u)

    def _close_tab(self, idx):
        if len(self.tabs) <= 1: return
        if idx < 0 or idx >= len(self.tabs): return
        tb, br = self.tabs[idx]
        self.tab_layout.removeWidget(tb)
        tb.deleteLater()
        self.browser_stack.removeWidget(br)
        br.deleteLater()
        self.tabs.pop(idx)
        # Re-index remaining tabs
        for i, (t, _) in enumerate(self.tabs):
            t.index = i
        self._switch_tab(min(idx, len(self.tabs) - 1))

    def _move_tab(self, from_idx, to_idx):
        if from_idx == to_idx: return
        if from_idx < 0 or from_idx >= len(self.tabs): return
        if to_idx < 0 or to_idx >= len(self.tabs): return

        # Record old geometries of all tab buttons
        old_geom = {}
        for i, (tb, _) in enumerate(self.tabs):
            old_geom[id(tb)] = tb.geometry()

        # Move in layout
        item = self.tab_layout.takeAt(from_idx)
        self.tab_layout.insertItem(to_idx, item)
        # Move in list
        tab = self.tabs.pop(from_idx)
        self.tabs.insert(to_idx, tab)
        for i, (t, _) in enumerate(self.tabs):
            t.index = i

        self.tab_layout.activate()

        # Animate each tab button from its old geometry to its new one
        self._tab_move_anims = []
        for tb, _ in self.tabs:
            old = old_geom.get(id(tb))
            new = tb.geometry()
            if old is None or old == new:
                continue
            tb.setGeometry(old)
            anim = QPropertyAnimation(tb, b"geometry", self)
            anim.setDuration(300)
            anim.setStartValue(old)
            anim.setEndValue(new)
            anim.setEasingCurve(QEasingCurve.Type.OutQuint)
            anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
            self._tab_move_anims.append(anim)

        self._switch_tab(to_idx)

    def _close_others(self, keep_idx):
        for i in range(len(self.tabs) - 1, -1, -1):
            if i != keep_idx:
                self._close_tab(i)

    def _duplicate_tab(self, idx):
        if idx < len(self.tabs):
            url = self.tabs[idx][1].url().toString()
            self._add_tab(url)

    def _current_browser(self):
        if 0 <= self.current_tab < len(self.tabs):
            return self.tabs[self.current_tab][1]
        return None

    def _next_tab(self):
        if self.tabs:
            self._switch_tab((self.current_tab + 1) % len(self.tabs))

    def _prev_tab(self):
        if self.tabs:
            self._switch_tab((self.current_tab - 1) % len(self.tabs))

    def _tab_bar_wheel(self, e):
        if e.angleDelta().y() < 0: self._next_tab()
        else: self._prev_tab()

    # ──────────────────────────────────────────
    #  Navigation
    # ──────────────────────────────────────────
    def _go(self):
        q = self.url_input.text().strip()
        if not q: return
        b = self._current_browser()
        if not b: return
        if q.startswith("http://") or q.startswith("https://") or q.startswith("file://"):
            b.setUrl(QUrl(q))
        elif "." in q and " " not in q:
            b.setUrl(QUrl("https://" + q))
        else:
            b.setUrl(QUrl("https://www.google.com/search?q=" + q.replace(" ", "+")))

    def _go_home(self):
        b = self._current_browser()
        if b:
            b.setHtml(self._home_html(), QUrl("about:blank"))
            self.url_input.clear()

    def _open_url_new_tab(self, url):
        self._add_tab(url)

    def _reload_current(self):
        b = self._current_browser()
        if b: b.reload()

    # ──────────────────────────────────────────
    #  Load events
    # ──────────────────────────────────────────
    def _on_load_start(self, idx):
        if idx == self.current_tab:
            self.progress.setVisible(True)
            self.progress.setValue(0)
            self.rel_btn.setText("✕")
            self.rel_btn.clicked.disconnect()
            self.rel_btn.clicked.connect(lambda: self._current_browser() and self._current_browser().stop())
        if idx < len(self.tabs):
            self.tabs[idx][0].set_loading(True)

    def _on_load_progress(self, p, idx):
        if idx == self.current_tab:
            self.progress.setValue(p)

    def _on_load_finish(self, ok, idx):
        if idx == self.current_tab:
            self.progress.setVisible(False)
            self.rel_btn.setText("↺")
            self.rel_btn.clicked.disconnect()
            self.rel_btn.clicked.connect(lambda: self._current_browser() and self._current_browser().reload())
        if idx < len(self.tabs):
            self.tabs[idx][0].set_loading(False)

    def _on_url_changed(self, url, idx):
        u = url.toString()
        if idx == self.current_tab and u not in ("about:blank", ""):
            self.url_input.setText(u)
            self._update_lock(u)

    def _on_title_changed(self, title, idx):
        if idx < len(self.tabs):
            self.tabs[idx][0].set_title(title or "NEW_TAB")
        if idx == self.current_tab:
            self.setWindowTitle(f"NEURA // {title}")

    def _on_icon_changed(self, icon, idx):
        if idx < len(self.tabs):
            self.tabs[idx][0].set_favicon(icon)

    def _update_lock(self, url):
        self.lock_lbl.setText("🔒" if url.startswith("https://") else "🔓")

    # ──────────────────────────────────────────
    #  Browser features
    # ──────────────────────────────────────────
    def _zoom_in(self):
        b = self._current_browser()
        if b:
            f = min(b.zoomFactor() + 0.1, 5.0)
            b.setZoomFactor(f)
            self.zoom_lbl.setText(f"{int(f*100)}%")

    def _zoom_out(self):
        b = self._current_browser()
        if b:
            f = max(b.zoomFactor() - 0.1, 0.25)
            b.setZoomFactor(f)
            self.zoom_lbl.setText(f"{int(f*100)}%")

    def _zoom_reset(self):
        b = self._current_browser()
        if b:
            b.setZoomFactor(1.0)
            self.zoom_lbl.setText("100%")

    def _bookmark(self):
        b = self._current_browser()
        if not b: return
        url = b.url().toString()
        title = b.title()
        bm_file = os.path.join(os.path.expanduser("~"), ".neura_bookmarks.json")
        try:
            with open(bm_file) as f:
                bms = json.load(f)
        except:
            bms = []
        if not any(x["url"] == url for x in bms):
            bms.append({"title": title, "url": url})
            with open(bm_file, "w") as f:
                json.dump(bms, f, indent=2)
            self.statusBar().showMessage(f"  ★ BOOKMARKED: {title[:40]}", 3000)
        else:
            self.statusBar().showMessage("  ★ ALREADY BOOKMARKED", 2000)

    def _open_downloads(self):
        b = self._current_browser()
        if b:
            b.setUrl(QUrl("about:downloads"))

    def _toggle_mute(self):
        b = self._current_browser()
        if b:
            page = b.page()
            muted = page.isAudioMuted()
            page.setAudioMuted(not muted)
            self.statusBar().showMessage(f"  {'🔇 MUTED' if not muted else '🔊 UNMUTED'}", 2000)

    def _devtools(self):
        b = self._current_browser()
        if not b: return
        dev = QWebEngineView()
        b.page().setDevToolsPage(dev.page())
        dev.resize(900, 600)
        dev.setWindowTitle("NEURA // DevTools")
        dev.show()
        self._devtools_win = dev

    def _on_download(self, item: QWebEngineDownloadRequest):
        path, _ = QFileDialog.getSaveFileName(self, "Save File", item.suggestedFileName())
        if path:
            item.setDownloadFileName(os.path.basename(path))
            item.setDownloadDirectory(os.path.dirname(path))
            item.accept()
            self.statusBar().showMessage(f"  ⬇ DOWNLOADING: {os.path.basename(path)}", 4000)
        else:
            item.cancel()

    # ──────────────────────────────────────────
    #  Settings / Profile
    # ──────────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._load_chip()

    def _open_passwords(self):
        dlg = PasswordManagerDialog(self)
        dlg.exec()

    def _open_incognito(self):
        win = NeuraApp(incognito=True)
        win.show()
        self._incognito_windows.append(win)

    def _toggle_ai_panel(self):
        visible = self.ai_panel.isVisible()
        if visible:
            anim = QPropertyAnimation(self.ai_panel, b"maximumWidth", self)
            anim.setDuration(260)
            anim.setStartValue(self.ai_panel.width())
            anim.setEndValue(0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuart)
            anim.finished.connect(lambda: self.ai_panel.setVisible(False))
            anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
            self._ai_anim = anim
        else:
            self.ai_panel.setMaximumWidth(0)
            self.ai_panel.setVisible(True)
            anim = QPropertyAnimation(self.ai_panel, b"maximumWidth", self)
            anim.setDuration(260)
            anim.setStartValue(0)
            anim.setEndValue(320)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuart)
            anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
            self._ai_anim = anim

    def _load_chip(self):
        p = load_profile()
        if not p.get("name"): return
        self.chip.setVisible(True)
        self.chip_name.setText(p["name"].upper())
        if p.get("avatar") and os.path.exists(p["avatar"]):
            pix = QPixmap(p["avatar"]).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            r = QPixmap(20, 20)
            r.fill(Qt.GlobalColor.transparent)
            ptr = QPainter(r)
            ptr.setRenderHint(QPainter.RenderHint.Antialiasing)
            ptr.setBrush(QBrush(pix))
            ptr.setPen(Qt.PenStyle.NoPen)
            ptr.drawEllipse(0, 0, 20, 20)
            ptr.end()
            self.chip_av.setPixmap(r)
        else:
            ini = "".join(w[0] for w in p["name"].split() if w).upper()[:2]
            self.chip_av.setText(ini)
            self.chip_av.setFont(mono(8, True))
            self.chip_av.setStyleSheet(f"color:{PRIMARY};")

    # ──────────────────────────────────────────
    #  Status bar clock
    # ──────────────────────────────────────────
    def _tick_status(self):
        from datetime import datetime
        self.statusBar().showMessage(
            f"  ● NEURA [V3.0.0]    //    {datetime.now().strftime('%H:%M:%S')}    //    NEURA_OS 2026"
        )
        QTimer.singleShot(1000, self._tick_status)

    # ──────────────────────────────────────────
    #  Home HTML
    # ──────────────────────────────────────────
    def _home_html(self):
        return r"""<!DOCTYPE html><html class="dark" lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>NEURA // HOME</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:#000;color:#b1c5ff;font-family:'Courier New',monospace;overflow-x:hidden;}
  .grid{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
    background-image:linear-gradient(rgba(177,197,255,0.04)1px,transparent 1px),linear-gradient(90deg,rgba(177,197,255,0.04)1px,transparent 1px);
    background-size:24px 24px;}
  .crt{position:fixed;inset:0;background:linear-gradient(rgba(0,0,0,0)50%,rgba(0,0,0,0.08)50%);background-size:100% 2px;pointer-events:none;z-index:99;}
  h1{font-size:52px;font-weight:900;letter-spacing:18px;color:#b1c5ff;text-align:center;margin-bottom:40px;
     opacity:0;transform:translateY(-12px);animation:fadeUp .5s cubic-bezier(.22,1,.36,1) forwards;}
  .search-box{width:700px;border:1px solid #b1c5ff;padding:3px;background:#131313;
    box-shadow:0 0 20px rgba(177,197,255,0.12);
    opacity:0;transform:translateY(8px);animation:fadeUp .45s cubic-bezier(.22,1,.36,1) .12s forwards;}
  .search-inner{display:flex;align-items:center;gap:12px;padding:14px 18px;background:#0e0e0e;border:1px solid #424654;}
  .prompt{font-size:26px;font-weight:900;color:#b1c5ff;}
  #q{flex:1;background:transparent;border:none;color:#b1c5ff;font-family:'Courier New',monospace;font-size:18px;outline:none;transition:color .15s;}
  #q::placeholder{color:rgba(177,197,255,0.3);}
  .cursor{width:12px;height:28px;background:#b1c5ff;animation:blink 1s step-end infinite;}
  @keyframes blink{from,to{opacity:1}50%{opacity:0}}
  @keyframes fadeUp{to{opacity:1;transform:none}}
  .btns{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap;justify-content:center;
    opacity:0;transform:translateY(8px);animation:fadeUp .45s cubic-bezier(.22,1,.36,1) .22s forwards;}
  .btn{padding:10px 28px;border:1px solid #b1c5ff;background:transparent;color:#b1c5ff;
    font-family:'Courier New',monospace;font-size:11px;font-weight:700;letter-spacing:2px;cursor:pointer;
    transition:background .18s cubic-bezier(.22,1,.36,1),color .18s cubic-bezier(.22,1,.36,1),box-shadow .18s;}
  .btn:hover{background:#b1c5ff;color:#002c70;box-shadow:0 0 16px rgba(177,197,255,0.3);}
  #log{width:700px;margin-top:28px;opacity:0;animation:fadeUp .45s cubic-bezier(.22,1,.36,1) .32s forwards;}
  .log-header{font-size:10px;letter-spacing:2px;color:#8c90a0;border-bottom:1px dashed #424654;padding-bottom:6px;margin-bottom:10px;}
  .log-list{max-height:160px;overflow-y:auto;display:flex;flex-direction:column;gap:5px;}
  .log-list::-webkit-scrollbar{width:3px;} .log-list::-webkit-scrollbar-thumb{background:#424654;}
  .le{display:flex;gap:10px;opacity:0;transform:translateX(-8px);transition:opacity .25s cubic-bezier(.22,1,.36,1),transform .25s cubic-bezier(.22,1,.36,1);}
  .le.show{opacity:1;transform:none;}
  .lt{font-size:10px;color:#8c90a0;flex-shrink:0;margin-top:1px;}
  .lq{font-size:11px;} .ll{color:#b1c5ff;} .lv{color:#e2e2e2;} .ls{display:block;font-size:10px;color:#00e639;margin-top:1px;}
</style></head>
<body>
<div class="crt"></div>
<div class="grid">
  <h1>NEURA</h1>
  <div class="search-box">
    <div class="search-inner">
      <span class="prompt">&gt;</span>
      <input id="q" placeholder="SEARCH..." autofocus>
      <div class="cursor"></div>
    </div>
  </div>
  <div class="btns">
    <button class="btn" onclick="go('google')">EXECUTE_SEARCH</button>
  </div>
  <div id="log">
    <div class="log-header">SESSION_LOG:// &nbsp;<span id="cnt" style="color:#b1c5ff;">0 QUERIES</span></div>
    <div class="log-list" id="ll"><div style="font-size:11px;color:#424654;">// awaiting input...</div></div>
  </div>
</div>
<script>
  const q=document.getElementById('q'),ll=document.getElementById('ll'),cnt=document.getElementById('cnt');
  let n=0;
  function addLog(query,eng){
    const first=ll.querySelector('div[style]');if(first)first.remove();
    n++;cnt.textContent=n+' QUER'+(n===1?'Y':'IES');
    const t=new Date().toLocaleTimeString('en-GB',{hour12:false});
    const e=document.createElement('div');e.className='le';
    e.innerHTML='<span class="lt">'+t+'</span><span class="lq"><span class="ll">SEARCH['+eng+']:</span><span class="lv"> "'+query.toUpperCase()+'"</span><span class="ls">>> EXECUTING...</span></span>';
    ll.prepend(e);setTimeout(()=>e.classList.add('show'),10);
  }
  function go(eng){
    const v=q.value.trim();if(!v)return;
    addLog(v,eng);
    const url=eng==='youtube'
      ?'https://www.youtube.com/results?search_query='+encodeURIComponent(v)
      :(v.startsWith('http')?v:'https://www.google.com/search?q='+encodeURIComponent(v));
    setTimeout(()=>window.location.href=url,220);
    q.value='';q.focus();
  }
  q.addEventListener('keydown',e=>{if(e.key==='Enter')go('google');});
</script>
</body></html>"""


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = NeuraApp()
    w.show()
    # Checa actualizaciones en background, 2 segundos después de abrir
    # para no ralentizar el arranque
    QTimer.singleShot(2000, lambda: check_for_updates_async(w))
    sys.exit(app.exec())
