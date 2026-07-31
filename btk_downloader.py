import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyleFactory,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from yt_dlp import YoutubeDL

CONFIG_FILE = Path.home() / ".btk_downloader_config.json"
BASE_URL = "https://www.btkakademi.gov.tr/api/service/v1"

# --- HELPER FUNCTIONS ---


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def extract_course_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip().split("?")[0].strip("/")
    return url_or_id.split("-")[-1]


# --- CONFIG MANAGER ---


class ConfigManager:
    @staticmethod
    def load_config() -> dict:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "access_token": "",
            "download_dir": str(Path.home() / "Downloads" / "btk_downloads"),
            "organize_folders": True,
            "auto_register": True,
        }

    @staticmethod
    def save_config(config: dict):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Config kaydedilemedi: {e}")


# --- API HELPERS ---


class BTKApi:
    @staticmethod
    def get_headers(access_token: str) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
            "Authorization": f"Bearer {access_token.strip()}",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }

    @staticmethod
    def register_course(course_id: str, access_token: str) -> tuple[bool, str]:
        url = f"{BASE_URL}/course/registration/register/{course_id}?language=tr"
        try:
            res = requests.post(
                url,
                headers=BTKApi.get_headers(access_token),
                json={"demandForm": {}},
                timeout=30,
            )
            if res.status_code == 200:
                return True, f"Kayıt durumu: {res.json().get('status', 'Bilinmiyor')}"
            return False, f"Kayıt yanıtı (HTTP {res.status_code})"
        except Exception as e:
            return False, f"Kayıt sırasında hata: {e}"

    @staticmethod
    def get_syllabus(course_id: str, access_token: str) -> tuple[bool, list, str]:
        url = f"{BASE_URL}/public/51/course/details/program/syllabus/{
            course_id
        }?language=tr"
        try:
            res = requests.get(
                url, headers=BTKApi.get_headers(access_token), timeout=30
            )
            if res.status_code == 200 and isinstance(res.json(), list):
                return True, res.json(), "Müfredat başarıyla çekildi."
            return False, [], f"Müfredat alınamadı (HTTP {res.status_code})"
        except Exception as e:
            return False, [], f"Müfredat çekilirken hata: {e}"

    @staticmethod
    def start_lesson(
        course_id: str, lesson_id: str, access_token: str
    ) -> tuple[str | None, str]:
        url = f"{BASE_URL}/course/deliver/start/{lesson_id}"
        try:
            res = requests.post(
                url,
                headers=BTKApi.get_headers(access_token),
                json={"programId": int(course_id)},
                timeout=30,
            )
            if res.status_code == 200:
                video_id = res.json().get("remoteCourseReference", "")
                if video_id:
                    return video_id, "Ders başlatıldı."
                return None, "Video ID bulunamadı. Token geçersiz veya yetkisiz."
            return None, f"Ders başlatılamadı (HTTP {res.status_code})"
        except Exception as e:
            return None, f"Ders başlatılırken hata: {e}"

    @staticmethod
    def get_video_url(video_id: str) -> tuple[str | None, str | None, str]:
        url = f"https://cinema8.com/api/v1/uscene/rawvideo/flavor/{video_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://cinema8.com/",
            "Origin": "https://cinema8.com",
        }
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                d = res.json()
                return (
                    d.get("name", "video.mp4"),
                    d.get("hlsUrl", ""),
                    "Video bağlantısı alındı.",
                )
            return None, None, f"Video bilgisi alınamadı (HTTP {res.status_code})"
        except Exception as e:
            return None, None, f"Video URL sorgulanırken hata: {e}"


# --- WORKER THREADS ---


class FetchSyllabusWorker(QThread):
    finished_signal = Signal(bool, list, str)

    def __init__(self, course_id: str, access_token: str):
        super().__init__()
        self.course_id = course_id
        self.access_token = access_token

    def run(self):
        success, data, msg = BTKApi.get_syllabus(self.course_id, self.access_token)
        self.finished_signal.emit(success, data, msg)


