# HTTPService, WebService (Веб-сервисы)

Both modules are `Ext/Module.bsl`, handlers are implemented there.

## HTTPService (HTTP-сервис)

| Key | Default | Values |
|------|-----------|----------|
| `rootURL` | `= name` (lowercase) | root URL |
| `reuseSessions` | `DontUse` | `DontUse` / `Use` / `AutoUse` |
| `sessionMaxAge` | `20` | session lifetime, sec |
| `urlTemplates` | `{}` | URL templates (see below) |

`urlTemplates` is an object `{ "ИмяШаблона": def }`, where `def` is:
- a string - a URL path without methods: `"/health"`;
- an object: `template` (path with parameters `{id}`, default `/имяшаблона`), `synonym`, `comment`,
  `methods` - `{ "ИмяМетода": def }`.

`methods` - the value is either a string (the HTTP method only) or an object: `httpMethod`, `handler`,
`synonym`, `comment`.

HTTP methods: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`, `CONNECT`, `TRACE`, `MERGE`.
The default handler is named `{ИмяШаблона}{ИмяМетода}`; in typical configurations it is often
arbitrary - then set `handler` explicitly.

```json
{ "type": "HTTPService", "name": "API", "rootURL": "api",
  "urlTemplates": {
    "Users": { "template": "/v1/users/{id}", "methods": { "Get": "GET", "Create": "POST", "Delete": "DELETE" } },
    "Health": "/health"
  } }
```

## WebService (Веб-сервис, SOAP)

| Key | Default | Values |
|------|-----------|----------|
| `namespace` | empty | WSDL namespace URI |
| `xdtoPackages` | empty | package list (see below) |
| `descriptorFileName` | `= name` + `.1cws` | descriptor file name |
| `reuseSessions` | `DontUse` | `DontUse` / `Use` / `AutoUse` |
| `sessionMaxAge` | `20` | session lifetime, sec |
| `operations` | `{}` | operations (see below) |

`xdtoPackages` - an **array** of values: `"XDTOPackage.Имя"` - a configuration package, any other
value - an external namespace URI (for example `"http://v8.1c.ru/8.3/data/ext"`).

`operations` - an object `{ "ИмяОперации": def }`, where `def` is:
- a string - the XDTO return type without parameters: `"xs:string"`;
- an object: `returnType` (`xs:string` by default), `nillable` (bool), `transactioned` (bool),
  `procedureName` (procedure name, by default = the operation name; key synonym - `handler`),
  `dataLockControlMode` (`Managed` by default), `synonym`, `comment`, `parameters`.

`parameters` - an object `{ "ИмяПараметра": def }`, where `def` is:
- a string - an XDTO type (`direction` = `In`);
- an object: `type` (`xs:string` by default), `nillable` (bool, `true` by default),
  `direction` (`In` / `Out` / `InOut`), `synonym`, `comment`.

XDTO types: `xs:string`, `xs:boolean`, `xs:int`, `xs:long`, `xs:decimal`, `xs:dateTime`, `xs:base64Binary`.
A type from its own namespace is specified in Clark notation - `"{http://ваш.uri}ИмяТипа"`;
the compiler declares the local `xmlns` in the tag itself, as the platform does.

```json
{ "type": "WebService", "name": "DataExchange", "namespace": "http://www.1c.ru/DataExchange",
  "operations": {
    "TestConnection": { "returnType": "xs:boolean", "handler": "ПроверкаПодключения",
                        "parameters": { "ErrorMessage": { "type": "xs:string", "direction": "Out" } } },
    "GetVersion": "xs:string"
  } }
```
