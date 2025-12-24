import sys
import psutil
import os
import json
import requests
import subprocess
import platform
import datetime
from PyQt6.QtWidgets import (QApplication, QLabel, QWidget, QVBoxLayout, QMenu, 
                             QSystemTrayIcon, QDialog, QFormLayout, QSpinBox, 
                             QDoubleSpinBox, QPushButton, QHBoxLayout, QProgressBar, 
                             QFrame, QCheckBox, QGroupBox, QGridLayout, QComboBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QPoint, QSize
from PyQt6.QtGui import QMovie, QCursor, QAction, QIcon, QFont, QColor, QPixmap, QPainter

# --- CONFIGURAÇÃO ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "opacity": 1.0,
    "size": 170,
    "game_mode": False,
    "theme": "purple",
    "modules": {
        "show_cpu": True,
        "show_ram": True,
        "show_disk": True,
        "show_net": True,
        "show_hardware": True
    }
}

# --- TEMAS ---
THEMES = {
    "purple": {"main": "#9d00ff", "acc": "#d600ff", "bg": "rgba(15, 15, 20, 0.96)"},
    "green":  {"main": "#00ff00", "acc": "#ccff00", "bg": "rgba(10, 20, 10, 0.96)"},
    "blue":   {"main": "#00ccff", "acc": "#00ffff", "bg": "rgba(10, 15, 30, 0.96)"},
    "red":    {"main": "#ff0000", "acc": "#ff4444", "bg": "rgba(20, 10, 10, 0.96)"},
}

def get_stylesheet(theme_name):
    t = THEMES.get(theme_name, THEMES["purple"])
    return f"""
    QDialog, QMenu {{
        background-color: #0f0f14; border: 1px solid {t['main']};
        color: #e0e0e0; font-family: 'Consolas', monospace;
    }}
    QMenu::item {{ padding: 8px 25px; }}
    QMenu::item:selected {{ background-color: {t['main']}; color: black; }}
    QMenu::separator {{ background: #333; height: 1px; margin: 5px; }}
    
    QLabel {{ background: transparent; border: none; font-size: 11px; color: white; }}
    QLabel#Title {{ 
        color: {t['main']}; font-size: 14px; font-weight: bold; 
        border-bottom: 2px solid {t['main']}; padding-bottom: 5px;
    }}
    QLabel#Section {{ color: {t['acc']}; font-weight: bold; margin-top: 5px; }}
    
    QProgressBar {{
        border: 1px solid #444; border-radius: 4px;
        background-color: #1a1a1a; height: 12px;
        text-align: center; color: white; font-size: 9px;
    }}
    QProgressBar::chunk {{ background-color: {t['main']}; border-radius: 3px; }}
    
    QPushButton {{
        background-color: #222; border: 1px solid {t['main']}; color: {t['main']};
        padding: 6px; border-radius: 5px; font-weight: bold;
    }}
    QPushButton:hover {{ background-color: {t['main']}; color: black; }}
    QGroupBox {{ border: 1px solid #555; margin-top: 10px; padding-top: 10px; font-weight: bold; }}
    """

# --- WORKERS ---
def get_detailed_cpu():
    try:
        freq = psutil.cpu_freq()
        return f"{platform.processor()}\n{psutil.cpu_count()} Cores @ {freq.max:.0f}MHz"
    except: return "CPU Virtual / Genérica"

def format_bytes(size):
    power = 2**10
    n = 0
    labels = {0 : '', 1: 'K', 2: 'M', 3: 'G'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.1f} {labels[n]}B/s"

class NetWorker(QThread):
    data_ready = pyqtSignal(dict)
    def run(self):
        data = {"ip": "Offline", "country": "??"}
        try:
            r = requests.get("http://ip-api.com/json/", timeout=2).json()
            data["ip"] = r.get("query", "Offline")
            data["country"] = r.get("countryCode", "??")
        except: pass
        self.data_ready.emit(data)

