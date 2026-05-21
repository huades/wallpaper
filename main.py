import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import ssl
import sys
import tempfile
import threading
import time
import tkinter as tk
from queue import Empty, Queue
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

try:
    import winreg
except ImportError:
    winreg = None


SPI_SETDESKWALLPAPER = 20
SPI_GETDESKWALLPAPER = 0x0073
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "TinyWallpaperChanger"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
SLIDESHOW_PID_FILE = ".slideshow.pid"
SLIDESHOW_STOP_FILE = ".slideshow.stop"
SLIDESHOW_STATE_FILE = ".slideshow_state.json"
SLIDESHOW_LOG_FILE = "slideshow.log"
DOWNLOAD_HISTORY_FILE = "download_history.json"
PREFETCH_DIR = "prefetch"
PREFETCH_STATE_FILE = "prefetch_state.json"
SETTINGS_FILE = "settings.json"
MIN_CACHE_LIMIT_MB = 10
MAX_CACHE_LIMIT_MB = 1024
DEFAULT_CACHE_LIMIT_MB = 100
MAX_LOG_BYTES = 1024 * 1024
DOWNLOAD_HISTORY_MAX_ITEMS = 5000
DOWNLOAD_HISTORY_RETENTION_DAYS = 180
MIN_UNPREVIEWED_PER_CATEGORY = 3


CATEGORIES = {
    "随机": {"q": "", "categories": "100"},
    "自然风光": {"q": "nature landscape", "categories": "100"},
    "城市建筑": {"q": "city architecture", "categories": "100"},
    "动物": {"q": "animals wildlife", "categories": "100"},
    "极简": {"q": "minimalism", "categories": "100"},
    "科技": {"q": "technology futuristic", "categories": "100"},
    "汽车": {"q": "cars", "categories": "100"},
    "动漫": {"q": "anime", "categories": "010"},
    "人物": {"q": "portrait people", "categories": "001"},
}

SLIDESHOW_INTERVALS = {
    "10秒": 10,
    "20秒": 20,
    "30秒": 30,
    "45秒": 45,
    "1分钟": 60,
    "3分钟": 180,
    "5分钟": 300,
    "10分钟": 600,
}


class WallpaperChangerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Wallpaper")
        self.root.geometry("320x170")
        self.root.resizable(False, False)
        self.window_alpha = 0.7
        self.root.attributes("-alpha", self.window_alpha)
        self.root.configure(bg="#20252B")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.base_dir = Path(__file__).resolve().parent
        self.favorites_dir = self.base_dir / "favorites"
        self.prefetch_dir = self.base_dir / PREFETCH_DIR
        self.slideshow_pid_file = self.base_dir / SLIDESHOW_PID_FILE
        self.slideshow_stop_file = self.base_dir / SLIDESHOW_STOP_FILE
        self.slideshow_state_file = self.base_dir / SLIDESHOW_STATE_FILE
        self.download_history_file = self.base_dir / DOWNLOAD_HISTORY_FILE
        self.prefetch_state_file = self.base_dir / PREFETCH_STATE_FILE
        self.settings_file = self.base_dir / SETTINGS_FILE
        self.favorites_dir.mkdir(exist_ok=True)
        self.prefetch_dir.mkdir(exist_ok=True)
        self.trim_runtime_files()
        self.sync_download_history()
        self.sync_prefetch_state()

        self.current_file: Optional[Path] = None
        self.favorited_files: set[Path] = set()
        self.session_previewed_files: set[Path] = set()
        self.history: list[Path] = []
        self.history_index = -1
        self.slideshow_running = self.is_slideshow_running()
        self.slideshow_index = -1
        self.slideshow_restart_job: Optional[str] = None
        self.state_lock = threading.Lock()
        self.status_queue: Queue[str] = Queue()
        self.stop_prefetch_event = threading.Event()
        settings = self.load_settings()
        initial_category = str(settings.get("last_category", "随机"))
        if initial_category not in CATEGORIES:
            initial_category = "随机"
        self.prefetch_category = initial_category

        self.category_var = tk.StringVar(value=initial_category)
        self.interval_var = tk.StringVar(value="10秒")
        self.cache_size_var = tk.StringVar(value=str(settings["cache_limit_mb"]))
        self.autostart_var = tk.BooleanVar(value=self.is_autostart_enabled())
        self.status_var = tk.StringVar(value="选择分类后点击 ▶")
        if self.slideshow_running:
            self.restore_slideshow_position()

        self.build_ui()
        self.refresh_nav_buttons()
        self.refresh_button_colors()
        self.start_prefetch_worker()
        self.poll_status_queue()

    def build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground="#F5F7FA",
            background="#F5F7FA",
            foreground="#1B2026",
            arrowcolor="#1B2026",
            padding=3,
        )

        shell = tk.Frame(self.root, bg="#20252B")
        shell.place(x=8, y=5, width=304, height=120)

        title = tk.Label(
            shell,
            text="Wallpaper Changer",
            bg="#20252B",
            fg="#F5F7FA",
            font=("Segoe UI", 11, "bold"),
        )
        title.pack(anchor="w")

        selector_frame = tk.Frame(shell, bg="#20252B")
        selector_frame.pack(fill="x", pady=(3, 3))

        category_label = tk.Label(
            selector_frame,
            text="分类:",
            bg="#20252B",
            fg="#C8D1DB",
            font=("Microsoft YaHei UI", 8),
        )
        category_label.grid(row=0, column=0, sticky="w", padx=(0, 4))

        interval_label = tk.Label(
            selector_frame,
            text="轮播:",
            bg="#20252B",
            fg="#C8D1DB",
            font=("Microsoft YaHei UI", 8),
        )
        interval_label.grid(row=0, column=2, sticky="w", padx=(8, 4))

        self.category_box = ttk.Combobox(
            selector_frame,
            textvariable=self.category_var,
            values=list(CATEGORIES.keys()),
            width=8,
            state="readonly",
            font=("Microsoft YaHei UI", 8),
            style="Dark.TCombobox",
        )
        self.category_box.grid(row=0, column=1, sticky="w")
        self.category_box.bind("<<ComboboxSelected>>", self.on_category_changed)

        self.interval_box = ttk.Combobox(
            selector_frame,
            textvariable=self.interval_var,
            values=list(SLIDESHOW_INTERVALS.keys()),
            width=6,
            state="readonly",
            font=("Microsoft YaHei UI", 8),
            style="Dark.TCombobox",
        )
        self.interval_box.grid(row=0, column=3, sticky="w")
        self.interval_box.bind("<<ComboboxSelected>>", self.on_interval_changed)

        selector_frame.columnconfigure(4, weight=1)

        button_frame = tk.Frame(shell, bg="#20252B")
        button_frame.pack(fill="x", pady=(0, 3))

        btn_style = {
            "font": ("Segoe UI Emoji", 10),
            "width": 2,
            "height": 1,
            "bg": "#2F3843",
            "fg": "#F5F7FA",
            "activebackground": "#3E4A57",
            "activeforeground": "#FFFFFF",
            "bd": 0,
            "cursor": "hand2",
        }

        self.prev_btn = tk.Button(
            button_frame,
            text="◀",
            command=self.previous_wallpaper,
            **btn_style,
        )
        self.prev_btn.grid(row=0, column=0, padx=2, pady=(1, 0))
        self.add_button_label(button_frame, "上一张", 1, 0)

        self.next_btn = tk.Button(
            button_frame,
            text="▶",
            command=self.next_wallpaper,
            **btn_style,
        )
        self.next_btn.grid(row=0, column=1, padx=2, pady=(1, 0))
        self.add_button_label(button_frame, "下一张", 1, 1)

        self.favorite_btn = tk.Button(
            button_frame,
            text="❤",
            command=self.favorite_current,
            **btn_style,
        )
        self.favorite_btn.grid(row=0, column=2, padx=2, pady=(1, 0))
        self.add_button_label(button_frame, "收藏/取消", 1, 2)

        self.autostart_btn = tk.Button(
            button_frame,
            text="🚀",
            command=self.toggle_autostart,
            **btn_style,
        )
        self.autostart_btn.grid(row=0, column=4, padx=2, pady=(1, 0))
        self.add_button_label(button_frame, "开机启动", 1, 4)

        self.close_btn = tk.Button(
            button_frame,
            text="✖",
            command=self.clear_previewed_cache,
            **btn_style,
        )
        self.close_btn.grid(row=0, column=5, padx=2, pady=(1, 0))
        self.add_button_label(button_frame, "清已浏览", 1, 5)

        self.settings_btn = tk.Button(
            button_frame,
            text="⚙",
            command=self.open_settings,
            **btn_style,
        )
        self.settings_btn.grid(row=0, column=6, padx=2, pady=(1, 0))
        self.add_button_label(button_frame, "设置", 1, 6)

        self.slideshow_btn = tk.Button(
            button_frame,
            text="🎞",
            command=self.toggle_slideshow,
            **btn_style,
        )
        self.slideshow_btn.grid(row=0, column=3, padx=2, pady=(1, 0))
        self.add_button_label(button_frame, "收藏轮播", 1, 3)

        for col in range(7):
            button_frame.columnconfigure(col, weight=1)

        status_box = tk.Frame(self.root, bg="#171B20", height=40)
        status_box.place(x=8, y=122, width=304, height=40)
        status_box.pack_propagate(False)

        status = tk.Label(
            status_box,
            textvariable=self.status_var,
            bg="#171B20",
            fg="#C8D1DB",
            wraplength=292,
            justify="left",
            anchor="nw",
            font=("Microsoft YaHei UI", 8),
        )
        status.pack(anchor="nw", fill="both", expand=True, padx=6, pady=3)

    @staticmethod
    def add_button_label(parent: tk.Frame, text: str, row: int, column: int) -> None:
        label = tk.Label(
            parent,
            text=text,
            bg="#20252B",
            fg="#AEB8C4",
            font=("Microsoft YaHei UI", 6),
        )
        label.grid(row=row, column=column, padx=1, pady=(0, 0))

    def next_wallpaper(self) -> None:
        if self.is_slideshow_mode():
            self.step_favorite_wallpaper(1)
            return

        category_name = self.category_var.get()
        file_path = self.consume_prefetch_image(category_name)
        if file_path is None:
            self.status_var.set("缓存为空\n正在后台补图")
            return

        try:
            self.set_wallpaper_with_fade(file_path)
            self.current_file = file_path
            self.session_previewed_files.add(file_path.resolve())
            self.push_history(file_path)
            self.status_var.set(f"已预览：{category_name}\n{file_path.name}")
        except Exception as exc:
            self.status_var.set("切换失败")
            messagebox.showerror("错误", f"处理失败：{exc}")
        finally:
            self.refresh_nav_buttons()
            self.refresh_button_colors()

    def previous_wallpaper(self) -> None:
        if self.is_slideshow_mode():
            self.step_favorite_wallpaper(-1)
            return

        if self.history_index <= 0:
            self.status_var.set("没有上一张")
            return

        self.history_index -= 1
        file_path = self.history[self.history_index]
        if not file_path.exists():
            self.status_var.set("上一张图片已不存在")
            self.refresh_nav_buttons()
            return

        try:
            self.set_wallpaper_with_fade(file_path)
            self.current_file = file_path
            self.status_var.set(f"上一张\n{file_path.name}")
        except Exception as exc:
            messagebox.showerror("错误", f"切换上一张失败：{exc}")
        finally:
            self.refresh_nav_buttons()
            self.refresh_button_colors()

    def favorite_current(self) -> None:
        if self.is_slideshow_mode() and (
            not self.current_file or not self.current_file.exists()
        ):
            if not self.pick_favorite_wallpaper(0, show_message=False):
                self.status_var.set("收藏夹还没有壁纸")
                return

        if not self.current_file or not self.current_file.exists():
            self.status_var.set("当前没有可收藏图片")
            return

        try:
            target = self.favorites_dir / self.current_file.name
            if self.is_current_favorited():
                self.unfavorite_current()
                return

            shutil.copy2(self.current_file, target)
            self.favorited_files.add(self.current_file.resolve())
            self.update_prefetch_item(self.current_file, is_favorite=True)
            self.status_var.set(f"已收藏\n{target.name}")
            self.refresh_button_colors()
        except Exception as exc:
            messagebox.showerror("错误", f"收藏失败：{exc}")

    def unfavorite_current(self) -> None:
        if not self.current_file:
            return

        was_slideshow = self.is_slideshow_mode()
        old_favorites = self.favorite_files() if was_slideshow else []
        old_index = self.favorite_index(old_favorites) if old_favorites else None
        targets = {self.favorites_dir / self.current_file.name}
        if self.is_path_under(self.current_file, self.favorites_dir):
            targets.add(self.current_file)

        removed = False
        for target in targets:
            if not self.is_path_under(target, self.favorites_dir):
                continue
            try:
                if target.exists():
                    target.unlink()
                    removed = True
            except Exception as exc:
                messagebox.showerror("错误", f"取消收藏失败：{exc}")
                return

        self.favorited_files.discard(self.current_file.resolve())
        self.update_prefetch_item(self.current_file, is_favorite=False)
        if was_slideshow and removed:
            self.switch_after_unfavorite(old_index)
            return
        self.status_var.set("已取消收藏" if removed else "当前图片未收藏")
        self.refresh_button_colors()

    def switch_after_unfavorite(self, old_index: Optional[int]) -> None:
        favorites = self.favorite_files()
        if not favorites:
            self.current_file = None
            self.slideshow_index = -1
            self.clear_slideshow_state()
            self.stop_slideshow(update_status=False)
            self.status_var.set("已取消收藏\n收藏夹已空")
            self.refresh_nav_buttons()
            self.refresh_button_colors()
            return

        next_index = old_index if old_index is not None else self.slideshow_index
        next_index = max(0, next_index) % len(favorites)
        file_path = favorites[next_index]
        try:
            self.set_wallpaper_with_fade(file_path)
            self.current_file = file_path
            self.slideshow_index = next_index
            self.save_slideshow_state(file_path, next_index)
            self.status_var.set(f"已取消收藏\n切到 {file_path.name}")
            self.reset_slideshow_timer()
        except Exception as exc:
            messagebox.showerror("错误", f"切换下一张收藏失败：{exc}")
        finally:
            self.refresh_nav_buttons()
            self.refresh_button_colors()

    def toggle_autostart(self) -> None:
        try:
            if self.is_autostart_enabled():
                self.disable_autostart()
                self.autostart_var.set(False)
                self.status_var.set("已关闭开机自动启动")
            else:
                self.enable_autostart()
                self.autostart_var.set(True)
                self.status_var.set("已开启开机自动启动")
            self.refresh_button_colors()
        except Exception as exc:
            messagebox.showerror("错误", f"设置开机启动失败：{exc}")

    def on_close(self) -> None:
        self.stop_prefetch_event.set()
        self.cleanup_unfavorited()
        self.root.destroy()

    def clear_previewed_cache(self) -> None:
        removed = self.cleanup_unfavorited()
        if self.current_file and not self.current_file.exists():
            self.current_file = None
        self.status_var.set(f"已清理浏览缓存\n删除 {removed} 张")
        self.refresh_button_colors()

    def cleanup_unfavorited(self) -> int:
        removed_count = 0
        favorite_names = {
            path.name
            for path in self.favorites_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS
        }

        for file_path in list(self.session_previewed_files):
            if not self.is_path_under(file_path, self.prefetch_dir):
                self.session_previewed_files.discard(file_path)
                continue
            if file_path.name in favorite_names or file_path in self.favorited_files:
                continue
            try:
                if file_path.exists():
                    file_path.unlink()
                    self.remove_prefetch_item(file_path)
                    removed_count += 1
                self.session_previewed_files.discard(file_path)
            except Exception:
                pass
        return removed_count

    @staticmethod
    def is_path_under(path: Path, parent: Path) -> bool:
        try:
            path.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            return False

    def push_history(self, file_path: Path) -> None:
        if self.history_index < len(self.history) - 1:
            self.history = self.history[: self.history_index + 1]
        self.history.append(file_path)
        self.history_index = len(self.history) - 1

    def step_favorite_wallpaper(self, direction: int) -> None:
        if self.pick_favorite_wallpaper(direction, show_message=True):
            self.reset_slideshow_timer()
        else:
            self.status_var.set("收藏夹还没有壁纸")

    def pick_favorite_wallpaper(self, direction: int, show_message: bool) -> bool:
        favorites = self.favorite_files()
        if not favorites:
            return False

        current_index = self.favorite_index(favorites)
        if current_index is None:
            next_index = 0
        else:
            next_index = (current_index + direction) % len(favorites)

        file_path = favorites[next_index]
        try:
            self.set_wallpaper_with_fade(file_path)
            self.current_file = file_path
            self.slideshow_index = next_index
            self.save_slideshow_state(file_path, next_index)
            if show_message:
                action = "收藏下一张" if direction >= 0 else "收藏上一张"
                self.status_var.set(f"{action}\n{file_path.name}")
            return True
        except Exception as exc:
            messagebox.showerror("错误", f"切换收藏壁纸失败：{exc}")
            return False

    def favorite_index(self, favorites: list[Path]) -> Optional[int]:
        if self.current_file:
            current = self.current_file.resolve()
            for index, path in enumerate(favorites):
                if path.resolve() == current or path.name == self.current_file.name:
                    return index

        if 0 <= self.slideshow_index < len(favorites):
            return self.slideshow_index

        return None

    def restore_slideshow_position(self) -> None:
        favorites = self.favorite_files()
        if not favorites:
            return

        state_name = ""
        try:
            data = json.loads(self.slideshow_state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("file_name"), str):
                state_name = data["file_name"]
        except (OSError, json.JSONDecodeError):
            state_name = ""

        desktop_path = self.current_desktop_wallpaper()
        for source_name, source_path in ((state_name, None), ("", desktop_path)):
            for index, path in enumerate(favorites):
                if source_name and path.name == source_name:
                    self.current_file = path
                    self.slideshow_index = index
                    self.save_slideshow_state(path, index)
                    return
                if source_path and self.same_file_or_name(path, source_path):
                    self.current_file = path
                    self.slideshow_index = index
                    self.save_slideshow_state(path, index)
                    return

    def save_slideshow_state(self, file_path: Path, index: int) -> None:
        write_slideshow_state(self.base_dir, file_path, index)

    def clear_slideshow_state(self) -> None:
        self.slideshow_state_file.unlink(missing_ok=True)

    @staticmethod
    def same_file_or_name(left: Path, right: Path) -> bool:
        try:
            if left.resolve() == right.resolve():
                return True
        except OSError:
            pass
        return left.name == right.name

    @staticmethod
    def current_desktop_wallpaper() -> Optional[Path]:
        if os.name != "nt":
            return None
        buffer = ctypes.create_unicode_buffer(1024)
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETDESKWALLPAPER,
            len(buffer),
            buffer,
            0,
        )
        if not result or not buffer.value:
            return None
        return Path(buffer.value)

    def refresh_nav_buttons(self) -> None:
        if self.is_slideshow_mode():
            state = "normal" if self.favorite_files() else "disabled"
            self.prev_btn.config(state=state)
            return

        state = "normal" if self.history_index > 0 else "disabled"
        self.prev_btn.config(state=state)

    def refresh_button_colors(self) -> None:
        normal_bg = "#2F3843"
        self.favorite_btn.config(
            bg="#C92A2A" if self.is_current_favorited() else normal_bg,
            activebackground="#E03131" if self.is_current_favorited() else "#3E4A57",
            fg="#FFFFFF",
        )
        self.autostart_btn.config(
            bg="#F08C00" if self.autostart_var.get() else normal_bg,
            activebackground="#FFD43B" if self.autostart_var.get() else "#3E4A57",
            fg="#101418" if self.autostart_var.get() else "#F5F7FA",
        )
        self.slideshow_btn.config(
            bg="#2F9E44" if self.slideshow_running else normal_bg,
            activebackground="#51CF66" if self.slideshow_running else "#3E4A57",
            fg="#FFFFFF",
        )

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.next_btn.config(state=state)
        self.settings_btn.config(state=state)
        self.category_box.config(state="disabled" if busy else "readonly")
        self.interval_box.config(state="disabled" if busy else "readonly")

    def is_current_favorited(self) -> bool:
        if not self.current_file:
            return False
        favorite_copy = self.favorites_dir / self.current_file.name
        return (
            self.current_file.resolve() in self.favorited_files
            or favorite_copy.exists()
            or self.current_file.parent == self.favorites_dir
        )

    def on_interval_changed(self, _event: object = None) -> None:
        if self.is_slideshow_mode():
            self.restart_slideshow()
            self.status_var.set(f"轮播时间已改为：{self.interval_var.get()}")

    def toggle_slideshow(self) -> None:
        if self.is_slideshow_mode():
            self.slideshow_running = False
            self.refresh_button_colors()
            self.root.update_idletasks()
            self.stop_slideshow(update_status=True)
        else:
            self.slideshow_running = True
            self.refresh_button_colors()
            self.root.update_idletasks()
            self.start_slideshow()

    def start_slideshow(self, reset_current: bool = True) -> None:
        self.slideshow_restart_job = None
        favorites = self.favorite_files()
        if not favorites:
            self.slideshow_running = False
            self.refresh_button_colors()
            self.status_var.set("收藏夹还没有壁纸")
            return

        self.slideshow_stop_file.unlink(missing_ok=True)
        log_file = self.base_dir / SLIDESHOW_LOG_FILE
        runner = self.background_python()
        interval = str(SLIDESHOW_INTERVALS.get(self.interval_var.get(), 300))
        log_handle = open(log_file, "a", encoding="utf-8")
        kwargs = {
            "cwd": str(self.base_dir),
            "stdout": subprocess.DEVNULL,
            "stderr": log_handle,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

        command = [str(runner), str(Path(__file__).resolve()), "--slideshow-daemon", interval]
        continue_from: Optional[str] = None
        if not reset_current and self.current_file:
            for index, path in enumerate(favorites):
                if path.name == self.current_file.name:
                    continue_from = path.name
                    self.slideshow_index = index
                    break
        if continue_from:
            command.extend(["--continue-from", continue_from])

        try:
            subprocess.Popen(
                command,
                **kwargs,
            )
        finally:
            log_handle.close()
        self.slideshow_running = True
        if reset_current:
            self.current_file = favorites[0]
            self.slideshow_index = 0
            self.save_slideshow_state(self.current_file, self.slideshow_index)
        self.status_var.set(f"后台轮播已开启：{self.interval_var.get()}")
        self.refresh_nav_buttons()
        self.refresh_button_colors()

    def stop_slideshow(self, update_status: bool) -> None:
        self.cancel_slideshow_restart()
        self.slideshow_stop_file.write_text("stop", encoding="utf-8")
        self.slideshow_running = False
        if update_status:
            self.status_var.set("已停止收藏轮播")
        self.refresh_button_colors()

    def restart_slideshow(self) -> None:
        if not self.is_slideshow_mode():
            return
        self.cancel_slideshow_restart()
        self.slideshow_stop_file.write_text("stop", encoding="utf-8")
        self.slideshow_running = True
        self.refresh_button_colors()
        self.slideshow_restart_job = self.root.after(
            1500,
            lambda: self.start_slideshow(reset_current=False),
        )

    def reset_slideshow_timer(self) -> None:
        if not self.is_slideshow_mode():
            return
        self.cancel_slideshow_restart()
        self.slideshow_stop_file.write_text("stop", encoding="utf-8")
        self.slideshow_running = True
        self.refresh_button_colors()
        self.slideshow_restart_job = self.root.after(
            1200,
            lambda: self.start_slideshow(reset_current=False),
        )

    def is_slideshow_running(self) -> bool:
        return self.slideshow_pid_file.exists() and not self.slideshow_stop_file.exists()

    def is_slideshow_mode(self) -> bool:
        return self.slideshow_running or self.is_slideshow_running()

    def cancel_slideshow_restart(self) -> None:
        if self.slideshow_restart_job is None:
            return
        try:
            self.root.after_cancel(self.slideshow_restart_job)
        except tk.TclError:
            pass
        self.slideshow_restart_job = None

    def favorite_files(self) -> list[Path]:
        return favorite_files_in(self.favorites_dir)

    def on_category_changed(self, _event: object = None) -> None:
        category = self.category_var.get()
        with self.state_lock:
            self.prefetch_category = category
        settings = self.load_settings()
        settings["last_category"] = category
        self.save_settings(settings)
        removed = self.clear_other_categories_previewed_unfavorite(category)
        self.status_var.set(f"正在补图\n{self.prefetch_status_text()}")
        if removed:
            self.status_var.set(f"已切换分类\n清理 {removed} 张")

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("设置")
        dialog.geometry("230x125")
        dialog.resizable(False, False)
        dialog.configure(bg="#20252B")
        dialog.transient(self.root)
        dialog.grab_set()

        label = tk.Label(
            dialog,
            text="缓存大小 MB (10-1024)",
            bg="#20252B",
            fg="#C8D1DB",
            font=("Microsoft YaHei UI", 9),
        )
        label.pack(anchor="w", padx=12, pady=(10, 4))

        size_entry = tk.Entry(
            dialog,
            textvariable=self.cache_size_var,
            width=10,
            font=("Microsoft YaHei UI", 9),
            bg="#F5F7FA",
            fg="#1B2026",
            bd=0,
        )
        size_entry.pack(anchor="w", padx=12)

        def save_and_close() -> None:
            try:
                value = int(self.cache_size_var.get().strip())
            except ValueError:
                messagebox.showerror("错误", "缓存大小请输入数字")
                return
            if not MIN_CACHE_LIMIT_MB <= value <= MAX_CACHE_LIMIT_MB:
                messagebox.showerror("错误", "缓存大小范围是 10-1024 MB")
                return
            self.cache_size_var.set(str(value))
            settings = self.load_settings()
            settings["cache_limit_mb"] = value
            self.save_settings(settings)
            self.enforce_cache_limit()
            self.status_var.set(f"缓存上限：{value}MB\n{self.prefetch_status_text()}")
            dialog.destroy()

        def open_prefetch_folder() -> None:
            self.prefetch_dir.mkdir(exist_ok=True)
            os.startfile(str(self.prefetch_dir))

        action_frame = tk.Frame(dialog, bg="#20252B")
        action_frame.pack(anchor="e", padx=12, pady=(8, 0))

        folder_btn = tk.Button(
            action_frame,
            text="打开文件夹",
            command=open_prefetch_folder,
            bg="#2F3843",
            fg="#F5F7FA",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        folder_btn.grid(row=0, column=0, padx=(0, 8))

        close_btn = tk.Button(
            action_frame,
            text="关闭",
            command=dialog.destroy,
            bg="#2F3843",
            fg="#F5F7FA",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        close_btn.grid(row=0, column=1, padx=(0, 8))

        ok_btn = tk.Button(
            action_frame,
            text="确定",
            command=save_and_close,
            bg="#2F3843",
            fg="#F5F7FA",
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        ok_btn.grid(row=0, column=2)
        self.center_child_window(dialog, 230, 125)

    def load_settings(self) -> dict[str, object]:
        default: dict[str, object] = {
            "cache_limit_mb": DEFAULT_CACHE_LIMIT_MB,
            "last_category": "随机",
        }
        if not self.settings_file.exists():
            self.save_settings(default)
            return default
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.save_settings(default)
            return default
        try:
            limit = int(data.get("cache_limit_mb", DEFAULT_CACHE_LIMIT_MB))
        except (TypeError, ValueError):
            limit = DEFAULT_CACHE_LIMIT_MB
        if not MIN_CACHE_LIMIT_MB <= limit <= MAX_CACHE_LIMIT_MB:
            limit = DEFAULT_CACHE_LIMIT_MB
        last_category = str(data.get("last_category", "随机"))
        if last_category not in CATEGORIES:
            last_category = "随机"
        return {"cache_limit_mb": int(limit), "last_category": last_category}

    def save_settings(self, data: dict[str, object]) -> None:
        current = {
            "cache_limit_mb": int(data.get("cache_limit_mb", DEFAULT_CACHE_LIMIT_MB)),
            "last_category": str(data.get("last_category", "随机")),
        }
        if current["last_category"] not in CATEGORIES:
            current["last_category"] = "随机"
        self.settings_file.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def cache_limit_bytes(self) -> int:
        return int(self.load_settings()["cache_limit_mb"]) * 1024 * 1024

    def center_child_window(self, dialog: tk.Toplevel, width: int, height: int) -> None:
        self.root.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        x = root_x + max(0, (root_w - width) // 2)
        y = root_y + max(0, (root_h - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def start_prefetch_worker(self) -> None:
        worker = threading.Thread(target=self.prefetch_loop, daemon=True)
        worker.start()

    def prefetch_loop(self) -> None:
        while not self.stop_prefetch_event.is_set():
            try:
                self.enforce_cache_limit()
                if self.prefetch_total_size() < self.cache_limit_bytes():
                    category = self.next_prefetch_category()
                    if self.create_prefetch_image(category):
                        self.status_queue.put(self.prefetch_status_text())
                    else:
                        time.sleep(2)
                else:
                    with self.state_lock:
                        category = self.prefetch_category
                    if not self.has_unpreviewed_prefetch(category):
                        if self.evict_for_category_refill(category):
                            continue
                    time.sleep(2)
            except Exception as exc:
                self.status_queue.put(f"补图失败\n{exc}")
                time.sleep(5)

    def poll_status_queue(self) -> None:
        try:
            while True:
                message = self.status_queue.get_nowait()
                self.status_var.set(message)
        except Empty:
            pass
        if not self.stop_prefetch_event.is_set():
            self.root.after(800, self.poll_status_queue)

    def prefetch_status_text(self) -> str:
        used_mb = self.prefetch_total_size() / 1024 / 1024
        limit_mb = int(self.load_settings()["cache_limit_mb"])
        return f"缓存 {used_mb:.0f}MB/{limit_mb}MB"

    def next_prefetch_category(self) -> str:
        counts = self.unpreviewed_counts_by_category()
        for category in CATEGORIES:
            if counts.get(self.safe_category_name(category), 0) < MIN_UNPREVIEWED_PER_CATEGORY:
                return category
        with self.state_lock:
            return self.prefetch_category

    def unpreviewed_counts_by_category(self) -> dict[str, int]:
        state = self.load_prefetch_state()
        counts = {self.safe_category_name(category): 0 for category in CATEGORIES}
        for item in state["items"]:
            path = Path(str(item.get("path", "")))
            category = str(item.get("category", ""))
            if not item.get("is_previewed") and path.exists():
                counts[category] = counts.get(category, 0) + 1
        return counts

    def safe_category_name(self, category_name: str) -> str:
        return category_name.replace("/", "_").replace("\\", "_")

    def category_prefetch_dir(self, category_name: str) -> Path:
        folder = self.prefetch_dir / self.safe_category_name(category_name)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def load_prefetch_state(self) -> dict[str, list[dict[str, object]]]:
        if not self.prefetch_state_file.exists():
            return {"items": []}
        try:
            data = json.loads(self.prefetch_state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"items": []}
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return {"items": []}
        return data

    def save_prefetch_state(self, state: dict[str, list[dict[str, object]]]) -> None:
        self.prefetch_state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def sync_prefetch_state(self) -> None:
        state = self.load_prefetch_state()
        items = [
            item
            for item in state["items"]
            if Path(str(item.get("path", ""))).exists()
        ]
        known = {str(Path(str(item.get("path", ""))).resolve()) for item in items}
        for path in self.prefetch_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            resolved = str(path.resolve())
            if resolved in known:
                continue
            try:
                image_hash = self.file_hash(path)
                size = path.stat().st_size
            except OSError:
                continue
            items.append(
                {
                    "category": path.parent.name,
                    "path": resolved,
                    "hash": image_hash,
                    "size": size,
                    "is_previewed": False,
                    "is_favorite": False,
                    "downloaded_at": path.stat().st_mtime,
                }
            )
        self.save_prefetch_state({"items": items})

    def update_prefetch_item(self, file_path: Path, **updates: object) -> None:
        with self.state_lock:
            state = self.load_prefetch_state()
            target = str(file_path.resolve())
            for item in state["items"]:
                if str(Path(str(item.get("path", ""))).resolve()) == target:
                    item.update(updates)
                    break
            self.save_prefetch_state(state)

    def remove_prefetch_item(self, file_path: Path) -> None:
        with self.state_lock:
            state = self.load_prefetch_state()
            target = str(file_path.resolve())
            state["items"] = [
                item
                for item in state["items"]
                if str(Path(str(item.get("path", ""))).resolve()) != target
            ]
            self.save_prefetch_state(state)

    def consume_prefetch_image(self, category_name: str) -> Optional[Path]:
        with self.state_lock:
            state = self.load_prefetch_state()
            candidates = []
            for item in state["items"]:
                path = Path(str(item.get("path", "")))
                if (
                    item.get("category") == self.safe_category_name(category_name)
                    and not item.get("is_previewed")
                    and path.exists()
                ):
                    candidates.append(item)
            if not candidates:
                return None
            selected = sorted(candidates, key=lambda item: float(item.get("downloaded_at", 0)))[0]
            selected["is_previewed"] = True
            self.save_prefetch_state(state)
            return Path(str(selected["path"]))

    def has_unpreviewed_prefetch(self, category_name: str) -> bool:
        state = self.load_prefetch_state()
        category = self.safe_category_name(category_name)
        for item in state["items"]:
            path = Path(str(item.get("path", "")))
            if (
                item.get("category") == category
                and not item.get("is_previewed")
                and path.exists()
            ):
                return True
        return False

    def evict_oldest_previewed_unfavorite(self, category_name: str) -> bool:
        return self.evict_prefetch_item(
            category_name=category_name,
            is_previewed=True,
            include_other_categories=False,
        )

    def evict_for_category_refill(self, category_name: str) -> bool:
        return (
            self.evict_prefetch_item(
                category_name=category_name,
                is_previewed=True,
                include_other_categories=False,
            )
            or self.evict_prefetch_item(
                category_name=category_name,
                is_previewed=True,
                include_other_categories=True,
            )
            or self.evict_prefetch_item(
                category_name=category_name,
                is_previewed=False,
                include_other_categories=True,
            )
        )

    def evict_prefetch_item(
        self,
        category_name: str,
        is_previewed: bool,
        include_other_categories: bool,
    ) -> bool:
        state = self.load_prefetch_state()
        category = self.safe_category_name(category_name)
        counts = self.unpreviewed_counts_by_category()
        victims = sorted(
            [
                item
                for item in state["items"]
                if (item.get("category") != category if include_other_categories else item.get("category") == category)
                and bool(item.get("is_previewed")) == is_previewed
                and not item.get("is_favorite")
                and Path(str(item.get("path", ""))).exists()
                and (
                    is_previewed
                    or not include_other_categories
                    or counts.get(str(item.get("category", "")), 0) > MIN_UNPREVIEWED_PER_CATEGORY
                )
            ],
            key=lambda item: float(item.get("downloaded_at", 0)),
        )
        for item in victims:
            path = Path(str(item.get("path", "")))
            if self.current_file and path.resolve() == self.current_file.resolve():
                continue
            try:
                path.unlink()
                state["items"].remove(item)
                self.save_prefetch_state(state)
                return True
            except OSError:
                state["items"].remove(item)
                self.save_prefetch_state(state)
                return True
        return False

    def clear_other_categories_previewed_unfavorite(self, category_name: str) -> int:
        state = self.load_prefetch_state()
        category = self.safe_category_name(category_name)
        removed = 0
        for item in list(state["items"]):
            path = Path(str(item.get("path", "")))
            if (
                item.get("category") == category
                or not item.get("is_previewed")
                or item.get("is_favorite")
                or not path.exists()
            ):
                continue
            if self.current_file and path.resolve() == self.current_file.resolve():
                continue
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
            state["items"].remove(item)
        if removed:
            self.save_prefetch_state(state)
        return removed

    def create_prefetch_image(self, category_name: str) -> bool:
        if self.prefetch_total_size() >= self.cache_limit_bytes():
            return False
        image_bytes, image_ext = self.download_image_bytes(category_name)
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        if image_hash in self.existing_image_hashes():
            return False

        folder = self.category_prefetch_dir(category_name)
        file_path = folder / f"{self.safe_category_name(category_name)}_{int(time.time() * 1000)}{image_ext}"
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        size = file_path.stat().st_size
        self.remember_download_hash(image_hash)

        with self.state_lock:
            state = self.load_prefetch_state()
            state["items"].append(
                {
                    "category": self.safe_category_name(category_name),
                    "path": str(file_path.resolve()),
                    "hash": image_hash,
                    "size": size,
                    "is_previewed": False,
                    "is_favorite": False,
                    "downloaded_at": time.time(),
                }
            )
            self.save_prefetch_state(state)
        return True

    def prefetch_total_size(self) -> int:
        total = 0
        for path in self.prefetch_dir.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
        return total

    def enforce_cache_limit(self) -> None:
        limit = self.cache_limit_bytes()
        with self.state_lock:
            state = self.load_prefetch_state()
            items = [
                item
                for item in state["items"]
                if Path(str(item.get("path", ""))).exists()
            ]
            state["items"] = items
            total = sum(int(item.get("size", 0)) for item in items)
            victims = sorted(
                [
                    item
                    for item in items
                    if not item.get("is_previewed") and not item.get("is_favorite")
                ],
                key=lambda item: float(item.get("downloaded_at", 0)),
            )
            for item in victims:
                if total <= limit:
                    break
                path = Path(str(item.get("path", "")))
                if self.current_file and path.resolve() == self.current_file.resolve():
                    continue
                try:
                    size = path.stat().st_size
                    path.unlink()
                    total -= size
                    state["items"].remove(item)
                except OSError:
                    state["items"].remove(item)
            self.save_prefetch_state(state)

    def download_image_bytes(self, category_name: str) -> tuple[bytes, str]:
        image_bytes: Optional[bytes] = None
        image_ext = ".jpg"
        errors: list[str] = []
        category = CATEGORIES.get(category_name, CATEGORIES["随机"])
        existing_hashes = self.existing_image_hashes()
        params = {
            "sorting": "random",
            "purity": "100",
            "atleast": "1920x1080",
            "categories": category["categories"],
            "page": str(int(time.time()) % 10 + 1),
        }
        if category["q"]:
            params["q"] = category["q"]

        wallhaven_url = f"https://wallhaven.cc/api/v1/search?{urlencode(params)}"

        try:
            api_body = self.fetch_bytes(wallhaven_url, timeout=6)
            data = json.loads(api_body.decode("utf-8"))
            for item in data.get("data") or []:
                image_url = item.get("path")
                if not image_url:
                    continue
                candidate = self.fetch_bytes(image_url, timeout=10)
                if self.is_duplicate_image(candidate, existing_hashes):
                    errors.append("wallhaven: 跳过重复图片")
                    continue
                image_bytes = candidate
                image_ext = os.path.splitext(image_url)[1] or ".jpg"
                break
        except Exception as exc:
            errors.append(f"wallhaven: {exc}")

        if image_bytes is None:
            try:
                candidate = self.download_bing_wallpaper()
                if self.is_duplicate_image(candidate, existing_hashes):
                    raise RuntimeError("跳过重复图片")
                image_bytes = candidate
                image_ext = ".jpg"
            except Exception as exc:
                errors.append(f"bing: {exc}")

        if image_bytes is None:
            for attempt in range(5):
                try:
                    random_id = int(time.time() * 1000) + attempt
                    fallback_url = f"https://picsum.photos/2560/1440?random={random_id}"
                    candidate = self.fetch_bytes(fallback_url, timeout=10)
                    if self.is_duplicate_image(candidate, existing_hashes):
                        errors.append("picsum: 跳过重复图片")
                        continue
                    image_bytes = candidate
                    image_ext = ".jpg"
                    break
                except Exception as exc:
                    errors.append(f"picsum: {exc}")

        if image_bytes is None:
            raise RuntimeError("；".join(errors) if errors else "所有图片源都不可用")
        return image_bytes, image_ext

    def existing_image_hashes(self) -> set[str]:
        hashes = self.load_download_history_hashes()
        for folder in (self.favorites_dir, self.prefetch_dir):
            for path in folder.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                    continue
                try:
                    hashes.add(self.file_hash(path))
                except OSError:
                    continue
        return hashes

    def sync_download_history(self) -> None:
        hashes = self.load_download_history_hashes()
        before = len(hashes)
        for folder in (self.favorites_dir, self.prefetch_dir):
            for path in folder.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                    continue
                try:
                    hashes.add(self.file_hash(path))
                except OSError:
                    continue
        if len(hashes) != before:
            self.save_download_history_hashes(hashes)

    def trim_runtime_files(self) -> None:
        log_file = self.base_dir / SLIDESHOW_LOG_FILE
        try:
            if log_file.exists() and log_file.stat().st_size > MAX_LOG_BYTES:
                log_file.write_text("", encoding="utf-8")
        except OSError:
            pass

    def load_download_history_hashes(self) -> set[str]:
        return {item["hash"] for item in self.load_download_history_items()}

    def load_download_history_items(self) -> list[dict[str, float | str]]:
        if not self.download_history_file.exists():
            return []
        try:
            data = json.loads(self.download_history_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        now = time.time()
        if isinstance(data, list):
            items = []
            for item in data:
                if isinstance(item, str):
                    items.append({"hash": item, "first_seen": now, "last_seen": now})
                elif isinstance(item, dict) and isinstance(item.get("hash"), str):
                    first_seen = float(item.get("first_seen", now))
                    last_seen = float(item.get("last_seen", first_seen))
                    items.append({"hash": item["hash"], "first_seen": first_seen, "last_seen": last_seen})
            return self.compact_download_history_items(items)

        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = []
            for item in data["items"]:
                if isinstance(item, dict) and isinstance(item.get("hash"), str):
                    first_seen = float(item.get("first_seen", now))
                    last_seen = float(item.get("last_seen", first_seen))
                    items.append({"hash": item["hash"], "first_seen": first_seen, "last_seen": last_seen})
            return self.compact_download_history_items(items)

        return []

    def compact_download_history_items(
        self,
        items: list[dict[str, float | str]],
    ) -> list[dict[str, float | str]]:
        now = time.time()
        cutoff = now - DOWNLOAD_HISTORY_RETENTION_DAYS * 24 * 60 * 60
        by_hash: dict[str, dict[str, float | str]] = {}
        for item in items:
            image_hash = str(item["hash"])
            first_seen = float(item["first_seen"])
            last_seen = float(item["last_seen"])
            if last_seen < cutoff:
                continue
            existing = by_hash.get(image_hash)
            if existing is None:
                by_hash[image_hash] = {
                    "hash": image_hash,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                }
            else:
                existing["first_seen"] = min(float(existing["first_seen"]), first_seen)
                existing["last_seen"] = max(float(existing["last_seen"]), last_seen)

        compacted = sorted(by_hash.values(), key=lambda item: float(item["last_seen"]), reverse=True)
        return compacted[:DOWNLOAD_HISTORY_MAX_ITEMS]

    def save_download_history_items(self, items: list[dict[str, float | str]]) -> None:
        compacted = self.compact_download_history_items(items)
        self.download_history_file.write_text(
            json.dumps({"items": compacted}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_download_history_hashes(self, hashes: set[str]) -> None:
        now = time.time()
        existing = {item["hash"]: item for item in self.load_download_history_items()}
        for image_hash in hashes:
            item = existing.get(image_hash)
            if item is None:
                existing[image_hash] = {"hash": image_hash, "first_seen": now, "last_seen": now}
        self.save_download_history_items(list(existing.values()))

    def remember_download_hash(self, image_hash: str) -> None:
        now = time.time()
        items = self.load_download_history_items()
        found = False
        for item in items:
            if item["hash"] == image_hash:
                item["last_seen"] = now
                found = True
                break
        if not found:
            items.append({"hash": image_hash, "first_seen": now, "last_seen": now})
        self.save_download_history_items(items)

    @staticmethod
    def is_duplicate_image(image_bytes: bytes, existing_hashes: set[str]) -> bool:
        return hashlib.sha256(image_bytes).hexdigest() in existing_hashes

    @staticmethod
    def file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def download_bing_wallpaper(self) -> bytes:
        api_url = "https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1&mkt=zh-CN"
        api_body = self.fetch_bytes(api_url, timeout=6)
        data = json.loads(api_body.decode("utf-8"))
        images = data.get("images") or []
        if not images or not images[0].get("url"):
            raise RuntimeError("没有返回图片")
        image_url = urljoin("https://www.bing.com", images[0]["url"])
        return self.fetch_bytes(image_url, timeout=10)

    @staticmethod
    def fetch_bytes(url: str, timeout: int) -> bytes:
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 WallpaperChanger/1.0",
                "Accept": "*/*",
            },
        )
        try:
            context = ssl._create_unverified_context()
            with urlopen(req, timeout=timeout, context=context) as resp:
                return resp.read()
        except (HTTPError, URLError) as exc:
            raise RuntimeError(f"下载失败：{exc}") from exc

    def set_wallpaper_with_fade(self, file_path: Path) -> None:
        self.fade_window(self.window_alpha, 0.45)
        try:
            self.set_wallpaper(file_path)
        finally:
            self.fade_window(0.45, self.window_alpha)

    def fade_window(self, start: float, end: float) -> None:
        steps = 6
        delta = (end - start) / steps
        for index in range(steps + 1):
            self.root.attributes("-alpha", round(start + delta * index, 2))
            self.root.update_idletasks()
            self.root.update()
            time.sleep(0.025)

    @staticmethod
    def set_wallpaper(file_path: Path) -> None:
        abs_path = str(file_path.resolve())
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            abs_path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
        )
        if not result:
            raise RuntimeError("系统拒绝设置壁纸")

    def autostart_status_text(self) -> str:
        return "开机启动：开" if self.autostart_var.get() else "开机启动：关"

    @staticmethod
    def startup_command() -> str:
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        runner = pythonw if pythonw.exists() else executable
        script = Path(__file__).resolve()
        return f'"{runner}" "{script}"'

    @staticmethod
    def background_python() -> Path:
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        return pythonw if pythonw.exists() else executable

    @staticmethod
    def is_autostart_enabled() -> bool:
        if winreg is None:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value == WallpaperChangerApp.startup_command()
        except FileNotFoundError:
            return False
        except OSError:
            return False

    @staticmethod
    def enable_autostart() -> None:
        if winreg is None:
            raise RuntimeError("当前系统不支持注册表开机启动")
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, WallpaperChangerApp.startup_command())

    @staticmethod
    def disable_autostart() -> None:
        if winreg is None:
            raise RuntimeError("当前系统不支持注册表开机启动")
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def favorite_files_in(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    files = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(files, key=lambda path: path.stat().st_mtime)


def write_slideshow_state(base_dir: Path, file_path: Path, index: int) -> None:
    state_file = base_dir / SLIDESHOW_STATE_FILE
    data = {
        "file_name": file_path.name,
        "path": str(file_path.resolve()),
        "index": index,
        "updated_at": time.time(),
    }
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_slideshow_daemon(interval_seconds: int, continue_from: str = "") -> None:
    base_dir = Path(__file__).resolve().parent
    favorites_dir = base_dir / "favorites"
    pid_file = base_dir / SLIDESHOW_PID_FILE
    stop_file = base_dir / SLIDESHOW_STOP_FILE
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    index = -1
    try:
        if continue_from:
            for _ in range(max(1, interval_seconds)):
                if stop_file.exists():
                    break
                time.sleep(1)

        while not stop_file.exists():
            favorites = favorite_files_in(favorites_dir)
            if favorites:
                if continue_from:
                    for current_index, path in enumerate(favorites):
                        if path.name == continue_from:
                            index = current_index
                            break
                    continue_from = ""
                index = (index + 1) % len(favorites)
                WallpaperChangerApp.set_wallpaper(favorites[index])
                write_slideshow_state(base_dir, favorites[index], index)

            for _ in range(max(1, interval_seconds)):
                if stop_file.exists():
                    break
                time.sleep(1)
    finally:
        pid_file.unlink(missing_ok=True)


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--slideshow-daemon":
        continue_from = ""
        if len(sys.argv) >= 5 and sys.argv[3] == "--continue-from":
            continue_from = sys.argv[4]
        run_slideshow_daemon(int(sys.argv[2]), continue_from)
        return

    root = tk.Tk()
    WallpaperChangerApp(root)
    root.mainloop()


if __name__ == "__main__":
    tempfile.gettempdir()
    main()
