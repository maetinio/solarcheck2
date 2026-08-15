"""
dashboard.py - Hauptfenster des System-Dashboards.

Baut die Kopfzeile (Logo, Status-Pillen, Aktualisieren-Button), das
4x3-Kachel-Raster und den Hintergrund-Thread, der alle ~2 Sekunden neue
Systemwerte holt. GUI-Updates laufen ausschließlich im Main-Thread über
self.after(...), da Tkinter nicht thread-sicher ist.

Beim Aktualisieren werden ausschließlich Werte und Farben gesetzt -
niemals Widgets neu gebaut. Dadurch flackert die Oberfläche nicht.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk

from . import actions, cleaning, system_info, theme
from .widgets.dialogs import (
    AuswahlDialog,
    BestaetigungsDialog,
    EingabeDialog,
    InfoDialog,
    VerlaufsDialog,
)
from .widgets.gauge import CircularGauge
from .widgets.meter import Meter
from .widgets.tile import StatValue, Tile

AKTUALISIERUNGS_INTERVALL_SEKUNDEN = 2.0

# Standard-Warnschwellen für die beiden Temperatur-Kacheln (per Dialog änderbar).
STANDARD_WARNSCHWELLE_CPU = 80.0
STANDARD_WARNSCHWELLE_GPU = 85.0

# Ab dieser Fensterbreite wird von 4 auf 2 Spalten umgeschaltet.
SCHMAL_UMBRUCH_PIXEL = 820

# Mindesthöhe einer Kachel, damit Gauge/Balken und Buttonleiste hineinpassen.
KACHEL_MINDESTHOEHE = 186


class Dashboard(ctk.CTk):
    """Hauptfenster der Anwendung."""

    def __init__(self, ist_admin: bool) -> None:
        super().__init__()

        self.ist_admin = ist_admin
        self._daten_lock = threading.Lock()
        self._daten: dict = {}
        self._stop_event = threading.Event()
        # Warteschlange für GUI-Aktionen aus Nebenthreads. Tkinter ist
        # nicht thread-sicher - selbst after() darf nur aus dem Main-Thread
        # kommen. Nebenthreads legen hier ab, _gui_tick() arbeitet ab.
        self._gui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

        # Vom Nutzer einstellbare Warnschwellen der Temperatur-Kacheln.
        self._warnschwelle_cpu = STANDARD_WARNSCHWELLE_CPU
        self._warnschwelle_gpu = STANDARD_WARNSCHWELLE_GPU

        # Laptop-Sonderfall: Gibt es einen Akku, ersetzt die Akku-Kachel
        # die GPU-Temperatur-Kachel. Einmalig beim Start ermittelt.
        self._hat_akku = system_info.akku_info() is not None

        # CPU-Messung einmalig aufwärmen, damit der erste Wert stimmt.
        system_info.cpu_aufwaermen()

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
        if not self.ist_admin:
            # Ohne Adminrechte wird die Pille zum Neustart-Button.
            self._admin_pille.text_label.configure(  # type: ignore[attr-defined]
                cursor="hand2"
            )
            for widget in (self._admin_pille, self._admin_pille.text_label):  # type: ignore[attr-defined]
                widget.bind("<Button-1>", lambda _e: self.neu_starten_als_admin())

        self._live_pille = self._live_pille_erstellen(rechte_seite)
        self._live_pille.pack(side="left", padx=(0, 8))

        self._uhr_pille = self._pille_erstellen(
            rechte_seite, "--:--:--", theme.TEXT_BRIGHT
        )
        self._uhr_pille.pack(side="left", padx=(0, 12))

        aktualisieren_button = ctk.CTkButton(
            rechte_seite,
            text="↻ Aktualisieren",
            command=self._manuelle_aktualisierung,
            width=1,
            fg_color=theme.BUTTON_PRIMARY_BG,
            hover_color=theme.BUTTON_PRIMARY_HOVER,
            border_width=1,
            border_color=theme.ACCENT_BLUE,
            text_color=theme.TEXT_BRIGHT,
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
            corner_radius=10,
            height=32,
        )
        aktualisieren_button.pack(side="left", ipadx=10)

    def _pille_erstellen(self, master, text: str, textfarbe: str) -> ctk.CTkFrame:
        """Erzeugt eine kleine, abgerundete Status-Pille mit Text."""
        pille = ctk.CTkFrame(
            master,
            fg_color=theme.CARD_BG,
            corner_radius=14,
            border_width=1,
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

    def _live_pille_erstellen(self, master) -> ctk.CTkFrame:
        """Pille mit pulsierendem Punkt + "Live · alle 2 s"."""
        import tkinter as tk

        pille = ctk.CTkFrame(
            master,
            fg_color=theme.CARD_BG,
            corner_radius=14,
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        innen = ctk.CTkFrame(pille, fg_color="transparent")
        innen.pack(padx=12, pady=6)

        punkt_canvas = tk.Canvas(
            innen, width=10, height=10, highlightthickness=0, bg=theme.CARD_BG
        )
        punkt_canvas.pack(side="left", padx=(0, 6))
        punkt_id = punkt_canvas.create_oval(
            1, 1, 9, 9, fill=theme.ACCENT_BLUE, outline=""
        )

        ctk.CTkLabel(
            innen,
            text="Live · alle 2 s",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
            text_color=theme.TEXT_MUTED,
        ).pack(side="left")

        # Canvas + Punkt-ID am Frame ablegen, damit _puls_tick sie erreicht.
        pille.puls_canvas = punkt_canvas  # type: ignore[attr-defined]
        pille.puls_punkt_id = punkt_id  # type: ignore[attr-defined]
        pille.puls_hell = True  # type: ignore[attr-defined]
        return pille

    def _toast_leiste_bauen(self) -> None:
        """Statusmeldungs-Zeile unten im Fenster für Aktions-Ergebnisse."""
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
            self.after(5000, lambda: self._toast_label.configure(text=""))
        except Exception:
            pass

    def _melde(self, ergebnis: tuple[bool, str]) -> None:
        """Übernimmt ein (erfolg, meldung)-Tupel aus actions.py als Toast."""
        erfolg, meldung = ergebnis
        self.zeige_toast(meldung, "erfolg" if erfolg else "fehler")

    # ------------------------------------------------------------------
    # Kachel-Raster
    # ------------------------------------------------------------------

    def _raster_bauen(self) -> None:
        # Scrollbares Raster: im 4-Spalten-Betrieb passen alle Kacheln ohne
        # Scrollbalken ins Fenster; im schmalen 2-Spalten-Betrieb entstehen
        # 6 Reihen, die sonst plattgedrückt würden.
        self._raster = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=theme.CARD_BORDER,
            scrollbar_button_hover_color=theme.ACCENT_BLUE,
        )
        self._raster.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        self._kacheln: list[Tile] = []
        self._spalten_aktuell = 4
        self._zeilen_aktuell = 3
        self._zeilen_hoehe_aktuell = KACHEL_MINDESTHOEHE

        self._kachel_laufwerk_c_bauen()
        self._kachel_weitere_laufwerke_bauen()
        self._kachel_ram_bauen()
        self._kachel_cpu_bauen()
        self._kachel_cpu_temp_bauen()
        # Laptop-Sonderfall: Akku statt GPU-Temperatur.
        if self._hat_akku:
            self._kachel_akku_bauen()
        else:
            self._kachel_gpu_temp_bauen()
        self._kachel_netzwerk_bauen()
        self._kachel_autostart_bauen()
        self._kachel_papierkorb_bauen()
        self._kachel_temp_dateien_bauen()
        self._kachel_windows_update_bauen()
        self._kachel_system_bauen()

        self._kacheln_anordnen(4)
        self.bind("<Configure>", self._bei_groessenaenderung)

    def _kachel_anlegen(
        self, titel: str, untertitel: str, icon: str, akzent: str
    ) -> Tile:
        """Erzeugt eine Kachel und merkt sie für die Raster-Anordnung vor."""
        kachel = Tile(
            self._raster,
            titel=titel,
            untertitel=untertitel,
            icon=icon,
            akzentfarbe=akzent,
        )
        self._kacheln.append(kachel)
        return kachel

    def _kacheln_anordnen(self, spalten: int) -> None:
        """Verteilt alle Kacheln auf das Raster (4 Spalten, schmal: 2)."""
        zeilen = (len(self._kacheln) + spalten - 1) // spalten

        for spalte in range(max(4, spalten)):
            # Nicht genutzte Spalten bekommen Gewicht 0, damit sie kollabieren.
            gewicht = 1 if spalte < spalten else 0
            self._raster.grid_columnconfigure(
                spalte, weight=gewicht, uniform="spalte" if gewicht else ""
            )
        # Reihenhöhe: den verfügbaren Platz gleichmäßig aufteilen, aber nie
        # unter die Mindesthöhe gehen. So füllen die Kacheln im normalen
        # 4-Spalten-Betrieb das Fenster, während im schmalen 2-Spalten-
        # Betrieb (6 Reihen) stattdessen gescrollt wird.
        zeilen_hoehe = self._zeilen_hoehe_berechnen(zeilen)
        self._zeilen_hoehe_aktuell = zeilen_hoehe
        for zeile in range(max(3, zeilen)):
            gewicht = 1 if zeile < zeilen else 0
            self._raster.grid_rowconfigure(
                zeile,
                weight=gewicht,
                uniform="zeile" if gewicht else "",
                minsize=zeilen_hoehe if gewicht else 0,
            )

        for index, kachel in enumerate(self._kacheln):
            zeile, spalte = divmod(index, spalten)
            kachel.grid(row=zeile, column=spalte, sticky="nsew", padx=7, pady=5)

        self._spalten_aktuell = spalten
        self._zeilen_aktuell = zeilen

    def _zeilen_hoehe_berechnen(self, zeilen: int) -> int:
        """Teilt die verfügbare Rasterhöhe auf die Reihen auf (mit Untergrenze)."""
        try:
            verfuegbar = self._raster.winfo_height()
            # Vor dem ersten Zeichnen liefert Tk eine 1 - dann Fenstermaß nutzen.
            if verfuegbar <= 1:
                verfuegbar = self.winfo_height() - 130
            # Je Kachel kommen oben und unten 8 px Rasterabstand dazu.
            nutzbar = verfuegbar - zeilen * 10
            return max(KACHEL_MINDESTHOEHE, nutzbar // max(1, zeilen))
        except Exception:
            return KACHEL_MINDESTHOEHE

    def _bei_groessenaenderung(self, event=None) -> None:
        """Passt Spaltenzahl und Reihenhöhe an die neue Fenstergröße an."""
        try:
            if event is not None and event.widget is not self:
                return
            gewuenschte_spalten = 2 if self.winfo_width() < SCHMAL_UMBRUCH_PIXEL else 4
            if gewuenschte_spalten != self._spalten_aktuell:
                self._kacheln_anordnen(gewuenschte_spalten)
                return

            # Gleiche Spaltenzahl, aber geänderte Höhe: Reihen nachziehen.
            neue_hoehe = self._zeilen_hoehe_berechnen(self._zeilen_aktuell)
            if neue_hoehe != self._zeilen_hoehe_aktuell:
                self._zeilen_hoehe_aktuell = neue_hoehe
                for zeile in range(self._zeilen_aktuell):
                    self._raster.grid_rowconfigure(zeile, minsize=neue_hoehe)
        except Exception:
            pass

    # -- Kachel 1: Laufwerk C: ------------------------------------------

    def _kachel_laufwerk_c_bauen(self) -> None:
        kachel = self._kachel_anlegen("Laufwerk C:", "System", "💽", theme.ACCENT_BLUE)
        self._meter_laufwerk_c = Meter(kachel.body)
        self._meter_laufwerk_c.pack(fill="both", expand=True)

        kachel.add_button("Reinigen", self._aktion_reinigung_oeffnen, primaer=True)
        kachel.add_button("Eigenschaften", lambda: self._melde(actions.shell_properties("C:\\")))

    # -- Kachel 2: Weitere Laufwerke ------------------------------------

    def _kachel_weitere_laufwerke_bauen(self) -> None:
        self._kachel_weitere = self._kachel_anlegen(
            "Weitere Laufwerke", "—", "🗄", theme.ACCENT_BLUE
        )
        # Zwei kleine Balken; nicht benötigte werden ausgeblendet.
        self._meter_weitere = [
            Meter(self._kachel_weitere.body, kompakt=True) for _ in range(2)
        ]
        for meter in self._meter_weitere:
            meter.pack(fill="x", pady=(0, 6))

        self._label_keine_weiteren = ctk.CTkLabel(
            self._kachel_weitere.body,
            text="Keine weiteren Laufwerke gefunden.",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_DIM,
        )

        self._kachel_weitere.add_button("Öffnen", self._aktion_weiteres_laufwerk_oeffnen)
        self._kachel_weitere.add_button(
            "Eigenschaften", self._aktion_weiteres_laufwerk_eigenschaften
        )

    # -- Kachel 3: Arbeitsspeicher --------------------------------------

    def _kachel_ram_bauen(self) -> None:
        self._kachel_ram = self._kachel_anlegen(
            "Arbeitsspeicher", "— GB gesamt", "🧠", theme.ACCENT_BLUE
        )
        self._meter_ram = Meter(self._kachel_ram.body)
        self._meter_ram.pack(fill="both", expand=True)

        self._kachel_ram.add_button("Task-Manager", lambda: self._melde(actions.run("taskmgr")))
        self._kachel_ram.add_button(
            "Freigeben",
            self._aktion_speicher_freigeben,
            admin_erforderlich=True,
            ist_admin=self.ist_admin,
        )

    # -- Kachel 4: CPU-Auslastung ---------------------------------------

    def _kachel_cpu_bauen(self) -> None:
        self._kachel_cpu = self._kachel_anlegen(
            "CPU-Auslastung", "— Kerne", "⚡", theme.ACCENT_BLUE
        )
        self._gauge_cpu = CircularGauge(self._kachel_cpu.body)
        self._gauge_cpu.pack(fill="both", expand=True)

        self._kachel_cpu.add_button("Task-Manager", lambda: self._melde(actions.run("taskmgr")))
        self._kachel_cpu.add_button("Top-Prozesse", self._aktion_top_prozesse)

    # -- Kachel 5: CPU-Temperatur ---------------------------------------

    def _kachel_cpu_temp_bauen(self) -> None:
        self._kachel_cpu_temp = self._kachel_anlegen(
            "CPU-Temperatur", "Package", "🌡", theme.ACCENT_BLUE
        )
        self._gauge_cpu_temp = CircularGauge(self._kachel_cpu_temp.body)
        self._gauge_cpu_temp.pack(fill="both", expand=True)

        self._kachel_cpu_temp.add_button(
            "Verlauf",
            lambda: self._aktion_temperatur_verlauf(
                "CPU-Temperatur", system_info.VERLAUF_CPU_TEMP
            ),
        )
        self._kachel_cpu_temp.add_button(
            "Warnschwelle", lambda: self._aktion_warnschwelle("cpu")
        )

    # -- Kachel 6a: GPU-Temperatur (Desktop) ----------------------------

    def _kachel_gpu_temp_bauen(self) -> None:
        self._kachel_gpu_temp = self._kachel_anlegen(
            "GPU-Temperatur", "Grafikkarte", "🎮", theme.ACCENT_BLUE
        )
        self._gauge_gpu_temp = CircularGauge(self._kachel_gpu_temp.body)
        self._gauge_gpu_temp.pack(fill="both", expand=True)

        self._kachel_gpu_temp.add_button(
            "Verlauf",
            lambda: self._aktion_temperatur_verlauf(
                "GPU-Temperatur", system_info.VERLAUF_GPU_TEMP
            ),
        )
        self._kachel_gpu_temp.add_button(
            "Warnschwelle", lambda: self._aktion_warnschwelle("gpu")
        )

    # -- Kachel 6b: Akku (Laptop-Sonderfall) ----------------------------

    def _kachel_akku_bauen(self) -> None:
        self._kachel_akku = self._kachel_anlegen(
            "Akku", "Ladestand", "🔋", theme.ACCENT_BLUE
        )
        self._gauge_akku = CircularGauge(self._kachel_akku.body)
        self._gauge_akku.pack(fill="both", expand=True)

        self._kachel_akku.add_button(
            "Energieoptionen",
            lambda: self._melde(
                actions.open_settings("ms-settings:powersleep", "control powercfg.cpl")
            ),
        )

    # -- Kachel 7: Netzwerk ---------------------------------------------

    def _kachel_netzwerk_bauen(self) -> None:
        self._kachel_netz = self._kachel_anlegen(
            "Netzwerk", "—", "🌐", theme.ACCENT_PURPLE
        )
        self._stat_down = StatValue(
            self._kachel_netz.body, farbe=theme.ACCENT_BLUE, kompakt=True
        )
        self._stat_down.pack(fill="x", anchor="w", expand=True)
        self._stat_up = StatValue(
            self._kachel_netz.body, farbe=theme.ACCENT_PURPLE, kompakt=True
        )
        self._stat_up.pack(fill="x", anchor="w", expand=True)

        self._kachel_netz.add_button(
            "Einstellungen",
            lambda: self._melde(
                actions.open_settings("ms-settings:network-status", "control ncpa.cpl")
            ),
        )
        self._kachel_netz.add_button(
            "IP erneuern",
            lambda: self._melde(actions.run("ipconfig /renew")),
            admin_erforderlich=True,
            ist_admin=self.ist_admin,
        )

    # -- Kachel 8: Autostart ---------------------------------------------

    def _kachel_autostart_bauen(self) -> None:
        self._kachel_autostart = self._kachel_anlegen(
            "Autostart", "beim Hochfahren", "🚀", theme.ACCENT_PURPLE
        )
        self._stat_autostart = StatValue(
            self._kachel_autostart.body, farbe=theme.ACCENT_PURPLE
        )
        self._stat_autostart.pack(fill="both", expand=True)

        self._kachel_autostart.add_button(
            "Verwalten", lambda: self._melde(actions.run("taskmgr /7"))
        )
        self._kachel_autostart.add_button("Liste", self._aktion_autostart_liste)

    # -- Kachel 9: Papierkorb --------------------------------------------

    def _kachel_papierkorb_bauen(self) -> None:
        self._kachel_papierkorb = self._kachel_anlegen(
            "Papierkorb", "gelöschte Dateien", "🗑", theme.ACCENT_BLUE
        )
        self._stat_papierkorb = StatValue(
            self._kachel_papierkorb.body, farbe=theme.ACCENT_BLUE
        )
        self._stat_papierkorb.pack(fill="both", expand=True)

        self._kachel_papierkorb.add_button(
            "Leeren", self._aktion_papierkorb_leeren, primaer=True
        )
        self._kachel_papierkorb.add_button(
            "Öffnen", lambda: self._melde(actions.shell_open("shell:RecycleBinFolder"))
        )

    # -- Kachel 10: Temporäre Dateien -------------------------------------

    def _kachel_temp_dateien_bauen(self) -> None:
        self._kachel_temp = self._kachel_anlegen(
            "Temporäre Dateien", "%TEMP% + Windows", "📄", theme.ACCENT_YELLOW
        )
        self._stat_temp = StatValue(self._kachel_temp.body, farbe=theme.ACCENT_YELLOW)
        self._stat_temp.pack(fill="both", expand=True)

        self._kachel_temp.add_button("Löschen", self._aktion_temp_loeschen, primaer=True)
        self._kachel_temp.add_button("Reinigung öffnen", self._aktion_reinigung_oeffnen)

    # -- Kachel 11: Windows-Update ----------------------------------------

    def _kachel_windows_update_bauen(self) -> None:
        self._kachel_update = self._kachel_anlegen(
            "Windows-Update", "Status", "🔄", theme.ACCENT_BLUE
        )

        # Statuspunkt + Statustext nebeneinander.
        zeile = ctk.CTkFrame(self._kachel_update.body, fg_color="transparent")
        zeile.pack(fill="x", anchor="w", expand=True)

        import tkinter as tk

        self._update_punkt_canvas = tk.Canvas(
            zeile, width=12, height=12, highlightthickness=0, bg=theme.CARD_BG
        )
        self._update_punkt_canvas.pack(side="left", padx=(0, 8), anchor="n", pady=(3, 0))
        self._update_punkt_id = self._update_punkt_canvas.create_oval(
            1, 1, 11, 11, fill=theme.ACCENT_BLUE, outline=""
        )

        self._label_update = ctk.CTkLabel(
            zeile,
            text="—",
            font=(theme.FONT_FAMILY_UI, 13, "bold"),
            text_color=theme.TEXT_BRIGHT,
            anchor="w",
            justify="left",
            wraplength=205,
        )
        self._label_update.pack(side="left", fill="x", expand=True)

        self._kachel_update.add_button(
            "Nach Updates suchen",
            lambda: self._melde(
                actions.open_settings("ms-settings:windowsupdate", "usoclient StartScan")
            ),
        )

    # -- Kachel 12: System -------------------------------------------------

    def _kachel_system_bauen(self) -> None:
        self._kachel_system = self._kachel_anlegen(
            "System", "—", "🖥", theme.ACCENT_PURPLE
        )

        self._label_laufzeit = ctk.CTkLabel(
            self._kachel_system.body,
            text="—",
            font=(theme.FONT_FAMILY_MONO, 17, "bold"),
            text_color=theme.ACCENT_PURPLE,
            anchor="w",
        )
        self._label_laufzeit.pack(fill="x", anchor="w")

        self._label_hostname = ctk.CTkLabel(
            self._kachel_system.body,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        self._label_hostname.pack(fill="x", anchor="w")

        self._kachel_system.add_button(
            "Systeminfo", lambda: self._melde(actions.run("msinfo32"))
        )
        self._kachel_system.add_button("Neustart", self._aktion_neustart)

    # ------------------------------------------------------------------
    # Aktionen
    # ------------------------------------------------------------------

    def _aktion_reinigung_oeffnen(self) -> None:
        """Öffnet die modale Reinigungs-Routine (cleaning.py)."""
        try:
            cleaning.ReinigungsFenster(self, ist_admin=self.ist_admin)
        except Exception as fehler:
            self.zeige_toast(f"Reinigung konnte nicht geöffnet werden: {fehler}", "fehler")

    def _aktion_weiteres_laufwerk_oeffnen(self) -> None:
        """Öffnet ein weiteres Laufwerk; bei mehreren erst ein Auswahl-Popup."""
        laufwerk = self._weiteres_laufwerk_waehlen("Welches Laufwerk öffnen?")
        if laufwerk:
            self._melde(actions.shell_open(laufwerk))

    def _aktion_weiteres_laufwerk_eigenschaften(self) -> None:
        laufwerk = self._weiteres_laufwerk_waehlen("Eigenschaften welches Laufwerks?")
        if laufwerk:
            self._melde(actions.shell_properties(laufwerk))

    def _weiteres_laufwerk_waehlen(self, frage: str) -> Optional[str]:
        """Liefert das einzige weitere Laufwerk oder lässt den Nutzer wählen."""
        with self._daten_lock:
            laufwerke = list(self._daten.get("weitere_disks") or [])

        if not laufwerke:
            self.zeige_toast("Es wurden keine weiteren Laufwerke gefunden.", "warnung")
            return None
        if len(laufwerke) == 1:
            return laufwerke[0]["laufwerk"]

        optionen = [
            (f"{eintrag['laufwerk']}  ({eintrag['free_gb']:.0f} GB frei)", eintrag["laufwerk"])
            for eintrag in laufwerke
        ]
        dialog = AuswahlDialog(self, "Laufwerk wählen", frage, optionen)
        return dialog.warte_auf_antwort()

    def _aktion_speicher_freigeben(self) -> None:
        """Leert die Standby-Liste (Adminrechte erforderlich)."""
        self.zeige_toast("Speicher wird freigegeben …", "erfolg")

        def im_hintergrund() -> None:
            ergebnis = actions.free_standby_memory()
            self.aus_thread(lambda: self._melde(ergebnis))

        threading.Thread(target=im_hintergrund, daemon=True).start()

    def _aktion_top_prozesse(self) -> None:
        """Zeigt die 5 CPU-hungrigsten Prozesse in einem Info-Popup."""
        self.zeige_toast("Prozesse werden gemessen …", "erfolg")

        def im_hintergrund() -> None:
            prozesse = system_info.top_cpu_prozesse(5)

            def anzeigen() -> None:
                zeilen = [
                    (name, f"{wert:.1f} % CPU") for name, wert in prozesse
                ]
                InfoDialog(
                    self,
                    "Top-Prozesse (CPU)",
                    zeilen,
                    icon="⚡",
                    akzent=theme.ACCENT_BLUE,
                    leer_text="Prozessliste konnte nicht gelesen werden.",
                )

            self.aus_thread(anzeigen)

        threading.Thread(target=im_hintergrund, daemon=True).start()

    def _aktion_temperatur_verlauf(self, titel: str, puffer) -> None:
        """Öffnet den Mini-Verlaufsgraph für eine Temperatur-Kachel."""
        VerlaufsDialog(
            self,
            f"{titel} · Verlauf",
            list(puffer),
            einheit="°C",
            akzent=theme.ACCENT_BLUE,
        )

    def _aktion_warnschwelle(self, welche: str) -> None:
        """Lässt den Nutzer die Warnschwelle einer Temperatur-Kachel setzen."""
        ist_cpu = welche == "cpu"
        aktueller_wert = self._warnschwelle_cpu if ist_cpu else self._warnschwelle_gpu
        bezeichnung = "CPU" if ist_cpu else "GPU"

        dialog = EingabeDialog(
            self,
            f"Warnschwelle {bezeichnung}",
            f"Ab welcher {bezeichnung}-Temperatur soll die Kachel warnen? "
            "Oberhalb der Schwelle färbt sie sich lila und zeigt ein Warnzeichen.",
            startwert=aktueller_wert,
        )
        neuer_wert = dialog.warte_auf_antwort()
        if neuer_wert is None:
            return

        if ist_cpu:
            self._warnschwelle_cpu = float(neuer_wert)
        else:
            self._warnschwelle_gpu = float(neuer_wert)
        self.zeige_toast(
            f"Warnschwelle {bezeichnung} auf {neuer_wert:.0f} °C gesetzt.", "erfolg"
        )

    def _aktion_autostart_liste(self) -> None:
        """Zeigt alle Autostart-Einträge mit Name und Pfad."""
        with self._daten_lock:
            eintraege = list(self._daten.get("autostart") or [])
        InfoDialog(
            self,
            "Autostart-Einträge",
            eintraege,
            icon="🚀",
            akzent=theme.ACCENT_PURPLE,
            leer_text="Keine Autostart-Einträge gefunden.",
        )

    def _aktion_papierkorb_leeren(self) -> None:
        """Leert den Papierkorb nach eigener Sicherheitsabfrage."""
        with self._daten_lock:
            papierkorb = self._daten.get("papierkorb")

        if papierkorb and papierkorb["anzahl"] == 0:
            self.zeige_toast("Der Papierkorb ist bereits leer.", "warnung")
            return

        beschreibung = "Alle Objekte im Papierkorb werden endgültig gelöscht."
        if papierkorb:
            mb = papierkorb["bytes"] / (1024 ** 2)
            beschreibung = (
                f"{papierkorb['anzahl']} Objekte ({mb:.1f} MB) werden endgültig "
                "gelöscht. Dieser Vorgang lässt sich nicht rückgängig machen."
            )

        dialog = BestaetigungsDialog(
            self, "Papierkorb leeren", beschreibung, bestaetigen_text="Endgültig leeren"
        )
        if dialog.warte_auf_antwort() is not True:
            return

        ergebnis = actions.empty_recycle_bin()
        self._melde(ergebnis)
        system_info.cache_leeren()
        self._manuelle_aktualisierung(still=True)

    def _aktion_temp_loeschen(self) -> None:
        """Löscht den Inhalt von %TEMP% nach Sicherheitsabfrage."""
        dialog = BestaetigungsDialog(
            self,
            "Temporäre Dateien löschen",
            "Der Inhalt von %TEMP% wird gelöscht. Dateien, die gerade in "
            "Benutzung sind, werden dabei übersprungen. Benutzerdaten sind "
            "davon nicht betroffen.",
            bestaetigen_text="Jetzt löschen",
        )
        if dialog.warte_auf_antwort() is not True:
            return

        self.zeige_toast("Temporäre Dateien werden gelöscht …", "erfolg")

        def im_hintergrund() -> None:
            ergebnis = actions.delete_temp_files()

            def fertig() -> None:
                self._melde(ergebnis)
                system_info.cache_leeren()
                self._manuelle_aktualisierung(still=True)

            self.aus_thread(fertig)

        threading.Thread(target=im_hintergrund, daemon=True).start()

    def _aktion_neustart(self) -> None:
        """Fährt den Rechner nach Sicherheitsabfrage neu hoch."""
        dialog = BestaetigungsDialog(
            self,
            "Windows neu starten",
            "Der Computer wird sofort neu gestartet. Bitte speichern Sie "
            "vorher alle offenen Arbeiten.",
            bestaetigen_text="Jetzt neu starten",
        )
        if dialog.warte_auf_antwort() is not True:
            return
        self._melde(actions.run("shutdown /r /t 0"))

    def neu_starten_als_admin(self) -> None:
        """Startet die App mit Adminrechten neu (Klick auf die Rechte-Pille)."""
        dialog = BestaetigungsDialog(
            self,
            "Als Administrator neu starten",
            "Die Anwendung wird beendet und mit Administratorrechten neu "
            "gestartet. Windows fragt dabei nach Ihrer Bestätigung.",
            bestaetigen_text="Neu starten",
            gefaehrlich=False,
        )
        if dialog.warte_auf_antwort() is not True:
            return
        self._melde(actions.restart_as_admin())

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

    def aus_thread(self, funktion: Callable[[], None]) -> None:
        """Von Nebenthreads aufzurufen: reicht eine GUI-Aktion sicher weiter."""
        self._gui_queue.put(funktion)

    def _gui_tick(self) -> None:
        """Läuft im Main-Thread: Werte übernehmen und Thread-Aufträge abarbeiten."""
        # 1) Aufträge aus Nebenthreads abarbeiten (Toasts, Popups).
        while True:
            try:
                funktion = self._gui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                funktion()
            except Exception:
                continue

        # 2) Aktuelle Messwerte in die Kacheln schreiben.
        with self._daten_lock:
            daten = dict(self._daten)
        self._kacheln_aktualisieren(daten)

        self.after(500, self._gui_tick)

    def _kacheln_aktualisieren(self, daten: dict) -> None:
        """Verteilt neue Werte auf die Kacheln - jede einzeln abgesichert."""
        # Jede Kachel bekommt ihren eigenen try/except-Block, damit ein
        # Fehler in einer Kachel die übrigen nicht mitreißt.
        for aktualisieren in (
            self._update_laufwerk_c,
            self._update_weitere_laufwerke,
            self._update_ram,
            self._update_cpu,
            self._update_temperaturen,
            self._update_netzwerk,
            self._update_autostart,
            self._update_papierkorb,
            self._update_temp_dateien,
            self._update_windows_update,
            self._update_system,
        ):
            try:
                aktualisieren(daten)
            except Exception:
                continue

    def _update_laufwerk_c(self, daten: dict) -> None:
        disk = daten.get("disk_c")
        if disk is None:
            self._meter_laufwerk_c.set_value(None, "—")
            return
        self._meter_laufwerk_c.set_value(
            disk["percent"],
            f"{disk['used_gb']:.0f} GB belegt",
            f"{disk['free_gb']:.0f} GB frei",
        )

    def _update_weitere_laufwerke(self, daten: dict) -> None:
        laufwerke = daten.get("weitere_disks") or []

        # Ein-/Ausblenden der Balken nur bei Änderung der Laufwerksanzahl -
        # pack()/pack_forget() bei jedem Tick würde sichtbar flackern.
        sichtbar = min(len(laufwerke), len(self._meter_weitere))
        if sichtbar != getattr(self, "_weitere_sichtbar", -1):
            self._weitere_sichtbar = sichtbar
            self._label_keine_weiteren.pack_forget()
            for index, meter in enumerate(self._meter_weitere):
                meter.pack_forget()
                if index < sichtbar:
                    meter.pack(fill="x", pady=(0, 6))
            if sichtbar == 0:
                self._label_keine_weiteren.pack(expand=True)

        if not laufwerke:
            self._kachel_weitere.set_untertitel("keine gefunden")
            return

        for index in range(sichtbar):
            eintrag = laufwerke[index]
            meter = self._meter_weitere[index]
            meter.set_titel(eintrag["laufwerk"].rstrip("\\"))
            meter.set_value(
                eintrag["percent"],
                f"{eintrag['percent']:.0f} %",
                f"{eintrag['free_gb']:.0f} GB frei",
            )

        namen = " · ".join(eintrag["laufwerk"].rstrip("\\") for eintrag in laufwerke)
        self._kachel_weitere.set_untertitel(namen)

    def _update_ram(self, daten: dict) -> None:
        ram = daten.get("ram")
        if ram is None:
            self._meter_ram.set_value(None, "—")
            return
        self._meter_ram.set_value(
            ram["percent"],
            f"{ram['used_gb']:.1f} GB belegt",
            f"{ram['total_gb'] - ram['used_gb']:.1f} GB frei",
        )
        self._kachel_ram.set_untertitel(f"{ram['total_gb']:.0f} GB gesamt")

    def _update_cpu(self, daten: dict) -> None:
        cpu = daten.get("cpu")
        if cpu is None:
            self._gauge_cpu.set_value(None, "—", na=True)
            return
        self._gauge_cpu.set_value(
            cpu["percent"],
            f"{cpu['percent']:.0f} %",
            meta_oben=f"Ø 60 s: {cpu['avg60']:.0f} %",
            meta_unten=f"Spitze: {cpu['peak60']:.0f} %",
        )
        self._kachel_cpu.set_untertitel(f"{cpu['kerne']} Kerne")

    def _update_temperaturen(self, daten: dict) -> None:
        temps = daten.get("temps") or {}

        # CPU-Temperatur
        self._temperatur_kachel_setzen(
            kachel=self._kachel_cpu_temp,
            gauge=self._gauge_cpu_temp,
            celsius=temps.get("cpu"),
            schwelle=self._warnschwelle_cpu,
        )

        # GPU-Temperatur (nur auf Desktops - sonst steht dort die Akku-Kachel).
        if self._hat_akku:
            self._update_akku(daten)
        else:
            self._temperatur_kachel_setzen(
                kachel=self._kachel_gpu_temp,
                gauge=self._gauge_gpu_temp,
                celsius=temps.get("gpu"),
                schwelle=self._warnschwelle_gpu,
            )

    def _temperatur_kachel_setzen(
        self, kachel: Tile, gauge: CircularGauge, celsius: Optional[float], schwelle: float
    ) -> None:
        """Gemeinsame Anzeige-Logik der beiden Temperatur-Kacheln."""
        if celsius is None:
            # Kein Sensor: "n/a", grauer Ring, Buttons deaktiviert.
            gauge.set_value(None, "n/a", meta_oben="Kein Sensor",
                            meta_unten="DLL fehlt?", na=True)
            kachel.set_akzent(theme.DISABLED_GRAY)
            kachel.set_warnung(False)
            kachel.set_button_zustand(0, False)
            kachel.set_button_zustand(1, False)
            return

        farbe = theme.temp_color(celsius, schwelle)
        ueberschritten = celsius > schwelle

        gauge.set_value(
            celsius,  # Ring-Prozent = Temperatur / 100
            f"{celsius:.0f} °C",
            meta_oben=f"Warnung ab {schwelle:.0f} °C",
            meta_unten="Überschritten!" if ueberschritten else "Normalbereich",
            farbe=farbe,
        )
        kachel.set_akzent(farbe)
        kachel.set_warnung(ueberschritten)
        kachel.set_button_zustand(0, True)
        kachel.set_button_zustand(1, True)

    def _update_akku(self, daten: dict) -> None:
        akku = daten.get("akku")
        if akku is None:
            self._gauge_akku.set_value(None, "n/a", na=True)
            return
        farbe = theme.status_color(100 - akku["percent"])  # wenig Akku = kritisch
        self._gauge_akku.set_value(
            akku["percent"],
            f"{akku['percent']:.0f} %",
            meta_oben="Netzbetrieb" if akku["netzbetrieb"] else "Akkubetrieb",
            meta_unten=akku["restzeit"],
            farbe=farbe,
        )
        self._kachel_akku.set_akzent(farbe)

    def _update_netzwerk(self, daten: dict) -> None:
        netz = daten.get("netz")
        if netz is None:
            self._stat_down.set_value("↓ —", "MB/s Download")
            self._stat_up.set_value("↑ —", "MB/s Upload")
            return
        # Pfeile statt Unterzeilen: so passen beide Werte sicher in die Kachel.
        self._stat_down.set_value(f"↓ {netz['down_mbs']:.2f}", "MB/s Download")
        self._stat_up.set_value(f"↑ {netz['up_mbs']:.2f}", "MB/s Upload")
        self._kachel_netz.set_untertitel(netz["ip"])

    def _update_autostart(self, daten: dict) -> None:
        eintraege = daten.get("autostart")
        if eintraege is None:
            self._stat_autostart.set_value("—", "", "Einträge")
            return
        self._stat_autostart.set_value(
            str(len(eintraege)), "Einträge", "Registry + Autostart-Ordner"
        )

    def _update_papierkorb(self, daten: dict) -> None:
        papierkorb = daten.get("papierkorb")
        if papierkorb is None:
            self._stat_papierkorb.set_value("—", "", "nicht lesbar")
            return
        mb = papierkorb["bytes"] / (1024 ** 2)
        if mb >= 1024:
            zahl, einheit = f"{mb / 1024:.1f}", "GB"
        else:
            zahl, einheit = f"{mb:.0f}", "MB"
        self._stat_papierkorb.set_value(
            zahl, einheit, f"{papierkorb['anzahl']} Objekte"
        )

    def _update_temp_dateien(self, daten: dict) -> None:
        bytes_gesamt = daten.get("temp_bytes")
        if bytes_gesamt is None:
            self._stat_temp.set_value("—", "", "nicht lesbar")
            return
        mb = bytes_gesamt / (1024 ** 2)
        if mb >= 1024:
            zahl, einheit = f"{mb / 1024:.1f}", "GB"
        else:
            zahl, einheit = f"{mb:.0f}", "MB"
        self._stat_temp.set_value(zahl, einheit, "belegt durch Temp-Dateien")

    @staticmethod
    def _label_text_setzen(label, text: str) -> None:
        """Schreibt ein Label nur bei tatsächlicher Änderung (kein Flackern)."""
        try:
            if label.cget("text") != text:
                label.configure(text=text)
        except Exception:
            pass

    def _update_windows_update(self, daten: dict) -> None:
        update = daten.get("update")
        if update is None:
            return
        self._label_text_setzen(self._label_update, update["text"])
        farbe = theme.ACCENT_BLUE if update["ok"] else theme.ACCENT_YELLOW
        if farbe != getattr(self, "_update_punkt_farbe", None):
            self._update_punkt_farbe = farbe
            self._update_punkt_canvas.itemconfigure(self._update_punkt_id, fill=farbe)
        self._kachel_update.set_akzent(farbe)

    def _update_system(self, daten: dict) -> None:
        system = daten.get("system")
        if system is None:
            return
        self._label_text_setzen(self._label_laufzeit, system["laufzeit"])
        self._label_text_setzen(
            self._label_hostname, f"Laufzeit · {system['hostname']}"
        )
        self._kachel_system.set_untertitel(system["os_name"])

    def _manuelle_aktualisierung(self, still: bool = False) -> None:
        """Erzwingt ein sofortiges Neuladen aller Werte (auch der gecachten)."""

        def sofort_laden() -> None:
            try:
                system_info.cache_leeren()
                neue_daten = system_info.snapshot()
            except Exception:
                neue_daten = {}
            with self._daten_lock:
                self._daten = neue_daten

        threading.Thread(target=sofort_laden, daemon=True).start()
        if not still:
            self.zeige_toast("Alle Kacheln werden neu geladen.", "erfolg")

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
