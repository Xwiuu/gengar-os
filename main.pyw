import sys
import psutil
import os
import json
import subprocess
import platform
import time
import requests
import socket

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QLabel,
        QWidget,
        QVBoxLayout,
        QMenu,
        QSystemTrayIcon,
        QDialog,
        QGridLayout,
        QProgressBar,
        QPushButton,
        QMessageBox,
        QGroupBox,
        QFormLayout,
        QDoubleSpinBox,
        QSpinBox,
        QCheckBox,
        QFrame,
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize
    from PyQt6.QtGui import QMovie, QAction, QIcon, QPixmap, QColor
except ImportError:
    sys.exit(1)

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "opacity": 1.0,
    "size": 170,
    "game_mode": False,
    "theme": "purple",
    "auto_game": True,
    "modules": {
        "show_cpu": True,
        "show_ram": True,
        "show_gpu": True,
        "show_disk": True,
        "show_net": True,
        "show_hardware": True,
    },
}

THEMES = {
    "purple": {"main": "#9d00ff", "acc": "#d600ff", "bg": "rgba(10, 10, 15, 0.95)"},
    "green": {"main": "#00ff00", "acc": "#ccff00", "bg": "rgba(10, 20, 10, 0.95)"},
    "blue": {"main": "#00ccff", "acc": "#00ffff", "bg": "rgba(10, 15, 30, 0.95)"},
    "red": {"main": "#ff0000", "acc": "#ff4444", "bg": "rgba(20, 10, 10, 0.95)"},
}

GAMES_LIST = [
    "cs2.exe",
    "csgo.exe",
    "valorant.exe",
    "valorant-win64-shipping.exe",
    "league of legends.exe",
    "dota2.exe",
    "gta5.exe",
    "r5apex.exe",
    "fortniteclient-win64-shipping.exe",
    "minecraft.exe",
    "robloxplayerbeta.exe",
    "cod.exe",
    "overwatch.exe",
]


def get_stylesheet(theme_name):
    t = THEMES.get(theme_name, THEMES["purple"])
    return f"""
    QDialog, QMenu {{ background-color: #0f0f14; border: 1px solid {t['main']}; color: #e0e0e0; font-family: 'Consolas', monospace; }}
    QMenu::item {{ padding: 5px 20px; }}
    QMenu::item:selected {{ background-color: {t['main']}; color: black; }}
    QLabel {{ background: transparent; border: none; font-size: 11px; color: white; }}
    QLabel#Title {{ color: {t['main']}; font-size: 14px; font-weight: bold; border-bottom: 2px solid {t['main']}; padding-bottom: 5px; }}
    QProgressBar {{ border: 1px solid #444; background: #1a1a1a; height: 10px; border-radius: 2px; text-align: center; font-size: 9px; color: white; }}
    QProgressBar::chunk {{ background-color: {t['main']}; }}
    QPushButton {{ background: #222; border: 1px solid {t['main']}; color: {t['main']}; font-weight: bold; padding: 5px; }}
    QPushButton:hover {{ background: {t['main']}; color: black; }}
    QGroupBox {{ border: 1px solid #555; margin-top: 10px; padding-top: 10px; font-weight: bold; color: {t['acc']}; }}
    """


def format_bytes(size):
    power = 2**10
    n = 0
    labels = {0: "", 1: "K", 2: "M", 3: "G"}
    while size > power:
        size /= power
        n += 1
    return f"{size:.1f} {labels[n]}B/s"


def get_cpu_info():
    try:
        freq = psutil.cpu_freq()
        f_max = freq.max if freq else 0
        return f"{platform.processor()}\n{psutil.cpu_count()} Cores @ {f_max:.0f}MHz"
    except:
        return "CPU Genérica"


def get_temp_color(temp_str):
    if "--" in temp_str or "N/A" in temp_str:
        return "#00ff00"
    try:
        temp = float(temp_str.replace("°C", ""))
        if temp < 45:
            return "#00ffff"
        if temp < 65:
            return "#00ff00"
        if temp < 80:
            return "#ffff00"
        if temp < 90:
            return "#ff8800"
        return "#ff0000"
    except:
        return "#00ff00"


