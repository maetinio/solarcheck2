"""
Tile: Basis-Kachel für das Dashboard-Raster.

Jede Kachel besteht aus drei Zonen:
1. Kopf   - Icon-Quadrat, Titel, Untertitel
2. Body   - freier Slot für Gauge / Meter / große Zahl (vertikal zentriert)
3. Buttons - 1-2 Aktions-Buttons über die volle Breite

Die Kachel kümmert sich außerdem um die obere Akzentlinie und den
dezenten Hover-Effekt (Rahmen hellt sich auf).

Zusätzlich enthält dieses Modul den dritten Anzeigetyp StatValue
("große Zahl") - er ist reine Label-Komposition und braucht daher keine
eigene Zeichenlogik wie Gauge oder Meter.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from .. import theme


class Tile(ctk.CTkFrame):
    """Wiederverwendbare Dashboard-Kachel."""

    def __init__(
        self,
        master,
        titel: str,
        untertitel: str,
        icon: str,
        akzentfarbe: str = theme.ACCENT_BLUE,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            fg_color=theme.CARD_BG,
            corner_radius=16,
            border_width=1,
            border_color=theme.CARD_BORDER,
            **kwargs,
        )
        self._akzentfarbe = akzentfarbe

        # --- Obere Akzentlinie (2 px) -----------------------------------
        self._akzentlinie = ctk.CTkFrame(
            self, fg_color=akzentfarbe, height=2, corner_radius=0
        )
        self._akzentlinie.pack(fill="x", side="top")

        # --- Innerer Container mit Innenabstand -------------------------
        self._innen = ctk.CTkFrame(self, fg_color="transparent")
        self._innen.pack(fill="both", expand=True, padx=12, pady=(8, 10))

        # --- Kopf: Icon + Titel/Untertitel -------------------------------
        kopf = ctk.CTkFrame(self._innen, fg_color="transparent")
        kopf.pack(fill="x", side="top")

        icon_quadrat = ctk.CTkFrame(
            kopf,
            fg_color=theme.ICON_BG_TINT,
            corner_radius=9,
            width=32,
            height=32,
        )
        icon_quadrat.pack(side="left", padx=(0, 10))
        icon_quadrat.pack_propagate(False)

        icon_label = ctk.CTkLabel(
            icon_quadrat, text=icon, font=(theme.FONT_FAMILY_UI_REGULAR, 15)
        )
        icon_label.place(relx=0.5, rely=0.5, anchor="center")

        text_container = ctk.CTkFrame(kopf, fg_color="transparent")
        text_container.pack(side="left", fill="x", expand=True)

        self._titel_label = ctk.CTkLabel(
            text_container,
            text=titel,
            font=(theme.FONT_FAMILY_UI, theme.FONT_SIZE_TITLE, "bold"),
            text_color=theme.TEXT_BRIGHT,
            anchor="w",
        )
        self._titel_label.pack(fill="x", anchor="w")

        self._untertitel_label = ctk.CTkLabel(
            text_container,
            text=untertitel,
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        self._untertitel_label.pack(fill="x", anchor="w")

        # Warnzeichen rechts oben, standardmäßig leer (siehe set_warnung).
        self._warn_label = ctk.CTkLabel(
            kopf,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, 15),
            text_color=theme.ACCENT_YELLOW,
            width=18,
        )
        self._warn_label.pack(side="right", anchor="n")

        # --- Body: freier Slot, vertikal zentriert -----------------------
        self.body = ctk.CTkFrame(self._innen, fg_color="transparent")
        self.body.pack(fill="both", expand=True, pady=(6, 6))

        # --- Buttonleiste --------------------------------------------------
        self._button_leiste = ctk.CTkFrame(self._innen, fg_color="transparent")
        self._button_leiste.pack(fill="x", side="bottom")
        self._buttons: list[ctk.CTkButton] = []

        # --- Hover-Effekt: Rahmen hellt sich beim Überfahren auf ----------
        for widget in (self, self._innen, kopf, self.body):
            widget.bind("<Enter>", self._bei_hover_start)
            widget.bind("<Leave>", self._bei_hover_ende)

    def set_untertitel(self, text: str, max_zeichen: int = 26) -> None:
        """Aktualisiert die Untertitel-Zeile (z. B. lokale IP, OS-Name).

        Zu lange Texte werden gekürzt, damit sie die Kachel nicht sprengen.
        Geschrieben wird nur bei tatsächlicher Änderung (kein Flackern).
        """
        try:
            gekuerzt = text if len(text) <= max_zeichen else text[: max_zeichen - 1] + "…"
            if gekuerzt != getattr(self, "_letzter_untertitel", None):
                self._letzter_untertitel = gekuerzt
                self._untertitel_label.configure(text=gekuerzt)
        except Exception:
            pass

    def _bei_hover_start(self, _event=None) -> None:
        try:
            self.configure(border_color=theme.CARD_BORDER_HOVER)
        except Exception:
            pass

    def _bei_hover_ende(self, _event=None) -> None:
        try:
            self.configure(border_color=theme.CARD_BORDER)
        except Exception:
            pass

    def add_button(
        self,
        text: str,
        befehl: Callable[[], None],
        primaer: bool = False,
        admin_erforderlich: bool = False,
        ist_admin: bool = True,
    ) -> ctk.CTkButton:
        """Fügt einen Aktions-Button zur unteren Leiste hinzu.

        Primäre Buttons (wichtigste Aktion) sind blau hervorgehoben,
        alle anderen dezent mit blauem Hover-Rand. Admin-Aktionen tragen
        ein Schild-Symbol und werden ausgegraut, wenn ist_admin=False.
        """
        beschriftung = f"🛡 {text}" if admin_erforderlich else text
        aktiviert = (not admin_erforderlich) or ist_admin

        if primaer:
            fg_color = theme.BUTTON_PRIMARY_BG
            hover_color = theme.BUTTON_PRIMARY_HOVER
            border_color = theme.BUTTON_PRIMARY_BORDER
            text_color = theme.TEXT_BRIGHT
        else:
            fg_color = theme.BUTTON_SECONDARY_BG
            hover_color = theme.BUTTON_SECONDARY_BG
            border_color = theme.BUTTON_SECONDARY_BORDER
            text_color = theme.TEXT_MUTED

        def sicherer_befehl() -> None:
            # Kapselt jede Aktion ab: ein Fehler in einer Aktion darf die
            # App niemals zum Absturz bringen.
            try:
                befehl()
            except Exception:
                pass

        button = ctk.CTkButton(
            self._button_leiste,
            text=beschriftung,
            command=sicherer_befehl,
            width=1,  # minimale Anforderungsbreite, damit pack(fill="x") die
                      # tatsächliche Breite bestimmt statt CTk-Standardbreite (140)
            fg_color=fg_color,
            hover_color=hover_color,
            border_width=1,
            border_color=border_color if aktiviert else theme.CARD_BORDER,
            text_color=text_color if aktiviert else theme.TEXT_DIM,
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
            corner_radius=10,
            height=30,
            state="normal" if aktiviert else "disabled",
        )
        # Ohne Hover-Rand für dezente Buttons per Bind nachrüsten, da
        # CTkButton keinen separaten "Hover-Border" kennt.
        if not primaer and aktiviert:
            button.bind(
                "<Enter>",
                lambda _e: button.configure(
                    border_color=theme.BUTTON_SECONDARY_HOVER_BORDER
                ),
            )
            button.bind(
                "<Leave>",
                lambda _e: button.configure(
                    border_color=theme.BUTTON_SECONDARY_BORDER
                ),
            )

        self._buttons.append(button)
        self._buttons_neu_anordnen()
        return button

    def _buttons_neu_anordnen(self) -> None:
        """Verteilt alle Buttons zu gleichen Teilen über die volle Breite."""
        for button in self._buttons:
            button.pack_forget()
        for index, button in enumerate(self._buttons):
            padx = (0, 6) if index < len(self._buttons) - 1 else (0, 0)
            button.pack(side="left", fill="x", expand=True, padx=padx)

    def set_button_zustand(self, index: int, aktiviert: bool) -> None:
        """Aktiviert/deaktiviert einen Button nachträglich (z. B. Sensor fehlt).

        Schreibt nur bei tatsächlicher Zustandsänderung, da diese Methode
        aus dem GUI-Tick heraus zyklisch aufgerufen wird.
        """
        try:
            button = self._buttons[index]
            gewuenscht = "normal" if aktiviert else "disabled"
            if button.cget("state") != gewuenscht:
                button.configure(
                    state=gewuenscht,
                    text_color=theme.TEXT_MUTED if aktiviert else theme.TEXT_DIM,
                )
        except Exception:
            pass

    def set_akzent(self, farbe: str) -> None:
        """Färbt die obere Akzentlinie um (z. B. bei Temperatur-Warnung)."""
        try:
            if farbe != self._akzentfarbe:
                self._akzentlinie.configure(fg_color=farbe)
                self._akzentfarbe = farbe
        except Exception:
            pass

    def set_warnung(self, aktiv: bool) -> None:
        """Blendet ein Warnzeichen rechts oben in der Kopfzeile ein/aus."""
        try:
            if aktiv != getattr(self, "_warnung_aktiv", None):
                self._warnung_aktiv = aktiv
                self._warn_label.configure(text="⚠" if aktiv else "")
        except Exception:
            pass


class StatValue(ctk.CTkFrame):
    """Dritter Anzeigetyp: sehr große Zahl mit Einheit und Unterzeile.

    Wird für Netzwerk, Autostart, Papierkorb und Temporäre Dateien
    verwendet. Über kompakt=True lassen sich zwei Werte platzsparend
    untereinander stapeln (Down-/Upload in der Netzwerk-Kachel).
    """

    def __init__(
        self,
        master,
        farbe: str = theme.ACCENT_BLUE,
        kompakt: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self._farbe = farbe
        zahl_groesse = 22 if kompakt else theme.FONT_SIZE_VALUE_LARGE

        # Zahl und Einheit sitzen in einer Zeile auf gemeinsamer Grundlinie.
        zahlen_zeile = ctk.CTkFrame(self, fg_color="transparent")
        zahlen_zeile.pack(anchor="w")

        self._zahl_label = ctk.CTkLabel(
            zahlen_zeile,
            text="—",
            font=(theme.FONT_FAMILY_MONO, zahl_groesse, "bold"),
            text_color=farbe,
            anchor="w",
        )
        self._zahl_label.pack(side="left")

        self._einheit_label = ctk.CTkLabel(
            zahlen_zeile,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL, "bold"),
            text_color=theme.TEXT_MUTED,
            anchor="w",
        )
        self._einheit_label.pack(side="left", padx=(4, 0), pady=(6, 0))

        # Die Unterzeile wird erst eingeblendet, wenn sie Text bekommt -
        # eine leere Zeile würde sonst unnötig Kachelhöhe verbrauchen.
        self._unterzeile_label = ctk.CTkLabel(
            self,
            text="",
            font=(theme.FONT_FAMILY_UI_REGULAR, theme.FONT_SIZE_LABEL),
            text_color=theme.TEXT_MUTED,
            anchor="w",
            justify="left",
        )
        self._unterzeile_sichtbar = False

    def set_value(
        self,
        zahl: str,
        einheit: str = "",
        unterzeile: str = "",
        farbe: Optional[str] = None,
    ) -> None:
        """Aktualisiert Zahl, Einheit und Unterzeile ohne Neuaufbau."""
        try:
            # Nur bei tatsächlicher Änderung neu zeichnen ("Zahlenblitzer"
            # vermeiden, wenn der GUI-Tick denselben Wert erneut setzt).
            stand = (zahl, einheit, unterzeile, farbe)
            if stand == getattr(self, "_letzter_stand", None):
                return
            self._letzter_stand = stand

            self._zahl_label.configure(text=zahl, text_color=farbe or self._farbe)
            self._einheit_label.configure(text=einheit)
            self._unterzeile_label.configure(text=unterzeile)

            # Unterzeile nur einblenden, wenn sie tatsächlich Text hat.
            soll_sichtbar = bool(unterzeile)
            if soll_sichtbar != self._unterzeile_sichtbar:
                if soll_sichtbar:
                    self._unterzeile_label.pack(anchor="w")
                else:
                    self._unterzeile_label.pack_forget()
                self._unterzeile_sichtbar = soll_sichtbar
        except Exception:
            pass
