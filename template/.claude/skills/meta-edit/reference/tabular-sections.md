# Tabular sections

Operations on a tabular section and its attributes. General rules of the shorthand format, flags, batch and
positional insert - in `attributes.md`.

## add-ts

Format: `ИмяТЧ: Реквизит1: Тип1, Реквизит2: Тип2, ...`

```bash
-Operation add-ts -Value "Товары: Ном: CatalogRef.Ном | req, Кол: Число(15,3), Цена: Число(15,2), Сумма: Число(15,2)"
```

## add-ts-attribute / remove-ts-attribute / modify-ts-attribute

Operations on attributes **inside an existing tabular section**. Format: `ИмяТЧ.ОпределениеРеквизита` (dot notation).

```bash
# Добавить реквизит в ТЧ
-Operation add-ts-attribute -Value "Товары.СтавкаНДС: EnumRef.СтавкиНДС"
-Operation add-ts-attribute -Value "Товары.Скидка: Число(15,2) ;; Товары.Бонус: Число(15,2)"

# Позиционная вставка в ТЧ
-Operation add-ts-attribute -Value "Товары.Скидка: Число(15,2) >> after Цена"

# Удалить реквизит из ТЧ
-Operation remove-ts-attribute -Value "Товары.УстаревшийРекв"
-Operation remove-ts-attribute -Value "Товары.Рекв1 ;; Товары.Рекв2"

# Изменить реквизит в ТЧ (rename, type change и т.д.)
-Operation modify-ts-attribute -Value "Товары.СтароеИмя: name=НовоеИмя, type=Строка(500)"
```

Batch via `;;` - different tabular sections can be specified: `"Товары.А: Строка(50) ;; Услуги.Б: Число(10)"`.

Composite type of a tabular section attribute:
```bash
-Operation modify-ts-attribute -Value "Данные.Значение: type=Строка + Число(15,2) + Дата"
```

## modify-ts

Changing the properties of **the tabular section itself** (Synonym, FillChecking, Use, etc.):

```bash
-Operation modify-ts -Value "Товары: synonym=Товарный состав"
-Operation modify-ts -Value "Товары: fillChecking=ShowError"
```

The format is similar to `modify-attribute`: `ИмяТЧ: ключ=значение, ключ=значение`.

## remove-ts

```bash
-Operation remove-ts -Value "УстаревшаяТЧ"
```
