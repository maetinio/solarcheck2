"""
dialogs.py - Wiederverwendbare Dialoge im App-Farbschema.

Enthält:
- BestaetigungsDialog: Sicherheitsabfrage vor zerstörerischen Aktionen.
- InfoDialog:          Scrollbares Info-Popup (Prozessliste, Autostart-Liste).
- VerlaufsDialog:      Mini-Graph der letzten Minuten (Temperatur-Verlauf).
- EingabeDialog:       Zahleneingabe (Warnschwelle für Temperaturen).
- AuswahlDialog:       Auswahl eines Eintrags aus einer Liste (Laufwerkswahl).

Alle Dialoge sind modal (grab_set), zentrieren sich über dem Hauptfenster
und liefern ihr Ergebnis über das Attribut `ergebnis` zurück, nachdem
`warte_auf_antwort()` zurückgekehrt ist.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional, Sequence

import customtkinter as ctk

from .. import theme


class _BasisDialog(ctk.CTkToplevel):
    """Gemeinsame Grundlage aller Dialoge: dunkles Fenster, modal, zentriert."""

    def __init__(self, master, titel: str, breite: int = 420, hoehe: int = 240) -> None:
        super().__init__(master)
        self.ergebnis = None

        self.title(titel)
        self.geometry(f"{breite}x{hoehe}")
        self.minsize(320, 180)
        self.configure(fg_color=theme.BG_DARK)
        self.resizable(False, False)

        # Modal machen und über dem Hauptfenster zentrieren.
        self.transient(master)
        self._zentrieren(master, breite, hoehe)
        # grab_set erst nach dem Sichtbarwerden, sonst schlägt es unter
        # manchen Window-Managern fehl.
        self.after(50, self._modal_machen)

        self.protocol("WM_DELETE_WINDOW", self._abbrechen)

        self.rahmen = ctk.CTkFrame(
            self,
            fg_color=theme.CARD_BG,
            corner_radius=16,
            border_width=1,
            border_color=theme.CARD_BORDER,
        )
        self.rahmen.pack(fill="both", expand=True, padx=12, pady=12)

    def _modal_machen(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _zentrieren(self, master, breite: int, hoehe: int) -> None:
        """Positioniert den Dialog mittig über dem Hauptfenster."""
        try:
            master.update_idletasks()
            x = master.winfo_rootx() + (master.winfo_width() - breite) // 2
            y = master.winfo_rooty() + (master.winfo_height() - hoehe) // 3
            self.geometry(f"{breite}x{hoehe}+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _abbrechen(self) -> None:
        self.ergebnis = None
        self._schliessen()

    def _schliessen(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def warte_auf_antwort(self):
        """Blockiert, bis der Dialog geschlossen ist, und liefert das Ergebnis."""
        try:
            self.wait_window()
        except Exception:
            pass
        return self.ergebnis

    # -- gemeinsame Bausteine -------------------------------------------

    def _titelzeile(self, icon: str, titel: str, akzent: str) -> None:
        kopf = ctk.CTkFrame(self.rahmen, fg_color="transparent")
        kopf.pack(fill="x", padx=18, pady=(16, 8))

        ctk.CTkLabel(
            kopf,
            text=f"{icon}  {titel}",
            font=(theme.FONT_FAMILY_UI, 15, "bold"),
            text_color=akzent,
            anchor="w",
        ).pack(fill="x")

    def _button(
        self,
        master,
        text: str,
        befehl: Callable[[], None],
        primaer: bool = False,
        warnfarbe: Optional[str] = None,
    ) -> ctk.CTkButton:
        if primaer:
            fg = theme.BUTTON_PRIMARY_BG
            hover = theme.BUTTON_PRIMARY_HOVER
            rand = warnfarbe or theme.BUTTON_PRIMARY_BORDER
            textfarbe = theme.TEXT_BRIGHT
        else:
            fg = theme.BUTTON_SECONDARY_BG
            hover = theme.BUTTON_SECONDARY_BG
            rand = theme.BUTTON_SECONDARY_BORDER
            textfarbe = theme.TEXT_MUTED

        return ctk.CTkButton(
            master,
            text=text,
            command=befehl,
            width=1,
            height=38,
            corner_radius=10,
            fg_color=fg,
            hover_color=hover,
            border_width=1,
            border_color=rand,
            text_color=textfarbe,
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
        )


class BestaetigungsDialog(_BasisDialog):
    """Sicherheitsabfrage vor zerstörerischen Aktionen (Ergebnis: True/None)."""

    def __init__(
        self,
        master,
        titel: str,
        nachricht: str,
        bestaetigen_text: str = "Fortfahren",
        gefaehrlich: bool = True,
    ) -> None:
        # Höhe an die Textlänge anpassen: bei langen Nachrichten (z. B. der
        # Kategorienliste der Reinigung) würden die Buttons sonst
        # zusammengequetscht. Grobe Schätzung: 50 Zeichen je umbrochener Zeile.
        zeilen = sum(
            max(1, len(zeile) // 50 + 1) for zeile in nachricht.split("\n")
        )
        hoehe = max(225, min(460, 155 + 19 * zeilen))
        super().__init__(master, titel, breite=440, hoehe=hoehe)

        akzent = theme.ACCENT_YELLOW if gefaehrlich else theme.ACCENT_BLUE
        self._titelzeile("⚠" if gefaehrlich else "ℹ", titel, akzent)

        ctk.CTkLabel(
            self.rahmen,
            text=nachricht,
            font=(theme.FONT_FAMILY_UI_REGULAR, 12),
            text_color=theme.TEXT_MUTED,
            wraplength=380,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 16))

        leiste = ctk.CTkFrame(self.rahmen, fg_color="transparent")
        leiste.pack(fill="x", side="bottom", padx=18, pady=(0, 16))

        self._button(leiste, "Abbrechen", self._abbrechen).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        self._button(
            leiste,
            bestaetigen_text,
            self._bestaetigen,
            primaer=True,
            warnfarbe=akzent if gefaehrlich else None,
        ).pack(side="left", fill="x", expand=True)

    def _bestaetigen(self) -> None:
        self.ergebnis = True
        self._schliessen()


class InfoDialog(_BasisDialog):
    """Scrollbares Info-Popup mit Zeilen aus (Titel, Detail)-Paaren."""

    def __init__(
        self,
        master,
        titel: str,
        zeilen: Sequence[tuple[str, str]],
        icon: str = "ℹ",
        akzent: str = theme.ACCENT_BLUE,
        leer_text: str = "Keine Einträge gefunden.",
    ) -> None:
        super().__init__(master, titel, breite=520, hoehe=420)
        self._titelzeile(icon, titel, akzent)

        liste = ctk.CTkScrollableFrame(
            self.rahmen,
            fg_color=theme.CARD_BG_GRADIENT_END,
            corner_radius=12,
            scrollbar_button_color=theme.CARD_BORDER,
            scrollbar_button_hover_color=theme.ACCENT_BLUE,
        )
        liste.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        if not zeilen:
            ctk.CTkLabel(
                liste,
                text=leer_text,
                font=(theme.FONT_FAMILY_UI_REGULAR, 12),
                text_color=theme.TEXT_DIM,
            ).pack(pady=20)
        else:
            for name, detail in zeilen:
                eintrag = ctk.CTkFrame(liste, fg_color="transparent")
                eintrag.pack(fill="x", pady=4, padx=4)

                ctk.CTkLabel(
                    eintrag,
                    text=str(name),
                    font=(theme.FONT_FAMILY_UI, 12, "bold"),
                    text_color=theme.TEXT_BRIGHT,
                    anchor="w",
                ).pack(fill="x")

                if detail:
                    ctk.CTkLabel(
                        eintrag,
                        text=str(detail),
                        font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
                        text_color=theme.TEXT_DIM,
                        anchor="w",
                        wraplength=440,
                        justify="left",
                    ).pack(fill="x")

        self._button(self.rahmen, "Schließen", self._abbrechen).pack(
            fill="x", padx=18, pady=(0, 16)
        )


class VerlaufsDialog(_BasisDialog):
    """Popup mit einem Mini-Liniengraph der letzten Messwerte."""

    def __init__(
        self,
        master,
        titel: str,
        messwerte: Sequence[tuple[float, float]],
        einheit: str = "°C",
        akzent: str = theme.ACCENT_BLUE,
    ) -> None:
        super().__init__(master, titel, breite=520, hoehe=340)
        self._titelzeile("📈", titel, akzent)

        canvas_breite, canvas_hoehe = 452, 170
        canvas = tk.Canvas(
            self.rahmen,
            width=canvas_breite,
            height=canvas_hoehe,
            highlightthickness=0,
            bg=theme.CARD_BG_GRADIENT_END,
        )
        canvas.pack(padx=18, pady=(0, 8))

        werte = [wert for (_zeit, wert) in messwerte]
        if len(werte) < 2:
            canvas.create_text(
                canvas_breite / 2,
                canvas_hoehe / 2,
                text="Noch nicht genug Messwerte gesammelt.",
                fill=theme.TEXT_DIM,
                font=(theme.FONT_FAMILY_UI_REGULAR, 11),
            )
        else:
            self._zeichne_graph(canvas, werte, canvas_breite, canvas_hoehe, akzent, einheit)

        # Kennzahlen unter dem Graph.
        if werte:
            infozeile = (
                f"Min {min(werte):.0f} {einheit}   ·   "
                f"Ø {sum(werte) / len(werte):.0f} {einheit}   ·   "
                f"Max {max(werte):.0f} {einheit}   ·   "
                f"{len(werte)} Messwerte"
            )
        else:
            infozeile = "Keine Messwerte vorhanden."

        ctk.CTkLabel(
            self.rahmen,
            text=infozeile,
            font=(theme.FONT_FAMILY_MONO, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
        ).pack(padx=18, pady=(0, 10))

        self._button(self.rahmen, "Schließen", self._abbrechen).pack(
            fill="x", padx=18, pady=(0, 16)
        )

    def _zeichne_graph(
        self,
        canvas: tk.Canvas,
        werte: Sequence[float],
        breite: int,
        hoehe: int,
        akzent: str,
        einheit: str,
    ) -> None:
        """Zeichnet Gitterlinien und den Werteverlauf als Linienzug."""
        rand_links, rand_rechts = 38, 10
        rand_oben, rand_unten = 12, 20
        plot_breite = breite - rand_links - rand_rechts
        plot_hoehe = hoehe - rand_oben - rand_unten

        minimum = min(werte)
        maximum = max(werte)
        # Etwas Luft nach oben/unten, damit die Linie nicht am Rand klebt.
        spanne = max(1.0, maximum - minimum)
        y_min = minimum - spanne * 0.15
        y_max = maximum + spanne * 0.15

        # Waagerechte Gitterlinien mit Achsenbeschriftung.
        for anteil in (0.0, 0.5, 1.0):
            y = rand_oben + plot_hoehe * anteil
            canvas.create_line(
                rand_links, y, breite - rand_rechts, y, fill=theme.CARD_BORDER
            )
            wert = y_max - (y_max - y_min) * anteil
            canvas.create_text(
                rand_links - 6,
                y,
                text=f"{wert:.0f}",
                anchor="e",
                fill=theme.TEXT_DIM,
                font=(theme.FONT_FAMILY_MONO, 9),
            )

        # Linienzug der Messwerte.
        punkte: list[float] = []
        for index, wert in enumerate(werte):
            x = rand_links + plot_breite * (index / max(1, len(werte) - 1))
            y = rand_oben + plot_hoehe * (1 - (wert - y_min) / (y_max - y_min))
            punkte.extend((x, y))

        canvas.create_line(*punkte, fill=akzent, width=2, smooth=True)

        canvas.create_text(
            breite - rand_rechts,
            hoehe - 8,
            text=f"jetzt ({werte[-1]:.0f} {einheit})",
            anchor="e",
            fill=theme.TEXT_DIM,
            font=(theme.FONT_FAMILY_UI_REGULAR, 9),
        )
        canvas.create_text(
            rand_links,
            hoehe - 8,
            text="älter",
            anchor="w",
            fill=theme.TEXT_DIM,
            font=(theme.FONT_FAMILY_UI_REGULAR, 9),
        )


class EingabeDialog(_BasisDialog):
    """Dialog zur Eingabe einer Zahl (z. B. Temperatur-Warnschwelle)."""

    def __init__(
        self,
        master,
        titel: str,
        beschreibung: str,
        startwert: float,
        minimum: float = 30.0,
        maximum: float = 110.0,
        einheit: str = "°C",
    ) -> None:
        super().__init__(master, titel, breite=430, hoehe=270)
        self._minimum = minimum
        self._maximum = maximum

        self._titelzeile("🌡", titel, theme.ACCENT_YELLOW)

        ctk.CTkLabel(
            self.rahmen,
            text=beschreibung,
            font=(theme.FONT_FAMILY_UI_REGULAR, 12),
            text_color=theme.TEXT_MUTED,
            wraplength=370,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 10))

        eingabe_zeile = ctk.CTkFrame(self.rahmen, fg_color="transparent")
        eingabe_zeile.pack(fill="x", padx=18, pady=(0, 6))

        self._eingabefeld = ctk.CTkEntry(
            eingabe_zeile,
            width=100,
            height=36,
            corner_radius=10,
            fg_color=theme.CARD_BG_GRADIENT_END,
            border_color=theme.CARD_BORDER,
            text_color=theme.TEXT_BRIGHT,
            font=(theme.FONT_FAMILY_MONO, 15, "bold"),
            justify="center",
        )
        self._eingabefeld.insert(0, f"{startwert:.0f}")
        self._eingabefeld.pack(side="left")

        ctk.CTkLabel(
            eingabe_zeile,
            text=f" {einheit}   (gültig: {minimum:.0f}–{maximum:.0f})",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_DIM,
        ).pack(side="left")

        self._hinweis_label = ctk.CTkLabel(
            self.rahmen,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.ACCENT_PURPLE,
            anchor="w",
        )
        self._hinweis_label.pack(fill="x", padx=18, pady=(0, 6))

        leiste = ctk.CTkFrame(self.rahmen, fg_color="transparent")
        leiste.pack(fill="x", side="bottom", padx=18, pady=(0, 16))

        self._button(leiste, "Abbrechen", self._abbrechen).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        self._button(leiste, "Übernehmen", self._uebernehmen, primaer=True).pack(
            side="left", fill="x", expand=True
        )

        self._eingabefeld.bind("<Return>", lambda _e: self._uebernehmen())

    def _uebernehmen(self) -> None:
        """Prüft die Eingabe und schließt den Dialog nur bei gültigem Wert."""
        try:
            wert = float(self._eingabefeld.get().replace(",", ".").strip())
        except ValueError:
            self._hinweis_label.configure(text="Bitte eine Zahl eingeben.")
            return

        if not (self._minimum <= wert <= self._maximum):
            self._hinweis_label.configure(
                text=f"Wert muss zwischen {self._minimum:.0f} und {self._maximum:.0f} liegen."
            )
            return

        self.ergebnis = wert
        self._schliessen()


class AuswahlDialog(_BasisDialog):
    """Kleines Popup zur Auswahl eines Eintrags (z. B. welches Laufwerk)."""

    def __init__(
        self,
        master,
        titel: str,
        beschreibung: str,
        optionen: Sequence[tuple[str, str]],
    ) -> None:
        hoehe = min(420, 180 + 44 * max(1, len(optionen)))
        super().__init__(master, titel, breite=400, hoehe=hoehe)

        self._titelzeile("🗄", titel, theme.ACCENT_BLUE)

        ctk.CTkLabel(
            self.rahmen,
            text=beschreibung,
            font=(theme.FONT_FAMILY_UI_REGULAR, 12),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 10))

        for beschriftung, wert in optionen:
            self._button(
                self.rahmen,
                beschriftung,
                lambda gewaehlt=wert: self._waehlen(gewaehlt),
            ).pack(fill="x", padx=18, pady=(0, 8))

        self._button(self.rahmen, "Abbrechen", self._abbrechen).pack(
            fill="x", padx=18, pady=(6, 16)
        )

    def _waehlen(self, wert: str) -> None:
        self.ergebnis = wert
        self._schliessen()
