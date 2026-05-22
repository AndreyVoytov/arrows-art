# Localisation Workflow

Source docs: Yandex Games uses ISO 639-1 language codes and publishes the supported language list in the official SDK documentation: https://yandex.com/dev/games/doc/en/concepts/languages-and-domains

## Source File

Prepare balance data first:

```bash
npm run prepare-balance
```

For already downloaded local sheet cache:

```bash
npm run prepare-balance-local
```

The exporter writes one Russian source dictionary:

- `tmp/text_src/ru.json`

Treat `tmp/text_src/ru.json` as an intermediate source file. Do not write translated target languages into `tmp/text_src`.

It also writes game balance configs:

- `config/level_rewards.json`
- `config/dialogs.json`

## Target Files

Create publishable localization dictionaries here:

```text
config/text/<lang>.json
```

The Russian publish copy is:

```text
config/text/ru.json
```

## Target Languages

Use these Yandex Games language codes unless the platform docs change:

```text
ar az be bg ca cs de en es fa fr he hi hu hy id it ja ka kk ko nl pl pt ro ru sk sr th tk tr uk uz vi zh
```

Minimum high-traffic set from Yandex docs:

```text
ru tr zh ko hi vi en
```

## AI Translation Prompt

Use `tmp/text_src/ru.json` as the source. Tell the model to translate values only and keep keys byte-for-byte identical.

```text
Translate this game localization JSON from Russian to <LANGUAGE>.

Rules:
- Return valid JSON only.
- Keep every key exactly unchanged.
- Translate only string values.
- Keep object names short and natural for a casual room renovation game.
- Do not transliterate unless that is natural in the target language.
- Preserve capitalization style.
- Do not add comments, markdown, or extra keys.

JSON:
<PASTE ru.json>
```

Save outputs as:

```text
config/text/<lang>.json
```

Examples:

```text
config/text/en.json
config/text/tr.json
```

## Validation

After translation, validate that all localized files have the same keys as the Russian source:

PowerShell:

```powershell
@'
import json
from pathlib import Path

source_path = Path("tmp/text_src/ru.json")
target_root = Path("config/text")
source = json.loads(source_path.read_text(encoding="utf-8"))
source_keys = set(source)

for path in sorted(target_root.glob("*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    keys = set(data)
    missing = sorted(source_keys - keys)
    extra = sorted(keys - source_keys)
    if missing or extra:
        raise SystemExit(
            f"{path}: missing={missing[:10]} extra={extra[:10]}"
        )

    empty = [key for key, value in data.items() if not str(value).strip()]
    if empty:
        raise SystemExit(f"{path}: empty translations={empty[:10]}")

print("localization ok")
'@ | python -
```

## Review Checklist

- Keep `*_loc` identifiers untranslated.
- Check short UI labels in-game because German, Spanish, Turkish, and Vietnamese strings can be longer than Russian.
- For `ar`, `fa`, and `he`, verify right-to-left rendering in the UI.
- For `zh`, `ja`, `ko`, and `th`, verify that the game font contains glyphs for the language.
- Before release, compare the target language list with the current Yandex Games documentation.
