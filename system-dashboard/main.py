"""
main.py - Einstiegspunkt des System-Dashboards.

Prüft beim Start, ob die App mit Administratorrechten läuft (ohne dies
zu erzwingen - admin-pflichtige Aktionen werden in der GUI einfach
ausgegraut/deaktiviert), und startet anschließend das Hauptfenster.
"""

from __future__ import annotations

import sys


def _pruefe_admin_rechte() -> bool:
    """Prüft per Windows-API, ob der aktuelle Prozess erhöhte Rechte hat.

    Läuft die App nicht unter Windows (z. B. während der Entwicklung),
    wird sicherheitshalber False zurückgegeben.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


def main() -> None:
    from app.dashboard import Dashboard

    ist_admin = _pruefe_admin_rechte()
    fenster = Dashboard(ist_admin=ist_admin)
    fenster.mainloop()


if __name__ == "__main__":
    main()
