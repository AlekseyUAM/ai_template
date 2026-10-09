# P1.7 — Возможности MCP/скилов в субагентах — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** В каждом субагенте `template/agents/*.md` прописать возможности стандартных MCP (считаем все поднятыми) и скилов `template/skills` (по `tmp/NOTE.md`).

## Global Constraints
- 6 агентов: orchestrator, analyst, architect, developer, tester, reviewer.
- Тексты на русском. Не трогать frontmatter/плейсхолдеры `{{MODEL}}`/`{{EFFORT}}`.
- Скилов в `template/skills` ~72 — НЕ перечислять все построчно; сгруппировать.

## Task 1: добавить раздел «Возможности окружения» во все 6 агентов
В каждый `template/agents/<name>.md` добавить общий раздел (одинаковый блок, можно с лёгкой ролевой припиской):

```markdown
## Возможности окружения

Считай, что все стандартные MCP-серверы подняты и доступны:
- `1c-md` — запросы к метаданным конфигурации.
- `1c-syntax-checker-mcp` — статический анализ BSL.
- `bsl-platform-context` — справка по методам платформы.
- `1c-naparnic` — любые вопросы по 1С.
- `code-index` — поиск по индексированной кодовой базе.

Доступны навыки из `.claude/skills` (копируются из `template/skills`):
- Руководства: `mcp-usage`, `bsl-coding-standards`, `sdd-tdd-workflow`, `task-orchestration`.
- Пакетные операции с платформой: `1c-batch` (выгрузка/загрузка cf/cfe/xml, epf/erf, dt, проверки).
- Операционные навыки 1С (из cc-1c-skills): анализ и правка метаданных (`meta-*`),
  конфигурации (`cf-*`) и расширений (`cfe-*`), форм (`form-*`), ролей (`role-*`),
  СКД (`skd-*`), макетов (`mxl-*`), XDTO (`xdto-*`), подсистем (`subsystem-*`),
  веб-публикации и web-тесты (`web-*`), служебные (`help-add`, `template-*`, `img-grid`).

Перед работой сверяйся с навыком `mcp-usage` (какой MCP когда применять).
```

Валидационный тест `app/tests/env/test_agent_capabilities.py`:
```python
from pathlib import Path
A = Path(__file__).resolve().parents[3] / "template" / "agents"
MCP = ["1c-md","1c-syntax-checker-mcp","bsl-platform-context","1c-naparnic","code-index"]

def test_each_agent_lists_mcp_and_skills():
    for name in ("orchestrator","analyst","architect","developer","tester","reviewer"):
        t = (A / f"{name}.md").read_text(encoding="utf-8")
        assert "Возможности окружения" in t, name
        for m in MCP:
            assert m in t, f"{name}:{m}"
        assert "1c-batch" in t and ".claude/skills" in t
```

- [ ] Step1 write test → fail. Step2 add the section to all 6 agents. Step3 run `cd app && PYTHONPATH=src python -m pytest tests/env/test_agent_capabilities.py tests/env/test_content_files.py tests/env/test_agent_inputs.py -q` → pass (не ломаем существующие). Step4 FULL suite. Step5 commit `feat(agents): возможности стандартных MCP и скилов в субагентах`.

## Self-Review
- Все 6 агентов получают раздел возможностей (MCP + сгруппированные скилы). Не ломает прочие проверки агентов (frontmatter, деградируемый Вход, отсутствие YaxUnit).
