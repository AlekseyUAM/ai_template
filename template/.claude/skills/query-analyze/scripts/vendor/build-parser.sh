#!/usr/bin/env bash
# Пересобирает автономный бандл SDBL-парсера (sdbl_parse.js) из проекта
# query_console_vscode через esbuild. Бандл самодостаточен (без npm install в
# рантайме) и дёргается из Python-анализатора через `node`.
#
# Источник парсера: query_console_vscode/src/core/query/sdblParser.ts
#   parseBatch(text) -> BatchDocument (структурная модель запроса, без метаданных).
#
# Путь к репозиторию query_console_vscode: переменная окружения QUERY_CONSOLE_REPO,
# иначе — стандартное расположение рядом с проектом (../../.../query_console_vscode).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

repo="${QUERY_CONSOLE_REPO:-}"
if [ -z "$repo" ]; then
  # projects/ рядом: vendor -> scripts -> query-analyze -> skills -> .claude ->
  # template -> ai_template -> projects
  cand="$HERE/../../../../../../../query_console_vscode"
  if [ -d "$cand" ]; then repo="$(cd "$cand" && pwd)"; fi
fi

if [ -z "$repo" ] || [ ! -f "$repo/src/core/query/sdblParser.ts" ]; then
  echo "Не найден query_console_vscode. Укажите путь: QUERY_CONSOLE_REPO=/путь/к/query_console_vscode $0" >&2
  exit 1
fi
repo="$(cd "$repo" && pwd)"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/entry.ts" <<EOF
// Автогенерировано build-parser.sh. Читает текст запроса из stdin, печатает
// структурную модель (BatchDocument) в JSON. Ошибки разбора -> {"error": "..."}.
import { parseBatch } from '$repo/src/core/query/sdblParser';
let text = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (d) => (text += d));
process.stdin.on('end', () => {
  try {
    process.stdout.write(JSON.stringify(parseBatch(text)));
  } catch (e) {
    process.stdout.write(JSON.stringify({ error: String(e) }));
  }
});
EOF

( cd "$repo" && npx esbuild "$tmp/entry.ts" --bundle \
  --outfile="$HERE/sdbl_parse.js" --platform=node --format=cjs )

echo "Собрано: $HERE/sdbl_parse.js (из $repo)"
