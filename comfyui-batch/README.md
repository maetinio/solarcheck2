# ComfyUI Stapelverarbeitung (Batch)

Schickt jeden Prompt aus `prompts.txt` mehrfach mit zufaelligem Seed an eine
laufende ComfyUI-Instanz und legt die fertigen Videos unter
`output/<Zeilennummer>_<Seed>.mp4` ab.

Benoetigt: Python 3 und eine laufende ComfyUI-Instanz.
Es muss **nichts** zusaetzlich installiert werden (nur Standardbibliothek).

## Dateien

| Datei | Zweck |
|---|---|
| `comfyui_batch.py` | Das Skript |
| `prompts.txt` | Deine Prompts, ein Prompt pro Zeile |
| `workflow_api.json` | Dein ComfyUI-Export (musst du selbst hineinlegen) |
| `output/` | Wird automatisch angelegt, hier landen die Videos |
| `output/_fehler.log` | Wird nur angelegt, wenn etwas schiefgeht |

## Schritt fuer Schritt

**1. Workflow im API-Format exportieren**

In ComfyUI: Menue `Workflow` -> `Export (API)`. Die Datei muss `workflow_api.json`
heissen und neben dem Skript liegen. Der normale Export (`Export`) funktioniert
**nicht** - das Skript erkennt das und sagt es dir.

**2. Prompts eintragen**

`prompts.txt` mit einem Texteditor oeffnen, pro Zeile einen Prompt.
Zeilen, die mit `#` beginnen, und leere Zeilen werden uebersprungen.
Die Zeilennummer aus der Datei landet spaeter im Dateinamen.

**3. Erkennung pruefen (empfohlen, dauert 2 Sekunden)**

```
python3 comfyui_batch.py --pruefen
```

Das schickt nichts an ComfyUI, sondern zeigt nur an, **in welchen Knoten** das
Skript deinen Prompt schreiben und den Seed setzen wuerde. Bitte einmal
kontrollieren, ob dort der positive Prompt steht (nicht der negative).

Stimmt es nicht: oben in `comfyui_batch.py` bei `POSITIV_NODE_ID = None`
die richtige Knotennummer eintragen, z. B. `POSITIV_NODE_ID = "6"`.

**4. Losschicken**

ComfyUI starten, dann:

```
python3 comfyui_batch.py
```

Im Terminal siehst du laufend, welcher Prompt gerade gerendert wird.

## Optionen

```
python3 comfyui_batch.py --runs 5                 # 5 statt 3 Durchlaeufe pro Prompt
python3 comfyui_batch.py --server 127.0.0.1:8188  # andere Adresse/Port
python3 comfyui_batch.py --prompts andere.txt     # andere Promptdatei
python3 comfyui_batch.py --workflow anderer.json  # anderer Workflow
python3 comfyui_batch.py --output videos          # anderer Zielordner
python3 comfyui_batch.py --pruefen                # nur analysieren
```

Dauerhafte Einstellungen stehen ganz oben in `comfyui_batch.py` im Block
"1. Einstellungen".

## Verhalten bei Fehlern

Faellt ein Durchlauf aus (z. B. zu wenig VRAM), bricht das Skript **nicht** ab.
Der Fehler wird angezeigt, in `output/_fehler.log` geschrieben, und es geht mit
dem naechsten Prompt weiter. Am Ende kommt eine Zusammenfassung.

Wenn stattdessen nur der einzelne Durchlauf verworfen und die restlichen
Durchlaeufe desselben Prompts trotzdem versucht werden sollen, im Skript
`BEI_FEHLER_ZUM_NAECHSTEN_PROMPT = False` setzen.

Mit `Strg+C` kannst du jederzeit sauber abbrechen.

## Getestet / nicht getestet

Getestet wurde gegen einen nachgebauten ComfyUI-Server (Erfolgsfall, Fehlerfall,
Server nicht erreichbar, falsches Exportformat, fehlende Dateien) sowie die
Knotenerkennung an zwei Workflow-Varianten: KSampler + CLIPTextEncode und
WanVideoWrapper (WanVideoTextEncode + WanVideoSampler).

**Nicht** getestet gegen eine echte Wan-2.1-VACE-Installation - dafuer fehlt die
Hardware. Fuehre deshalb vor dem grossen Lauf einmal `--pruefen` aus und danach
einen Testlauf mit einer einzigen Promptzeile.
