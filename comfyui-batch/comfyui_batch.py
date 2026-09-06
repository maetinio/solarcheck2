#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comfyui_batch.py — Stapelverarbeitung fuer ComfyUI.

Liest prompts.txt (ein Prompt pro Zeile), schickt jeden Prompt mehrfach
mit zufaelligem Seed an eine laufende ComfyUI-Instanz und legt die
fertigen Videos unter ./output/<Zeilennummer>_<Seed>.mp4 ab.

Benoetigt nur die Python-Standardbibliothek (kein "pip install").
Getestet werden muss es gegen die eigene ComfyUI-Installation, weil
Node-Namen je nach installierten Custom Nodes unterschiedlich sind.
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy

# ---------------------------------------------------------------------------
# 1. Einstellungen — das hier darfst du gefahrlos anpassen
# ---------------------------------------------------------------------------

SERVER = "127.0.0.1:8188"      # Adresse deiner ComfyUI-Instanz
WORKFLOW_DATEI = "workflow_api.json"
PROMPT_DATEI = "prompts.txt"
AUSGABE_ORDNER = "output"
DURCHLAEUFE_PRO_PROMPT = 3     # wie oft jeder Prompt gerendert wird
TIMEOUT_SEKUNDEN = 3600        # Abbruch, wenn ein Video laenger braucht
# True  = nach einem Fehler die restlichen Durchlaeufe dieses Prompts ueberspringen
#         und direkt mit dem naechsten Prompt weitermachen (so gewuenscht).
# False = nur den fehlgeschlagenen Durchlauf verwerfen und den naechsten
#         Durchlauf desselben Prompts trotzdem versuchen.
BEI_FEHLER_ZUM_NAECHSTEN_PROMPT = True
POLL_INTERVALL = 2.0           # wie oft nach dem Ergebnis gefragt wird

# Nur ausfuellen, wenn die automatische Erkennung danebenliegt.
# Beispiel: POSITIV_NODE_ID = "6" und POSITIV_FELD = "text"
POSITIV_NODE_ID = None
POSITIV_FELD = "text"
# Liste von Node-IDs, deren Seed gesetzt wird. None = automatisch alle finden.
SEED_NODE_IDS = None

VIDEO_ENDUNGEN = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v")

# ---------------------------------------------------------------------------
# 2. Kleine Helfer fuer die Kommunikation mit ComfyUI
# ---------------------------------------------------------------------------


def api_url(pfad, params=None):
    url = "http://%s%s" % (SERVER, pfad)
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return url


def hole_json(pfad, params=None, timeout=30):
    """GET-Anfrage an ComfyUI, Antwort wird als JSON zurueckgegeben."""
    with urllib.request.urlopen(api_url(pfad, params), timeout=timeout) as antwort:
        return json.loads(antwort.read().decode("utf-8"))