# --- WORKER INTELIGENTE V32 ---
class FastWorker(QThread):
    data_ready = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.running = True
        self.found_ip = None

    def find_monitor_ip(self):
        # Tenta descobrir onde o LibreMonitor está rodando
        ips = ["127.0.0.1", "localhost"]
        try:
            # Pega todos os IPs da máquina
            host_name = socket.gethostname()
            for ip in socket.gethostbyname_ex(host_name)[2]:
                ips.append(ip)
        except:
            pass

        # Testa qual responde
        for ip in ips:
            try:
                url = f"http://{ip}:8085/data.json"
                r = requests.get(url, timeout=0.2)
                if r.status_code == 200:
                    return url
            except:
                pass
        return None

    def parse_hardware_json(self, data, d):
        for item in data:
            txt = item.get("Text", "")
            image = item.get("ImageURL", "")
            children = item.get("Children", [])

            # --- LÓGICA DE TEMPERATURA ---
            # Procura sensores de temperatura
            if "Temperature" in item.get("Type", "") or "Temperature" in txt:
                try:
                    val_clean = item["Value"].replace(" °C", "").replace(",", ".")
                    val = float(val_clean)

                    # FILTRO DE REALIDADE:
                    # Ignora se for menor que 20°C (Provavelmente é "Distance to TjMax" ou erro)
                    # Ignora se tiver "Distance" no nome
                    if val > 20 and "distance" not in txt.lower():
                        # Prioriza Package ou Core Max
                        if "package" in txt.lower() or "max" in txt.lower():
                            d["temp"] = f"{val:.0f}°C"
                        # Se ainda não tem nada, pega o primeiro que achar válido
                        elif d["temp"] == "--":
                            d["temp"] = f"{val:.0f}°C"
                except:
                    pass

            # --- LÓGICA DE GPU ---
            is_gpu_section = (
                "nvidia" in txt.lower()
                or "amd" in txt.lower()
                or "geforce" in txt.lower()
                or "radeon" in txt.lower()
            )

            # Se for GPU, olha dentro
            if is_gpu_section and children:
                self.parse_gpu_children(children, d)

            # Recursão para achar a seção certa
            if children:
                self.parse_hardware_json(children, d)

    def parse_gpu_children(self, nodes, d):
        for s in nodes:
            txt = s.get("Text", "")
            val_str = s.get("Value", "0")
            type_ = s.get("Type", "")

            # Load
            if "Load" in type_ or "Load" in txt:
                if "Core" in txt or "GPU" in txt:
                    try:
                        val = float(val_str.replace(" %", "").replace(",", "."))
                        if val > d["gpu_load"]:
                            d["gpu_load"] = int(val)
                    except:
                        pass

            # Temp GPU
            if "Temperature" in type_ or "Temperature" in txt:
                if "Core" in txt or "GPU" in txt:
                    try:
                        val = float(val_str.replace(" °C", "").replace(",", "."))
                        if val > 0:
                            d["gpu_temp"] = f"{val:.0f}°C"
                    except:
                        pass

            if s.get("Children"):
                self.parse_gpu_children(s["Children"], d)

    def run(self):
        while self.running:
            d = {"ping": "--", "temp": "--", "gpu_load": 0, "gpu_temp": None}

            # PING
            try:
                t1 = time.time()
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect(("8.8.8.8", 53))
                s.close()
                d["ping"] = f"{(time.time() - t1)*1000:.0f}ms"
            except:
                d["ping"] = "Err"

            # BUSCA IP SE AINDA NÃO ACHOU
            if not self.found_ip:
                self.found_ip = self.find_monitor_ip()

            # LEITURA DO HARDWARE
            if self.found_ip:
                try:
                    r = requests.get(self.found_ip, timeout=0.5)
                    if r.status_code == 200:
                        data = r.json()
                        if "Children" in data:
                            self.parse_hardware_json(data["Children"], d)
                except:
                    self.found_ip = None  # Se falhar, procura de novo no próximo ciclo

            # FALLBACKS FINAIS
            if d["temp"] == "--" and d["gpu_temp"]:
                d["temp"] = d["gpu_temp"]
            if d["temp"] == "--":
                try:
                    d["temp"] = f"{psutil.cpu_freq().current/1000:.1f}GHz"
                except:
                    pass

            self.data_ready.emit(d)
            time.sleep(0.5)

    def stop(self):
        self.running = False
        self.wait()


