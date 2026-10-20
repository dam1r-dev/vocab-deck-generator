#!/usr/bin/env bash
# Устанавливает скиллы ui-ux-pro-max-skill и OmniRoute в ~/.claude/skills (глобально).
# Существующие скиллы с тем же именем НЕ перезаписываются: они пропускаются и выводятся в отчёте.
# Сервер OmniRoute, claude-mem и Headroom скрипт не трогает.
#
# Использование:
#   bash install-global-skills.sh --dry-run   # только показать, что будет сделано
#   bash install-global-skills.sh             # установить
set -euo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

SRC="$HOME/skill-sources"
DEST="$HOME/.claude/skills"
mkdir -p "$SRC" "$DEST"

clone() { # url dir
  if [ -d "$SRC/$2/.git" ]; then
    echo "[=] $2 уже склонирован, используем как есть"
  else
    git clone --depth 1 "$1" "$SRC/$2"
  fi
}

installed=(); skipped=(); bad=()

install_skill() { # путь к папке скилла
  local dir="$1" name
  name="$(basename "$dir")"
  if [ ! -f "$dir/SKILL.md" ]; then bad+=("$name (нет SKILL.md)"); return; fi
  if [ -e "$DEST/$name" ]; then skipped+=("$name"); return; fi
  if [ "$DRY" = 1 ]; then installed+=("$name (dry-run)"); return; fi
  cp -R "$dir" "$DEST/$name"
  installed+=("$name")
}

clone https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git ui-ux-pro-max-skill
clone https://github.com/diegosouzapw/OmniRoute.git OmniRoute

for d in "$SRC"/ui-ux-pro-max-skill/.claude/skills/*/; do install_skill "${d%/}"; done
for d in "$SRC"/OmniRoute/skills/*/; do install_skill "${d%/}"; done

echo
echo "Установлено (${#installed[@]}):"; printf '  - %s\n' "${installed[@]:-}"
echo "Пропущено, т.к. такое имя уже есть (${#skipped[@]}):"; printf '  - %s\n' "${skipped[@]:-}"
echo "Проблемы (${#bad[@]}):"; printf '  - %s\n' "${bad[@]:-}"

echo
echo "Проверка полей name/description:"
for d in "$DEST"/*/; do
  f="$d/SKILL.md"; [ -f "$f" ] || continue
  head -15 "$f" | grep -q '^name:' && head -15 "$f" | grep -q '^description:' || echo "  ! $(basename "$d"): нет name/description в начале"
done
echo "Готово. Перезапустите Claude Code (или откройте новый чат), чтобы скиллы подхватились."
