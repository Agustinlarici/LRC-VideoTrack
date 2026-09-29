"""Ajustes editables desde el dashboard (umbrales de avisos y debounce). Se guardan en JSON."""
import json
import threading

from .. import config

PRESETS = {
    "real": {  # restaurante en servicio
        "occupy_seconds": 30, "free_seconds": 120,
        "unattended_seconds": 300, "service_seconds": 900, "long_stay_seconds": 5400, "free_idle_seconds": 1800,
    },
    "demo": {  # vídeos cortos: los avisos saltan en segundos
        "occupy_seconds": 2, "free_seconds": 3,
        "unattended_seconds": 6, "service_seconds": 10, "long_stay_seconds": 12, "free_idle_seconds": 8,
    },
}

NUMERIC = ("occupy_seconds", "free_seconds", "unattended_seconds", "service_seconds",
           "long_stay_seconds", "free_idle_seconds")


class Settings:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = dict(config.DEFAULT_SETTINGS)
        if config.SETTINGS_FILE.exists():
            try:
                self._data.update(json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                pass  # archivo corrupto: se usan los valores por defecto

    def get(self) -> dict:
        with self._lock:
            return dict(self._data)

    def update(self, changes: dict) -> dict:
        with self._lock:
            for key, value in changes.items():
                if key not in config.DEFAULT_SETTINGS or value is None:
                    continue
                if key in NUMERIC:
                    value = max(0.0, float(value))
                elif key == "sound":
                    value = bool(value)
                else:
                    value = str(value).strip()
                self._data[key] = value
            # el debounce nunca puede ser 0: sería cambiar de estado por un frame aislado
            for key in ("occupy_seconds", "free_seconds"):
                self._data[key] = max(0.5, self._data[key])
            config.SETTINGS_FILE.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
            return dict(self._data)
