#!/usr/bin/env python3
"""NVIDIA VRAM Monitor - GTK4/Adwaita app with AppIndicator3 tray icon."""

import os
import signal
import subprocess
import sys

import gi

APP_ID = "io.github.edgan.nvidia_vram_monitor"
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", 5))
VRAM_WARN_THRESHOLD = int(os.environ.get("VRAM_WARN_THRESHOLD", 90))


def query_vram():
    """Query nvidia-smi for VRAM usage. Returns (used_mib, total_mib) or None."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            return int(parts[0]), int(parts[1])
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
        pass
    return None


# ---------------------------------------------------------------------------
# Tray helper (GTK3 + AppIndicator3) — runs in a subprocess
# ---------------------------------------------------------------------------

def run_tray():
    """Tray icon subprocess using GTK3 + AppIndicator3."""
    gi.require_version("Gtk", "3.0")
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3, GLib, Gtk

    indicator = AppIndicator3.Indicator.new(
        "nvidia_vram_monitor",
        "video-display",
        AppIndicator3.IndicatorCategory.HARDWARE,
    )
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("VRAM Monitor")

    menu = Gtk.Menu()

    usage_item = Gtk.MenuItem(label="VRAM: …")
    usage_item.set_sensitive(False)
    menu.append(usage_item)

    menu.append(Gtk.SeparatorMenuItem())

    show_item = Gtk.MenuItem(label="Show Window")
    show_item.connect("activate", lambda _: _dbus_activate())
    menu.append(show_item)

    quit_item = Gtk.MenuItem(label="Quit")
    quit_item.connect("activate", lambda _: _tray_quit())
    menu.append(quit_item)

    menu.show_all()
    indicator.set_menu(menu)

    def _dbus_activate():
        """Activate the main GTK4 app over D-Bus."""
        try:
            subprocess.Popen(
                [
                    "gdbus", "call", "--session",
                    "--dest", APP_ID,
                    "--object-path", "/" + APP_ID.replace(".", "/"),
                    "--method", "org.gtk.Application.Activate",
                    "[]",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def _tray_quit():
        """Tell the main app to quit, then exit tray."""
        try:
            subprocess.Popen(
                [
                    "gdbus", "call", "--session",
                    "--dest", APP_ID,
                    "--object-path", "/" + APP_ID.replace(".", "/"),
                    "--method", "org.freedesktop.Application.ActivateAction",
                    "quit", "[]", "{}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass
        Gtk.main_quit()

    def _poll_label():
        data = query_vram()
        if data:
            used, total = data
            pct = (used / total) * 100.0
            indicator.set_label(f" {pct:.0f}%", "")
            usage_item.set_label(f"VRAM: {used} / {total} MiB ({pct:.1f}%)")
        else:
            indicator.set_label(" ?%", "")
            usage_item.set_label("VRAM: unavailable")
        return True

    GLib.timeout_add_seconds(POLL_INTERVAL_SECONDS, _poll_label)
    GLib.idle_add(_poll_label)

    # Exit cleanly if parent dies
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())

    Gtk.main()


# ---------------------------------------------------------------------------
# Main app (GTK4 + Adwaita)
# ---------------------------------------------------------------------------

def run_app():
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, GLib, Gtk

    class VramMonitorWindow(Adw.ApplicationWindow):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.set_default_size(600, 260)
            self.set_title("NVIDIA VRAM Monitor")
            self.set_resizable(False)

            self.connect("close-request", self._on_close_request)

            header = Adw.HeaderBar()
            quit_btn = Gtk.Button(label="Quit")
            quit_btn.add_css_class("destructive-action")
            quit_btn.connect("clicked", lambda _: self.get_application().quit())
            header.pack_end(quit_btn)

            hide_btn = Gtk.Button(label="Hide to Tray")
            hide_btn.connect("clicked", lambda _: self.set_visible(False))
            header.pack_start(hide_btn)

            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            content.append(header)

            clamp = Adw.Clamp(maximum_size=360)
            clamp.set_margin_top(24)
            clamp.set_margin_bottom(24)
            clamp.set_margin_start(16)
            clamp.set_margin_end(16)

            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)

            self.gpu_label = Gtk.Label(label="GPU: detecting…")
            self.gpu_label.add_css_class("title-4")
            self.gpu_label.set_halign(Gtk.Align.START)
            inner.append(self.gpu_label)

            bar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            bar_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            bar_title = Gtk.Label(label="VRAM Usage")
            bar_title.set_halign(Gtk.Align.START)
            bar_title.set_hexpand(True)
            bar_title.add_css_class("heading")
            self.pct_label = Gtk.Label(label="—%")
            self.pct_label.add_css_class("heading")
            bar_header.append(bar_title)
            bar_header.append(self.pct_label)
            bar_box.append(bar_header)

            self.progress = Gtk.ProgressBar()
            self.progress.set_show_text(False)
            bar_box.append(self.progress)

            self.usage_label = Gtk.Label(label="— MiB / — MiB")
            self.usage_label.set_halign(Gtk.Align.START)
            self.usage_label.add_css_class("dim-label")
            bar_box.append(self.usage_label)

            inner.append(bar_box)

            self.status_label = Gtk.Label(label="Monitoring…")
            self.status_label.set_halign(Gtk.Align.START)
            self.status_label.set_wrap(True)
            self.status_label.add_css_class("dim-label")
            inner.append(self.status_label)

            clamp.set_child(inner)
            content.append(clamp)
            self.set_content(content)

            self._detect_gpu_name()

        def _on_close_request(self, _window):
            self.set_visible(False)
            return True

        def _detect_gpu_name(self):
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    self.gpu_label.set_label(f"GPU: {result.stdout.strip()}")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                self.gpu_label.set_label("GPU: unknown")

        def update(self, used, total, pct):
            self.progress.set_fraction(pct / 100.0)
            self.pct_label.set_label(f"{pct:.1f}%")
            self.usage_label.set_label(f"{used} MiB / {total} MiB")

            self.progress.remove_css_class("warning-bar")
            self.progress.remove_css_class("critical-bar")
            if pct >= VRAM_WARN_THRESHOLD:
                self.progress.add_css_class("critical-bar")
            elif pct >= 70:
                self.progress.add_css_class("warning-bar")

            self.status_label.set_label(
                f"Polling every {POLL_INTERVAL_SECONDS}s · "
                f"Alert threshold: {VRAM_WARN_THRESHOLD}%"
            )

        def show_error(self, msg):
            self.status_label.set_label(msg)
            self.pct_label.set_label("—%")
            self.usage_label.set_label("— MiB / — MiB")
            self.progress.set_fraction(0)

    class NvidiaVramMonitorApp(Adw.Application):
        def __init__(self):
            super().__init__(
                application_id=APP_ID,
                flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            )
            self._warned = False
            self._window = None
            self._tray_proc = None

        def do_startup(self):
            Adw.Application.do_startup(self)
            # Keep running when all windows are hidden
            self.hold()

            css = Gtk.CssProvider()
            css.load_from_string(
                """
                progressbar.warning-bar > trough > progress {
                    background-color: @warning_color;
                }
                progressbar.critical-bar > trough > progress {
                    background-color: @error_color;
                }
                """
            )
            Gtk.StyleContext.add_provider_for_display(
                __import__("gi").repository.Gdk.Display.get_default(),
                css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

            show_action = Gio.SimpleAction.new("show-window", None)
            show_action.connect("activate", self._on_show_window)
            self.add_action(show_action)

            quit_action = Gio.SimpleAction.new("quit", None)
            quit_action.connect("activate", lambda *_: self.quit())
            self.add_action(quit_action)

            # Spawn tray icon subprocess
            self._tray_proc = subprocess.Popen(
                [sys.executable, os.path.abspath(__file__), "--tray"],
                env={**os.environ, "POLL_INTERVAL_SECONDS": str(POLL_INTERVAL_SECONDS),
                     "VRAM_WARN_THRESHOLD": str(VRAM_WARN_THRESHOLD)},
            )

            GLib.timeout_add_seconds(POLL_INTERVAL_SECONDS, self._poll)
            GLib.idle_add(self._poll)

        def do_activate(self):
            if not self._window:
                self._window = VramMonitorWindow(application=self)
            self._window.set_visible(True)
            self._window.present()

        def do_shutdown(self):
            if self._tray_proc and self._tray_proc.poll() is None:
                self._tray_proc.terminate()
                try:
                    self._tray_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._tray_proc.kill()
            Adw.Application.do_shutdown(self)

        def _on_show_window(self, _action, _param):
            self.activate()

        def _poll(self):
            data = query_vram()
            if data:
                used, total = data
                pct = (used / total) * 100.0
                if self._window:
                    self._window.update(used, total, pct)

                if pct >= VRAM_WARN_THRESHOLD and not self._warned:
                    self._send_warning(used, total, pct)
                    self._warned = True
                elif pct < VRAM_WARN_THRESHOLD - 5:
                    self._warned = False
            else:
                if self._window:
                    self._window.show_error("Failed to query nvidia-smi")
            return True

        def _send_warning(self, used, total, pct):
            notification = Gio.Notification.new("VRAM Usage Critical!")
            notification.set_body(
                f"GPU VRAM is at {pct:.1f}% ({used} MiB / {total} MiB)\n"
                f"Consider closing some GPU applications."
            )
            notification.set_priority(Gio.NotificationPriority.URGENT)
            notification.set_default_action("app.show-window")
            self.send_notification("vram-warning", notification)

    app = NvidiaVramMonitorApp()
    app.run(sys.argv)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if "--tray" in sys.argv:
        run_tray()
    else:
        run_app()


if __name__ == "__main__":
    main()
