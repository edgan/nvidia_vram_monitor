# nvidia_vram_monitor

This is a small gtk4/gtk3 application that uses `nvidia-smi` to monitor VRAM usage and sends you a Gnome notification if you go over 90%.

There is an environment variable `VRAM_WARN_THRESHOLD` to let you override the default percentage to alert on.

Example:

VRAM_WARN_THRESHOLD=30 ./nvidia_vram_monitor.py

## Dependencies

- Python 3
- [PyGObject](https://pygobject.gnome.org/) (GTK4, Adwaita, and AppIndicator3 bindings)
- `nvidia-smi` (provided by the NVIDIA driver)
- GTK4, libadwaita, and libappindicator3 system libraries

Install Python dependencies:

```
pip install -r requirements.txt
```

**Note:** PyGObject requires system libraries to build.

On Fedora:

```
sudo dnf install gcc gobject-introspection-devel cairo-gobject-devel pkg-config python3-devel gtk4-devel libadwaita-devel libappindicator-gtk3-devel
```

On Ubuntu/Debian:

```
sudo apt-get install gcc libgirepository1.0-dev libcairo2-dev pkg-config python3-dev libgtk-4-dev libadwaita-1-dev gir1.2-appindicator3-0.1
```

# .desktop
There is an example `.desktop` file. You need to call the application from it to allow the notifications to work.
