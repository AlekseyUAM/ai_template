# Enum values and commands

## add-enumValue / add-command

Just names (batch via `;;`):
```bash
-Operation add-enumValue -Value "Значение1 ;; Значение2 ;; Значение3"
-Operation add-command -Value "ОткрытьДосье"
```

A command is created together with a module stub `Commands/<Имя>/Ext/CommandModule.bsl`.

## Forms and templates - by other skills

Besides the entry in `ChildObjects`, a form and a template have their own files, so `meta-edit`
does not add or remove them:

| What | Add | Remove |
|-----|----------|---------|
| Form | the `form-add` skill | the `form-remove` skill |
| Template | the `template-add` skill | the `template-remove` skill |

The form content is assembled by the `form-compile` skill.
