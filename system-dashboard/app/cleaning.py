"""
cleaning.py - Reinigungs-Routine als eigenes, modales Fenster.

Ablauf in drei Schritten: Analysieren -> Auswählen -> Löschen.
Analyse und Löschvorgang laufen in Hintergrund-Threads, alle
GUI-Updates werden über after(...) in den Main-Thread zurückgereicht.

SICHERHEITSREGELN (streng eingehalten):
- Es werden ausschließlich die unten als Konstanten definierten Cache-
  und Temp-Pfade angefasst. Benutzerdaten (Downloads, Dokumente, Bilder,
  Browser-Historie, Programmdateien) werden NIEMALS berührt.
- Jede Datei und jeder Ordner wird einzeln in try/except gelöscht;
  gesperrte oder gerade benutzte Dateien werden übersprungen, nicht
  abgebrochen.
- Existiert ein Pfad nicht, wird er still übersprungen.
"""

from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

import customtkinter as ctk

from . import actions, theme
from .widgets.dialogs import BestaetigungsDialog

# ---------------------------------------------------------------------------
# Pfad-Konstanten - hier zentral anpassbar
# ---------------------------------------------------------------------------

PFAD_TEMP_BENUTZER = os.environ.get("TEMP", "")
PFAD_TEMP_WINDOWS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")
PFAD_THUMBNAIL_CACHE = os.path.expandvars(
    r"%LocalAppData%\Microsoft\Windows\Explorer"
)
THUMBNAIL_DATEIMUSTER = "thumbcache_"
PFAD_UPDATE_CACHE = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"), "SoftwareDistribution", "Download"
)
PFAD_DELIVERY_OPTIMIZATION = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"),
    "ServiceProfiles",
    "NetworkService",
    "AppData",
    "Local",
    "Microsoft",
    "Windows",
    "DeliveryOptimization",
    "Cache",
)

# Dienstname des Windows-Update-Dienstes (muss zum Leeren gestoppt werden).
DIENST_WINDOWS_UPDATE = "wuauserv"


@dataclass
class Kategorie:
    """Eine bereinigbare Kategorie mit Analyse-Ergebnis und Auswahl-Zustand."""

    schluessel: str
    name: str
    pfad_hinweis: str
    admin_noetig: bool = False
    erweitert: bool = False
    standard_aktiv: bool = False

    # Von der Analyse gefüllt:
    groesse_bytes: int = 0
    analysiert: bool = False

    # GUI-Elemente (erst beim Aufbau gesetzt):
    checkbox_variable: Optional[ctk.BooleanVar] = field(default=None, repr=False)
    groessen_label: Optional[ctk.CTkLabel] = field(default=None, repr=False)


