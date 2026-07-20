"""
dashboard.py - Hauptfenster des System-Dashboards.

Baut die Kopfzeile (Logo, Status-Pillen, Aktualisieren-Button), das
4x3-Kachel-Raster und den Hintergrund-Thread, der alle ~2 Sekunden neue
Systemwerte holt. GUI-Updates laufen ausschließlich im Main-Thread über
self.after(...), da Tkinter nicht thread-sicher ist.

Aktueller Stand (Schritt 3 aus der Aufgabenstellung): Nur die Kachel
"Laufwerk C:" ist voll funktionsfähig (echte Daten + Eigenschaften-
Aktion). Die übrigen 11 Kachel-Plätze sind als Platzhalter sichtbar und
werden in Schritt 4 durch echte Kacheln ersetzt.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import customtkinter as ctk

from . import actions, system_info, theme
from .widgets.meter import Meter
from .widgets.tile import Tile

AKTUALISIERUNGS_INTERVALL_SEKUNDEN = 2.0


class Dashboard(ctk.CTk):
    """Hauptfenster der Anwendung."""

    def __init__(self, ist_admin: bool) -> None:
        super().__init__()

        self.ist_admin = ist_admin
        self._daten_lock = threading.Lock()
        self._daten: dict = {}
        self._stop_event = threading.Event()

        self._fenster_einrichten()
        self._kopfzeile_bauen()
        self._toast_leiste_bauen()
        self._raster_bauen()

        # Hintergrund-Thread für die zyklische Datenabfrage starten.
        self._worker_thread = threading.Thread(
            target=self._hintergrund_worker, daemon=True
        )
        self._worker_thread.start()

        self.protocol("WM_DELETE_WINDOW", self._beim_schliessen)

        # GUI-Update-Schleife (Main-Thread) und Uhr separat starten.
        self.after(200, self._gui_tick)
        self._uhr_tick()
        self._puls_tick()

    # ------------------------------------------------------------------
    # Grundgerüst
    # ------------------------------------------------------------------

    def _fenster_einrichten(self) -> None:
        ctk.set_appearance_mode("dark")
        self.title("System-Dashboard")
        self.geometry("1180x760")
        self.minsize(960, 640)
        self.configure(fg_color=theme.BG_DARK)

    def _kopfzeile_bauen(self) -> None:
        kopfzeile = ctk.CTkFrame(self, fg_color="transparent", height=56)
        kopfzeile.pack(fill="x", padx=20, pady=(16, 8))

        # --- Logo: Verlauf Blau -> Lila + Titel --------------------------
        logo_container = ctk.CTkFrame(kopfzeile, fg_color="transparent")
        logo_container.pack(side="left")

        logo_kreis = ctk.CTkFrame(
            logo_container,
            width=34,
            height=34,
            corner_radius=10,
            fg_color=theme.ACCENT_BLUE,
        )
        logo_kreis.pack(side="left", padx=(0, 10))
        logo_kreis.pack_propagate(False)
        # Simulierter Verlauf Blau->Lila über zwei überlappende Flächen.
        logo_kreis_lila = ctk.CTkFrame(
            logo_kreis, fg_color=theme.ACCENT_PURPLE, corner_radius=10
        )
        logo_kreis_lila.place(relx=0.45, rely=0.0, relwidth=0.55, relheight=1.0)

        titel_label = ctk.CTkLabel(
            logo_container,
            text="System-Dashboard",
            font=(theme.FONT_FAMILY_UI, 20, "bold"),
            text_color=theme.TEXT_BRIGHT,
        )
        titel_label.pack(side="left")

        # --- Rechte Seite: Status-Pillen + Aktualisieren-Button --------
        rechte_seite = ctk.CTkFrame(kopfzeile, fg_color="transparent")
        rechte_seite.pack(side="right")

        admin_text = "🛡 Administrator" if self.ist_admin else "Standard-Benutzer"
        admin_farbe = theme.ACCENT_YELLOW if self.ist_admin else theme.TEXT_MUTED
        self._admin_pille = self._pille_erstellen(rechte_seite, admin_text, admin_farbe)
        self._admin_pille.pack(side="left", padx=(0, 8))

        self._live_pille, self._puls_punkt_label = self._live_pille_erstellen(
            rechte_seite
        )
        self._live_pille.pack(side="left", padx=(0, 8))

        self._uhr_pille = self._pille_erstellen(rechte_seite, "--:--:--", theme.TEXT_BRIGHT)
        self._uhr_pille.pack(side="left", padx=(0, 12))

        aktualisieren_button = ctk.CTkButton(
            rechte_seite,
            text="↻ Aktualisieren",
            command=self._manuelle_aktualisierung,
            fg_color=theme.BUTTON_PRIMARY_BG,
            hover_color=theme.BUTTON_PRIMARY_HOVER,
            border_width=1,
            border_color=theme.ACCENT_BLUE,
            text_color=theme.TEXT_BRIGHT,
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
            corner_radius=10,
            height=32,
        )
        aktualisieren_button.pack(side="left")

    def _pille_erstellen(self, master, text: str, textfarbe: str) -> ctk.CTkFrame:
        """Erzeugt eine kleine, abgerundete Status-Pille mit Text."""
        pille = ctk.CTkFrame(
            master, fg_color=theme.CARD_BG, corner_radius=14, border_width=1,
            border_color=theme.CARD_BORDER,
        )
        label = ctk.CTkLabel(
            pille,
            text=text,
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
            text_color=textfarbe,
        )
        label.pack(padx=12, pady=6)
        pille.text_label = label  # type: ignore[attr-defined]
        return pille

    def _live_pille_erstellen(self, master) -> tuple[ctk.CTkFrame, "object"]:
        """Pille mit pulsierendem Punkt + "Live · alle 2 s"."""
        pille = ctk.CTkFrame(
            master, fg_color=theme.CARD_BG, corner_radius=14, border_width=1,
            border_color=theme.CARD_BORDER,
        )
        innen = ctk.CTkFrame(pille, fg_color="transparent")
        innen.pack(padx=12, pady=6)

        import tkinter as tk

        punkt_canvas = tk.Canvas(
            innen, width=10, height=10, highlightthickness=0, bg=theme.CARD_BG
        )
        punkt_canvas.pack(side="left", padx=(0, 6))
        punkt_id = punkt_canvas.create_oval(1, 1, 9, 9, fill=theme.ACCENT_BLUE, outline="")

        text_label = ctk.CTkLabel(
            innen,
            text="Live · alle 2 s",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
            text_color=theme.TEXT_MUTED,
        )
        text_label.pack(side="left")

        # Canvas + Punkt-ID am Frame ablegen, damit _puls_tick sie erreicht.
        pille.puls_canvas = punkt_canvas  # type: ignore[attr-defined]
        pille.puls_punkt_id = punkt_id  # type: ignore[attr-defined]
        pille.puls_hell = True  # type: ignore[attr-defined]
        return pille, text_label

    def _toast_leiste_bauen(self) -> None:
        """Kleine Statusmeldungs-Zeile unten im Fenster für Aktions-Ergebnisse."""
        self._toast_label = ctk.CTkLabel(
            self,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        self._toast_label.pack(fill="x", padx=24, pady=(0, 8), side="bottom")

    def zeige_toast(self, meldung: str, art: str = "erfolg") -> None:
        """Zeigt eine Toast-/Statusmeldung unten im Fenster.

        art: "erfolg" (blau), "warnung" (gelb) oder "fehler" (lila).
        """
        farben = {
            "erfolg": theme.ACCENT_BLUE,
            "warnung": theme.ACCENT_YELLOW,
            "fehler": theme.ACCENT_PURPLE,
        }
        try:
            self._toast_label.configure(
                text=meldung, text_color=farben.get(art, theme.TEXT_MUTED)
            )
            self.after(4000, lambda: self._toast_label.configure(text=""))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Kachel-Raster
    # ------------------------------------------------------------------

    def _raster_bauen(self) -> None:
        raster_container = ctk.CTkFrame(self, fg_color="transparent")
        raster_container.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        for spalte in range(4):
            raster_container.grid_columnconfigure(spalte, weight=1, uniform="spalte")
        for zeile in range(3):
            raster_container.grid_rowconfigure(zeile, weight=1, uniform="zeile")

        # --- Kachel 1: Laufwerk C: (voll funktionsfähig) -------------------
        self._kachel_laufwerk_c = Tile(
            raster_container,
            titel="Laufwerk C:",
            untertitel="System",
            icon="💽",
            akzentfarbe=theme.ACCENT_BLUE,
        )
        self._kachel_laufwerk_c.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self._meter_laufwerk_c = Meter(self._kachel_laufwerk_c.body)
        self._meter_laufwerk_c.pack(fill="both", expand=True)

        self._kachel_laufwerk_c.add_button(
            "Reinigen",
            self._aktion_reinigen_c,
            primaer=True,
        )
        self._kachel_laufwerk_c.add_button(
            "Eigenschaften",
            self._aktion_eigenschaften_c,
        )

        # --- Restliche 11 Plätze: Platzhalter (folgen in Schritt 4) ------
        titel_platzhalter = [
            "Weitere Laufwerke", "Arbeitsspeicher", "CPU-Auslastung",
            "CPU-Temperatur", "GPU-Temperatur", "Netzwerk",
            "Autostart", "Papierkorb", "Temporäre Dateien",
            "Windows-Update", "System",
        ]
        for index, titel in enumerate(titel_platzhalter, start=1):
            zeile, spalte = divmod(index, 4)
            platzhalter = ctk.CTkFrame(
                raster_container,
                fg_color=theme.CARD_BG_GRADIENT_END,
                corner_radius=16,
                border_width=1,
                border_color=theme.CARD_BORDER,
            )
            platzhalter.grid(row=zeile, column=spalte, sticky="nsew", padx=8, pady=8)
            ctk.CTkLabel(
                platzhalter,
                text=f"{titel}\n(folgt in Schritt 4)",
                font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
                text_color=theme.TEXT_DIM,
            ).place(relx=0.5, rely=0.5, anchor="center")

    # ------------------------------------------------------------------
    # Aktionen der Beispiel-Kachel
    # ------------------------------------------------------------------

    def _aktion_reinigen_c(self) -> None:
        # Die volle Reinigungs-Routine (cleaning.py) folgt in Schritt 5.
        self.zeige_toast(
            "Reinigungs-Routine folgt in einem späteren Schritt.", "warnung"
        )

    def _aktion_eigenschaften_c(self) -> None:
        erfolg, meldung = actions.shell_properties("C:\\")
        self.zeige_toast(meldung, "erfolg" if erfolg else "fehler")

    # ------------------------------------------------------------------
    # Hintergrund-Thread & GUI-Refresh
    # ------------------------------------------------------------------

    def _hintergrund_worker(self) -> None:
        """Läuft im Hintergrund-Thread: holt alle ~2s neue Systemwerte."""
        while not self._stop_event.is_set():
            try:
                neue_daten = system_info.snapshot()
            except Exception:
                neue_daten = {}
            with self._daten_lock:
                self._daten = neue_daten
            self._stop_event.wait(AKTUALISIERUNGS_INTERVALL_SEKUNDEN)

    def _gui_tick(self) -> None:
        """Läuft im Main-Thread: übernimmt die zuletzt gelesenen Werte in die GUI."""
        with self._daten_lock:
            daten = dict(self._daten)
        self._kacheln_aktualisieren(daten)
        self.after(500, self._gui_tick)

    def _kacheln_aktualisieren(self, daten: dict) -> None:
        """Schreibt neue Werte in die Widgets - baut niemals Widgets neu auf."""
        try:
            disk_c = daten.get("disk_c")
            if disk_c is None:
                self._meter_laufwerk_c.set_value(None, "—")
            else:
                belegt_text = f"{disk_c['used_gb']:.0f} GB belegt"
                frei_text = f"{disk_c['free_gb']:.0f} GB frei"
                self._meter_laufwerk_c.set_value(
                    disk_c["percent"], belegt_text, frei_text
                )
        except Exception:
            # Eine fehlerhafte Kachel darf die anderen nicht mitreißen.
            pass

    def _manuelle_aktualisierung(self) -> None:
        """Erzwingt ein sofortiges Neuladen aller Werte (Button "↻ Aktualisieren")."""

        def sofort_laden() -> None:
            try:
                neue_daten = system_info.snapshot()
            except Exception:
                neue_daten = {}
            with self._daten_lock:
                self._daten = neue_daten

        threading.Thread(target=sofort_laden, daemon=True).start()
        self.zeige_toast("Aktualisierung angestoßen.", "erfolg")

    # ------------------------------------------------------------------
    # Uhr & Live-Puls
    # ------------------------------------------------------------------

    def _uhr_tick(self) -> None:
        try:
            jetzt = datetime.now().strftime("%H:%M:%S")
            self._uhr_pille.text_label.configure(text=jetzt)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.after(1000, self._uhr_tick)

    def _puls_tick(self) -> None:
        try:
            pille = self._live_pille
            hell = pille.puls_hell  # type: ignore[attr-defined]
            farbe = theme.ACCENT_BLUE if hell else theme.CARD_BORDER
            pille.puls_canvas.itemconfigure(pille.puls_punkt_id, fill=farbe)  # type: ignore[attr-defined]
            pille.puls_hell = not hell  # type: ignore[attr-defined]
        except Exception:
            pass
        self.after(700, self._puls_tick)

    # ------------------------------------------------------------------
    # Beenden
    # ------------------------------------------------------------------

    def _beim_schliessen(self) -> None:
        self._stop_event.set()
        self.destroy()
