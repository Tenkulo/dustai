# Prompt Ottimizzati – Operazioni File Windows
# Copia e adatta questi prompt in PyGPT Agent mode

---

## 📁 Crea cartella + file con testo

```
Esegui con sys_exec usando cmd /c:
1. Crea la cartella: [PERCORSO]
2. Crea il file [NOME.EXT] con contenuto: [TESTO]
3. Verifica che entrambi esistano con dir
Usa %OneDrive%\Desktop come Desktop se OneDrive è attivo.
```

## 📋 Leggi contenuto file

```
Leggi il contenuto del file [PERCORSO\NOME.EXT] usando sys_exec con cmd /c type
```

## 🔄 Rinomina o sposta file

```
Sposta il file da [SORGENTE] a [DESTINAZIONE] usando sys_exec con cmd /c move
Verifica con dir dopo l'operazione.
```

## 🗑️ Elimina file o cartella

```
Elimina [FILE/CARTELLA] usando sys_exec:
- File: cmd /c del "[PERCORSO]"
- Cartella: cmd /c rmdir /s /q "[PERCORSO]"
Conferma l'eliminazione con dir del parent.
```

## 📂 Lista contenuto cartella

```
Mostrami il contenuto di [CARTELLA] usando sys_exec con: cmd /c dir "[CARTELLA]"
```

## ✏️ Scrivi script e salvalo

```
Crea il file [NOME.py] in [CARTELLA] con questo contenuto:
[CODICE]
Poi verificalo con: cmd /c type "[PERCORSO\NOME.py]"
```

## 🔍 Trova file per nome

```
Cerca tutti i file *.txt in [CARTELLA] e sottocartelle usando:
cmd /c dir "[CARTELLA]\*.txt" /s /b
```

---

## ⚠️ Note Windows Critiche

| Problema | Causa | Fix |
|---|---|---|
| Cartella non appare su Desktop | OneDrive reindirizza il path | Usa `%OneDrive%\Desktop` |
| `mkdir` OK ma cartella assente | Tool nativo PyGPT non scrive su disco | Usa `sys_exec` + `cmd /c mkdir` |
| Caratteri speciali nel testo | Echo interpreta `<>|` | Usa `cmd /c echo [testo] > file` oppure script Python |
| Percorsi con spazi | Windows richiede virgolette | Sempre `"C:\Users\Nome Cognome\..."` |