def _kategorien_erzeugen() -> list[Kategorie]:
    """Baut die Kategorie-Liste laut Spezifikation auf."""
    return [
        Kategorie(
            schluessel="temp_benutzer",
            name="Temporäre Dateien (Benutzer)",
            pfad_hinweis="%TEMP%",
            standard_aktiv=True,
        ),
        Kategorie(
            schluessel="temp_windows",
            name="Temporäre Dateien (Windows)",
            pfad_hinweis=PFAD_TEMP_WINDOWS,
            admin_noetig=True,
        ),
        Kategorie(
            schluessel="papierkorb",
            name="Papierkorb",
            pfad_hinweis="Alle Laufwerke",
            standard_aktiv=True,
        ),
        Kategorie(
            schluessel="thumbnails",
            name="Miniaturansichten-Cache",
            pfad_hinweis=r"%LocalAppData%\…\Explorer\thumbcache_*.db",
            standard_aktiv=True,
        ),
        Kategorie(
            schluessel="update_cache",
            name="Windows-Update-Cache",
            pfad_hinweis=PFAD_UPDATE_CACHE,
            admin_noetig=True,
            erweitert=True,
        ),
        Kategorie(
            schluessel="delivery_optimization",
            name="Delivery-Optimization-Dateien",
            pfad_hinweis="Übermittlungsoptimierung (cleanmgr)",
            admin_noetig=True,
            erweitert=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Analyse: wie viel Platz würde je Kategorie frei?
# ---------------------------------------------------------------------------


def _thumbnail_dateien() -> list[str]:
    """Alle thumbcache_*.db-Dateien im Explorer-Cache-Ordner."""
    treffer: list[str] = []
    try:
        if not os.path.isdir(PFAD_THUMBNAIL_CACHE):
            return treffer
        for eintrag in os.scandir(PFAD_THUMBNAIL_CACHE):
            if (
                eintrag.is_file()
                and eintrag.name.lower().startswith(THUMBNAIL_DATEIMUSTER)
                and eintrag.name.lower().endswith(".db")
            ):
                treffer.append(eintrag.path)
    except Exception:
        pass
    return treffer


def analysiere_kategorie(kategorie: Kategorie) -> int:
    """Ermittelt die freigebbare Größe einer Kategorie in Bytes."""
    try:
        if kategorie.schluessel == "temp_benutzer":
            return actions._ordner_groesse_leise(PFAD_TEMP_BENUTZER)

        if kategorie.schluessel == "temp_windows":
            return actions._ordner_groesse_leise(PFAD_TEMP_WINDOWS)

        if kategorie.schluessel == "papierkorb":
            ergebnis = actions.recycle_bin_size()
            return ergebnis[0] if ergebnis else 0

        if kategorie.schluessel == "thumbnails":
            summe = 0
            for pfad in _thumbnail_dateien():
                try:
                    summe += os.path.getsize(pfad)
                except Exception:
                    pass
            return summe

        if kategorie.schluessel == "update_cache":
            return actions._ordner_groesse_leise(PFAD_UPDATE_CACHE)

        if kategorie.schluessel == "delivery_optimization":
            return actions._ordner_groesse_leise(PFAD_DELIVERY_OPTIMIZATION)
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# Löschen einer Kategorie
# ---------------------------------------------------------------------------


def bereinige_kategorie(kategorie: Kategorie) -> tuple[int, int, int]:
    """Bereinigt eine Kategorie defensiv.

    Rückgabe: (freigegebene Bytes, gelöschte Einträge, übersprungene Einträge).
    Gesperrte Dateien werden übersprungen; ein Fehler bricht nie ab.
    """
    try:
        if kategorie.schluessel == "temp_benutzer":
            return actions.leere_ordner_inhalt(PFAD_TEMP_BENUTZER)

        if kategorie.schluessel == "temp_windows":
            return actions.leere_ordner_inhalt(PFAD_TEMP_WINDOWS)

        if kategorie.schluessel == "papierkorb":
            vorher = actions.recycle_bin_size()
            groesse = vorher[0] if vorher else 0
            anzahl = vorher[1] if vorher else 0
            erfolg, _ = actions.empty_recycle_bin()
            if erfolg:
                return groesse, anzahl, 0
            return 0, 0, anzahl

        if kategorie.schluessel == "thumbnails":
            freigegeben = 0
            geloescht = 0
            uebersprungen = 0
            for pfad in _thumbnail_dateien():
                try:
                    groesse = os.path.getsize(pfad)
                    os.remove(pfad)
                    freigegeben += groesse
                    geloescht += 1
                except Exception:
                    # Der Explorer hält die Cache-Dateien meist offen -
                    # das ist normal und kein Grund abzubrechen.
                    uebersprungen += 1
            return freigegeben, geloescht, uebersprungen

        if kategorie.schluessel == "update_cache":
            # Der Update-Dienst muss den Ordner erst freigeben.
            actions.run_und_warten(f"net stop {DIENST_WINDOWS_UPDATE}", timeout=45)
            ergebnis = actions.leere_ordner_inhalt(PFAD_UPDATE_CACHE)
            actions.run_und_warten(f"net start {DIENST_WINDOWS_UPDATE}", timeout=45)
            return ergebnis

        if kategorie.schluessel == "delivery_optimization":
            return actions.leere_ordner_inhalt(PFAD_DELIVERY_OPTIMIZATION)
    except Exception:
        pass
    return 0, 0, 0


def formatiere_groesse(bytes_wert: int) -> str:
    """Formatiert eine Byte-Größe menschenlesbar als MB oder GB."""
    mb = bytes_wert / (1024 ** 2)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    if mb >= 1:
        return f"{mb:.1f} MB"
    kb = bytes_wert / 1024
    return f"{kb:.0f} KB" if kb >= 1 else "0 KB"


# ---------------------------------------------------------------------------
# Das Reinigungs-Fenster
# ---------------------------------------------------------------------------


class ReinigungsFenster(ctk.CTkToplevel):
    """Modales Fenster mit Analyse, Auswahl, Fortschritt und Zusammenfassung."""

    def __init__(self, master, ist_admin: bool, vorauswahl_laufwerk: str = "C:\\") -> None:
        super().__init__(master)

        self.ist_admin = ist_admin
        self._vorauswahl_laufwerk = vorauswahl_laufwerk
        self._kategorien = _kategorien_erzeugen()
        self._laeuft = False
        # Signalisiert den Hintergrund-Threads, dass das Fenster zu ist.
        # Wichtig: Tkinter-Aufrufe (auch winfo_exists oder after) dürfen
        # NICHT aus einem Nebenthread erfolgen - daher dieses Event ...
        self._geschlossen = threading.Event()
        # ... und diese Warteschlange: Nebenthreads legen GUI-Aktionen
        # hier ab, der Main-Thread arbeitet sie in _queue_tick() ab.
        self._gui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()

        self.title("Reinigungs-Routine")
        self.geometry("620x680")
        self.minsize(560, 600)
        self.configure(fg_color=theme.BG_DARK)
        self.transient(master)
        self._zentrieren(master, 620, 680)
        self.after(50, self._modal_machen)
        self.protocol("WM_DELETE_WINDOW", self._schliessen_versuchen)

        self._aufbauen()
        # Poller im Main-Thread starten, bevor der erste Thread loslegt.
        self._queue_tick()
        self._analyse_starten()

    def _modal_machen(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _zentrieren(self, master, breite: int, hoehe: int) -> None:
        """Positioniert das Fenster mittig über dem Hauptfenster."""
        try:
            master.update_idletasks()
            x = master.winfo_rootx() + (master.winfo_width() - breite) // 2
            y = master.winfo_rooty() + (master.winfo_height() - hoehe) // 3
            self.geometry(f"{breite}x{hoehe}+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _im_main_thread(self, funktion: Callable[[], None]) -> None:
        """Reicht eine GUI-Aktualisierung aus einem Nebenthread sicher weiter.

        Tkinter ist nicht thread-sicher - selbst after() ist bereits ein
        Tcl-Aufruf und darf nicht aus einem Nebenthread kommen. Deshalb
        wandert die Funktion nur in die Warteschlange; ausgeführt wird sie
        vom Main-Thread in _queue_tick().
        """
        if self._geschlossen.is_set():
            return
        self._gui_queue.put(funktion)

    def _queue_tick(self) -> None:
        """Läuft im Main-Thread: arbeitet die Warteschlange der Threads ab."""
        while True:
            try:
                funktion = self._gui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                funktion()
            except Exception:
                # Eine fehlerhafte Einzelaktualisierung darf den Poller
                # nicht stoppen.
                continue

        if not self._geschlossen.is_set():
            try:
                self.after(80, self._queue_tick)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------

    def _aufbauen(self) -> None:
        rahmen = ctk.CTkFrame(
            self,
            fg_color=theme.CARD_BG,
            corner_radius=16,
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        rahmen.pack(fill="both", expand=True, padx=12, pady=12)

        # --- Kopf -------------------------------------------------------
        kopf = ctk.CTkFrame(rahmen, fg_color="transparent")
        kopf.pack(fill="x", padx=18, pady=(16, 4))

        ctk.CTkLabel(
            kopf,
            text=f"🧹  Reinigungs-Routine · Laufwerk {self._vorauswahl_laufwerk.rstrip(chr(92))}",
            font=(theme.FONT_FAMILY_UI, 16, "bold"),
            text_color=theme.TEXT_BRIGHT,
            anchor="w",
        ).pack(fill="x")

        self._schritt_label = ctk.CTkLabel(
            kopf,
            text="Schritt 1 von 3 · Analysieren",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.ACCENT_BLUE,
            anchor="w",
        )
        self._schritt_label.pack(fill="x", pady=(2, 0))

        if not self.ist_admin:
            ctk.CTkLabel(
                kopf,
                text="🛡 Ohne Administratorrechte sind einige Kategorien gesperrt. "
                "Zum Freischalten die App als Administrator neu starten.",
                font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
                text_color=theme.ACCENT_YELLOW,
                anchor="w",
                wraplength=540,
                justify="left",
            ).pack(fill="x", pady=(8, 0))

        # --- Kategorie-Liste --------------------------------------------
        self._liste = ctk.CTkScrollableFrame(
            rahmen,
            fg_color=theme.CARD_BG_GRADIENT_END,
            corner_radius=12,
            scrollbar_button_color=theme.CARD_BORDER,
            scrollbar_button_hover_color=theme.ACCENT_BLUE,
        )
        self._liste.pack(fill="both", expand=True, padx=18, pady=(14, 10))

        self._kategorie_zeilen_bauen()

        # --- Summenzeile -------------------------------------------------
        self._summen_label = ctk.CTkLabel(
            rahmen,
            text="Analysiere …",
            font=(theme.FONT_FAMILY_UI, 14, "bold"),
            text_color=theme.TEXT_BRIGHT,
            anchor="w",
        )
        self._summen_label.pack(fill="x", padx=18, pady=(0, 8))

        # --- Fortschrittsbalken (erst beim Löschen sichtbar) ------------
        self._fortschritt = ctk.CTkProgressBar(
            rahmen,
            height=10,
            corner_radius=5,
            fg_color=theme.TRACK_GRAY,
            progress_color=theme.ACCENT_BLUE,
        )
        self._fortschritt.set(0)

        self._fortschritt_label = ctk.CTkLabel(
            rahmen,
            text="",
            font=(theme.FONT_FAMILY_MONO, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )

        # --- Buttonleiste --------------------------------------------------
        leiste = ctk.CTkFrame(rahmen, fg_color="transparent")
        leiste.pack(fill="x", padx=18, pady=(0, 16))

        self._button_datentraeger = self._button_bauen(
            leiste, "Windows-Datenträgerbereinigung", self._aktion_cleanmgr
        )
        self._button_datentraeger.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._button_schliessen = self._button_bauen(
            leiste, "Schließen", self._schliessen_versuchen
        )
        self._button_schliessen.pack(side="left", padx=(0, 8))

        self._button_start = self._button_bauen(
            leiste, "Bereinigen starten", self._bereinigung_starten, primaer=True
        )
        self._button_start.pack(side="left", fill="x", expand=True)
        self._button_start.configure(state="disabled")

    def _button_bauen(
        self, master, text: str, befehl: Callable[[], None], primaer: bool = False
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            master,
            text=text,
            command=befehl,
            width=1,
            height=36,
            corner_radius=10,
            fg_color=theme.BUTTON_PRIMARY_BG if primaer else theme.BUTTON_SECONDARY_BG,
            hover_color=theme.BUTTON_PRIMARY_HOVER if primaer else theme.BUTTON_SECONDARY_BG,
            border_width=1,
            border_color=theme.ACCENT_BLUE if primaer else theme.BUTTON_SECONDARY_BORDER,
            text_color=theme.TEXT_BRIGHT if primaer else theme.TEXT_MUTED,
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
        )

    def _kategorie_zeilen_bauen(self) -> None:
        """Erzeugt pro Kategorie eine Zeile mit Checkbox, Pfad und Größe."""
        erweitert_ueberschrift_gesetzt = False

        for kategorie in self._kategorien:
            # Optische Trennung der "erweiterten" Kategorien.
            if kategorie.erweitert and not erweitert_ueberschrift_gesetzt:
                erweitert_ueberschrift_gesetzt = True
                trenner = ctk.CTkFrame(self._liste, fg_color=theme.CARD_BORDER, height=1)
                trenner.pack(fill="x", pady=(12, 8), padx=6)
                ctk.CTkLabel(
                    self._liste,
                    text="Erweitert · nur bei Bedarf aktivieren",
                    font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
                    text_color=theme.TEXT_DIM,
                    anchor="w",
                ).pack(fill="x", padx=8, pady=(0, 4))

            gesperrt = kategorie.admin_noetig and not self.ist_admin
            # Erweiterte Kategorien sind nie standardmäßig aktiv.
            aktiv = kategorie.standard_aktiv and not gesperrt and not kategorie.erweitert

            # Rechts etwas Luft lassen, damit der Scrollbalken die
            # Größenangabe nicht überdeckt.
            zeile = ctk.CTkFrame(self._liste, fg_color="transparent")
            zeile.pack(fill="x", padx=(6, 16), pady=5)

            kategorie.checkbox_variable = ctk.BooleanVar(value=aktiv)

            beschriftung = kategorie.name
            if kategorie.admin_noetig:
                beschriftung = f"🛡 {beschriftung}"

            checkbox = ctk.CTkCheckBox(
                zeile,
                text=beschriftung,
                variable=kategorie.checkbox_variable,
                command=self._summe_aktualisieren,
                font=(theme.FONT_FAMILY_UI, 12, "bold"),
                text_color=theme.TEXT_BRIGHT if not gesperrt else theme.TEXT_DIM,
                fg_color=theme.ACCENT_BLUE,
                hover_color=theme.BUTTON_PRIMARY_HOVER,
                border_color=theme.CARD_BORDER if gesperrt else theme.BUTTON_SECONDARY_BORDER,
                checkbox_width=18,
                checkbox_height=18,
                corner_radius=5,
            )
            checkbox.pack(side="left", anchor="w")
            if gesperrt:
                checkbox.configure(state="disabled")

            kategorie.groessen_label = ctk.CTkLabel(
                zeile,
                text="…",
                font=(theme.FONT_FAMILY_MONO, 12, "bold"),
                text_color=theme.TEXT_MUTED,
                anchor="e",
            )
            kategorie.groessen_label.pack(side="right")

            # Pfad-Hinweis bzw. Admin-Hinweis unter der Checkbox.
            hinweis = kategorie.pfad_hinweis
            if gesperrt:
                hinweis = f"{hinweis}  ·  Als Administrator neu starten"
            ctk.CTkLabel(
                self._liste,
                text=hinweis,
                font=(theme.FONT_FAMILY_UI_REGULAR, 10),
                text_color=theme.TEXT_DIM,
                anchor="w",
                wraplength=480,
                justify="left",
            ).pack(fill="x", padx=(32, 8), pady=(0, 2))

    # ------------------------------------------------------------------
    # Schritt 1: Analysieren
    # ------------------------------------------------------------------

    def _analyse_starten(self) -> None:
        """Berechnet die Größen aller Kategorien in einem Hintergrund-Thread."""

        def im_hintergrund() -> None:
            for kategorie in self._kategorien:
                if self._geschlossen.is_set():
                    return
                groesse = analysiere_kategorie(kategorie)
                kategorie.groesse_bytes = groesse
                kategorie.analysiert = True
                # Ergebnis im Main-Thread eintragen.
                self._im_main_thread(
                    lambda k=kategorie: self._kategorie_groesse_anzeigen(k)
                )
            self._im_main_thread(self._analyse_abgeschlossen)

        threading.Thread(target=im_hintergrund, daemon=True).start()

    def _kategorie_groesse_anzeigen(self, kategorie: Kategorie) -> None:
        try:
            if kategorie.groessen_label is not None:
                kategorie.groessen_label.configure(
                    text=formatiere_groesse(kategorie.groesse_bytes)
                )
            self._summe_aktualisieren()
        except Exception:
            pass

    def _analyse_abgeschlossen(self) -> None:
        try:
            self._schritt_label.configure(
                text="Schritt 2 von 3 · Kategorien auswählen"
            )
            self._button_start.configure(state="normal")
            self._summe_aktualisieren()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Schritt 2: Auswählen (laufende Summe)
    # ------------------------------------------------------------------

    def _gewaehlte_kategorien(self) -> list[Kategorie]:
        gewaehlt = []
        for kategorie in self._kategorien:
            try:
                if kategorie.checkbox_variable and kategorie.checkbox_variable.get():
                    gewaehlt.append(kategorie)
            except Exception:
                continue
        return gewaehlt

    def _summe_aktualisieren(self) -> None:
        """Hält die Zeile "ca. X MB werden freigegeben" aktuell."""
        try:
            summe = sum(k.groesse_bytes for k in self._gewaehlte_kategorien())
            noch_am_analysieren = any(not k.analysiert for k in self._kategorien)
            praefix = "Analysiere … bisher " if noch_am_analysieren else "ca. "
            self._summen_label.configure(
                text=f"{praefix}{formatiere_groesse(summe)} werden freigegeben"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Schritt 3: Löschen
    # ------------------------------------------------------------------

    def _bereinigung_starten(self) -> None:
        gewaehlt = self._gewaehlte_kategorien()
        if not gewaehlt:
            self._summen_label.configure(
                text="Bitte mindestens eine Kategorie auswählen."
            )
            return

        summe = sum(k.groesse_bytes for k in gewaehlt)
        namen = "\n".join(f"·  {k.name}" for k in gewaehlt)
        dialog = BestaetigungsDialog(
            self,
            "Bereinigung starten",
            f"Folgende Kategorien werden bereinigt:\n\n{namen}\n\n"
            f"Erwartet werden ca. {formatiere_groesse(summe)}. Gesperrte Dateien "
            "werden übersprungen. Benutzerdaten sind nicht betroffen.",
            bestaetigen_text="Jetzt bereinigen",
        )
        if dialog.warte_auf_antwort() is not True:
            return

        self._in_loesch_modus_wechseln()

        def im_hintergrund() -> None:
            gesamt_freigegeben = 0
            gesamt_geloescht = 0
            gesamt_uebersprungen = 0

            for index, kategorie in enumerate(gewaehlt):
                if self._geschlossen.is_set():
                    return
                self._im_main_thread(
                    lambda k=kategorie, i=index: self._fortschritt_setzen(
                        i / len(gewaehlt), f"Bereinige: {k.name} …"
                    )
                )

                freigegeben, geloescht, uebersprungen = bereinige_kategorie(kategorie)
                gesamt_freigegeben += freigegeben
                gesamt_geloescht += geloescht
                gesamt_uebersprungen += uebersprungen

                self._im_main_thread(
                    lambda i=index, g=gesamt_geloescht, u=gesamt_uebersprungen: (
                        self._fortschritt_setzen(
                            (i + 1) / len(gewaehlt),
                            f"{g} gelöscht / {u} übersprungen",
                        )
                    )
                )

            self._im_main_thread(
                lambda: self._zusammenfassung_zeigen(
                    gesamt_freigegeben, gesamt_geloescht, gesamt_uebersprungen
                )
            )

        threading.Thread(target=im_hintergrund, daemon=True).start()

    def _in_loesch_modus_wechseln(self) -> None:
        """Blendet den Fortschrittsbalken ein und sperrt die Bedienelemente."""
        self._laeuft = True
        try:
            self._schritt_label.configure(text="Schritt 3 von 3 · Wird bereinigt …")
            self._button_start.configure(state="disabled")
            self._button_datentraeger.configure(state="disabled")
            self._button_schliessen.configure(state="disabled")

            self._fortschritt.pack(fill="x", padx=18, pady=(0, 4), before=self._button_start.master)
            self._fortschritt_label.pack(
                fill="x", padx=18, pady=(0, 10), before=self._button_start.master
            )
            self._fortschritt.set(0)

            # Während des Löschens darf die Auswahl nicht mehr geändert werden.
            for kind in self._liste.winfo_children():
                if isinstance(kind, ctk.CTkFrame):
                    for enkel in kind.winfo_children():
                        if isinstance(enkel, ctk.CTkCheckBox):
                            enkel.configure(state="disabled")
        except Exception:
            pass

    def _fortschritt_setzen(self, anteil: float, text: str) -> None:
        try:
            self._fortschritt.set(max(0.0, min(1.0, anteil)))
            self._fortschritt_label.configure(text=text)
        except Exception:
            pass

    def _zusammenfassung_zeigen(
        self, freigegeben: int, geloescht: int, uebersprungen: int
    ) -> None:
        """Schlussbericht: freigegebener Platz und übersprungene Dateien."""
        self._laeuft = False
        try:
            self._fortschritt.set(1.0)
            self._schritt_label.configure(
                text="Fertig · Bereinigung abgeschlossen",
            )
            self._summen_label.configure(
                text=f"{formatiere_groesse(freigegeben)} freigegeben"
            )
            self._fortschritt_label.configure(
                text=f"{geloescht} Einträge gelöscht · {uebersprungen} übersprungen "
                "(gesperrt oder in Benutzung)"
            )
            self._button_schliessen.configure(state="normal")
            self._button_datentraeger.configure(state="normal")

            # Größen zurücksetzen, damit die Anzeige nicht veraltet wirkt.
            for kategorie in self._kategorien:
                kategorie.groesse_bytes = 0
                if kategorie.groessen_label is not None:
                    kategorie.groessen_label.configure(text="—")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Sonstiges
    # ------------------------------------------------------------------

    def _aktion_cleanmgr(self) -> None:
        """Startet die offizielle Windows-Datenträgerbereinigung."""
        laufwerk = self._vorauswahl_laufwerk.rstrip("\\")
        erfolg, meldung = actions.run(f"cleanmgr /d {laufwerk}")
        self._summen_label.configure(
            text="Windows-Datenträgerbereinigung geöffnet."
            if erfolg
            else f"Konnte nicht geöffnet werden: {meldung}"
        )

    def _schliessen_versuchen(self) -> None:
        """Verhindert das Schließen, solange ein Löschvorgang läuft."""
        if self._laeuft:
            return
        # Laufende Hintergrund-Threads informieren, bevor Widgets verschwinden.
        self._geschlossen.set()
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