class DownloadWorker(QThread):
    log_signal = Signal(str)
    overall_progress_signal = Signal(int, int)
    current_progress_signal = Signal(float, str, str)
    # is_cancelled, downloaded_count, total_count
    finished_signal = Signal(bool, int, int)

    def __init__(
        self,
        course_id: str,
        selected_items: list[dict],
        access_token: str,
        download_dir: str,
        organize_folders: bool,
        auto_register: bool,
    ):
        super().__init__()
        self.course_id = course_id
        self.selected_items = selected_items
        self.access_token = access_token
        self.download_dir = Path(download_dir)
        self.organize_folders = organize_folders
        self.auto_register = auto_register
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        total_items = len(self.selected_items)
        downloaded_count = 0
        if total_items == 0:
            self.log_signal.emit("İndirilecek ders seçilmedi.")
            self.finished_signal.emit(False, 0, 0)
            return

        if self.auto_register:
            self.log_signal.emit("Kursa kaydolma isteği gönderiliyor...")
            reg_ok, reg_msg = BTKApi.register_course(self.course_id, self.access_token)
            self.log_signal.emit(f"Kayıt işlemi: {reg_msg}")
            time.sleep(2)

        self.log_signal.emit(f"Toplam {total_items} ders indirilecek.")

        for index, item in enumerate(self.selected_items, start=1):
            if self.is_cancelled:
                self.log_signal.emit(
                    "İndirme işlemi kullanıcı tarafından iptal edildi."
                )
                break

            self.overall_progress_signal.emit(index - 1, total_items)
            sec_idx = item["sec_idx"]
            sec_title = sanitize_filename(item["sec_title"])
            les_idx = item["les_idx"]
            les_title = sanitize_filename(item["les_title"])
            les_id = str(item["les_id"])

            self.log_signal.emit(
                f"\n[{index}/{total_items}] Başlatılıyor: B{sec_idx + 1}.D{
                    les_idx + 1
                } - {les_title}"
            )

            save_dir = self.download_dir / (
                f"{sec_idx + 1:02d}_{sec_title}" if self.organize_folders else ""
            )
            save_dir.mkdir(parents=True, exist_ok=True)

            # Retry logic on 404
            video_id, err_msg = BTKApi.start_lesson(
                self.course_id, les_id, self.access_token
            )
            if not video_id and "404" in err_msg:
                self.log_signal.emit(
                    "  ⌛ Ders başlatılamadı, 3 saniye sonra tekrar deneniyor..."
                )
                time.sleep(3)
                video_id, err_msg = BTKApi.start_lesson(
                    self.course_id, les_id, self.access_token
                )

            if not video_id:
                if "404" in err_msg:
                    self.log_signal.emit(
                        f"  ❌ HATA: {
                            err_msg
                        }\n  💡 İPUCU: Kursa kaydolmamış olabilirsiniz. 'Kursa Otomatik Kaydol' seçeneğini aktif edin."
                    )
                else:
                    self.log_signal.emit(f"  ❌ HATA: {err_msg}")
                continue

            v_name, hls_url, v_msg = BTKApi.get_video_url(video_id)
            if not hls_url:
                self.log_signal.emit(f"  ❌ HATA: {v_msg}")
                continue

            file_name = f"{les_idx + 1:02d}_{les_title}.mp4"
            output_file = save_dir / file_name

            if output_file.exists():
                self.log_signal.emit(f"  ℹ️ Dosya zaten var, atlanıyor: {file_name}")
                downloaded_count += 1
                continue

            self.log_signal.emit(f"  ⬇️ İndiriliyor: {file_name}")

            def ytdl_hook(d):
                if self.is_cancelled:
                    raise Exception("İptal Edildi")
                if d["status"] == "downloading":
                    p = (
                        re.sub(r"\x1b\[[0-9;]*m", "", d.get("_percent_str", "0%"))
                        .replace("%", "")
                        .strip()
                    )
                    sp = re.sub(r"\x1b\[[0-9;]*m", "", d.get("_speed_str", "N/A"))
                    eta = re.sub(r"\x1b\[[0-9;]*m", "", d.get("_eta_str", "N/A"))
                    try:
                        pct = float(p)
                    except ValueError:
                        pct = 0.0
                    self.current_progress_signal.emit(pct, sp, eta)
                elif d["status"] == "finished":
                    self.current_progress_signal.emit(100.0, "Tamamlandı", "00:00")

            cinema8_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://cinema8.com/",
                "Origin": "https://cinema8.com",
            }

            ydl_opts = {
                "outtmpl": str(output_file),
                "progress_hooks": [ytdl_hook],
                "http_headers": cinema8_headers,
                "no_color": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([hls_url])
                downloaded_count += 1
                self.log_signal.emit(f"  ✅ Tamamlandı: {file_name}")
            except Exception as e:
                clean_err = re.sub(r"\x1b\[[0-9;]*m", "", str(e))
                if "İptal Edildi" in clean_err:
                    self.log_signal.emit("  ⚠️ İndirme iptal edildi.")
                    break
                self.log_signal.emit(f"  ❌ İndirme hatası: {clean_err}")

            self.overall_progress_signal.emit(index, total_items)

        self.finished_signal.emit(self.is_cancelled, downloaded_count, total_items)


# --- MODERN PYSIDE6 GUI ---


class ModernBTKDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BTK Akademi Kurs İndirici v1.0.0")
        self.resize(1000, 750)
        self.setMinimumSize(850, 600)
        self.showMaximized()

        self.config = ConfigManager.load_config()
        self.syllabus_data = []
        self.download_worker = None
        self.fetch_worker = None
        self._updating_tree_checks = False

        self.init_ui()
        self.apply_stylesheet()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header Title
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        title_label = QLabel("🎓 BTK Akademi Video İndirici")
        title_label.setObjectName("appTitle")
        font = title_label.font()
        font.setPointSize(16)
        font.setBold(True)
        title_label.setFont(font)
        sub_label = QLabel("Modern & Çok İşlevli İndirme Yöneticisi")
        sub_label.setObjectName("appSubTitle")
        header_layout.addWidget(title_label)
        header_layout.addSpacing(10)
        header_layout.addWidget(sub_label)
        header_layout.addStretch()
        main_layout.addWidget(header_frame)

        # Inputs
        input_group = QGroupBox("Giriş Bilgileri ve Bağlantı")
        input_layout = QVBoxLayout(input_group)
        url_row = QHBoxLayout()
        url_label = QLabel("Kurs Linki / ID:")
        url_label.setFixedWidth(100)
        self.url_input = QLineEdit(
            placeholderText="Örn: https://www.btkakademi.gov.tr/kategori/python-dersleri-12345"
        )
        url_row.addWidget(url_label)
        url_row.addWidget(self.url_input)
        input_layout.addLayout(url_row)

        token_row = QHBoxLayout()
        token_label = QLabel("Access Token:")
        token_label.setFixedWidth(100)
        self.token_input = QLineEdit(
            self.config.get("access_token", ""),
            echoMode=QLineEdit.Password,
            placeholderText="Bearer Token...",
        )
        self.toggle_token_btn = QPushButton(
            "Göster", fixedWidth=70, clicked=self.toggle_token_visibility
        )
        self.btn_fetch_syllabus = QPushButton(
            "🔍 Müfredatı Getir",
            objectName="primaryBtn",
            clicked=self.start_fetch_syllabus,
        )
        token_row.addWidget(token_label)
        token_row.addWidget(self.token_input)
        token_row.addWidget(self.toggle_token_btn)
        token_row.addWidget(self.btn_fetch_syllabus)
        input_layout.addLayout(token_row)
        main_layout.addWidget(input_group)

        # Splitter (Tree Left, Settings/Log Right)
        splitter = QSplitter(Qt.Horizontal)
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)

        tree_hdr_row = QHBoxLayout()
        tree_hdr_row.addWidget(
            QLabel("📚 Kurs İçeriği (İndirmek İstediklerinizi Seçin):")
        )
        tree_hdr_row.addStretch()

        self.btn_expand_all = QPushButton(
            "📂 Tümünü Aç", clicked=lambda: self.tree_widget.expandAll()
        )
        self.btn_collapse_all = QPushButton(
            "📁 Tümünü Kapat", clicked=lambda: self.tree_widget.collapseAll()
        )
        self.btn_select_all = QPushButton(
            "☑️ Tümünü Seç", clicked=lambda: self.set_all_checks(True)
        )
        self.btn_deselect_all = QPushButton(
            "🧹 Seçimi Temizle", clicked=lambda: self.set_all_checks(False)
        )

        tree_hdr_row.addWidget(self.btn_expand_all)
        tree_hdr_row.addWidget(self.btn_collapse_all)
        tree_hdr_row.addWidget(self.btn_select_all)
        tree_hdr_row.addWidget(self.btn_deselect_all)
        tree_layout.addLayout(tree_hdr_row)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Bölümler ve Dersler"])
        self.tree_widget.header().setSectionResizeMode(QHeaderView.Stretch)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.tree_widget.itemChanged.connect(self.on_tree_item_changed)
        tree_layout.addWidget(self.tree_widget)
        splitter.addWidget(tree_container)

        # Right Panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        opt_group = QGroupBox("İndirme Ayarları")
        opt_layout = QVBoxLayout(opt_group)
        dir_row = QHBoxLayout()
        dir_label = QLabel("İndirme Yeri:")
        dir_label.setFixedWidth(80)
        self.dir_input = QLineEdit(self.config.get("download_dir", ""))
        self.btn_select_dir = QPushButton("Gözat...", clicked=self.select_download_dir)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self.dir_input)
        dir_row.addWidget(self.btn_select_dir)
        opt_layout.addLayout(dir_row)

        self.chk_folders = QCheckBox(
            "Bölüm Klasörleri Oluştur (Örn: 01_Bölüm/01_Ders.mp4)",
            checked=self.config.get("organize_folders", True),
        )
        self.chk_register = QCheckBox(
            "İndirme Başlamadan Kursa Otomatik Kaydol",
            checked=self.config.get("auto_register", True),
        )
        opt_layout.addWidget(self.chk_folders)
        opt_layout.addWidget(self.chk_register)
        right_layout.addWidget(opt_group)

        right_layout.addWidget(QLabel("📝 Canlı Günlük ve Durum:"))
        self.log_console = QTextEdit(readOnly=True, objectName="logConsole")
        right_layout.addWidget(self.log_console)
        splitter.addWidget(right_panel)

        splitter.setSizes([550, 450])
        main_layout.addWidget(splitter, stretch=1)

        # Progress & Controls
        action_frame = QFrame()
        action_layout = QVBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        prog_row1 = QHBoxLayout()
        prog_row1.addWidget(QLabel("Genel İlerleme:"))
        self.overall_bar = QProgressBar()
        prog_row1.addWidget(self.overall_bar)
        action_layout.addLayout(prog_row1)

        prog_row2 = QHBoxLayout()
        prog_row2.addWidget(QLabel("Mevcut Video:"))
        self.current_bar = QProgressBar()
        self.speed_label = QLabel("Hız: N/A", fixedWidth=120)
        self.eta_label = QLabel("Kalan: N/A", fixedWidth=100)
        prog_row2.addWidget(self.current_bar)
        prog_row2.addWidget(self.speed_label)
        prog_row2.addWidget(self.eta_label)
        action_layout.addLayout(prog_row2)

        btn_row = QHBoxLayout()
        self.btn_start_download = QPushButton(
            "🚀 İndirmeyi Başlat",
            objectName="successBtn",
            fixedHeight=40,
            clicked=self.start_download,
        )
        self.btn_cancel_download = QPushButton(
            "🛑 İptal Et",
            objectName="dangerBtn",
            fixedHeight=40,
            enabled=False,
            clicked=self.cancel_download,
        )
        btn_row.addStretch()
        btn_row.addWidget(self.btn_start_download)
        btn_row.addWidget(self.btn_cancel_download)
        action_layout.addLayout(btn_row)
        main_layout.addWidget(action_frame)

    def toggle_token_visibility(self):
        if self.token_input.echoMode() == QLineEdit.Password:
            self.token_input.setEchoMode(QLineEdit.Normal)
            self.toggle_token_btn.setText("Gizle")
        else:
            self.token_input.setEchoMode(QLineEdit.Password)
            self.toggle_token_btn.setText("Göster")

    def select_download_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "İndirme Klasörü Seçin", self.dir_input.text()
        )
        if d:
            self.dir_input.setText(d)

    def log(self, message: str):
        self.log_console.append(message)
        sb = self.log_console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def save_current_config(self):
        self.config.update(
            {
                "access_token": self.token_input.text().strip(),
                "download_dir": self.dir_input.text().strip(),
                "organize_folders": self.chk_folders.isChecked(),
                "auto_register": self.chk_register.isChecked(),
            }
        )
        ConfigManager.save_config(self.config)

    def start_fetch_syllabus(self):
        raw_input = self.url_input.text().strip()
        token = self.token_input.text().strip()
        if not raw_input:
            return QMessageBox.warning(
                self, "Uyarı", "Lütfen bir kurs URL'si veya Kurs ID giriniz!"
            )

        course_id = extract_course_id(raw_input)
        self.save_current_config()
        self.btn_fetch_syllabus.setEnabled(False)
        self.btn_fetch_syllabus.setText("Yükleniyor...")
        self.log(f"🔄 Kurs ID: {course_id} için müfredat sorgulanıyor...")

        self.fetch_worker = FetchSyllabusWorker(course_id, token)
        self.fetch_worker.finished_signal.connect(self.on_fetch_syllabus_finished)
        self.fetch_worker.start()

    def on_fetch_syllabus_finished(self, success: bool, data: list, message: str):
        self.btn_fetch_syllabus.setEnabled(True)
        self.btn_fetch_syllabus.setText("🔍 Müfredatı Getir")
        if not success:
            self.log(f"❌ {message}")
            QMessageBox.critical(self, "Hata", message)
            return
        self.syllabus_data = data
        self.populate_tree(data)
        self.log(f"✅ Müfredat yüklendi. Toplam bölüm sayısı: {len(data)}")

    def populate_tree(self, syllabus: list):
        self.tree_widget.blockSignals(True)
        self.tree_widget.clear()
        for sec_idx, section in enumerate(syllabus):
            sec_title = section.get("title", f"Bölüm {sec_idx + 1}")
            courses = section.get("courses", [])
            sec_item = QTreeWidgetItem(
                self.tree_widget,
                [f"📁 Bölüm {sec_idx + 1}: {sec_title} ({len(courses)} Ders)"],
            )
            sec_item.setFlags(sec_item.flags() | Qt.ItemIsUserCheckable)
            sec_item.setCheckState(0, Qt.Checked)
            sec_item.setData(0, Qt.UserRole, {"type": "section", "idx": sec_idx})

            for les_idx, lesson in enumerate(courses):
                les_title = lesson.get("title", f"Ders {les_idx + 1}")
                les_id = lesson.get("id", "")
                duration = lesson.get("duration", "")
                disp = f"▶️ {les_idx + 1}. {les_title}" + (
                    f" ({duration})" if duration else ""
                )
                les_item = QTreeWidgetItem(sec_item, [disp])
                les_item.setFlags(les_item.flags() | Qt.ItemIsUserCheckable)
                les_item.setCheckState(0, Qt.Checked)
                les_item.setData(
                    0,
                    Qt.UserRole,
                    {
                        "type": "lesson",
                        "sec_idx": sec_idx,
                        "sec_title": sec_title,
                        "les_idx": les_idx,
                        "les_title": les_title,
                        "les_id": les_id,
                    },
                )
            sec_item.setExpanded(False)
        self.tree_widget.blockSignals(False)

    def on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        if getattr(self, "_updating_tree_checks", False):
            return
        self._updating_tree_checks = True
        try:
            state = item.checkState(column)
            data = item.data(0, Qt.UserRole)
            if data:
                item_type = data.get("type")
                if item_type == "section":
                    if state in (Qt.Checked, Qt.Unchecked):
                        for i in range(item.childCount()):
                            item.child(i).setCheckState(0, state)
                elif item_type == "lesson":
                    parent = item.parent()
                    if parent:
                        cnt = sum(
                            1
                            for i in range(parent.childCount())
                            if parent.child(i).checkState(0) == Qt.Checked
                        )
                        tot = parent.childCount()
                        if cnt == tot:
                            parent.setCheckState(0, Qt.Checked)
                        elif cnt == 0:
                            parent.setCheckState(0, Qt.Unchecked)
                        else:
                            parent.setCheckState(0, Qt.PartiallyChecked)
        finally:
            self._updating_tree_checks = False

    def show_tree_context_menu(self, pos):
        item = self.tree_widget.itemAt(pos)
        menu = QMenu(self)
        if item:
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "lesson":
                menu.addAction(
                    "🎯 Sadece Bu Dersi Seç", lambda: self.select_only_item(item)
                )
            elif data and data.get("type") == "section":
                menu.addAction(
                    "📁 Sadece Bu Bölümü Seç", lambda: self.select_only_section(item)
                )
            menu.addSeparator()
        menu.addAction("📂 Tümünü Aç", self.tree_widget.expandAll)
        menu.addAction("📁 Tümünü Kapat", self.tree_widget.collapseAll)
        menu.addSeparator()
        menu.addAction("☑️ Tümünü Seç", lambda: self.set_all_checks(True))
        menu.addAction("☐ Seçimi Temizle", lambda: self.set_all_checks(False))
        menu.exec(self.tree_widget.viewport().mapToGlobal(pos))

    def select_only_item(self, target_item: QTreeWidgetItem):
        self._updating_tree_checks = True
        try:
            root = self.tree_widget.invisibleRootItem()
            for i in range(root.childCount()):
                sec_item = root.child(i)
                cnt = 0
                for j in range(sec_item.childCount()):
                    les = sec_item.child(j)
                    if les == target_item:
                        les.setCheckState(0, Qt.Checked)
                        cnt += 1
                    else:
                        les.setCheckState(0, Qt.Unchecked)
                if sec_item.childCount() > 0:
                    if cnt == sec_item.childCount():
                        sec_item.setCheckState(0, Qt.Checked)
                    elif cnt > 0:
                        sec_item.setCheckState(0, Qt.PartiallyChecked)
                    else:
                        sec_item.setCheckState(0, Qt.Unchecked)
        finally:
            self._updating_tree_checks = False

    def select_only_section(self, target_section: QTreeWidgetItem):
        self._updating_tree_checks = True
        try:
            root = self.tree_widget.invisibleRootItem()
            for i in range(root.childCount()):
                sec_item = root.child(i)
                st = Qt.Checked if sec_item == target_section else Qt.Unchecked
                sec_item.setCheckState(0, st)
                for j in range(sec_item.childCount()):
                    sec_item.child(j).setCheckState(0, st)
        finally:
            self._updating_tree_checks = False

    def set_all_checks(self, checked: bool):
        self._updating_tree_checks = True
        try:
            st = Qt.Checked if checked else Qt.Unchecked
            root = self.tree_widget.invisibleRootItem()
            for i in range(root.childCount()):
                sec_item = root.child(i)
                sec_item.setCheckState(0, st)
                for j in range(sec_item.childCount()):
                    sec_item.child(j).setCheckState(0, st)
        finally:
            self._updating_tree_checks = False

    def get_selected_lessons(self) -> list[dict]:
        selected = []
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            sec_item = root.child(i)
            for j in range(sec_item.childCount()):
                les_item = sec_item.child(j)
                if les_item.checkState(0) == Qt.Checked:
                    d = les_item.data(0, Qt.UserRole)
                    if d:
                        selected.append(d)
        return selected

    def start_download(self):
        raw_input = self.url_input.text().strip()
        token = self.token_input.text().strip()
        download_dir = self.dir_input.text().strip()

        if not raw_input or not token or not download_dir:
            return QMessageBox.warning(
                self, "Uyarı", "Giriş bilgileri ve indirme yeri boş bırakılamaz!"
            )

        selected_lessons = self.get_selected_lessons()
        if not selected_lessons:
            return QMessageBox.warning(
                self, "Uyarı", "İndirmek için en az 1 ders seçmelisiniz!"
            )

        course_id = extract_course_id(raw_input)
        self.save_current_config()
        self.btn_start_download.setEnabled(False)
        self.btn_cancel_download.setEnabled(True)
        self.btn_fetch_syllabus.setEnabled(False)
        self.overall_bar.setValue(0)
        self.current_bar.setValue(0)

        self.download_worker = DownloadWorker(
            course_id,
            selected_lessons,
            token,
            download_dir,
            self.chk_folders.isChecked(),
            self.chk_register.isChecked(),
        )
        self.download_worker.log_signal.connect(self.log)
        self.download_worker.overall_progress_signal.connect(self.on_overall_progress)
        self.download_worker.current_progress_signal.connect(self.on_current_progress)
        self.download_worker.finished_signal.connect(self.on_download_finished)
        self.download_worker.start()

    def cancel_download(self):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.log("🛑 İptal talebi gönderildi, mevcut işlem tamamlanıyor...")
            self.btn_cancel_download.setEnabled(False)

    def on_overall_progress(self, current: int, total: int):
        if total > 0:
            self.overall_bar.setValue(int((current / total) * 100))

    def on_current_progress(self, percent: float, speed: str, eta: str):
        self.current_bar.setValue(int(percent))
        self.speed_label.setText(f"Hız: {speed}")
        self.eta_label.setText(f"Kalan: {eta}")

    def on_download_finished(
        self, is_cancelled: bool, downloaded_count: int, total_count: int
    ):
        self.btn_start_download.setEnabled(True)
        self.btn_cancel_download.setEnabled(False)
        self.btn_fetch_syllabus.setEnabled(True)
        if is_cancelled:
            self.log("\n⚠️ İndirme işlemi kullanıcı tarafından iptal edildi.")
            QMessageBox.warning(
                self,
                "İptal Edildi",
                "İndirme işlemi kullanıcı tarafından iptal edildi.",
            )
        elif downloaded_count == 0:
            self.log(
                "\n⚠️ Hiçbir ders indirilemedi! Kurs kaydınızı ve Access Token değerinizi kontrol ediniz."
            )
            QMessageBox.warning(
                self,
                "Uyarı",
                "Hiçbir ders indirilemedi!\n\n• BTK Akademi üzerinde bu kursa kayıtlı olduğunuzdan emin olun.\n• Access Token süreniz dolmuş olabilir.",
            )
        else:
            self.log(
                f"\n🎉 İndirme işlemi tamamlandı! ({downloaded_count}/{
                    total_count
                } ders indirildi)"
            )
            QMessageBox.information(
                self,
                "Başarılı",
                f"İndirme işlemi tamamlandı!\n({downloaded_count}/{
                    total_count
                } ders indirildi)",
            )

    def apply_stylesheet(self):
        qss = """
        QMainWindow { background-color: #1e1e2e; color: #cdd6f4; }
        QWidget { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; color: #cdd6f4; }
        #headerFrame { background-color: #24273a; border-radius: 8px; border: 1px solid #363a4f; }
        #appTitle { color: #89b4fa; }
        #appSubTitle { color: #a6adc8; font-size: 11px; }
        QGroupBox { font-weight: bold; border: 1px solid #363a4f; border-radius: 8px; margin-top: 10px; padding-top: 12px; background-color: #24273a; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 12px; padding: 0 4px; color: #89b4fa; }
        QLineEdit { background-color: #181825; border: 1px solid #45475a; border-radius: 6px; padding: 6px 10px; color: #cdd6f4; }
        QLineEdit:focus { border: 1px solid #89b4fa; }
        QPushButton { background-color: #313244; border: 1px solid #45475a; border-radius: 6px; padding: 6px 14px; color: #cdd6f4; font-weight: 500; }
        QPushButton:hover { background-color: #45475a; }
        QPushButton:pressed { background-color: #585b70; }
        QPushButton:disabled { background-color: #181825; color: #6c7086; border-color: #313244; }
        #primaryBtn { background-color: #89b4fa; color: #11111b; font-weight: bold; border: none; }
        #primaryBtn:hover { background-color: #b4befe; }
        #successBtn { background-color: #a6e3a1; color: #11111b; font-weight: bold; border: none; font-size: 14px; }
        #successBtn:hover { background-color: #94e2d5; }
        #dangerBtn { background-color: #f38ba8; color: #11111b; font-weight: bold; border: none; font-size: 14px; }
        #dangerBtn:hover { background-color: #eba0ac; }
        QTreeWidget { background-color: #181825; border: 1px solid #363a4f; border-radius: 8px; padding: 4px; }
        QTreeWidget::item { padding: 4px; border-radius: 4px; }
        QTreeWidget::item:hover { background-color: #313244; }
        QTreeWidget::item:selected { background-color: #45475a; color: #cdd6f4; }
        QHeaderView::section { background-color: #24273a; color: #89b4fa; padding: 6px; font-weight: bold; border: none; border-bottom: 1px solid #363a4f; }
        #logConsole { background-color: #11111b; border: 1px solid #363a4f; border-radius: 8px; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; color: #a6e3a1; }
        QProgressBar { border: 1px solid #363a4f; border-radius: 6px; text-align: center; background-color: #181825; color: #cdd6f4; height: 18px; }
        QProgressBar::chunk { background-color: #89b4fa; border-radius: 5px; }
        QCheckBox { color: #cdd6f4; spacing: 8px; }
        QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #45475a; background-color: #181825; }
        QCheckBox::indicator:checked { background-color: #89b4fa; border-color: #89b4fa; }
        """
        self.setStyleSheet(qss)


def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    window = ModernBTKDownloader()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
