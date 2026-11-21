# XSD <-> XDTO - reference

## Mappings

| XML Schema | XDTO model |
|---|---|
| `xs:schema/@targetNamespace` | package namespace |
| `elementFormDefault` / `attributeFormDefault` | `elementFormQualified` / `attributeFormQualified` |
| `xs:import/@namespace` | dependency on another package (resolved by namespace) |
| `xs:complexType` | object type |
| `xs:simpleType` | value type |
| `xs:element` / `xs:attribute` at top level | global package property |
| `xs:element` / `xs:attribute` inside a type | property of the type |
| `@minOccurs` / `@maxOccurs="unbounded"` | `lowerBound` / `upperBound="-1"` |
| `@nillable`, `@default`, `@fixed`, `@ref` | same in meaning |
| anonymous `xs:simpleType`/`xs:complexType` in a declaration | inline property type |
| `xs:complexContent/xs:extension/@base` | type inheritance |
| `@abstract`, `@mixed` | same |
| `xs:choice` | a type choosing one of the variants |
| `xs:any` + `xs:anyAttribute` | open type |
| `xs:simpleContent/xs:extension/@base` | property for the element's own value |
| `xs:restriction` + facets | base type + restrictions |
| `xs:pattern`, `xs:enumeration` | same |
| `xs:list/@itemType` | list |
| `xs:union/@memberTypes` | union |

Top-level declaration order in XSD is arbitrary - the skill arranges them
in the order the model requires.

## `xdto:` annotations

The namespace is `http://v8.1c.ru/8.1/xdto`. They are needed only where XML Schema
cannot express what the model can. In most schemas they are not needed at all.

Rule: **what XSD cannot say - write as a `xdto:` attribute with the same name
as in the model**.

| Annotation | Where | Purpose |
|---|---|---|
| `xdto:nillable` | `xs:attribute` | `nillable` on an attribute property (XSD allows it only on elements) |
| `xdto:lowerBound`, `xdto:upperBound` | `xs:attribute` | multiplicity of an attribute property |
| `xdto:qualified` | declaration | override `*FormQualified` for one property |
| `xdto:name` | declaration | property name if the XML name is not suitable as a 1C identifier; the XML name goes to `localName` |
| `xdto:form` | `xs:element` | write `form` explicitly |
| `xdto:variety` | `xs:restriction`, `xs:list`, `xs:union` | write the type variety explicitly |
| `xdto:open`, `xdto:abstract`, `xdto:mixed`, `xdto:ordered`, `xdto:sequenced` | `xs:complexType` | type flags not inferable from the content model |
| `xdto:order` | `xs:complexType` | source property order if it is not "attributes first"; names via `\|` |
| `xdto:textName`, `xdto:textlowerBound`, `xdto:textupperBound`, `xdto:textnillable` | `xs:extension` in `xs:simpleContent` | parameters of the own-value property |
| `xdto:type` | `xs:enumeration` | enum literal type |
| `xdto:prefix` | declaration | a meaningful namespace prefix instead of a generated one |
| `xdto:memberTypesForm="prefixed"` | `xs:union` | write the union composition with prefixes, not `{ns}имя` |
| `xdto:declareNs` | `xs:union` | declare a namespace prefix on the node |
| `xdto:elementFormQualified`, `xdto:attributeFormQualified` | `xs:schema` | write the flags explicitly |

Example:

```xml
<xs:complexType name="КонтактнаяИнформация" xdto:sequenced="true">
    <xs:sequence>
        <xs:element name="Комментарий" type="xs:string" minOccurs="0"/>
        <xs:element name="Адрес по документу" type="xs:string"
                    xdto:name="Адрес_по_документу" minOccurs="0"/>
    </xs:sequence>
    <xs:attribute name="Представление" type="xs:string"
                  xdto:nillable="true" xdto:lowerBound="0"/>
</xs:complexType>
```

Annotations that `/xdto-decompile` writes when dumping an existing package
do not need to be written by hand - they are needed so that a reverse build returns exactly the same file.

## Metadata object properties

```xml
<xs:annotation>
    <xs:appinfo>
        <xdto:package xmlns:xdto="http://v8.1c.ru/8.1/xdto">
            <xdto:name>ОбменСБанком</xdto:name>
            <xdto:synonym lang="ru">Обмен с банком</xdto:synonym>
            <xdto:synonym lang="en">Bank exchange</xdto:synonym>
            <xdto:comment>Формат 1С:Предприятие — Клиент банка</xdto:comment>
        </xdto:package>
    </xs:appinfo>
</xs:annotation>
```

The package namespace is taken from `targetNamespace` and is not duplicated here.
The `-Name`, `-Synonym`, `-Comment` parameters take priority over this block.
