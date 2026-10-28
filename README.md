# AI značka

Windows aplikácia, ktorá do obrázkov (JPG, PNG, WebP) zapíše značku, že sú vytvorené AI.
Obrazové dáta sa nemenia, obrázok sa znova nekomprimuje, EXIF a ostatné metadáta ostávajú.

## Čo sa zapíše (XMP)
| Pole (exiftool) | Hodnota |
|---|---|
| Digital Source Type | `http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia` (alebo `compositeWith…` pri úprave fotky) |
| Subject | `Generated AI` – vo Windows *Vlastnosti → Podrobnosti → Značky* |
| Description | `Generated AI` – len ak obrázok ešte nemá popis |
| AI System Used | názov nástroja, ak ho vyplníš (napr. Midjourney) |

Text značky aj nástroj sa dajú v aplikácii zmeniť. Prepínač vypnutý = súbor sa uloží ako presná kópia.

## Stiahnutie
Najnovšia verzia: **[AI-znacka.exe](https://github.com/ambidsignSK/ai-znacka/releases/latest/download/AI-znacka.exe)**
(všetky verzie v [Releases](https://github.com/ambidsignSK/ai-znacka/releases)).

Aplikácia má tlačidlo **Aktualizovať** – stiahne a nainštaluje novú verziu sama.
Novú verziu zostaví workflow `.github/workflows/build.yml` pri každom pushi do `main`.

## Použitie
- Spusti `AI-znacka.exe` a pretiahni obrázky (alebo celý priečinok) do okna.
- **Stiahnuť všetky** uloží upravené obrázky s rovnakými názvami do priečinka
  `Stiahnuté súbory\AI_oznacene` (priečinok sa dá zmeniť tlačidlom *Zmeniť…*) a ponúkne ho otvoriť.
- **Stiahnuť vybraný ako…** (aj pravý klik na riadok) uloží jeden obrázok kam chceš.
- **Zmazať originály** presunie do Koša pôvodné obrázky, ktorých upravenú kópiu už máš stiahnutú
  (vybrané riadky, alebo všetky, ak nie je nič vybrané).
- Dvojklik na riadok zobrazí metadáta súboru ako exiftool.
- Skratka do ponuky *Odoslať do*: `Win+R` → `shell:sendto` → vlož tam odkaz na `AI-znacka.exe`.

## Spustenie zo zdrojákov
```
pip install tkinterdnd2
python app.py
```