def sende_json(pfad, daten, timeout=30):
    """POST-Anfrage mit JSON-Koerper."""
    koerper = json.dumps(daten).encode("utf-8")
    anfrage = urllib.request.Request(
        api_url(pfad),
        data=koerper,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
        return json.loads(antwort.read().decode("utf-8"))


def lade_datei(filename, subfolder, typ, timeout=300):
    """Holt eine fertige Datei ueber die /view-Schnittstelle als Bytes."""
    params = {"filename": filename, "subfolder": subfolder or "", "type": typ or "output"}
    with urllib.request.urlopen(api_url("/view", params), timeout=timeout) as antwort:
        return antwort.read()


# ---------------------------------------------------------------------------
# 3. Workflow analysieren: Wo steht der Prompt? Wo stehen die Seeds?
# ---------------------------------------------------------------------------

TEXT_FELDER = ("text", "prompt", "positive_prompt", "string", "value")


def ist_link(wert):
    """In workflow_api.json ist eine Verbindung eine Liste wie ["6", 0]."""
    return isinstance(wert, list) and len(wert) == 2 and isinstance(wert[0], (str, int))


def finde_textnode(workflow, start_node_id, besucht=None, tiefe=0):
    """
    Geht vom Startknoten rueckwaerts durch den Graphen und sucht den ersten
    Knoten, der einen echten Text (kein Kabel) enthaelt.
    Rueckgabe: (node_id, feldname) oder (None, None).
    """
    if besucht is None:
        besucht = set()
    node_id = str(start_node_id)
    if node_id in besucht or tiefe > 30:
        return (None, None)
    besucht.add(node_id)

    node = workflow.get(node_id)
    if not isinstance(node, dict):
        return (None, None)
    inputs = node.get("inputs", {}) or {}

    for feld in TEXT_FELDER:
        if isinstance(inputs.get(feld), str):
            return (node_id, feld)

    for wert in inputs.values():
        if ist_link(wert):
            treffer = finde_textnode(workflow, wert[0], besucht, tiefe + 1)
            if treffer[0]:
                return treffer
    return (None, None)


def erkenne_prompt_node(workflow):
    """
    Sucht den Knoten, in den der positive Prompt geschrieben werden muss.

    Vorgehen (in dieser Reihenfolge):
    a) Knoten finden, der 'positive' UND 'negative' als Eingang hat (Sampler).
       Vom 'positive'-Kabel rueckwaerts bis zum ersten Textfeld laufen.
    b) Falls das scheitert: alle Textknoten sammeln und ueber den Titel raten.
    c) Falls auch das scheitert: abbrechen und um manuelle Angabe bitten.
    """
    if POSITIV_NODE_ID:
        return (str(POSITIV_NODE_ID), POSITIV_FELD, "manuell in der Konfiguration gesetzt")

    negative_ids = set()
    for node_id, node in workflow.items():
        inputs = (node or {}).get("inputs", {}) or {}
        if ist_link(inputs.get("negative")):
            neg = finde_textnode(workflow, inputs["negative"][0])
            if neg[0]:
                negative_ids.add(neg[0])

    for node_id, node in workflow.items():
        inputs = (node or {}).get("inputs", {}) or {}
        if ist_link(inputs.get("positive")) and "negative" in inputs:
            treffer = finde_textnode(workflow, inputs["positive"][0])
            if treffer[0] and treffer[0] not in negative_ids:
                grund = "ueber den 'positive'-Eingang von Node %s (%s)" % (
                    node_id, node.get("class_type", "?"))
                return (treffer[0], treffer[1], grund)

    kandidaten = []
    for node_id, node in workflow.items():
        inputs = (node or {}).get("inputs", {}) or {}
        for feld in TEXT_FELDER:
            if isinstance(inputs.get(feld), str):
                kandidaten.append((node_id, feld))
                break

    if len(kandidaten) == 1:
        return (kandidaten[0][0], kandidaten[0][1], "einziger Textknoten im Workflow")

    for node_id, feld in kandidaten:
        titel = ((workflow[node_id].get("_meta") or {}).get("title") or "").lower()
        if "posi" in titel or titel.strip() in ("prompt", "text prompt"):
            return (node_id, feld, "Titel des Knotens lautet '%s'" % titel)

    raise SystemExit(
        "ABBRUCH: Der Prompt-Knoten konnte nicht eindeutig bestimmt werden.\n"
        "Gefundene Textknoten: %s\n"
        "Bitte oben im Skript POSITIV_NODE_ID auf die richtige Nummer setzen.\n"
        "Tipp: 'python3 comfyui_batch.py --pruefen' listet alle Knoten auf."
        % ", ".join("%s (%s)" % (n, f) for n, f in kandidaten)
    )


def erkenne_seed_nodes(workflow):
    """Alle Knoten mit einem echten Zahlen-Feld 'seed' oder 'noise_seed'."""
    if SEED_NODE_IDS:
        gefunden = []
        for node_id in SEED_NODE_IDS:
            inputs = (workflow.get(str(node_id)) or {}).get("inputs", {}) or {}
            for feld in ("seed", "noise_seed"):
                if feld in inputs:
                    gefunden.append((str(node_id), feld))
        return gefunden

    gefunden = []
    for node_id, node in workflow.items():
        inputs = (node or {}).get("inputs", {}) or {}
        for feld in ("seed", "noise_seed"):
            if isinstance(inputs.get(feld), (int, float)) and not isinstance(inputs.get(feld), bool):
                gefunden.append((node_id, feld))
    return gefunden


def beschreibe(workflow, node_id):
    node = workflow.get(str(node_id), {}) or {}
    titel = (node.get("_meta") or {}).get("title")
    return "Node %s — %s%s" % (
        node_id,
        node.get("class_type", "unbekannt"),
        (" (Titel: '%s')" % titel) if titel else "",
    )


# ---------------------------------------------------------------------------
# 4. Einen einzelnen Durchlauf ausfuehren
# ---------------------------------------------------------------------------


def in_warteschlange(prompt_id):
    """True, solange der Auftrag laut ComfyUI noch laeuft oder wartet."""
    try:
        queue = hole_json("/queue")
    except Exception:
        return True  # im Zweifel weiterwarten
    for schluessel in ("queue_running", "queue_pending"):
        for eintrag in queue.get(schluessel, []):
            if len(eintrag) > 1 and eintrag[1] == prompt_id:
                return True
    return False


def warte_auf_ergebnis(prompt_id, etikett):
    """
    Fragt ComfyUI so lange, bis der Auftrag in der History auftaucht.
    Gibt den History-Eintrag zurueck oder wirft eine Ausnahme.
    """
    start = time.time()
    fehlversuche = 0
    while True:
        verlauf = hole_json("/history/%s" % prompt_id)
        if prompt_id in verlauf:
            print("")  # Zeilenumbruch nach der Fortschrittsanzeige
            return verlauf[prompt_id]

        if not in_warteschlange(prompt_id):
            # Kurze Gnadenfrist: History wird minimal spaeter geschrieben.
            fehlversuche += 1
            if fehlversuche > 5:
                print("")
                raise RuntimeError(
                    "Auftrag %s ist aus der Warteschlange verschwunden, ohne ein "
                    "Ergebnis zu hinterlassen. Bitte im ComfyUI-Terminal nach der "
                    "Fehlermeldung schauen." % prompt_id)
        else:
            fehlversuche = 0

        vergangen = time.time() - start
        if vergangen > TIMEOUT_SEKUNDEN:
            print("")
            raise TimeoutError("Zeitlimit von %d Sekunden ueberschritten." % TIMEOUT_SEKUNDEN)

        sys.stdout.write("\r   ... %s laeuft seit %d s " % (etikett, int(vergangen)))
        sys.stdout.flush()
        time.sleep(POLL_INTERVALL)


def sammle_videos(history_eintrag):
    """
    Durchsucht das Ergebnis nach Videodateien.

    Je nach verwendetem Speicher-Node liegen die Dateien unter
    unterschiedlichen Schluesseln ('gifs' bei VideoHelperSuite, 'videos'
    oder 'images' bei anderen). Deshalb wird jede Liste durchsucht und
    anhand der Dateiendung entschieden.
    """
    treffer = []
    for node_ausgabe in (history_eintrag.get("outputs") or {}).values():
        if not isinstance(node_ausgabe, dict):
            continue
        for eintraege in node_ausgabe.values():
            if not isinstance(eintraege, list):
                continue
            for eintrag in eintraege:
                if not isinstance(eintrag, dict):
                    continue
                name = eintrag.get("filename")
                if isinstance(name, str) and name.lower().endswith(VIDEO_ENDUNGEN):
                    if eintrag not in treffer:
                        treffer.append(eintrag)
    # Legt ein Node zusaetzlich eine Vorschau (z. B. .webm/.gif) an, wird nur
    # die MP4 gespeichert — sie ist das eigentlich gewuenschte Ergebnis.
    mp4s = [t for t in treffer if t["filename"].lower().endswith(".mp4")]
    return mp4s or treffer


def pruefe_status(history_eintrag, prompt_id):
    """Wirft eine Ausnahme, wenn ComfyUI den Lauf als fehlerhaft meldet."""
    status = history_eintrag.get("status") or {}
    if status.get("status_str") == "error" or status.get("completed") is False:
        meldungen = []
        for nachricht in status.get("messages") or []:
            if isinstance(nachricht, list) and len(nachricht) > 1:
                daten = nachricht[1]
                if isinstance(daten, dict) and daten.get("exception_message"):
                    meldungen.append("%s: %s" % (
                        daten.get("node_type", "?"), daten["exception_message"]))
        raise RuntimeError("ComfyUI meldet einen Fehler fuer %s. %s" % (
            prompt_id, " | ".join(meldungen) if meldungen else "Details siehe ComfyUI-Terminal."))


def fuehre_durchlauf_aus(workflow, prompt_text, prompt_node, prompt_feld,
                         seed_nodes, seed, zielbasis, client_id, etikett):
    """Ein kompletter Durchlauf: Workflow anpassen, senden, warten, speichern."""
    auftrag = deepcopy(workflow)
    auftrag[prompt_node]["inputs"][prompt_feld] = prompt_text
    for node_id, feld in seed_nodes:
        auftrag[node_id]["inputs"][feld] = seed

    antwort = sende_json("/prompt", {"prompt": auftrag, "client_id": client_id})
    prompt_id = antwort.get("prompt_id")
    if not prompt_id:
        raise RuntimeError("ComfyUI hat keine prompt_id zurueckgegeben: %r" % antwort)

    eintrag = warte_auf_ergebnis(prompt_id, etikett)
    pruefe_status(eintrag, prompt_id)

    videos = sammle_videos(eintrag)
    if not videos:
        raise RuntimeError(
            "Der Lauf ist fertig, aber es wurde keine Videodatei gefunden. "
            "Enthaelt der Workflow einen Speicher-Node (z. B. 'Video Combine')?")

    gespeichert = []
    for index, video in enumerate(videos):
        endung = os.path.splitext(video["filename"])[1] or ".mp4"
        suffix = "" if len(videos) == 1 else "_%d" % (index + 1)
        zielpfad = os.path.join(AUSGABE_ORDNER, "%s%s%s" % (zielbasis, suffix, endung))
        daten = lade_datei(video["filename"], video.get("subfolder"), video.get("type"))
        with open(zielpfad, "wb") as ziel:
            ziel.write(daten)
        gespeichert.append((zielpfad, len(daten)))
    return gespeichert


# ---------------------------------------------------------------------------
# 5. Hauptprogramm
# ---------------------------------------------------------------------------


def lade_prompts(pfad):
    """Liest die Promptdatei. Leere Zeilen und #-Kommentare werden ignoriert."""
    if not os.path.exists(pfad):
        raise SystemExit("ABBRUCH: '%s' wurde nicht gefunden." % pfad)
    prompts = []
    with open(pfad, "r", encoding="utf-8") as datei:
        for nummer, zeile in enumerate(datei, start=1):
            text = zeile.strip()
            if text and not text.startswith("#"):
                prompts.append((nummer, text))
    if not prompts:
        raise SystemExit("ABBRUCH: '%s' enthaelt keine verwertbaren Zeilen." % pfad)
    return prompts


def main():
    global SERVER, WORKFLOW_DATEI, PROMPT_DATEI, AUSGABE_ORDNER, DURCHLAEUFE_PRO_PROMPT

    parser = argparse.ArgumentParser(
        description="Schickt jeden Prompt aus prompts.txt mehrfach an ComfyUI.")
    parser.add_argument("--server", default=SERVER, help="Adresse von ComfyUI (Standard: %s)" % SERVER)
    parser.add_argument("--workflow", default=WORKFLOW_DATEI)
    parser.add_argument("--prompts", default=PROMPT_DATEI)
    parser.add_argument("--output", default=AUSGABE_ORDNER)
    parser.add_argument("--runs", type=int, default=DURCHLAEUFE_PRO_PROMPT,
                        help="Durchlaeufe pro Prompt (Standard: %d)" % DURCHLAEUFE_PRO_PROMPT)
    parser.add_argument("--pruefen", action="store_true",
                        help="Nur analysieren und alle Knoten auflisten, nichts rendern.")
    args = parser.parse_args()

    SERVER = args.server
    WORKFLOW_DATEI = args.workflow
    PROMPT_DATEI = args.prompts
    AUSGABE_ORDNER = args.output
    DURCHLAEUFE_PRO_PROMPT = args.runs

    if not os.path.exists(WORKFLOW_DATEI):
        raise SystemExit("ABBRUCH: '%s' wurde nicht gefunden." % WORKFLOW_DATEI)
    with open(WORKFLOW_DATEI, "r", encoding="utf-8") as datei:
        workflow = json.load(datei)

    if "nodes" in workflow and "last_node_id" in workflow:
        raise SystemExit(
            "ABBRUCH: '%s' ist ein normaler Workflow-Export, kein API-Export.\n"
            "In ComfyUI exportieren ueber: Workflow -> Export (API)." % WORKFLOW_DATEI)

    if args.pruefen:
        print("Knoten in %s:" % WORKFLOW_DATEI)
        for node_id in sorted(workflow, key=lambda x: (len(x), x)):
            print("  " + beschreibe(workflow, node_id))

    prompt_node, prompt_feld, grund = erkenne_prompt_node(workflow)
    seed_nodes = erkenne_seed_nodes(workflow)

    print("")
    print("Erkennung")
    print("  Prompt wird geschrieben in: %s, Feld '%s'" % (beschreibe(workflow, prompt_node), prompt_feld))
    print("  Erkannt %s" % grund)
    altwert = workflow[prompt_node]["inputs"][prompt_feld]
    print("  Bisheriger Inhalt: %r" % (altwert[:120] + ("..." if len(altwert) > 120 else "")))
    if seed_nodes:
        for node_id, feld in seed_nodes:
            print("  Seed wird gesetzt in: %s, Feld '%s'" % (beschreibe(workflow, node_id), feld))
    else:
        print("  WARNUNG: Kein Seed-Feld gefunden — alle Durchlaeufe waeren identisch.")
    print("")
    print("  Bitte kurz pruefen, ob das stimmt. Falls nicht: POSITIV_NODE_ID")
    print("  oben im Skript auf die richtige Nummer setzen.")
    print("")

    if args.pruefen:
        print("Nur Pruefmodus — es wurde nichts an ComfyUI geschickt.")
        return 0

    try:
        hole_json("/system_stats", timeout=10)
    except Exception as fehler:
        raise SystemExit(
            "ABBRUCH: ComfyUI ist unter http://%s nicht erreichbar (%s).\n"
            "Laeuft ComfyUI und stimmt der Port?" % (SERVER, fehler))

    prompts = lade_prompts(PROMPT_DATEI)
    os.makedirs(AUSGABE_ORDNER, exist_ok=True)
    client_id = str(uuid.uuid4())
    fehlerprotokoll = os.path.join(AUSGABE_ORDNER, "_fehler.log")

    gesamt = len(prompts) * DURCHLAEUFE_PRO_PROMPT
    erfolgreich = 0
    fehlgeschlagen = 0
    zaehler = 0
    startzeit = time.time()

    print("=" * 70)
    print("%d Prompts x %d Durchlaeufe = %d Videos" % (len(prompts), DURCHLAEUFE_PRO_PROMPT, gesamt))
    print("=" * 70)

    for zeilennummer, prompt_text in prompts:
        print("")
        print("[Zeile %d] %s" % (zeilennummer, prompt_text))

        for durchlauf in range(1, DURCHLAEUFE_PRO_PROMPT + 1):
            zaehler += 1
            seed = random.randint(0, 2**32 - 1)
            etikett = "Zeile %d, Durchlauf %d/%d, Seed %d" % (
                zeilennummer, durchlauf, DURCHLAEUFE_PRO_PROMPT, seed)
            print("  -> [%d/%d] Durchlauf %d, Seed %d" % (
                zaehler, gesamt, durchlauf, seed))

            try:
                dateien = fuehre_durchlauf_aus(
                    workflow, prompt_text, prompt_node, prompt_feld,
                    seed_nodes, seed, "%d_%d" % (zeilennummer, seed),
                    client_id, etikett)
                for pfad, groesse in dateien:
                    print("     OK: %s (%.1f MB)" % (pfad, groesse / 1048576.0))
                erfolgreich += 1
            except KeyboardInterrupt:
                print("\nAbbruch durch Benutzer.")
                return 130
            except Exception as fehler:
                fehlgeschlagen += 1
                meldung = "[Zeile %d, Durchlauf %d, Seed %d] %s: %s" % (
                    zeilennummer, durchlauf, seed, type(fehler).__name__, fehler)
                print("     FEHLER: %s" % fehler)
                with open(fehlerprotokoll, "a", encoding="utf-8") as protokoll:
                    protokoll.write("%s  %s\n" % (
                        time.strftime("%Y-%m-%d %H:%M:%S"), meldung))
                if BEI_FEHLER_ZUM_NAECHSTEN_PROMPT:
                    uebersprungen = DURCHLAEUFE_PRO_PROMPT - durchlauf
                    zaehler += uebersprungen
                    fehlgeschlagen += uebersprungen
                    if uebersprungen:
                        print("     -> restliche %d Durchlaeufe dieser Zeile werden "
                              "uebersprungen" % uebersprungen)
                    print("     -> weiter mit dem naechsten Prompt")
                    break
                print("     -> weiter mit dem naechsten Durchlauf")

    dauer = time.time() - startzeit
    print("")
    print("=" * 70)
    print("Fertig. %d erfolgreich, %d fehlgeschlagen, Gesamtdauer %d min %d s" % (
        erfolgreich, fehlgeschlagen, int(dauer // 60), int(dauer % 60)))
    print("Videos liegen in: %s" % os.path.abspath(AUSGABE_ORDNER))
    if fehlgeschlagen:
        print("Fehlerdetails: %s" % os.path.abspath(fehlerprotokoll))
    print("=" * 70)
    return 0 if fehlgeschlagen == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