# --- CONFIG HUB ---
class ConfigHub(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gengar Control Panel")
        self.config = current_config
        self.mods = self.config.get("modules", DEFAULT_CONFIG["modules"])
        
        current_theme = parent.config.get("theme", "purple")
        self.setStyleSheet(get_stylesheet(current_theme))

        layout = QVBoxLayout()
        layout.addWidget(QLabel("⚙️ SYSTEM CONFIG", objectName="Title"))

        grp_vis = QGroupBox("Aparência")
        v_layout = QFormLayout()
        self.op_spin = QDoubleSpinBox()
        self.op_spin.setRange(0.1, 1.0)
        self.op_spin.setValue(self.config.get("opacity", 1.0))
        self.op_spin.setSingleStep(0.1)
        v_layout.addRow("Opacidade:", self.op_spin)
        
        self.sz_spin = QSpinBox()
        self.sz_spin.setRange(50, 500)
        self.sz_spin.setValue(self.config.get("size", 170))
        v_layout.addRow("Tamanho (px):", self.sz_spin)
        grp_vis.setLayout(v_layout)
        layout.addWidget(grp_vis)

        grp_mods = QGroupBox("Módulos Ativos")
        m_layout = QVBoxLayout()
        self.chk_hw = QCheckBox("Hardware Info")
        self.chk_hw.setChecked(self.mods.get("show_hardware", True))
        m_layout.addWidget(self.chk_hw)
        self.chk_cpu = QCheckBox("Monitorar CPU")
        self.chk_cpu.setChecked(self.mods.get("show_cpu", True))
        m_layout.addWidget(self.chk_cpu)
        self.chk_ram = QCheckBox("Monitorar RAM")
        self.chk_ram.setChecked(self.mods.get("show_ram", True))
        m_layout.addWidget(self.chk_ram)
        self.chk_disk = QCheckBox("Monitorar Disco")
        self.chk_disk.setChecked(self.mods.get("show_disk", True))
        m_layout.addWidget(self.chk_disk)
        self.chk_net = QCheckBox("Monitorar Rede")
        self.chk_net.setChecked(self.mods.get("show_net", True))
        m_layout.addWidget(self.chk_net)
        grp_mods.setLayout(m_layout)
        layout.addWidget(grp_mods)

        btn_save = QPushButton("SALVAR & APLICAR")
        btn_save.clicked.connect(self.accept)
        layout.addWidget(btn_save)
        self.setLayout(layout)

    def get_new_config(self):
        return {
            "opacity": self.op_spin.value(),
            "size": self.sz_spin.value(),
            "game_mode": self.config.get("game_mode", False),
            "theme": self.config.get("theme", "purple"),
            "modules": {
                "show_hardware": self.chk_hw.isChecked(),
                "show_cpu": self.chk_cpu.isChecked(),
                "show_ram": self.chk_ram.isChecked(),
                "show_disk": self.chk_disk.isChecked(),
                "show_net": self.chk_net.isChecked()
            }
        }

# --- HUD (MENU FLUTUANTE) ---
class ZenithHUD(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.parent_ref = parent_widget
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        current_theme = parent_widget.config.get("theme", "purple")
        self.setStyleSheet(get_stylesheet(current_theme))
        
        layout = QVBoxLayout()
        mods = parent_widget.config.get("modules", DEFAULT_CONFIG["modules"])

        title = QLabel(f"GENGAR_OS // ZENITH")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        if mods.get("show_hardware", True):
            grid = QGridLayout()
            grid.addWidget(QLabel("CHIP:", objectName="Section"), 0, 0)
            lbl_cpu = QLabel(get_detailed_cpu())
            lbl_cpu.setWordWrap(True)
            grid.addWidget(lbl_cpu, 0, 1)
            layout.addLayout(grid)
            layout.addWidget(QFrame(frameShape=QFrame.Shape.HLine, styleSheet="color: #444"))

        if mods.get("show_cpu", True): self.add_bar(layout, "CPU Load:", "bar_cpu")
        if mods.get("show_ram", True): self.add_bar(layout, "RAM Usage:", "bar_ram")
        if mods.get("show_disk", True): self.add_bar(layout, "Disk Root:", "bar_disk")

        if mods.get("show_net", True):
            self.lbl_net_speed = QLabel("⬇️ --  ⬆️ --")
            self.lbl_net_speed.setStyleSheet("color: cyan; font-weight: bold; margin-top: 5px;")
            self.lbl_net_speed.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.lbl_net_speed)
            
            geo = self.parent_ref.geo_data
            self.lbl_ip = QLabel(f"Ext IP: {geo['ip']}")
            self.lbl_ip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl_ip.setStyleSheet("color: #aaa;")
            layout.addWidget(self.lbl_ip)

        btn = QPushButton("⚙️ CONFIGURAR")
        btn.clicked.connect(parent_widget.open_config)
        layout.addWidget(btn)

        self.setLayout(layout)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_live)
        self.timer.start(1000)
        self.update_live()

    def add_bar(self, layout, text, attr_name):
        layout.addWidget(QLabel(text))
        bar = QProgressBar()
        bar.setRange(0, 100)
        setattr(self, attr_name, bar)
        layout.addWidget(bar)

    def update_live(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        if hasattr(self, 'bar_cpu'): self.bar_cpu.setValue(int(cpu))
        if hasattr(self, 'bar_ram'): self.bar_ram.setValue(int(ram.percent))
        if hasattr(self, 'bar_disk'): self.bar_disk.setValue(int(disk.percent))
        
        if hasattr(self, 'lbl_net_speed'):
            dl, ul = self.parent_ref.net_speed
            self.lbl_net_speed.setText(f"⬇️ {dl}  ⬆️ {ul}")

# --- APP PRINCIPAL ---
class GengarZenith(QWidget):
    def __init__(self):
        super().__init__()
        self.load_config()
        self.is_game_mode = self.config.get("game_mode", False)
        self.geo_data = {"ip": "...", "country": "??"}
        self.last_net = psutil.net_io_counters()
        self.net_speed = ("0 KB/s", "0 KB/s")
        
        self.init_ui()
        self.init_tray() # Inicializa a bandeja animada
        
        self.net_thread = NetWorker()
        self.net_thread.data_ready.connect(self.set_geo)
        self.net_thread.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

        self.vpn_timer = QTimer(self)
        self.vpn_timer.timeout.connect(self.check_vpn)
        self.vpn_timer.start(3000)
        
        if self.is_game_mode: self.apply_game_mode()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f: self.config = json.load(f)
        else:
            self.config = DEFAULT_CONFIG
            self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f: json.dump(self.config, f)

    def set_theme(self, theme_name):
        self.config["theme"] = theme_name
        self.save_config()
        self.tray.hide()
        self.init_tray()
        self.tray.showMessage("Gengar OS", f"Tema aplicado: {theme_name.upper()}")

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        sz = self.config.get("size", 170)
        self.setGeometry(100, 100, sz, sz)
        self.setWindowOpacity(self.config.get("opacity", 1.0))

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0,0,0,0)
        
        self.label = QLabel(self)
        self.movie = QMovie("gengar_oficial.gif")
        self.movie.setScaledSize(self.size())
        self.label.setMovie(self.movie)
        self.movie.start()
        self.layout.addWidget(self.label)

        self.vpn_dot = QLabel(self)
        self.vpn_dot.setFixedSize(12, 12)
        self.vpn_dot.setStyleSheet("background-color: red; border-radius: 6px; border: 1px solid black;")
        self.vpn_dot.move(15, 15)

        self.overlay = QLabel(self)
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay.setStyleSheet("color: #00ff00; font-family: monospace; font-weight: bold; background: rgba(0,0,0,0.7); border-radius: 5px; font-size: 10px;")
        self.overlay.hide()
        
        self.setLayout(self.layout)
        self.old_pos = None

    def init_tray(self):
        # --- LÓGICA DE ÍCONE ANIMADO NA BANDEJA ---
        self.tray = QSystemTrayIcon(self)
        
        # Carrega o GIF também para a bandeja
        self.tray_movie = QMovie("gengar_oficial.gif")
        self.tray_movie.frameChanged.connect(self.update_tray_icon)
        if self.tray_movie.loopCount() != -1: self.tray_movie.finished.connect(self.tray_movie.start)
        self.tray_movie.start()

        # Menu da Bandeja
        theme_name = self.config.get("theme", "purple")
        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet(get_stylesheet(theme_name))
        
        act_clean = QAction("🧹 Limpar RAM", self)
        act_clean.triggered.connect(self.tactical_clean_ram)
        self.tray_menu.addAction(act_clean)

        act_panic = QAction("⚠️ MODO PÂNICO", self)
        act_panic.triggered.connect(self.panic_mode)
        self.tray_menu.addAction(act_panic)
        
        self.tray_menu.addSeparator()

        theme_menu = QMenu("🎨 Mudar Tema", self.tray_menu)
        theme_menu.setStyleSheet(get_stylesheet(theme_name))
        for t_name in THEMES.keys():
            t_act = QAction(t_name.capitalize(), self)
            t_act.triggered.connect(lambda checked, n=t_name: self.set_theme(n))
            theme_menu.addAction(t_act)
        self.tray_menu.addMenu(theme_menu)

        act_conf = QAction("⚙️ Painel de Controle", self)
        act_conf.triggered.connect(self.open_config)
        self.tray_menu.addAction(act_conf)

        act_game = QAction("🎮 Modo Jogo (Toggle)", self)
        act_game.triggered.connect(self.toggle_game_mode)
        self.tray_menu.addAction(act_game)
        
        self.tray_menu.addSeparator()
        
        act_vis = QAction("👁️ Mostrar Gengar", self)
        act_vis.triggered.connect(self.show_normal)
        self.tray_menu.addAction(act_vis)

        act_quit = QAction("❌ Encerrar", self)
        act_quit.triggered.connect(QApplication.instance().quit)
        self.tray_menu.addAction(act_quit)

        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()

    def update_tray_icon(self):
        # Pega o frame atual do GIF e joga na bandeja
        if self.tray_movie.currentPixmap():
            self.tray.setIcon(QIcon(self.tray_movie.currentPixmap()))

    def set_geo(self, data): self.geo_data = data

    def check_vpn(self):
        active = False
        for iface in psutil.net_if_addrs():
            if "tun" in iface or "wg" in iface: active = True
        color = "#00ff00" if active else "#ff0000"
        self.vpn_dot.setStyleSheet(f"background-color: {color}; border-radius: 6px; border: 1px solid white;")
        if self.is_game_mode: self.vpn_dot.hide()

    def tick(self):
        cpu = psutil.cpu_percent()
        current_net = psutil.net_io_counters()
        bytes_sent = current_net.bytes_sent - self.last_net.bytes_sent
        bytes_recv = current_net.bytes_recv - self.last_net.bytes_recv
        self.net_speed = (format_bytes(bytes_recv), format_bytes(bytes_sent))
        self.last_net = current_net

        # Controla a velocidade dos DOIS Gengars (Mesa e Bandeja)
        speed = 100 + (cpu * 2.5)
        if self.is_game_mode: speed = 50

        self.movie.setSpeed(int(speed))
        self.tray_movie.setSpeed(int(speed)) # Anima a bandeja na mesma velocidade

        if self.is_game_mode:
            self.overlay.setText(f"FPS: --\nCPU: {cpu}%\nDL: {self.net_speed[0]}")
            self.overlay.adjustSize()
            self.overlay.move(5, self.height() - 50)
            
        self.tray.setToolTip(f"Gengar OS\nCPU: {cpu}%\nDL: {self.net_speed[0]}")

    def toggle_game_mode(self):
        self.is_game_mode = not self.is_game_mode
        self.config["game_mode"] = self.is_game_mode
        self.save_config()
        self.apply_game_mode()

    def apply_game_mode(self):
        if self.is_game_mode:
            self.setWindowOpacity(0.4)
            self.resize(80, 80)
            self.movie.setScaledSize(self.size())
            self.vpn_dot.hide()
            self.overlay.show()
        else:
            self.setWindowOpacity(self.config.get("opacity", 1.0))
            sz = self.config.get("size", 170)
            self.resize(sz, sz)
            self.movie.setScaledSize(self.size())
            self.vpn_dot.show()
            self.overlay.hide()

    def contextMenuEvent(self, event):
        if not self.is_game_mode:
            self.hud = ZenithHUD(self)
            self.hud.move(event.globalPos())
            self.hud.exec()

    def open_config(self):
        dlg = ConfigHub(self.config, self)
        if dlg.exec():
            self.config = dlg.get_new_config()
            self.save_config()
            self.apply_game_mode()
            self.set_theme(self.config["theme"])

    def tactical_clean_ram(self):
        subprocess.Popen(["qterminal", "-e", "sudo sync; echo 3 | sudo tee /proc/sys/vm/drop_caches"])

    def panic_mode(self):
        self.hide()
        os.system("amixer set Master mute")
        self.tray.showMessage("GENGAR OS", "⚠️ MODO PÂNICO ATIVADO")

    def show_normal(self):
        self.show()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self.old_pos = e.globalPosition().toPoint()
    def mouseMoveEvent(self, e):
        if self.old_pos:
            delta = e.globalPosition().toPoint() - self.old_pos
            self.move(self.x()+delta.x(), self.y()+delta.y())
            self.old_pos = e.globalPosition().toPoint()
    def mouseReleaseEvent(self, e): self.old_pos = None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    p = GengarZenith()
    p.show()
    sys.exit(app.exec())