class GameDetector(QThread):
    game_found = pyqtSignal(bool)

    def run(self):
        while True:
            found = False
            try:
                for proc in psutil.process_iter(["name"]):
                    if proc.info["name"] and proc.info["name"].lower() in GAMES_LIST:
                        found = True
                        break
            except:
                pass
            self.game_found.emit(found)
            time.sleep(3)


class GeoWorker(QThread):
    data_ready = pyqtSignal(dict)

    def run(self):
        while True:
            d = {"ip": "...", "country": "??"}
            apis = [
                ("https://api.ipify.org?format=json", "ip"),
                ("http://ip-api.com/json", "query"),
                ("https://checkip.amazonaws.com", None),
            ]
            success = False
            for url, key in apis:
                try:
                    r = requests.get(url, timeout=3)
                    if key is None:
                        d["ip"] = r.text.strip()
                        d["country"] = "AWS"
                    else:
                        js = r.json()
                        d["ip"] = js.get(key, "Erro")
                        d["country"] = js.get("countryCode", "OK")
                    success = True
                    self.data_ready.emit(d)
                    break
                except:
                    continue
            if success:
                time.sleep(300)
            else:
                time.sleep(10)


class ConfigHub(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gengar Control Panel")
        self.config = current_config
        self.mods = self.config.get("modules", DEFAULT_CONFIG["modules"])
        self.setStyleSheet(get_stylesheet(parent.config.get("theme", "purple")))

        layout = QVBoxLayout()
        layout.addWidget(QLabel("⚙️ CONFIGURAÇÃO", objectName="Title"))

        grp_vis = QGroupBox("Visual")
        l = QFormLayout()
        self.op_spin = QDoubleSpinBox()
        self.op_spin.setRange(0.1, 1.0)
        self.op_spin.setValue(self.config.get("opacity", 1.0))
        self.op_spin.setSingleStep(0.1)
        l.addRow("Opacidade:", self.op_spin)
        self.sz_spin = QSpinBox()
        self.sz_spin.setRange(50, 500)
        self.sz_spin.setValue(self.config.get("size", 170))
        l.addRow("Tamanho:", self.sz_spin)
        grp_vis.setLayout(l)
        layout.addWidget(grp_vis)

        self.chk_auto = QCheckBox("Auto-Detectar Jogos")
        self.chk_auto.setChecked(self.config.get("auto_game", True))
        layout.addWidget(self.chk_auto)

        grp_mods = QGroupBox("Barras")
        l2 = QVBoxLayout()
        self.chk_hw = QCheckBox("Info Hardware")
        self.chk_hw.setChecked(self.mods.get("show_hardware", True))
        l2.addWidget(self.chk_hw)
        self.chk_cpu = QCheckBox("CPU")
        self.chk_cpu.setChecked(self.mods.get("show_cpu", True))
        l2.addWidget(self.chk_cpu)
        self.chk_ram = QCheckBox("RAM")
        self.chk_ram.setChecked(self.mods.get("show_ram", True))
        l2.addWidget(self.chk_ram)
        self.chk_gpu = QCheckBox("GPU")
        self.chk_gpu.setChecked(self.mods.get("show_gpu", True))
        l2.addWidget(self.chk_gpu)
        self.chk_disk = QCheckBox("Disco")
        self.chk_disk.setChecked(self.mods.get("show_disk", True))
        l2.addWidget(self.chk_disk)
        self.chk_net = QCheckBox("Rede")
        self.chk_net.setChecked(self.mods.get("show_net", True))
        l2.addWidget(self.chk_net)
        grp_mods.setLayout(l2)
        layout.addWidget(grp_mods)

        btn = QPushButton("SALVAR")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
        self.setLayout(layout)

    def get_new_config(self):
        return {
            "opacity": self.op_spin.value(),
            "size": self.sz_spin.value(),
            "game_mode": self.config.get("game_mode", False),
            "theme": self.config.get("theme", "purple"),
            "auto_game": self.chk_auto.isChecked(),
            "modules": {
                "show_hardware": self.chk_hw.isChecked(),
                "show_cpu": self.chk_cpu.isChecked(),
                "show_ram": self.chk_ram.isChecked(),
                "show_gpu": self.chk_gpu.isChecked(),
                "show_disk": self.chk_disk.isChecked(),
                "show_net": self.chk_net.isChecked(),
            },
        }


class ZenithHUD(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_ref = parent
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(get_stylesheet(parent.config.get("theme", "purple")))

        layout = QVBoxLayout()
        mods = parent.config.get("modules", DEFAULT_CONFIG["modules"])
        layout.addWidget(
            QLabel(
                "GENGAR OS // ULTIMATE",
                objectName="Title",
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
        )

        if mods.get("show_hardware", True):
            layout.addWidget(
                QLabel(get_cpu_info(), styleSheet="color:white; font-size:10px;")
            )
            layout.addWidget(
                QFrame(frameShape=QFrame.Shape.HLine, styleSheet="color:#444")
            )

        if mods.get("show_cpu", True):
            self.add_bar(layout, "CPU:", "bar_cpu")
        if mods.get("show_ram", True):
            self.add_bar(layout, "RAM:", "bar_ram")
        if mods.get("show_gpu", True):
            self.add_bar(layout, "GPU:", "bar_gpu")
        self.add_bar(layout, "TEMP:", "bar_temp")

        if mods.get("show_disk", True):
            self.add_bar(layout, "Disco:", "bar_disk")

        if mods.get("show_net", True):
            self.lbl_spd = QLabel(
                "⬇️ --  ⬆️ --",
                styleSheet="color:cyan; font-weight:bold; margin-top:5px; alignment:center",
            )
            layout.addWidget(self.lbl_spd)
            self.lbl_ip = QLabel(
                f"IP: {parent.geo_data['ip']}",
                styleSheet="color:#aaa; alignment:center",
            )
            layout.addWidget(self.lbl_ip)

        btn = QPushButton("FECHAR")
        btn.clicked.connect(self.hide)
        layout.addWidget(btn)
        self.setLayout(layout)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(500)
        self.update()

    def add_bar(self, layout, txt, attr):
        layout.addWidget(QLabel(txt))
        bar = QProgressBar()
        bar.setRange(0, 100)
        setattr(self, attr, bar)
        layout.addWidget(bar)

    def update(self):
        if hasattr(self, "bar_cpu"):
            self.bar_cpu.setValue(int(psutil.cpu_percent()))
        if hasattr(self, "bar_ram"):
            self.bar_ram.setValue(int(psutil.virtual_memory().percent))
        if hasattr(self, "bar_disk"):
            self.bar_disk.setValue(int(psutil.disk_usage("/").percent))
        if hasattr(self, "bar_gpu"):
            self.bar_gpu.setValue(self.parent_ref.game_data.get("gpu_load", 0))

        if hasattr(self, "bar_temp"):
            temp_str = self.parent_ref.game_data.get("temp", "0")
            try:
                temp_val = int(float(temp_str.replace("°C", "").replace("GHz", "0")))
                self.bar_temp.setValue(temp_val)
                self.bar_temp.setFormat(f"{temp_val}°C")
            except:
                self.bar_temp.setValue(0)

        if hasattr(self, "lbl_spd"):
            d, u = self.parent_ref.net_speed
            self.lbl_spd.setText(f"⬇️ {d}  ⬆️ {u}")
        if hasattr(self, "lbl_ip"):
            self.lbl_ip.setText(f"IP: {self.parent_ref.geo_data['ip']}")


class App(QWidget):
    def __init__(self):
        super().__init__()

        if not os.path.exists("gengar_oficial.gif"):
            QMessageBox.critical(None, "Erro", "Falta 'gengar_oficial.gif'!")
            sys.exit(1)

        if os.path.exists(CONFIG_FILE):
            try:
                self.config = json.load(open(CONFIG_FILE))
            except:
                self.config = DEFAULT_CONFIG
        else:
            self.config = DEFAULT_CONFIG

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.lbl = QLabel(self)
        self.mov = QMovie("gengar_oficial.gif")
        self.lbl.setMovie(self.mov)
        self.mov.start()
        self.lbl.move(0, 0)

        # UI DO MODO JOGO
        self.overlay_widget = QWidget(self)
        self.overlay_widget.hide()

        self.ov_layout = QVBoxLayout(self.overlay_widget)
        self.ov_layout.setContentsMargins(4, 4, 4, 4)
        self.ov_layout.setSpacing(1)

        self.l_gpu = QLabel("GPU: --")
        self.l_ping = QLabel("PING: --")
        self.l_temp = QLabel("TEMP: --")
        self.l_lat = QLabel("LAT: --")

        font = self.font()
        font.setFamily("Consolas")
        font.setPixelSize(10)
        font.setBold(True)

        for lb in [self.l_gpu, self.l_ping, self.l_temp, self.l_lat]:
            lb.setFont(font)
            lb.setStyleSheet("color: #00ff00;")
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.ov_layout.addWidget(lb)

        self.overlay_widget.setStyleSheet(
            """
            background-color: rgba(0, 0, 0, 0.5);
            border-radius: 5px;
            border: 1px solid rgba(0, 255, 0, 0.2);
        """
        )
        self.overlay_widget.setFixedWidth(80)

        self.apply_visuals()

        self.geo_data = {"ip": "...", "country": ".."}
        self.geo = GeoWorker()
        self.geo.data_ready.connect(self.set_geo)
        self.geo.start()

        self.game_data = {"ping": "--", "temp": "--", "gpu_load": 0, "gpu_temp": None}
        self.worker = FastWorker()
        self.worker.data_ready.connect(self.update_data)
        self.worker.start()

        self.detector = GameDetector()
        self.detector.game_found.connect(self.on_game_detected)
        self.detector.start()

        self.last_net = psutil.net_io_counters()
        self.net_speed = ("0", "0")

        self.init_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.hud = ZenithHUD(self)
        self.old_pos = None

    def set_geo(self, d):
        self.geo_data = d

    def update_data(self, d):
        self.game_data = d

    def on_game_detected(self, found):
        if self.config.get("auto_game", True):
            if found and not self.config["game_mode"]:
                self.config["game_mode"] = True
                self.apply_visuals()
            elif not found and self.config["game_mode"]:
                self.config["game_mode"] = False
                self.apply_visuals()

    def init_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray_mov = QMovie("gengar_oficial.gif")
        self.tray_mov.frameChanged.connect(self.update_tray_icon)
        if self.tray_mov.loopCount() != -1:
            self.tray_mov.finished.connect(self.tray_mov.start)
        self.tray_mov.start()

        self.menu = QMenu()
        self.update_tray_style()
        self.menu.addAction(
            QAction("🧹 Limpar RAM", self, triggered=lambda: os.system("start taskmgr"))
        )
        self.menu.addAction(QAction("⚠️ MODO PÂNICO", self, triggered=self.panic))
        self.menu.addSeparator()
        theme_menu = QMenu("🎨 Temas", self.menu)
        for t in THEMES:
            theme_menu.addAction(
                QAction(t.upper(), self, triggered=lambda c, x=t: self.set_theme(x))
            )
        self.menu.addMenu(theme_menu)
        self.menu.addAction(
            QAction("⚙️ Configurações", self, triggered=self.open_config)
        )
        self.menu.addAction(
            QAction("🎮 Modo Jogo (Toggle)", self, triggered=self.toggle_game)
        )
        self.menu.addSeparator()
        self.menu.addAction(QAction("👁️ Mostrar Gengar", self, triggered=self.show))
        self.menu.addAction(QAction("❌ Sair", self, triggered=self.close_app))
        self.tray.setContextMenu(self.menu)
        self.tray.show()

    def update_tray_icon(self):
        if self.tray_mov.currentPixmap():
            self.tray.setIcon(QIcon(self.tray_mov.currentPixmap()))

    def update_tray_style(self):
        self.menu.setStyleSheet(get_stylesheet(self.config.get("theme", "purple")))

    def tick(self):
        cpu = psutil.cpu_percent()
        net = psutil.net_io_counters()
        bs = net.bytes_sent - self.last_net.bytes_sent
        br = net.bytes_recv - self.last_net.bytes_recv
        self.net_speed = (format_bytes(br), format_bytes(bs))
        self.last_net = net

        spd = 50 if self.config["game_mode"] else 100 + (cpu * 2)
        self.mov.setSpeed(int(spd))
        self.tray_mov.setSpeed(int(spd))

        if self.config["game_mode"]:
            ping_val = self.game_data.get("ping", "--")
            temp_val = self.game_data.get("temp", "--")
            gpu_val = self.game_data.get("gpu_load", 0)

            self.l_gpu.setText(f"GPU: {gpu_val}%")
            self.l_ping.setText(f"PING: {ping_val}")
            self.l_temp.setText(f"TEMP: {temp_val}")
            self.l_lat.setText(f"LAT: {ping_val}")

            color = get_temp_color(temp_val)
            self.l_temp.setStyleSheet(f"color: {color};")

            x_pos = int((self.width() - self.overlay_widget.width()) / 2)
            y_pos = self.lbl.height() + 5
            self.overlay_widget.move(x_pos, y_pos)
            self.overlay_widget.show()
        else:
            self.overlay_widget.hide()
        self.tray.setToolTip(f"Gengar OS: {cpu}% CPU")

    def toggle_game(self):
        self.config["game_mode"] = not self.config["game_mode"]
        self.save_config()
        self.apply_visuals()

    def apply_visuals(self):
        current_size = self.config.get("size", 170)
        if self.config["game_mode"]:
            gengar_size = 110
            window_height = gengar_size + 80
            op = 0.85
            self.resize(gengar_size, window_height)
            self.lbl.resize(gengar_size, gengar_size)
            self.mov.setScaledSize(QSize(gengar_size, gengar_size))
        else:
            op = self.config.get("opacity", 1.0)
            self.resize(current_size, current_size)
            self.lbl.resize(current_size, current_size)
            self.mov.setScaledSize(QSize(current_size, current_size))
        self.setWindowOpacity(op)

    def open_config(self):
        d = ConfigHub(self.config, self)
        if d.exec():
            self.config = d.get_new_config()
            self.save_config()
            self.apply_visuals()
            self.set_theme(self.config["theme"])

    def set_theme(self, t):
        self.config["theme"] = t
        self.save_config()
        self.update_tray_style()
        if self.hud.isVisible():
            self.hud.hide()
            self.hud = ZenithHUD(self)
            self.hud.show()
        else:
            self.hud = ZenithHUD(self)

    def panic(self):
        self.hide()
        os.system("nircmd mutesysvolume 1")

    def save_config(self):
        json.dump(self.config, open(CONFIG_FILE, "w"))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.old_pos = e.globalPosition().toPoint()
        elif e.button() == Qt.MouseButton.RightButton:
            if not self.config["game_mode"]:
                if self.hud.isVisible():
                    self.hud.hide()
                else:
                    self.hud.move(e.globalPosition().toPoint())
                    self.hud.show()

    def mouseMoveEvent(self, e):
        if self.old_pos:
            self.move(self.pos() + e.globalPosition().toPoint() - self.old_pos)
            self.old_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self.old_pos = None

    def close_app(self):
        self.worker.stop()
        QApplication.instance().quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = App()
    win.show()
    sys.exit(app.exec())
