// src/core/query/queryModel.ts
function accountingPositionKeys(slice, hasSubconto, corr) {
  const sub = hasSubconto ? [null] : [];
  switch (slice) {
    case "\u041E\u0441\u0442\u0430\u0442\u043A\u0438":
      return ["period", "accountCondition", ...sub, "condition"];
    case "\u041E\u0431\u043E\u0440\u043E\u0442\u044B":
      return corr ? ["startPeriod", "endPeriod", "periodicity", "accountCondition", ...sub, "condition", "corrAccountCondition", ...sub] : ["startPeriod", "endPeriod", "periodicity", "accountCondition", ...sub, "condition"];
    case "\u041E\u0431\u043E\u0440\u043E\u0442\u044B\u0414\u0442\u041A\u0442":
      return ["startPeriod", "endPeriod", "periodicity", "accountDtCondition", ...sub, "accountKtCondition", ...sub, "condition"];
    case "\u041E\u0441\u0442\u0430\u0442\u043A\u0438\u0418\u041E\u0431\u043E\u0440\u043E\u0442\u044B":
      return ["startPeriod", "endPeriod", "periodicity", "fillMethod", "accountCondition", ...sub, "condition"];
    case "\u0414\u0432\u0438\u0436\u0435\u043D\u0438\u044F\u0421\u0421\u0443\u0431\u043A\u043E\u043D\u0442\u043E":
      return ["startPeriod", "endPeriod", "condition", "order", "top"];
    default:
      return [];
  }
}
function defaultTableAlias(t) {
  if (t.alias) return t.alias;
  const parts = t.fullName.split(".");
  if (parts.length > 2) return parts[1] + parts.slice(2).join("");
  const name = parts[1] ?? t.fullName;
  return name.startsWith("#") ? name.slice(1) : name;
}

// src/core/query/sdblLexer.ts
var KEYWORDS = /* @__PURE__ */ new Set([
  "\u0412\u042B\u0411\u0420\u0410\u0422\u042C",
  "\u0420\u0410\u0417\u0420\u0415\u0428\u0415\u041D\u041D\u042B\u0415",
  "\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415",
  "\u041F\u0415\u0420\u0412\u042B\u0415",
  "\u0418\u0417",
  "\u041A\u0410\u041A",
  "\u0421\u0423\u041C\u041C\u0410",
  "\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E",
  "\u041C\u0410\u041A\u0421\u0418\u041C\u0423\u041C",
  "\u041C\u0418\u041D\u0418\u041C\u0423\u041C",
  "\u0421\u0420\u0415\u0414\u041D\u0415\u0415",
  // 6.2.B: ГДЕ / соединения / группировка.
  "\u0413\u0414\u0415",
  "\u0418",
  "\u0412",
  "\u041C\u0415\u0416\u0414\u0423",
  "\u041F\u041E\u0414\u041E\u0411\u041D\u041E",
  "\u0421\u041E\u0415\u0414\u0418\u041D\u0415\u041D\u0418\u0415",
  "\u0412\u041D\u0423\u0422\u0420\u0415\u041D\u041D\u0415\u0415",
  "\u041B\u0415\u0412\u041E\u0415",
  "\u041F\u0420\u0410\u0412\u041E\u0415",
  "\u041F\u041E\u041B\u041D\u041E\u0415",
  "\u041F\u041E",
  "\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u0423\u042E\u0429\u0418\u041C",
  "\u041D\u0410\u0411\u041E\u0420\u0410\u041C",
  "\u0418\u041C\u0415\u042E\u0429\u0418\u0415",
  // 6.2.C: временные таблицы, порядок, итоги, индекс, построитель.
  "\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C",
  "\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C",
  "\u0423\u041D\u0418\u0427\u0422\u041E\u0416\u0418\u0422\u042C",
  "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C",
  "\u0423\u0411\u042B\u0412",
  "\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415",
  "\u0418\u0422\u041E\u0413\u0418",
  "\u041E\u0411\u0429\u0418\u0415",
  "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F",
  "\u0422\u041E\u041B\u042C\u041A\u041E",
  "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0423\u041D\u0418\u041A\u0410\u041B\u042C\u041D\u041E",
  "\u0414\u041B\u042F",
  "\u0418\u0417\u041C\u0415\u041D\u0415\u041D\u0418\u042F",
  // 6.2.D: объединения.
  "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C",
  "\u0412\u0421\u0415"
]);
var TWO_CHAR = /* @__PURE__ */ new Set(["<=", ">=", "<>"]);
var ONE_CHAR = /* @__PURE__ */ new Set([
  ".",
  ",",
  "(",
  ")",
  "*",
  "{",
  "}",
  ";",
  "=",
  "<",
  ">",
  "+",
  "-",
  "/",
  "%",
  "?",
  "@",
  "[",
  "]"
]);
function isIdentStart(ch) {
  return ch === "_" || /\p{L}/u.test(ch);
}
function isIdentPart(ch) {
  return ch === "_" || /[\p{L}\p{N}]/u.test(ch);
}
function isDigit(ch) {
  return ch >= "0" && ch <= "9";
}
function tokenize(text2, opts) {
  const tokens = [];
  let i = 0;
  let line = 1;
  let col = 1;
  const advance = (n = 1) => {
    for (let k = 0; k < n; k++) {
      if (text2[i] === "\n") {
        line++;
        col = 1;
      } else {
        col++;
      }
      i++;
    }
  };
  const push = (type, value, pos, l, c, text3) => {
    tokens.push({ type, value, text: text3 ?? value, pos, line: l, col: c });
  };
  while (i < text2.length) {
    const ch = text2[i];
    if (ch === " " || ch === "	" || ch === "\r" || ch === "\n") {
      advance();
      continue;
    }
    if (ch === "/" && text2[i + 1] === "/") {
      const startPos2 = i;
      const startLine2 = line;
      const startCol2 = col;
      while (i < text2.length && text2[i] !== "\n") advance();
      if (opts?.comments) {
        const value = text2.slice(startPos2, i);
        push("comment", value, startPos2, startLine2, startCol2);
      }
      continue;
    }
    const startPos = i;
    const startLine = line;
    const startCol = col;
    if (ch === "#") {
      advance();
      const nameStart = i;
      while (i < text2.length && isIdentPart(text2[i])) advance();
      if (i === nameStart) {
        throw lexError('\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u0438\u043C\u044F \u043F\u043E\u0441\u043B\u0435 "#"', startLine, startCol);
      }
      let name = "#" + text2.slice(nameStart, i);
      if (text2[i] === "#") {
        advance();
        name += "#";
      }
      push("ident", name, startPos, startLine, startCol);
      continue;
    }
    if (ch === "&") {
      advance();
      const nameStart = i;
      while (i < text2.length && isIdentPart(text2[i])) advance();
      if (i === nameStart) {
        throw lexError('\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u0438\u043C\u044F \u043F\u0430\u0440\u0430\u043C\u0435\u0442\u0440\u0430 \u043F\u043E\u0441\u043B\u0435 "&"', startLine, startCol);
      }
      push("param", "&" + text2.slice(nameStart, i), startPos, startLine, startCol);
      continue;
    }
    if (ch === '"') {
      advance();
      let value = '"';
      while (i < text2.length) {
        if (text2[i] === '"') {
          if (text2[i + 1] === '"') {
            value += '""';
            advance(2);
            continue;
          }
          value += '"';
          advance();
          break;
        }
        value += text2[i];
        advance();
      }
      push("string", value, startPos, startLine, startCol);
      continue;
    }
    if (ch === "'") {
      advance();
      let value = "'";
      while (i < text2.length && text2[i] !== "'") {
        value += text2[i];
        advance();
      }
      if (text2[i] === "'") {
        value += "'";
        advance();
      }
      push("date", value, startPos, startLine, startCol);
      continue;
    }
    if (isDigit(ch)) {
      let value = "";
      while (i < text2.length && isDigit(text2[i])) {
        value += text2[i];
        advance();
      }
      if (text2[i] === "." && isDigit(text2[i + 1])) {
        value += ".";
        advance();
        while (i < text2.length && isDigit(text2[i])) {
          value += text2[i];
          advance();
        }
      }
      push("number", value, startPos, startLine, startCol);
      continue;
    }
    if (isIdentStart(ch)) {
      let value = "";
      while (i < text2.length && isIdentPart(text2[i])) {
        value += text2[i];
        advance();
      }
      const upper = value.toUpperCase();
      if (KEYWORDS.has(upper)) {
        push("keyword", upper, startPos, startLine, startCol, value);
      } else {
        push("ident", value, startPos, startLine, startCol);
      }
      continue;
    }
    const two = text2.slice(i, i + 2);
    if (TWO_CHAR.has(two)) {
      advance(2);
      push("punct", two, startPos, startLine, startCol);
      continue;
    }
    if (ONE_CHAR.has(ch)) {
      advance();
      push("punct", ch, startPos, startLine, startCol);
      continue;
    }
    throw lexError(`\u043D\u0435\u043E\u0436\u0438\u0434\u0430\u043D\u043D\u044B\u0439 \u0441\u0438\u043C\u0432\u043E\u043B ${JSON.stringify(ch)}`, startLine, startCol);
  }
  push("eof", "", i, line, col);
  return tokens;
}
function lexError(message, line, col) {
  return new Error(`\u041B\u0435\u043A\u0441\u0438\u0447\u0435\u0441\u043A\u0430\u044F \u043E\u0448\u0438\u0431\u043A\u0430 ${line}:${col} \u2014 ${message}`);
}

// src/core/query/functionCatalog.ts
var fn = (label, template) => ({ label, template });
var op = (symbol) => ({ label: symbol, template: symbol });
var FUNCTION_CATALOG = {
  label: "\u0424\u0443\u043D\u043A\u0446\u0438\u0438 \u044F\u0437\u044B\u043A\u0430 \u0437\u0430\u043F\u0440\u043E\u0441\u043E\u0432",
  children: [
    {
      label: "\u0424\u0443\u043D\u043A\u0446\u0438\u0438",
      children: [
        {
          label: "\u0424\u0443\u043D\u043A\u0446\u0438\u0438 \u0440\u0430\u0431\u043E\u0442\u044B \u0441\u043E \u0441\u0442\u0440\u043E\u043A\u0430\u043C\u0438",
          children: [
            fn("\u0421\u0422\u0420\u041E\u041A\u0410", "\u0421\u0422\u0420\u041E\u041A\u0410(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u0414\u041B\u0418\u041D\u0410\u0421\u0422\u0420\u041E\u041A\u0418", "\u0414\u041B\u0418\u041D\u0410\u0421\u0422\u0420\u041E\u041A\u0418(<\u0421\u0442\u0440\u043E\u043A\u0430>)"),
            fn("\u041B\u0415\u0412", "\u041B\u0415\u0412(<\u0421\u0442\u0440\u043E\u043A\u0430>, <\u0427\u0438\u0441\u043B\u043E\u0421\u0438\u043C\u0432\u043E\u043B\u043E\u0432>)"),
            fn("\u041F\u0420\u0410\u0412", "\u041F\u0420\u0410\u0412(<\u0421\u0442\u0440\u043E\u043A\u0430>, <\u0427\u0438\u0441\u043B\u043E\u0421\u0438\u043C\u0432\u043E\u043B\u043E\u0432>)"),
            fn("\u0412\u0420\u0415\u0413", "\u0412\u0420\u0415\u0413(<\u0421\u0442\u0440\u043E\u043A\u0430>)"),
            fn("\u041D\u0420\u0415\u0413", "\u041D\u0420\u0415\u0413(<\u0421\u0442\u0440\u043E\u043A\u0430>)"),
            fn("\u041F\u041E\u0414\u0421\u0422\u0420\u041E\u041A\u0410", "\u041F\u041E\u0414\u0421\u0422\u0420\u041E\u041A\u0410(<\u0421\u0442\u0440\u043E\u043A\u0430>, <\u041F\u043E\u0437\u0438\u0446\u0438\u044F>, <\u0414\u043B\u0438\u043D\u0430>)"),
            fn("\u0421\u041E\u041A\u0420\u041B", "\u0421\u041E\u041A\u0420\u041B(<\u0421\u0442\u0440\u043E\u043A\u0430>)"),
            fn("\u0421\u041E\u041A\u0420\u041F", "\u0421\u041E\u041A\u0420\u041F(<\u0421\u0442\u0440\u043E\u043A\u0430>)"),
            fn("\u0421\u041E\u041A\u0420\u041B\u041F", "\u0421\u041E\u041A\u0420\u041B\u041F(<\u0421\u0442\u0440\u043E\u043A\u0430>)"),
            fn("\u0421\u0422\u0420\u041D\u0410\u0419\u0422\u0418", "\u0421\u0422\u0420\u041D\u0410\u0419\u0422\u0418(<\u0421\u0442\u0440\u043E\u043A\u0430>, <\u041F\u043E\u0434\u0441\u0442\u0440\u043E\u043A\u0430\u041F\u043E\u0438\u0441\u043A\u0430>)"),
            fn("\u0421\u0422\u0420\u0417\u0410\u041C\u0415\u041D\u0418\u0422\u042C", "\u0421\u0422\u0420\u0417\u0410\u041C\u0415\u041D\u0418\u0422\u042C(<\u0421\u0442\u0440\u043E\u043A\u0430>, <\u041F\u043E\u0434\u0441\u0442\u0440\u043E\u043A\u0430\u041F\u043E\u0438\u0441\u043A\u0430>, <\u041F\u043E\u0434\u0441\u0442\u0440\u043E\u043A\u0430\u0417\u0430\u043C\u0435\u043D\u044B>)")
          ]
        },
        {
          label: "\u0424\u0443\u043D\u043A\u0446\u0438\u0438 \u0440\u0430\u0431\u043E\u0442\u044B \u0441 \u0434\u0430\u0442\u0430\u043C\u0438",
          children: [
            fn("\u0413\u041E\u0414", "\u0413\u041E\u0414(<\u0414\u0430\u0442\u0430>)"),
            fn("\u041A\u0412\u0410\u0420\u0422\u0410\u041B", "\u041A\u0412\u0410\u0420\u0422\u0410\u041B(<\u0414\u0430\u0442\u0430>)"),
            fn("\u041C\u0415\u0421\u042F\u0426", "\u041C\u0415\u0421\u042F\u0426(<\u0414\u0430\u0442\u0430>)"),
            fn("\u0414\u0415\u041D\u042C\u0413\u041E\u0414\u0410", "\u0414\u0415\u041D\u042C\u0413\u041E\u0414\u0410(<\u0414\u0430\u0442\u0430>)"),
            fn("\u0414\u0415\u041D\u042C", "\u0414\u0415\u041D\u042C(<\u0414\u0430\u0442\u0430>)"),
            fn("\u041D\u0415\u0414\u0415\u041B\u042F", "\u041D\u0415\u0414\u0415\u041B\u042F(<\u0414\u0430\u0442\u0430>)"),
            fn("\u0414\u0415\u041D\u042C\u041D\u0415\u0414\u0415\u041B\u0418", "\u0414\u0415\u041D\u042C\u041D\u0415\u0414\u0415\u041B\u0418(<\u0414\u0430\u0442\u0430>)"),
            fn("\u0427\u0410\u0421", "\u0427\u0410\u0421(<\u0414\u0430\u0442\u0430>)"),
            fn("\u041C\u0418\u041D\u0423\u0422\u0410", "\u041C\u0418\u041D\u0423\u0422\u0410(<\u0414\u0430\u0442\u0430>)"),
            fn("\u0421\u0415\u041A\u0423\u041D\u0414\u0410", "\u0421\u0415\u041A\u0423\u041D\u0414\u0410(<\u0414\u0430\u0442\u0430>)"),
            fn("\u041D\u0410\u0427\u0410\u041B\u041E\u041F\u0415\u0420\u0418\u041E\u0414\u0410", "\u041D\u0410\u0427\u0410\u041B\u041E\u041F\u0415\u0420\u0418\u041E\u0414\u0410(<\u0414\u0430\u0442\u0430>, <\u041F\u0435\u0440\u0438\u043E\u0434>)"),
            fn("\u041A\u041E\u041D\u0415\u0426\u041F\u0415\u0420\u0418\u041E\u0414\u0410", "\u041A\u041E\u041D\u0415\u0426\u041F\u0415\u0420\u0418\u041E\u0414\u0410(<\u0414\u0430\u0442\u0430>, <\u041F\u0435\u0440\u0438\u043E\u0434>)"),
            fn("\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C\u041A\u0414\u0410\u0422\u0415", "\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C\u041A\u0414\u0410\u0422\u0415(<\u0414\u0430\u0442\u0430>, <\u0422\u0438\u043F>, <\u041A\u043E\u043B\u0438\u0447\u0435\u0441\u0442\u0432\u043E>)"),
            fn("\u0420\u0410\u0417\u041D\u041E\u0421\u0422\u042C\u0414\u0410\u0422", "\u0420\u0410\u0417\u041D\u041E\u0421\u0422\u042C\u0414\u0410\u0422(<\u0414\u0430\u0442\u04301>, <\u0414\u0430\u0442\u04302>, <\u0422\u0438\u043F>)")
          ]
        },
        {
          label: "\u0424\u0443\u043D\u043A\u0446\u0438\u0438 \u0440\u0430\u0431\u043E\u0442\u044B \u0441 \u0447\u0438\u0441\u043B\u0430\u043C\u0438",
          children: [
            fn("ACOS", "ACOS(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("ASIN", "ASIN(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("ATAN", "ATAN(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("COS", "COS(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("TAN", "TAN(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("SIN", "SIN(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("EXP", "EXP(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("LOG", "LOG(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("LOG10", "LOG10(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("POW", "POW(<\u041E\u0441\u043D\u043E\u0432\u0430\u043D\u0438\u0435>, <\u0421\u0442\u0435\u043F\u0435\u043D\u044C>)"),
            fn("SQRT", "SQRT(<\u0427\u0438\u0441\u043B\u043E>)"),
            fn("\u041E\u041A\u0420", "\u041E\u041A\u0420(<\u0427\u0438\u0441\u043B\u043E>, <\u0420\u0430\u0437\u0440\u044F\u0434\u043D\u043E\u0441\u0442\u044C>)"),
            fn("\u0426\u0415\u041B", "\u0426\u0415\u041B(<\u0427\u0438\u0441\u043B\u043E>)")
          ]
        },
        {
          label: "\u0410\u0433\u0440\u0435\u0433\u0430\u0442\u043D\u044B\u0435 \u0444\u0443\u043D\u043A\u0446\u0438\u0438",
          children: [
            fn("\u0421\u0423\u041C\u041C\u0410", "\u0421\u0423\u041C\u041C\u0410(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u041C\u0418\u041D\u0418\u041C\u0423\u041C", "\u041C\u0418\u041D\u0418\u041C\u0423\u041C(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u041C\u0410\u041A\u0421\u0418\u041C\u0423\u041C", "\u041C\u0410\u041A\u0421\u0418\u041C\u0423\u041C(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u0421\u0420\u0415\u0414\u041D\u0415\u0415", "\u0421\u0420\u0415\u0414\u041D\u0415\u0415(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E", "\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E(\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415)", "\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E(\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415 <\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)")
          ]
        },
        {
          label: "\u041F\u0440\u043E\u0447\u0438\u0435 \u0444\u0443\u043D\u043A\u0446\u0438\u0438",
          children: [
            fn("\u0415\u0421\u0422\u042CNULL", "\u0415\u0421\u0422\u042CNULL(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>, <\u0417\u043D\u0430\u0447\u0435\u043D\u0438\u0435\u0417\u0430\u043C\u0435\u043D\u044B>)"),
            fn("\u041F\u0420\u0415\u0414\u0421\u0422\u0410\u0412\u041B\u0415\u041D\u0418\u0415", "\u041F\u0420\u0415\u0414\u0421\u0422\u0410\u0412\u041B\u0415\u041D\u0418\u0415(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u041F\u0420\u0415\u0414\u0421\u0422\u0410\u0412\u041B\u0415\u041D\u0418\u0415\u0421\u0421\u042B\u041B\u041A\u0418", "\u041F\u0420\u0415\u0414\u0421\u0422\u0410\u0412\u041B\u0415\u041D\u0418\u0415\u0421\u0421\u042B\u041B\u041A\u0418(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u0422\u0418\u041F\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u042F", "\u0422\u0418\u041F\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u042F(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u0410\u0412\u0422\u041E\u041D\u041E\u041C\u0415\u0420\u0417\u0410\u041F\u0418\u0421\u0418", "\u0410\u0412\u0422\u041E\u041D\u041E\u041C\u0415\u0420\u0417\u0410\u041F\u0418\u0421\u0418()"),
            fn("\u0420\u0410\u0417\u041C\u0415\u0420\u0425\u0420\u0410\u041D\u0418\u041C\u042B\u0425\u0414\u0410\u041D\u041D\u042B\u0425", "\u0420\u0410\u0417\u041C\u0415\u0420\u0425\u0420\u0410\u041D\u0418\u041C\u042B\u0425\u0414\u0410\u041D\u041D\u042B\u0425(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)"),
            fn("\u0423\u041D\u0418\u041A\u0410\u041B\u042C\u041D\u042B\u0419\u0418\u0414\u0415\u041D\u0422\u0418\u0424\u0418\u041A\u0410\u0422\u041E\u0420", "\u0423\u041D\u0418\u041A\u0410\u041B\u042C\u041D\u042B\u0419\u0418\u0414\u0415\u041D\u0422\u0418\u0424\u0418\u041A\u0410\u0422\u041E\u0420(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435>)")
          ]
        }
      ]
    },
    {
      label: "\u041E\u043F\u0435\u0440\u0430\u0442\u043E\u0440\u044B",
      children: [
        {
          label: "\u0410\u0440\u0438\u0444\u043C\u0435\u0442\u0438\u0447\u0435\u0441\u043A\u0438\u0435 \u043E\u043F\u0435\u0440\u0430\u0442\u043E\u0440\u044B",
          children: [op("+"), op("-"), op("*"), op("/")]
        },
        {
          label: "\u041B\u043E\u0433\u0438\u0447\u0435\u0441\u043A\u0438\u0435 \u043E\u043F\u0435\u0440\u0430\u0442\u043E\u0440\u044B",
          children: [
            op("="),
            op("<>"),
            op("<"),
            op("<="),
            op(">"),
            op(">="),
            op("\u0418"),
            op("\u0418\u041B\u0418"),
            op("\u041D\u0415"),
            op("\u041F\u041E\u0414\u041E\u0411\u041D\u041E"),
            op("\u0412"),
            op("\u0412 \u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418"),
            op("\u041C\u0415\u0416\u0414\u0423"),
            op("\u0415\u0421\u0422\u042C NULL"),
            op("\u0421\u0421\u042B\u041B\u041A\u0410")
          ]
        },
        {
          label: "\u041F\u0440\u043E\u0447\u0438\u0435 \u043E\u043F\u0435\u0440\u0430\u0442\u043E\u0440\u044B",
          children: [
            fn("\u0412\u042B\u0411\u041E\u0420", "\u0412\u042B\u0411\u041E\u0420 \u041A\u041E\u0413\u0414\u0410 <\u0423\u0441\u043B\u043E\u0432\u0438\u0435> \u0422\u041E\u0413\u0414\u0410 <\u0417\u043D\u0430\u0447\u0435\u043D\u0438\u0435> \u0418\u041D\u0410\u0427\u0415 <\u0417\u043D\u0430\u0447\u0435\u043D\u0438\u0435> \u041A\u041E\u041D\u0415\u0426"),
            fn("\u0412\u042B\u0420\u0410\u0417\u0418\u0422\u042C", "\u0412\u042B\u0420\u0410\u0417\u0418\u0422\u042C(<\u0412\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435> \u041A\u0410\u041A <\u0422\u0438\u043F>)")
          ]
        }
      ]
    },
    {
      label: "\u041F\u0440\u043E\u0447\u0435\u0435",
      children: [
        fn("\u0414\u0410\u0422\u0410\u0412\u0420\u0415\u041C\u042F", "\u0414\u0410\u0422\u0410\u0412\u0420\u0415\u041C\u042F(<\u0413\u043E\u0434>, <\u041C\u0435\u0441\u044F\u0446>, <\u0414\u0435\u043D\u044C>)"),
        fn("\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415", "\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415(<\u041F\u043E\u043B\u043D\u043E\u0435\u0418\u043C\u044F>)"),
        fn("\u0422\u0418\u041F", "\u0422\u0418\u041F(<\u0418\u043C\u044F\u0422\u0438\u043F\u0430>)"),
        fn("\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u041D\u041E\u041F\u041E", "\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u041D\u041E\u041F\u041E(<\u041F\u043E\u043B\u0435>)")
      ]
    }
  ]
};

// src/core/query/exprFormatter.ts
var TAB = "	";
var inlineSubqueryReflow = null;
function setInlineSubqueryReflow(fn2) {
  inlineSubqueryReflow = fn2;
}
var FUNCTION_WORDS = (() => {
  const acc = [];
  const walk = (n) => {
    if ("children" in n) n.children.forEach(walk);
    else acc.push(n.label);
  };
  walk(FUNCTION_CATALOG);
  const wordRe = /^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9]*$/u;
  return new Set(acc.filter((l) => wordRe.test(l)).map((l) => l.toUpperCase()));
})();
var LITERAL_WORDS = /* @__PURE__ */ new Set(["\u041D\u0415\u041E\u041F\u0420\u0415\u0414\u0415\u041B\u0415\u041D\u041E", "\u0418\u0421\u0422\u0418\u041D\u0410", "\u041B\u041E\u0416\u042C", "NULL"]);
var AGGREGATE_WORDS = /* @__PURE__ */ new Set(["\u0421\u0423\u041C\u041C\u0410", "\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E", "\u041C\u0410\u041A\u0421\u0418\u041C\u0423\u041C", "\u041C\u0418\u041D\u0418\u041C\u0423\u041C", "\u0421\u0420\u0415\u0414\u041D\u0415\u0415"]);
var CALL_NOSPACE_WORDS = /* @__PURE__ */ new Set(["\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415"]);
var PRIMITIVE_TYPE_WORDS = /* @__PURE__ */ new Set(["\u0421\u0422\u0420\u041E\u041A\u0410", "\u0427\u0418\u0421\u041B\u041E", "\u0414\u0410\u0422\u0410", "\u0411\u0423\u041B\u0415\u0412\u041E"]);
var PERIOD_WORDS = /* @__PURE__ */ new Set([
  "\u0413\u041E\u0414",
  "\u041F\u041E\u041B\u0423\u0413\u041E\u0414\u0418\u0415",
  "\u041A\u0412\u0410\u0420\u0422\u0410\u041B",
  "\u041C\u0415\u0421\u042F\u0426",
  "\u0414\u0415\u041A\u0410\u0414\u0410",
  "\u041D\u0415\u0414\u0415\u041B\u042F",
  "\u0414\u0415\u041D\u042C",
  "\u0427\u0410\u0421",
  "\u041C\u0418\u041D\u0423\u0422\u0410",
  "\u0421\u0415\u041A\u0423\u041D\u0414\u0410"
]);
var PERIOD_FUNCTIONS = /* @__PURE__ */ new Set(["\u041D\u0410\u0427\u0410\u041B\u041E\u041F\u0415\u0420\u0418\u041E\u0414\u0410", "\u041A\u041E\u041D\u0415\u0426\u041F\u0415\u0420\u0418\u041E\u0414\u0410", "\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C\u041A\u0414\u0410\u0422\u0415", "\u0420\u0410\u0417\u041D\u041E\u0421\u0422\u042C\u0414\u0410\u0422"]);
function tokUpper(t) {
  return (t.text ?? t.value).toUpperCase();
}
var COMPARISON_PUNCT = /* @__PURE__ */ new Set(["=", "<>", "<", ">", "<=", ">="]);
var UNARY_MINUS_PREV_WORDS = /* @__PURE__ */ new Set([
  "\u0418\u041D\u0410\u0427\u0415",
  "\u0422\u041E\u0413\u0414\u0410",
  "\u041A\u041E\u0413\u0414\u0410",
  "\u0412\u042B\u0411\u041E\u0420",
  "\u0418",
  "\u0418\u041B\u0418",
  "\u041D\u0415",
  "\u041C\u0415\u0416\u0414\u0423",
  "\u0412",
  "\u041F\u041E\u0414\u041E\u0411\u041D\u041E",
  "\u0415\u0421\u0422\u042C",
  "\u041A\u0410\u041A",
  "\u0413\u0414\u0415",
  "\u0418\u041C\u0415\u042E\u0429\u0418\u0415",
  "\u0421\u041F\u0415\u0426\u0421\u0418\u041C\u0412\u041E\u041B",
  "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418"
]);
function leafHasSubquery(raw) {
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return false;
  }
  return toks.some((t) => (t.type === "keyword" || t.type === "ident") && t.value.toUpperCase() === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C");
}
function leafHasCase(raw) {
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return false;
  }
  return toks.some((t) => (t.type === "keyword" || t.type === "ident") && t.value.toUpperCase() === "\u0412\u042B\u0411\u041E\u0420");
}
var EST_NE_NULL_EOL_RE = /(^|[^\p{L}\p{N}_])ЕСТЬ\s+НЕ\s+NULL$/u;
var EST_NE_NULL_KAK_RE = /((?:^|[^\p{L}\p{N}_])ЕСТЬ\s+НЕ\s+NULL) (КАК[\s(])/gu;
var EST_NE_NULL_PAREN_RE = /((?:^|[^\p{L}\p{N}_])ЕСТЬ\s+НЕ\s+NULL)\)/gu;
function appendIsNotNullToLine(line) {
  let out = line.replace(EST_NE_NULL_KAK_RE, "$1  $2");
  out = out.replace(EST_NE_NULL_PAREN_RE, "$1 )");
  return EST_NE_NULL_EOL_RE.test(out) ? out + " " : out;
}
function appendIsNotNullTrailingSpace(text2) {
  return text2.includes("\n") ? text2.split("\n").map(appendIsNotNullToLine).join("\n") : appendIsNotNullToLine(text2);
}
var COMPARE_OPS = /* @__PURE__ */ new Set(["=", "<>", "<", ">", "<=", ">="]);
var CAST_OPERAND_OPS = /* @__PURE__ */ new Set([...COMPARE_OPS, "+", "-", "*", "/", "%"]);
function wrapBareCastOperand(text2) {
  if (text2.includes("\n")) return text2;
  let toks;
  try {
    toks = tokenize(text2);
  } catch {
    return text2;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  if (sig.length === 0) return text2;
  const opIdx = [];
  let depth = 0;
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    const v = t.text ?? t.value;
    if (v === "(") {
      depth++;
      continue;
    }
    if (v === ")") {
      if (depth > 0) depth--;
      continue;
    }
    if (depth !== 0) continue;
    if (t.type === "punct" && CAST_OPERAND_OPS.has(v)) {
      if ((v === "+" || v === "-") && (i === 0 || opIdx[opIdx.length - 1] === i - 1)) continue;
      opIdx.push(i);
    }
  }
  if (opIdx.length === 0) return text2;
  const isBareCast = (ops) => {
    if (ops.length < 3) return false;
    const head = ops[0];
    if ((head.text ?? head.value).toUpperCase() !== "\u0412\u042B\u0420\u0410\u0417\u0418\u0422\u042C") return false;
    if ((ops[1].text ?? ops[1].value) !== "(") return false;
    let d = 0;
    for (let i = 1; i < ops.length; i++) {
      const v = ops[i].text ?? ops[i].value;
      if (v === "(") d++;
      else if (v === ")") {
        d--;
        if (d === 0) return i === ops.length - 1;
      }
    }
    return false;
  };
  const opStr = (ops) => {
    const first = ops[0];
    const last = ops[ops.length - 1];
    const end = last.pos + (last.text ?? last.value).length;
    return text2.slice(first.pos, end);
  };
  const bounds = [0, ...opIdx.map((x) => x + 1)];
  const ends = [...opIdx, sig.length];
  let changed = false;
  const parts = [];
  for (let k = 0; k < bounds.length; k++) {
    const ops = sig.slice(bounds[k], ends[k]);
    if (ops.length === 0) {
      parts.push("");
      continue;
    }
    if (isBareCast(ops)) {
      parts.push(`(${opStr(ops)})`);
      changed = true;
    } else parts.push(opStr(ops));
    if (k < opIdx.length) parts.push(sig[opIdx[k]].text ?? sig[opIdx[k]].value);
  }
  if (!changed) return text2;
  return parts.join(" ");
}
function leafHasTopBoolean(raw) {
  return leafHasBoolean(raw, false);
}
function leafHasBoolean(raw, anyDepth) {
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return false;
  }
  let depth = 0;
  let betweenPending = 0;
  for (const t of toks) {
    if (t.type === "eof") break;
    if (t.type === "punct" && t.value === "(") {
      depth++;
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      if (depth > 0) depth--;
      continue;
    }
    if (!anyDepth && depth !== 0) continue;
    if (isWord(t, "\u041C\u0415\u0416\u0414\u0423")) {
      betweenPending++;
      continue;
    }
    if (isOr(t)) return true;
    if (isAnd(t)) {
      if (betweenPending > 0) betweenPending--;
      else return true;
    }
  }
  return false;
}
function flattenLeafText(raw) {
  if (!raw || !/\s/.test(raw)) return raw;
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  if (sig.length === 0) return raw;
  let out = "";
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    const text2 = t.text ?? t.value;
    if (i > 0) {
      const prev = sig[i - 1];
      const gapFrom = prev.pos + (prev.text ?? prev.value).length;
      const gap = raw.slice(gapFrom, t.pos);
      const prevText = prev.text ?? prev.value;
      const noSpaceAfter = prevText === "(";
      const noSpaceBefore = text2 === ")" || text2 === ",";
      out += gap.length > 0 && !noSpaceAfter && !noSpaceBefore ? " " : "";
    }
    out += text2;
  }
  return out;
}
function flattenMultilineLeaf(raw) {
  return raw.includes("\n") && !leafFlattenBlocked(raw) && !leafHasBoolean(raw, true) ? flattenLeafText(raw) : raw;
}
var FLATTEN_STOP_WORDS = /* @__PURE__ */ new Set([
  "\u0412\u042B\u0411\u0420\u0410\u0422\u042C",
  "\u0412\u042B\u0411\u041E\u0420",
  "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C",
  "\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0418\u0422\u041E\u0413\u0418",
  "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C",
  "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0418\u041C\u0415\u042E\u0429\u0418\u0415",
  "\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C"
]);
var FLATTEN_STOP_RESERVED = /* @__PURE__ */ new Set(["\u0412\u042B\u0411\u0420\u0410\u0422\u042C", "\u0412\u042B\u0411\u041E\u0420"]);
function leafFlattenBlocked(raw) {
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return true;
  }
  for (let k = 0; k < toks.length; k++) {
    const t = toks[k];
    if (t.type === "punct" && (t.value === "{" || t.value === "}")) return true;
    if ((t.type === "keyword" || t.type === "ident") && FLATTEN_STOP_WORDS.has(t.value.toUpperCase())) {
      if (FLATTEN_STOP_RESERVED.has(t.value.toUpperCase())) return true;
      const prev = toks[k - 1];
      const isPathSegment = prev !== void 0 && prev.type === "punct" && prev.value === ".";
      if (!isPathSegment) return true;
    }
  }
  return false;
}
function flattenInlineValueLists(text2) {
  if (!text2.includes("\n")) return text2;
  const lines = text2.split("\n");
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const opensInline = /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\($/u.test(line) && i + 1 < lines.length && !/^[\t ]*ВЫБРАТЬ(?![\p{L}\p{N}_])/u.test(lines[i + 1]);
    const opensNextLine = /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*$/u.test(line) && i + 1 < lines.length && /^[\t ]*\(/u.test(lines[i + 1]) && !/^[\t ]*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/u.test(lines[i + 1]);
    const opensList = opensInline || opensNextLine;
    if (!opensList) {
      out.push(line);
      continue;
    }
    let depth = 0;
    let inStr = false;
    const buf = [];
    let j = i;
    let closed = false;
    for (; j < lines.length; j++) {
      buf.push(lines[j]);
      for (const ch of lines[j]) {
        if (ch === '"') {
          inStr = !inStr;
          continue;
        }
        if (inStr) continue;
        if (ch === "(") depth++;
        else if (ch === ")") {
          depth--;
          if (depth === 0) {
            closed = true;
          }
        }
      }
      if (closed) break;
    }
    if (!closed) {
      out.push(line);
      continue;
    }
    if (buf.some((b) => /(?:^|[^\p{L}\p{N}_])ВЫБРАТЬ(?![\p{L}\p{N}_])/u.test(b))) {
      out.push(line);
      continue;
    }
    const indent = (buf[0].match(/^\t*/u) ?? [""])[0];
    out.push(indent + flattenLeafText(buf.join("\n").replace(/^\t*/u, "")));
    i = j;
  }
  return out.join("\n");
}
function reindentLeafSubquery(text2, base) {
  if (!text2.includes("\n")) return text2;
  text2 = flattenInlineValueLists(text2);
  if (!text2.includes("\n")) return text2;
  const lines = text2.split("\n");
  if (!lines.some((l) => l.replace(/^[\t ]+/u, "").startsWith("(\u0412\u042B\u0411\u0420\u0410\u0422\u042C"))) {
    for (let i = 0; i < lines.length - 1; i++) {
      if (!/(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\($/u.test(lines[i])) continue;
      if (!lines[i + 1].replace(/^[\t ]+/u, "").startsWith("\u0412\u042B\u0411\u0420\u0410\u0422\u042C")) continue;
      lines[i] = lines[i].replace(/\s*\($/u, "");
      lines[i + 1] = lines[i + 1].replace(/^([\t ]*)/u, "$1(");
      break;
    }
  }
  let start = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].replace(/^[\t ]+/u, "").startsWith("(\u0412\u042B\u0411\u0420\u0410\u0422\u042C")) {
      start = i;
      break;
    }
  }
  if (start <= 0) return text2;
  if (start > 1) {
    const lead = (lines[0].match(/^[\t ]*/u) ?? [""])[0];
    const body = lines.slice(0, start).map((l) => l.replace(/^[\t ]+/u, "").replace(/[ \t]+$/u, "")).filter((l) => l !== "").join(" ").replace(/[ \t]+/gu, " ").replace(/\(\s+/gu, "(").replace(/\s+\)/gu, ")").replace(/\s+,/gu, ",");
    if (/^\([^()=<>]*\)\s+В$/u.test(body) && !/(?:^|[^\p{L}\p{N}_])(?:И|ИЛИ|НЕ|МЕЖДУ|ПОДОБНО|ССЫЛКА|ЕСТЬ)(?:[^\p{L}\p{N}_])/u.test(body)) {
      lines.splice(0, start, lead + body);
      start = 1;
    }
  }
  let depth = 0;
  let inStr = false;
  for (let i = start; i < lines.length; i++) {
    for (const ch of lines[i]) {
      if (ch === '"') inStr = !inStr;
      else if (!inStr && ch === "(") depth++;
      else if (!inStr && ch === ")") depth--;
    }
    if (depth <= 0 && i < lines.length - 1) return text2;
  }
  if (depth > 0) return text2;
  const neMatch = /^[\s(]*((?:НЕ\s+)+)/u.exec(lines[0]);
  const neCount = neMatch ? (neMatch[1].match(/НЕ/gu) ?? []).length : 0;
  const target = base + neCount;
  lines[start - 1] = lines[start - 1].replace(/[ \t]+$/u, "");
  const visWidth = (ws) => {
    let w = 0;
    for (const ch of ws) w += ch === "	" ? 8 : 1;
    return w;
  };
  const bodyHasSpaceIndent = lines.slice(start).some((l) => l.trim() !== "" && / /u.test((l.match(/^[\t ]*/u) ?? [""])[0]));
  if (bodyHasSpaceIndent) {
    const headW = visWidth((lines[start].match(/^[\t ]*/u) ?? [""])[0]);
    let step = Infinity;
    for (let i = start; i < lines.length; i++) {
      if (lines[i].trim() === "") continue;
      const d = visWidth((lines[i].match(/^[\t ]*/u) ?? [""])[0]) - headW;
      if (d > 0 && d < step) step = d;
    }
    if (!Number.isFinite(step)) step = 1;
    for (let i = start; i < lines.length; i++) {
      if (lines[i].trim() === "") continue;
      const ws = (lines[i].match(/^[\t ]*/u) ?? [""])[0];
      const extra = visWidth(ws) - headW;
      const level = extra > 0 ? Math.round(extra / step) : 0;
      lines[i] = TAB.repeat(target + level) + lines[i].slice(ws.length);
    }
  } else {
    const cur = (lines[start].match(/^\t*/u) ?? [""])[0].length;
    const delta = target - cur;
    if (delta !== 0) {
      for (let i = start; i < lines.length; i++) {
        if (lines[i].trim() === "") {
          const haveB = (lines[i].match(/^\t*/u) ?? [""])[0].length;
          if (haveB > 0) lines[i] = TAB.repeat(Math.max(0, haveB + delta));
          continue;
        }
        if (delta > 0) {
          lines[i] = TAB.repeat(delta) + lines[i];
        } else {
          const have = (lines[i].match(/^\t*/u) ?? [""])[0].length;
          if (have < -delta) return text2;
          lines[i] = lines[i].slice(-delta);
        }
      }
    }
  }
  const isUnionKw = (s) => /^\t*ОБЪЕДИНИТЬ(?:\s+ВСЕ)?\s*$/u.test(s);
  for (let i = start; i < lines.length; i++) {
    if (lines[i] !== "") continue;
    const prevKw = i > 0 && isUnionKw(lines[i - 1]);
    const nextKw = i + 1 < lines.length && isUnionKw(lines[i + 1]);
    if (!prevKw && !nextKw) continue;
    const kwLine = prevKw ? lines[i - 1] : lines[i + 1];
    const kwInd = (kwLine.match(/^\t*/u) ?? [""])[0].length;
    lines[i] = TAB.repeat(Math.max(0, kwInd - 1));
  }
  for (let i = lines.length - 1; i > start; i--) {
    if (lines[i].trim() !== "") continue;
    const prevKw = isUnionKw(lines[i - 1] ?? "");
    const nextKw = i + 1 < lines.length && isUnionKw(lines[i + 1]);
    if (prevKw || nextKw) continue;
    lines.splice(i, 1);
  }
  for (let i = start; i < lines.length; i++) {
    if (lines[i].trim() === "") continue;
    if (!lines[i].includes('"')) lines[i] = lines[i].replace(/[ \t]+$/u, "");
  }
  {
    const JOIN_RE = /^(\t*)(?:ВНУТРЕННЕЕ|ЛЕВОЕ(?:\s+ВНЕШНЕЕ)?|ПРАВОЕ(?:\s+ВНЕШНЕЕ)?|ПОЛНОЕ(?:\s+ВНЕШНЕЕ)?)\s+СОЕДИНЕНИЕ(?:[^\p{L}\p{N}_]|$)/u;
    const PO_RE = /^(\t*)ПО(?:[^\p{L}\p{N}_]|$)/u;
    const indOf = (s) => (s.match(/^\t*/u) ?? [""])[0].length;
    let srcInd = -1;
    let expectSource = false;
    let joinExtra = 0;
    let poExtra = 0;
    for (let i = start; i < lines.length; i++) {
      const l = lines[i];
      if (l.trim() === "") continue;
      if (/^\t*ИЗ\s*$/u.test(l)) {
        expectSource = true;
        joinExtra = 0;
        poExtra = 0;
        continue;
      }
      if (expectSource) {
        srcInd = indOf(l);
        expectSource = false;
        continue;
      }
      const jm = JOIN_RE.exec(l);
      if (jm && srcInd >= 0 && jm[1].length === srcInd) {
        lines[i] = TAB + l;
        joinExtra = 1;
        poExtra = 0;
        continue;
      }
      const pm = PO_RE.exec(l);
      if (pm && joinExtra > 0 && pm[1].length === srcInd) {
        lines[i] = TAB + l;
        poExtra = 1;
        continue;
      }
      if (poExtra > 0 && /^\t*(?:И|ИЛИ)(?:[^\p{L}\p{N}_])/u.test(l) && indOf(l) <= srcInd + 1) {
        lines[i] = TAB + TAB + l;
        continue;
      }
      if (indOf(l) <= srcInd) {
        joinExtra = 0;
        poExtra = 0;
      }
    }
  }
  for (let i = start + 1; i < lines.length - 1; i++) {
    const opM = /^(\t*)(И|ИЛИ)$/u.exec(lines[i]);
    if (!opM) continue;
    let j = i + 1;
    while (j < lines.length && lines[j].trim() === "") j++;
    if (j >= lines.length) continue;
    const opInd = opM[1].length;
    const operandInd = (lines[j].match(/^\t*/u) ?? [""])[0].length;
    if (operandInd <= opInd) continue;
    const targetInd = opM[2] === "\u0418" ? opInd : operandInd;
    lines[j] = lines[j].replace(/^\t*/u, `${TAB.repeat(targetInd)}${opM[2]} `);
    lines.splice(i, 1);
    i--;
  }
  {
    const indOf = (s) => (s.match(/^\t*/u) ?? [""])[0].length;
    const balance = (s) => {
      let d = 0, inStr2 = false;
      for (const ch of s) {
        if (ch === '"') inStr2 = !inStr2;
        else if (!inStr2 && ch === "(") d++;
        else if (!inStr2 && ch === ")") d--;
      }
      return d;
    };
    const opensNotGroup = /(?:^|[^\p{L}\p{N}_])НЕ\s*\(/u;
    for (let i = start; i < lines.length; i++) {
      if (!opensNotGroup.test(lines[i])) continue;
      if (balance(lines[i]) < 1) continue;
      const openerInd = indOf(lines[i]);
      let depth2 = balance(lines[i]);
      let j = i + 1;
      const span = [];
      let flat = true;
      for (; j < lines.length && depth2 > 0; j++) {
        if (lines[j].trim() === "") continue;
        if (indOf(lines[j]) > openerInd) {
          flat = false;
          break;
        }
        if (/^\t*(?:И|ИЛИ)(?:[^\p{L}\p{N}_])/u.test(lines[j])) span.push(j);
        else {
          flat = false;
          break;
        }
        depth2 += balance(lines[j]);
      }
      if (flat && depth2 <= 0 && span.length > 0) {
        for (const k of span) {
          lines[k] = TAB.repeat(openerInd + 2) + lines[k].replace(/^\t*/u, "");
        }
        i = j - 1;
      }
    }
  }
  const split = [];
  for (const l of lines) {
    const m = /^(\t*)ПО\s+(\S.*)$/u.exec(l);
    if (m) {
      split.push(`${m[1]}\u041F\u041E`);
      split.push(`${m[1]}${TAB}${m[2]}`);
    } else {
      split.push(l);
    }
  }
  const last = split.length - 1;
  if (last > start && /^\t*\)+$/u.test(split[last])) {
    const close = split[last].trim();
    split.splice(last, 1);
    split[split.length - 1] = split[split.length - 1].replace(/[ \t]+$/u, "") + close;
  }
  return split.join("\n");
}
function isSingleTopLevelCaseValue(text2) {
  if (!text2.includes("\n")) return false;
  if (/(?:^|[^\p{L}\p{N}_])ВЫБРАТЬ(?:[^\p{L}\p{N}_]|$)/iu.test(text2)) return false;
  const vyborCount = (text2.match(/(?:^|[^\p{L}\p{N}_])ВЫБОР(?:[^\p{L}\p{N}_]|$)/giu) ?? []).length;
  if (vyborCount !== 1) return false;
  const lines = text2.split("\n");
  const trailingVyborPos = (line) => {
    const m = /(^|[^\p{L}\p{N}_])(ВЫБОР)\s*$/u.exec(line);
    if (!m) return -1;
    return m.index + m[1].length;
  };
  let depth = 0;
  let inStr = false;
  for (const line of lines) {
    const viPos = trailingVyborPos(line);
    let d = depth;
    let s = inStr;
    for (let c = 0; c < line.length; c++) {
      if (c === viPos && !s && d === 0) return true;
      const ch = line[c];
      if (ch === '"') {
        s = !s;
        continue;
      }
      if (s) continue;
      if (ch === "(") d++;
      else if (ch === ")") d--;
    }
    depth = d;
    inStr = s;
  }
  return false;
}
function opensWithTopLevelVybor(text2) {
  if (!text2.includes("\n")) return false;
  if (/(?:^|[^\p{L}\p{N}_])ВЫБРАТЬ(?:[^\p{L}\p{N}_]|$)/iu.test(text2)) return false;
  const lines = text2.split("\n");
  const first = lines.find((l) => l.trim() !== "");
  if (first === void 0 || !/(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u.test(first)) return false;
  const onlyParens = (s) => {
    let inStr = false, out = "";
    for (let c = 0; c < s.length; c++) {
      const ch = s[c];
      if (ch === '"') {
        inStr = !inStr;
        out += '"';
        continue;
      }
      out += ch;
    }
    return out;
  };
  const openGroupParensOf = (s) => {
    const st = [];
    let inStr = false, prev = "";
    for (let c = 0; c < s.length; c++) {
      const ch = s[c];
      if (ch === '"') {
        inStr = !inStr;
        prev = ch;
        continue;
      }
      if (inStr) continue;
      if (ch === "(") {
        st.push(/[\p{L}\p{N}_]/u.test(prev));
        prev = ch;
        continue;
      }
      if (ch === ")") {
        st.pop();
        prev = ch;
        continue;
      }
      if (ch !== " " && ch !== "	") prev = ch;
    }
    return st.filter((isCall) => !isCall).length;
  };
  for (const l of lines) {
    if (!/^[\t ]*КОНЕЦ(?![\p{L}\p{N}_])/u.test(l)) continue;
    if (!/(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u.test(l)) continue;
    const head = onlyParens(l.replace(/(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u, "$1").replace(/^[\t ]*/u, ""));
    if (openGroupParensOf(head) > 0) return false;
  }
  return true;
}
function opensWithVyborInCall(text2) {
  if (!text2.includes("\n")) return false;
  if (/(?:^|[^\p{L}\p{N}_])ВЫБРАТЬ(?:[^\p{L}\p{N}_]|$)/iu.test(text2)) return false;
  const vyborCount = (text2.match(/(?:^|[^\p{L}\p{N}_])ВЫБОР(?:[^\p{L}\p{N}_]|$)/giu) ?? []).length;
  if (vyborCount !== 1) return false;
  const lines = text2.split("\n");
  const trailingVyborPos = (line) => {
    const m = /(^|[^\p{L}\p{N}_])(ВЫБОР)\s*$/u.exec(line);
    return m ? m.index + m[1].length : -1;
  };
  let depth = 0;
  let inStr = false;
  let sawClose = false;
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    const viPos = trailingVyborPos(line);
    let d = depth;
    let s = inStr;
    for (let c = 0; c < line.length; c++) {
      if (c === viPos && !s) return d > 0 && li > 0 && !sawClose;
      const ch = line[c];
      if (ch === '"') {
        s = !s;
        continue;
      }
      if (s) continue;
      if (ch === "(") d++;
      else if (ch === ")") {
        d--;
        if (d < 0) return false;
        sawClose = true;
      }
    }
    depth = d;
    inStr = s;
  }
  return false;
}
function splitInlineLeafCase(text2) {
  if (!text2.includes("\u0412\u042B\u0411\u041E\u0420") && !/ВЫБОР/iu.test(text2)) return text2;
  let toks;
  try {
    toks = tokenize(text2);
  } catch {
    return text2;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  const isW = (t, w) => (t.type === "keyword" || t.type === "ident") && t.value.toUpperCase() === w;
  if (sig.some((t) => isW(t, "\u0412\u042B\u0411\u0420\u0410\u0422\u042C"))) return text2;
  if (!sig.some((t) => isW(t, "\u0412\u042B\u0411\u041E\u0420"))) return text2;
  const depthBefore = [];
  let pd = 0;
  for (const t of sig) {
    depthBefore.push(pd);
    if (t.type === "punct" && t.value === "(") pd++;
    else if (t.type === "punct" && t.value === ")") pd--;
  }
  for (let k = 0; k < sig.length; k++) {
    if (isW(sig[k], "\u0412\u042B\u0411\u041E\u0420")) {
      const nx = sig[k + 1];
      if (!nx || !isW(nx, "\u041A\u041E\u0413\u0414\u0410")) return text2;
    }
  }
  {
    const caseDepth = [];
    const dropPos = [];
    for (let k = 0; k < sig.length; k++) {
      const t = sig[k];
      if (isW(t, "\u0412\u042B\u0411\u041E\u0420")) {
        caseDepth.push(depthBefore[k]);
        continue;
      }
      const top = caseDepth[caseDepth.length - 1];
      if (top === void 0) continue;
      if (isW(t, "\u041A\u041E\u041D\u0415\u0426") && depthBefore[k] === top) {
        caseDepth.pop();
        continue;
      }
      if (!isW(t, "\u041A\u041E\u0413\u0414\u0410") || depthBefore[k] !== top) continue;
      const open = sig[k + 1];
      if (!open || !(open.type === "punct" && open.value === "(") || depthBefore[k + 1] !== top) continue;
      let j = k + 2;
      let closeIdx = -1;
      let hasTopBool = false;
      for (; j < sig.length; j++) {
        const d = depthBefore[j];
        if (d <= top) break;
        if (d === top + 1 && (isW(sig[j], "\u0418") || isW(sig[j], "\u0418\u041B\u0418"))) hasTopBool = true;
      }
      const closeTok = sig[j - 1];
      if (!closeTok || !(closeTok.type === "punct" && closeTok.value === ")")) continue;
      const next = sig[j];
      if (!next || !isW(next, "\u0422\u041E\u0413\u0414\u0410") || depthBefore[j] !== top) continue;
      if (!hasTopBool) continue;
      closeIdx = j - 1;
      dropPos.push(open.pos, closeTok.pos);
    }
    if (dropPos.length > 0) {
      const drop = new Set(dropPos);
      let rebuilt = "";
      for (let p = 0; p < text2.length; p++) if (!drop.has(p)) rebuilt += text2[p];
      return splitInlineLeafCase(rebuilt);
    }
  }
  const caseStack = [];
  let inCondition = false;
  let betweenPending = 0;
  const parenKind = [];
  const breakBefore = /* @__PURE__ */ new Set();
  const gluedToPrevAt = (k) => {
    const p = sig[k - 1];
    if (!p) return false;
    const pEnd = p.pos + p.text.length;
    return !text2.slice(pEnd, sig[k].pos).includes("\n");
  };
  for (let k = 0; k < sig.length; k++) {
    const t = sig[k];
    const dep = depthBefore[k];
    if (t.type === "punct" && t.value === "(") {
      const prev2 = sig[k - 1];
      const isCallOpen = !!prev2 && (prev2.type === "ident" || prev2.type === "keyword" && !isW(prev2, "\u0418") && !isW(prev2, "\u0418\u041B\u0418") && !isW(prev2, "\u041D\u0415") && !isW(prev2, "\u041A\u041E\u0413\u0414\u0410") && !isW(prev2, "\u041C\u0415\u0416\u0414\u0423"));
      parenKind.push(!isCallOpen);
    } else if (t.type === "punct" && t.value === ")") {
      parenKind.pop();
    }
    if (isW(t, "\u0412\u042B\u0411\u041E\u0420")) {
      caseStack.push(dep);
      inCondition = false;
      continue;
    }
    const top = caseStack[caseStack.length - 1];
    if (top === void 0) continue;
    if (inCondition && dep >= top && isW(t, "\u041C\u0415\u0416\u0414\u0423")) {
      betweenPending++;
      continue;
    }
    if (inCondition && dep === top + 1 && parenKind[parenKind.length - 1] === true && (isW(t, "\u0418") || isW(t, "\u0418\u041B\u0418"))) {
      if (isW(t, "\u0418") && betweenPending > 0) {
        betweenPending--;
        continue;
      }
      if (k > 0 && gluedToPrevAt(k)) breakBefore.add(k);
      continue;
    }
    if (dep !== top) continue;
    const gluedToPrev = () => gluedToPrevAt(k);
    if (isW(t, "\u041A\u041E\u0413\u0414\u0410")) {
      if (k > 0 && gluedToPrev()) breakBefore.add(k);
      inCondition = true;
    } else if (isW(t, "\u0422\u041E\u0413\u0414\u0410")) {
      if (k > 0 && gluedToPrev()) breakBefore.add(k);
      inCondition = false;
    } else if (isW(t, "\u0418\u041D\u0410\u0427\u0415")) {
      if (k > 0 && gluedToPrev()) breakBefore.add(k);
      inCondition = false;
    } else if (isW(t, "\u041A\u041E\u041D\u0415\u0426")) {
      if (k > 0 && gluedToPrev()) breakBefore.add(k);
      caseStack.pop();
      inCondition = false;
    } else if (inCondition && (isW(t, "\u0418") || isW(t, "\u0418\u041B\u0418"))) {
      if (isW(t, "\u0418") && betweenPending > 0) {
        betweenPending--;
        continue;
      }
      if (k > 0 && gluedToPrev()) breakBefore.add(k);
    }
  }
  if (breakBefore.size === 0) return text2;
  let out = "";
  let prev = 0;
  for (let k = 0; k < sig.length; k++) {
    if (breakBefore.has(k)) {
      out += text2.slice(prev, sig[k].pos).replace(/\s+$/u, "") + "\n";
      prev = sig[k].pos;
    }
  }
  out += text2.slice(prev);
  return out;
}
function stripRedundantCallWrapParens(text2) {
  if (!text2.includes("(")) return text2;
  let toks;
  try {
    toks = tokenize(text2);
  } catch {
    return text2;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  const match = /* @__PURE__ */ new Map();
  const stack = [];
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (t.type === "punct" && t.value === "(") stack.push(i);
    else if (t.type === "punct" && t.value === ")") {
      const o = stack.pop();
      if (o === void 0) return text2;
      match.set(o, i);
    }
  }
  if (stack.length) return text2;
  const isOpen = (t) => !!t && t.type === "punct" && t.value === "(";
  const drop = /* @__PURE__ */ new Set();
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (!(t.type === "punct" && t.value === "(")) continue;
    if (drop.has(i)) continue;
    const close = match.get(i);
    const prev = i > 0 ? sig[i - 1] : void 0;
    const nx = close + 1 < sig.length ? sig[close + 1] : void 0;
    if (isCallOpenContext(prev)) continue;
    const isCmpOrPred = (t2) => !!t2 && (t2.type === "punct" && COMPARISON_PUNCT_SET.has(t2.value) || (t2.type === "keyword" || t2.type === "ident") && PRED_NEIGHBOR_WORDS.has(t2.value.toUpperCase()));
    if (isCmpOrPred(prev) || isCmpOrPred(nx)) continue;
    const a = sig[i + 1];
    const b = sig[i + 2];
    if (!a) continue;
    if (!isOpen(b)) continue;
    const callClose = match.get(i + 2);
    if (callClose === void 0 || callClose !== close - 1) continue;
    const isAgg = AGGREGATE_WORDS.has(a.value.toUpperCase());
    const isCallWord = (a.type === "ident" || a.type === "keyword") && !PRED_NEIGHBOR_WORDS.has(a.value.toUpperCase());
    if (!isAgg) {
      if (!isCallWord) continue;
      if (prev !== void 0 || nx !== void 0) continue;
    }
    drop.add(i);
    drop.add(close);
  }
  if (!drop.size) return text2;
  const positions = [];
  for (const idx of drop) positions.push(sig[idx].pos);
  positions.sort((a, b) => b - a);
  let out = text2;
  for (const p of positions) {
    out = out.slice(0, p) + " " + out.slice(p + 1);
  }
  return out.replace(/\( +/g, "(").replace(/ +\)/g, ")").replace(/^ +/, "").replace(/ +$/, "");
}
function stripMultilineWhenWrap(lines) {
  const fw = (s) => {
    const m = /^[\t ]*([\p{L}]+)/u.exec(s);
    return m ? m[1].toUpperCase() : "";
  };
  const parenDelta = (s) => {
    let d = 0, inS = false;
    for (let c = 0; c < s.length; c++) {
      const ch = s[c];
      if (ch === '"') {
        inS = !inS;
        continue;
      }
      if (inS) continue;
      if (ch === "(") d++;
      else if (ch === ")") d--;
    }
    return d;
  };
  for (let i = 0; i < lines.length; i++) {
    if (fw(lines[i]) !== "\u041A\u041E\u0413\u0414\u0410") continue;
    const m = /^([\t ]*КОГДА[\t ]+)\((.*)$/u.exec(lines[i]);
    if (!m) continue;
    const headDelta = parenDelta("(" + m[2]);
    if (headDelta < 1) continue;
    let depth = headDelta;
    let closeLine = -1;
    let hasBool = /(?:^|[^\p{L}\p{N}_])(И|ИЛИ)(?:[^\p{L}\p{N}_]|$)/u.test(m[2]);
    for (let j = i + 1; j < lines.length; j++) {
      if (lines[j].trim() === "") continue;
      const w = fw(lines[j]);
      if (w === "\u0418" || w === "\u0418\u041B\u0418") {
        hasBool = true;
      } else if (w === "\u0422\u041E\u0413\u0414\u0410" || w === "\u041A\u041E\u041D\u0415\u0426" || w === "\u041A\u041E\u0413\u0414\u0410" || w === "\u0418\u041D\u0410\u0427\u0415") break;
      const before = depth;
      depth += parenDelta(lines[j]);
      if (depth === 0) {
        if (before > 0 && /\)\s*$/u.test(lines[j])) {
          let nextW = "";
          for (let k = j + 1; k < lines.length; k++) {
            if (lines[k].trim() === "") continue;
            nextW = fw(lines[k]);
            break;
          }
          if (nextW === "\u0422\u041E\u0413\u0414\u0410") closeLine = j;
        }
        break;
      }
      if (depth < 0) break;
    }
    if (closeLine < 0 || !hasBool) continue;
    lines[i] = m[1] + m[2];
    lines[closeLine] = lines[closeLine].replace(/\)(\s*)$/u, "$1");
  }
}
function stripRedundantThenArithmeticWrap(lines) {
  const fw = (s) => {
    const m = /^[\t ]*([\p{L}]+)/u.exec(s);
    return m ? m[1].toUpperCase() : "";
  };
  const parenDelta = (s) => {
    let d = 0, inS = false;
    for (let c = 0; c < s.length; c++) {
      const ch = s[c];
      if (ch === '"') {
        inS = !inS;
        continue;
      }
      if (inS) continue;
      if (ch === "(") d++;
      else if (ch === ")") d--;
    }
    return d;
  };
  for (let i = 0; i < lines.length; i++) {
    const w = fw(lines[i]);
    if (w !== "\u0422\u041E\u0413\u0414\u0410" && w !== "\u0418\u041D\u0410\u0427\u0415") continue;
    const m = new RegExp(`^([\\t ]*${w}[\\t ]+)\\((.*)$`, "u").exec(lines[i]);
    if (!m) continue;
    if (!/(?:^|[^\p{L}\p{N}_])ВЫБОР\s*$/u.test(m[2])) continue;
    const headBody = "(" + m[2];
    if (parenDelta(headBody) < 1) continue;
    let d = 0, inS = false, topMulOp = false;
    for (let c = 0; c < headBody.length; c++) {
      const ch = headBody[c];
      if (ch === '"') {
        inS = !inS;
        continue;
      }
      if (inS) continue;
      if (ch === "(") d++;
      else if (ch === ")") d--;
      else if (d === 1 && (ch === "*" || ch === "/")) topMulOp = true;
    }
    if (!topMulOp) continue;
    let depth = parenDelta(headBody);
    let closeLine = -1;
    for (let j = i + 1; j < lines.length; j++) {
      if (lines[j].trim() === "") continue;
      const before = depth;
      depth += parenDelta(lines[j]);
      if (depth <= 0) {
        if (before > 0 && fw(lines[j]) === "\u041A\u041E\u041D\u0415\u0426") {
          if (/^[\t ]*КОНЕЦ\)\s*[*/]\s/u.test(lines[j])) {
            closeLine = j;
          } else if (/^[\t ]*КОНЕЦ\)\s*$/u.test(lines[j])) {
            let nextW = "";
            for (let k = j + 1; k < lines.length; k++) {
              if (lines[k].trim() === "") continue;
              nextW = fw(lines[k]);
              break;
            }
            if (nextW === "\u041A\u041E\u041D\u0415\u0426" || nextW === "\u0422\u041E\u0413\u0414\u0410" || nextW === "\u0418\u041D\u0410\u0427\u0415" || nextW === "\u041A\u041E\u0413\u0414\u0410") {
              closeLine = j;
            }
          }
        }
        break;
      }
    }
    if (closeLine < 0) continue;
    lines[i] = m[1] + m[2];
    lines[closeLine] = lines[closeLine].replace(/^([\t ]*КОНЕЦ)\)/u, "$1");
  }
}
function reindentLeafCase(text2, base, funcParenDepth = false) {
  text2 = stripRedundantCallWrapParens(text2);
  text2 = splitInlineLeafCase(text2);
  if (!text2.includes("\n")) return text2;
  if (/\bВЫБРАТЬ\b/u.test(text2)) return text2;
  const lines = text2.split("\n");
  const endsWithVybor = (s) => /(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u.test(s);
  let openIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    if (endsWithVybor(lines[i])) {
      openIdx = i;
      break;
    }
  }
  if (openIdx < 0 && /^[\t ]*ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(lines[0]) && lines.some((l) => /^[\t ]*КОНЕЦ(?:[^\p{L}\p{N}_]|$)/u.test(l))) {
    openIdx = 0;
  }
  if (openIdx < 0) return text2;
  const HAS_SUBQUERY_RE = /(?:^|[^\p{L}\p{N}_])ВЫБРАТЬ(?:[^\p{L}\p{N}_]|$)/iu;
  if (!HAS_SUBQUERY_RE.test(text2)) {
    const STRUCT = /* @__PURE__ */ new Set(["\u041A\u041E\u0413\u0414\u0410", "\u0422\u041E\u0413\u0414\u0410", "\u0418\u041D\u0410\u0427\u0415", "\u041A\u041E\u041D\u0415\u0426", "\u0418", "\u0418\u041B\u0418"]);
    const fw = (s) => {
      const m = /^[\t ]*([\p{L}]+)/u.exec(s);
      return m ? m[1].toUpperCase() : "";
    };
    const joinAt = (a, b) => {
      const left = a.replace(/\s+$/u, "");
      const right = b.replace(/^[\t ]+/u, "");
      if (right === "") return left;
      if (left.endsWith("(")) return left + right;
      if (right.startsWith(")") || right.startsWith(",")) return left + right;
      return left + " " + right;
    };
    const opener = lines.slice(0, openIdx + 1).reduce((acc, l, i) => i === 0 ? l.replace(/\s+$/u, "") : joinAt(acc, l), "");
    const canonical = [opener];
    let cur = null;
    for (let i = openIdx + 1; i < lines.length; i++) {
      const r = lines[i];
      if (r.trim() === "") continue;
      if (STRUCT.has(fw(r))) {
        if (cur !== null) canonical.push(cur);
        cur = r.replace(/\s+$/u, "");
      } else if (cur === null) {
        cur = r.replace(/\s+$/u, "");
      } else {
        cur = joinAt(cur, r);
      }
    }
    if (cur !== null) canonical.push(cur);
    lines.length = 0;
    lines.push(...canonical);
    openIdx = 0;
  }
  stripMultilineWhenWrap(lines);
  stripRedundantThenArithmeticWrap(lines);
  const isIdentChar = (ch) => ch !== void 0 && /[\p{L}\p{N}_]/u.test(ch);
  let parenDepth = 0;
  let effectiveDepth = 0;
  let sawClose = false;
  let prevOpen = false;
  const callStack = [];
  let unbalanced = false;
  let prevNonSpace = "";
  let inStr = false;
  for (let i = 0; i <= openIdx; i++) {
    const line = lines[i];
    for (let c = 0; c < line.length; c++) {
      const ch = line[c];
      if (ch === '"') {
        inStr = !inStr;
        prevOpen = false;
        prevNonSpace = ch;
        continue;
      }
      if (inStr) continue;
      if (ch === "(") {
        parenDepth++;
        if (!prevOpen) effectiveDepth++;
        prevOpen = true;
        callStack.push(isIdentChar(prevNonSpace));
        prevNonSpace = ch;
        continue;
      }
      if (ch === ")") {
        parenDepth--;
        sawClose = true;
        prevOpen = false;
        if (callStack.pop() === void 0) unbalanced = true;
        prevNonSpace = ch;
        continue;
      }
      if (ch !== " " && ch !== "	") {
        prevOpen = false;
        prevNonSpace = ch;
      }
    }
  }
  if (parenDepth < 0 || unbalanced) return text2;
  const E0 = funcParenDepth ? base + callStack.filter(Boolean).length : base + (sawClose ? parenDepth : effectiveDepth);
  const stack = [E0];
  let curWhen = -1;
  let valueAnchor = -1;
  let condParen = 0;
  let condShiftStack = [0];
  let condOrLevels = /* @__PURE__ */ new Set();
  let condNeLevels = /* @__PURE__ */ new Set();
  const neParenOpens = (s) => {
    let opens = 0;
    let inS = false;
    let word = "";
    for (let c = 0; c < s.length; c++) {
      const ch = s[c];
      if (ch === '"') {
        inS = !inS;
        word = "";
        continue;
      }
      if (inS) continue;
      if (/[\p{L}\p{N}_]/u.test(ch)) {
        word += ch;
        continue;
      }
      if (ch === "(") {
        if (word.toUpperCase() === "\u041D\u0415") opens++;
        word = "";
        continue;
      }
      if (ch === " " || ch === "	") {
        if (word.toUpperCase() !== "\u041D\u0415") word = "";
        continue;
      }
      word = "";
    }
    return opens;
  };
  const parenDelta = (s) => {
    let d = 0;
    let inS = false;
    for (let c = 0; c < s.length; c++) {
      const ch = s[c];
      if (ch === '"') {
        inS = !inS;
        continue;
      }
      if (inS) continue;
      if (ch === "(") d++;
      else if (ch === ")") d--;
    }
    return d;
  };
  const openCallParens = (s) => {
    const stackC = [];
    let inS = false;
    let prevNonSpace2 = "";
    for (let c = 0; c < s.length; c++) {
      const ch = s[c];
      if (ch === '"') {
        inS = !inS;
        prevNonSpace2 = ch;
        continue;
      }
      if (inS) continue;
      if (ch === "(") {
        stackC.push(/[\p{L}\p{N}_]/u.test(prevNonSpace2));
        prevNonSpace2 = ch;
        continue;
      }
      if (ch === ")") {
        stackC.pop();
        prevNonSpace2 = ch;
        continue;
      }
      if (ch !== " " && ch !== "	") prevNonSpace2 = ch;
    }
    return stackC.filter(Boolean).length;
  };
  const tabsOf = (s) => (s.match(/^[\t ]*/u) ?? [""])[0].length;
  const reTab = (s, n) => "	".repeat(n) + appendIsNotNullTrailingSpace(normalizeLeafWhitespace(s.replace(/^[\t ]+/u, "").replace(/\s+$/u, "")));
  const firstWord = (s) => {
    const m = /^[\t ]*([\p{L}]+)/u.exec(s);
    return m ? m[1].toUpperCase() : "";
  };
  const stripClause = (line, kw) => {
    const m = new RegExp(`^([\\t ]*${kw}[\\t ]+)([\\s\\S]+)$`, "u").exec(line);
    if (!m) return line;
    const body = wrapBareCastOperand(reprintLeafComparison(reprintLeafArithmetic(stripRedundantCaseClauseParens(m[2]))));
    return body === m[2] ? line : m[1] + body;
  };
  const wrapClauseHeadCast = (line, kw) => {
    const m = new RegExp(`^([\\t ]*${kw}[\\t ]+)([\\s\\S]+)$`, "u").exec(line);
    if (!m) return line;
    const body = wrapBareCastOperand(m[2]);
    return body === m[2] ? line : m[1] + body;
  };
  const orLevelsForCondition = (startIdx) => {
    const levels = /* @__PURE__ */ new Set();
    let lvl = parenDelta(lines[startIdx]);
    for (let j = startIdx + 1; j < lines.length; j++) {
      const r = lines[j];
      if (r.trim() === "") continue;
      const fw = firstWord(r);
      if (fw === "\u0418" || fw === "\u0418\u041B\u0418") {
        if (fw === "\u0418\u041B\u0418") levels.add(lvl);
        lvl += parenDelta(r);
      } else {
        break;
      }
    }
    return levels;
  };
  const consumeValueSubquery = (kwIdx, anchor) => {
    if (!/(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*$/u.test(lines[kwIdx])) return kwIdx;
    let sub = -1;
    for (let j = kwIdx + 1; j < lines.length; j++) {
      if (lines[j].trim() === "") continue;
      if (/^[\t ]*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/u.test(lines[j])) {
        sub = j;
        break;
      }
      return kwIdx;
    }
    if (sub < 0) return kwIdx;
    let depth = 0, inS = false, end = -1;
    for (let j = sub; j < lines.length; j++) {
      for (const ch of lines[j]) {
        if (ch === '"') inS = !inS;
        else if (!inS && ch === "(") depth++;
        else if (!inS && ch === ")") depth--;
      }
      if (depth <= 0) {
        end = j;
        break;
      }
    }
    if (end < 0) return kwIdx;
    const block = ["", ...lines.slice(sub, end + 1)].join("\n");
    const re = reindentLeafSubquery(block, anchor + 2).split("\n");
    re.shift();
    if (re.length !== end - sub + 1) return kwIdx;
    for (let j = sub; j <= end; j++) lines[j] = re[j - sub];
    return end;
  };
  for (let i = openIdx + 1; i < lines.length; i++) {
    const raw = lines[i];
    if (raw.trim() === "") continue;
    const E = stack[stack.length - 1];
    if (E === void 0) return text2;
    const w = firstWord(raw);
    if (w === "\u041A\u041E\u0413\u0414\u0410") {
      const whenInd = E + 1;
      lines[i] = stripClause(reTab(raw, whenInd), "\u041A\u041E\u0413\u0414\u0410");
      if (endsWithVybor(lines[i])) {
        stack.push(whenInd + 1);
        curWhen = -1;
        valueAnchor = -1;
        condParen = 0;
        condOrLevels = /* @__PURE__ */ new Set();
        condShiftStack = [0];
        condNeLevels = /* @__PURE__ */ new Set();
      } else {
        curWhen = whenInd;
        valueAnchor = -1;
        condParen = 0;
        condShiftStack = [0];
        condNeLevels = /* @__PURE__ */ new Set();
        const condBody = stripClause(reTab(raw, whenInd), "\u041A\u041E\u0413\u0414\u0410").replace(/^\t*КОГДА\s*/u, "");
        const leadParenEncloses = () => {
          if (!/^\(/u.test(condBody)) return false;
          let d = 0, inS = false;
          for (let c = 0; c < condBody.length; c++) {
            const ch = condBody[c];
            if (ch === '"') {
              inS = !inS;
              continue;
            }
            if (inS) continue;
            if (ch === "(") d++;
            else if (ch === ")") {
              d--;
              if (d === 0 && c < condBody.length - 1) return false;
            }
          }
          return d >= 1;
        };
        const condLeadParen = leadParenEncloses() ? 1 : 0;
        condOrLevels = orLevelsForCondition(i);
        condParen += parenDelta(lines[i]) - condLeadParen;
      }
    } else if (w === "\u0418" || w === "\u0418\u041B\u0418") {
      if (valueAnchor >= 0) {
        lines[i] = reTab(raw, valueAnchor + 2 + condParen);
        condParen += parenDelta(raw);
        continue;
      }
      if (curWhen < 0) return text2;
      const orShift = w === "\u0418" && !condNeLevels.has(condParen) && condOrLevels.has(condParen) ? 1 : 0;
      const curShift = condShiftStack[condParen] ?? 0;
      lines[i] = reTab(raw, curWhen + 2 + condParen + curShift + orShift);
      if (w === "\u0418\u041B\u0418" && parenDelta(raw) === 0) {
        lines[i] = stripClause(lines[i], w);
      }
      const delta = parenDelta(raw);
      if (delta > 0) {
        const neOpens = w === "\u0418" || w === "\u0418\u041B\u0418" ? neParenOpens(raw) : 0;
        const inherited = curShift + orShift;
        for (let lv = condParen + 1; lv <= condParen + delta; lv++) {
          condShiftStack[lv] = inherited + (neOpens > 0 ? 1 : 0);
          if (neOpens > 0) condNeLevels.add(lv);
          else condNeLevels.delete(lv);
        }
      }
      condParen = Math.max(0, condParen + delta);
    } else if (w === "\u0422\u041E\u0413\u0414\u0410") {
      const tabbed = reTab(raw, E + 2);
      lines[i] = endsWithVybor(raw) ? wrapClauseHeadCast(tabbed, "\u0422\u041E\u0413\u0414\u0410") : stripClause(tabbed, "\u0422\u041E\u0413\u0414\u0410");
      if (endsWithVybor(raw)) {
        const head = lines[i].replace(/(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u, "$1");
        const callDepth = funcParenDepth ? openCallParens(head.replace(/^\t*/u, "")) : 0;
        stack.push(E + 2 + callDepth + 1);
        curWhen = -1;
        valueAnchor = -1;
      } else {
        curWhen = -1;
        valueAnchor = E + 2;
        condParen = parenDelta(lines[i]);
        const consumed = consumeValueSubquery(i, E + 2);
        if (consumed > i) {
          i = consumed;
          valueAnchor = -1;
        }
      }
    } else if (w === "\u0418\u041D\u0410\u0427\u0415") {
      const tabbed = reTab(raw, E + 1);
      lines[i] = endsWithVybor(raw) ? wrapClauseHeadCast(tabbed, "\u0418\u041D\u0410\u0427\u0415") : stripClause(tabbed, "\u0418\u041D\u0410\u0427\u0415");
      if (endsWithVybor(raw)) {
        const head = lines[i].replace(/(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u, "$1");
        const callDepth = funcParenDepth ? openCallParens(head.replace(/^\t*/u, "")) : 0;
        stack.push(E + 1 + callDepth + 1);
        curWhen = -1;
        valueAnchor = -1;
      } else {
        curWhen = -1;
        valueAnchor = E + 1;
        condParen = parenDelta(lines[i]);
        const consumed = consumeValueSubquery(i, E + 1);
        if (consumed > i) {
          i = consumed;
          valueAnchor = -1;
        }
      }
    } else if (w === "\u041A\u041E\u041D\u0415\u0426") {
      {
        const tabbed = reTab(raw, E);
        const lead = /^\t*/u.exec(tabbed)[0];
        lines[i] = lead + wrapBareCastOperand(tabbed.slice(lead.length));
      }
      stack.pop();
      curWhen = -1;
      valueAnchor = -1;
      if (endsWithVybor(lines[i])) {
        const head = lines[i].replace(/(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u, "$1");
        const typeStack = [];
        {
          let inS = false;
          let prev = "";
          const scan = (s) => {
            for (let c = 0; c < s.length; c++) {
              const ch = s[c];
              if (ch === '"') {
                inS = !inS;
                prev = ch;
                continue;
              }
              if (inS) continue;
              if (ch === "(") {
                typeStack.push(/[\p{L}\p{N}_]/u.test(prev));
                prev = ch;
              } else if (ch === ")") {
                typeStack.pop();
                prev = ch;
              } else if (ch !== " " && ch !== "	") prev = ch;
            }
          };
          for (let j = 0; j < i; j++) scan(lines[j]);
          let callDelta = 0;
          for (let c = 0; c < head.length; c++) {
            const ch = head[c];
            if (ch === '"') {
              inS = !inS;
              prev = ch;
              continue;
            }
            if (inS) continue;
            if (ch === "(") {
              const isCall = /[\p{L}\p{N}_]/u.test(prev);
              typeStack.push(isCall);
              if (isCall) callDelta++;
              prev = ch;
            } else if (ch === ")") {
              if (typeStack.pop()) callDelta--;
              prev = ch;
            } else if (ch !== " " && ch !== "	") prev = ch;
          }
          stack.push(E + callDelta);
        }
        continue;
      }
      if (stack.length === 0) {
        for (let j = i + 1; j < lines.length; j++) {
          if (lines[j].trim() !== "") return text2;
        }
        break;
      }
    } else {
      const t = tabsOf(raw);
      if (t < E) return text2;
      return text2;
    }
  }
  if (stack.length !== 0) return text2;
  return flattenInlineValueLists(lines.join("\n"));
}
function reflowLeafSelectorCase(text2, valueBaseInd) {
  if (!text2) return null;
  const flat = flattenLeafText(text2);
  let toks;
  try {
    toks = tokenize(flat);
  } catch {
    return null;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  const isW = (t, w) => (t.type === "keyword" || t.type === "ident") && t.value.toUpperCase() === w;
  if (!sig.some((t) => isW(t, "\u0412\u042B\u0411\u041E\u0420"))) return null;
  if (sig.some((t) => isW(t, "\u0412\u042B\u0411\u0420\u0410\u0422\u042C"))) return null;
  const depthBefore = [];
  let d = 0;
  for (const t of sig) {
    depthBefore.push(d);
    if (t.type === "punct" && t.value === "(") d++;
    else if (t.type === "punct" && t.value === ")") d--;
  }
  let vi = -1;
  for (let k = 0; k < sig.length; k++) {
    if (isW(sig[k], "\u0412\u042B\u0411\u041E\u0420") && depthBefore[k] > 0) {
      vi = k;
      break;
    }
  }
  if (vi < 0) return null;
  if (sig.some((t, k) => k !== vi && isW(t, "\u0412\u042B\u0411\u041E\u0420"))) return null;
  const caseDepth = depthBefore[vi];
  if (vi + 1 >= sig.length || isW(sig[vi + 1], "\u041A\u041E\u0413\u0414\u0410")) return null;
  let firstWhen = -1;
  for (let k = vi + 1; k < sig.length; k++) {
    if (depthBefore[k] === caseDepth && isW(sig[k], "\u041A\u041E\u0413\u0414\u0410")) {
      firstWhen = k;
      break;
    }
    if (depthBefore[k] < caseDepth) return null;
  }
  if (firstWhen < 0) return null;
  const E = valueBaseInd - 1 + caseDepth;
  const out = [];
  out.push(flat.slice(0, sig[firstWhen].pos).replace(/\s+$/u, ""));
  const marks = [];
  for (let k = firstWhen; k < sig.length; k++) {
    if (depthBefore[k] !== caseDepth) continue;
    const t = sig[k];
    if (isW(t, "\u041A\u041E\u0413\u0414\u0410")) marks.push({ k, word: "\u041A\u041E\u0413\u0414\u0410" });
    else if (isW(t, "\u0422\u041E\u0413\u0414\u0410")) marks.push({ k, word: "\u0422\u041E\u0413\u0414\u0410" });
    else if (isW(t, "\u0418\u041D\u0410\u0427\u0415")) marks.push({ k, word: "\u0418\u041D\u0410\u0427\u0415" });
    else if (isW(t, "\u041A\u041E\u041D\u0415\u0426")) {
      marks.push({ k, word: "\u041A\u041E\u041D\u0415\u0426" });
      break;
    }
  }
  if (marks.length === 0 || marks[marks.length - 1].word !== "\u041A\u041E\u041D\u0415\u0426") return null;
  for (let m = 0; m < marks.length; m++) {
    const cur = marks[m];
    const ind = cur.word === "\u041A\u041E\u0413\u0414\u0410" ? E + 1 : cur.word === "\u0422\u041E\u0413\u0414\u0410" ? E + 2 : cur.word === "\u0418\u041D\u0410\u0427\u0415" ? E + 1 : E;
    const from = cur.k;
    const to = m + 1 < marks.length ? marks[m + 1].k : -1;
    const sliceFrom = sig[from].pos;
    const sliceTo = to >= 0 ? sig[to].pos : flat.length;
    const seg = flat.slice(sliceFrom, sliceTo).replace(/\s+$/u, "");
    out.push("	".repeat(ind) + seg);
  }
  return out.join("\n");
}
function reindentLeafBool(text2, base) {
  if (!text2.includes("\n")) return text2;
  if (/\bВЫБРАТЬ\b|\bВЫБОР\b/u.test(text2)) return text2;
  const lines = text2.split("\n");
  const parenDelta = (s) => {
    let d = 0;
    let inS = false;
    for (let c = 0; c < s.length; c++) {
      const ch = s[c];
      if (ch === '"') {
        inS = !inS;
        continue;
      }
      if (inS) continue;
      if (ch === "(") d++;
      else if (ch === ")") d--;
    }
    return d;
  };
  const firstWord = (s) => {
    const m = /^\t*([\p{L}]+)/u.exec(s);
    return m ? m[1].toUpperCase() : "";
  };
  const orLevels = /* @__PURE__ */ new Set();
  let depth = parenDelta(lines[0]);
  for (let i = 1; i < lines.length; i++) {
    const raw = lines[i];
    if (raw.trim() === "") {
      depth += parenDelta(raw);
      continue;
    }
    const w = firstWord(raw);
    if (w !== "\u0418" && w !== "\u0418\u041B\u0418") return text2;
    const orShift = w === "\u0418" && orLevels.has(depth) ? 1 : 0;
    if (w === "\u0418\u041B\u0418") orLevels.add(depth);
    lines[i] = "	".repeat(base + 1 + depth + orShift) + raw.replace(/^\t+/u, "").replace(/\s+$/u, "");
    depth += parenDelta(lines[i]);
  }
  return lines.join("\n");
}
function renderOperatorRhs(op2, param, leafSpacing = false) {
  if (op2 === "\u0412") {
    if (param.startsWith("(")) {
      const list = param.includes("\n") && isPureBalancedList(param) && !leafHasSubquery(param) ? flattenLeafText(param) : param;
      return `\u0412${leafSpacing || valueListIsMulti(list) ? " " : ""}${list}`;
    }
    if (/^ИЕРАРХИИ ?\(/.test(param)) {
      return "\u0412 \u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418" + (leafSpacing ? " " : "") + param.slice("\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418".length).replace(/^ ?\(/, "(");
    }
  }
  return `${op2} ${param}`;
}
function isPureBalancedList(param) {
  if (param[0] !== "(") return false;
  let depth = 0;
  for (let i = 0; i < param.length; i++) {
    const ch = param[i];
    if (ch === "(") depth++;
    else if (ch === ")") {
      depth--;
      if (depth === 0) return i === param.length - 1;
    }
  }
  return false;
}
function valueListIsMulti(param) {
  const inner = param.slice(1, param.lastIndexOf(")"));
  if (/(^|[^\p{L}\p{N}_])ВЫБРАТЬ([^\p{L}\p{N}_]|$)/u.test(inner)) return false;
  let depth = 0;
  for (const ch of inner) {
    if (ch === "(") depth++;
    else if (ch === ")") depth--;
    else if (ch === "," && depth === 0) return true;
  }
  return false;
}
function tightenLeafInOperator(text2) {
  if (text2.includes("\n")) return text2;
  const m = /^([\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*)\s+(В(?:\s+ИЕРАРХИИ)?)\s+(\(.*\))$/u.exec(text2);
  if (!m) return text2;
  const group = m[3];
  if (!isPureBalancedList(group)) return text2;
  if (valueListIsMulti(group)) return text2;
  if (!/^\(\s*&[\p{L}_][\p{L}\p{N}_]*\s*\)$/u.test(group)) return text2;
  return `${m[1]} ${m[2].replace(/\s+/g, " ")}${group}`;
}
function stripLeadingZeros(value) {
  const dot = value.indexOf(".");
  const intPart = dot >= 0 ? value.slice(0, dot) : value;
  const frac = dot >= 0 ? value.slice(dot) : "";
  const trimmed = intPart.replace(/^0+(?=\d)/, "");
  return trimmed + frac;
}
function isUnaryMinusAt(sig, idx) {
  const prev = sig[idx - 1];
  if (!prev) return true;
  if (prev.type === "number" || prev.type === "string" || prev.type === "param" || prev.type === "date") return false;
  if (prev.type === "punct") {
    if (prev.value === ")") return false;
    return true;
  }
  const pp = sig[idx - 2];
  if (pp && pp.type === "punct" && pp.value === ".") return false;
  return UNARY_MINUS_PREV_WORDS.has((prev.text ?? prev.value).toUpperCase());
}
function isTupleGroupAt(sig, openIdx) {
  let depth = 0;
  for (let k = openIdx; k < sig.length; k++) {
    const t = sig[k];
    if (t.type === "punct" && t.value === "(") {
      depth++;
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      depth--;
      if (depth === 0) return false;
      continue;
    }
    if (depth !== 1) continue;
    if (t.type === "punct" && t.value === ",") return true;
    if (t.type === "punct" && COMPARISON_PUNCT.has(t.value)) return false;
  }
  return false;
}
function normalizeLeafWhitespace(raw) {
  if (!raw) return raw;
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  const isCmp = (t) => t.type === "punct" && COMPARISON_PUNCT.has(t.value);
  const isInOpWord = (t) => (t.type === "keyword" || t.type === "ident") && (t.value.toUpperCase() === "\u0412" || t.value.toUpperCase() === "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418");
  const edits = [];
  for (const t of sig) {
    if (t.type !== "number") continue;
    const v = t.value;
    const stripped = stripLeadingZeros(v);
    if (stripped !== v) {
      edits.push({ from: t.pos, to: t.pos + v.length, text: stripped });
    }
  }
  for (let i = 0; i < sig.length - 1; i++) {
    const a = sig[i];
    const b = sig[i + 1];
    const gapFrom = a.pos + (a.text ?? a.value).length;
    const gapTo = b.pos;
    if (gapTo <= gapFrom) {
      const needSpace = isCmp(a) || isCmp(b) || a.type === "punct" && a.value === "," && !(b.type === "punct" && b.value === ")") || isInOpWord(a) && b.type === "punct" && b.value === "(";
      if (needSpace) edits.push({ from: gapFrom, to: gapTo, text: " " });
      continue;
    }
    const gap = raw.slice(gapFrom, gapTo);
    if (gap.includes("\n")) continue;
    if (isInOpWord(b) && b.value.toUpperCase() === "\u0412" && gap !== " ") {
      edits.push({ from: gapFrom, to: gapTo, text: " " });
      continue;
    }
    if (isCmp(a) || isCmp(b)) {
      if (gap !== " ") edits.push({ from: gapFrom, to: gapTo, text: " " });
      continue;
    }
    if (a.type === "punct" && a.value === ",") {
      if (gap !== " ") edits.push({ from: gapFrom, to: gapTo, text: " " });
      continue;
    }
    if (b.type === "punct" && b.value === "," && !gap.includes("	")) {
      if (gap !== "") edits.push({ from: gapFrom, to: gapTo, text: "" });
      continue;
    }
    if (a.type === "punct" && a.value === "-" && !gap.includes("	") && isUnaryMinusAt(sig, i)) {
      if (gap !== "") edits.push({ from: gapFrom, to: gapTo, text: "" });
      continue;
    }
    if (a.type === "punct" && a.value === "(" && !gap.includes("	")) {
      if (gap !== "") edits.push({ from: gapFrom, to: gapTo, text: "" });
      continue;
    }
    if (b.type === "punct" && b.value === ")" && !gap.includes("	")) {
      const aUp = (a.text ?? a.value).toUpperCase();
      const prevW = sig[i - 1];
      const isNullTail = aUp === "NULL" && !!prevW && (prevW.value.toUpperCase() === "\u041D\u0415" || prevW.value.toUpperCase() === "\u0415\u0421\u0422\u042C");
      const want = isNullTail ? " " : "";
      if (gap !== want) edits.push({ from: gapFrom, to: gapTo, text: want });
      continue;
    }
    if (b.type === "punct" && b.value === "(" && (a.type === "ident" || a.type === "keyword") && !gap.includes("	")) {
      const aUp = (a.text ?? a.value).toUpperCase();
      if ((AGGREGATE_WORDS.has(aUp) || CALL_NOSPACE_WORDS.has(aUp)) && gap !== "") {
        edits.push({ from: gapFrom, to: gapTo, text: "" });
        continue;
      }
      if (PRIMITIVE_TYPE_WORDS.has(aUp) && gap !== "") {
        const prevW = sig[i - 1];
        if (prevW && (prevW.text ?? prevW.value).toUpperCase() === "\u041A\u0410\u041A") {
          edits.push({ from: gapFrom, to: gapTo, text: "" });
          continue;
        }
      }
      if (aUp === "\u041D\u0415" && gap !== "" && !isTupleGroupAt(sig, i + 1)) {
        edits.push({ from: gapFrom, to: gapTo, text: "" });
        continue;
      }
    }
    if (/ {2,}/.test(gap) && !gap.includes("	")) {
      const collapsed = gap.replace(/ {2,}/g, " ");
      if (collapsed !== gap) edits.push({ from: gapFrom, to: gapTo, text: collapsed });
    }
  }
  if (!edits.length) return raw;
  edits.sort((x, y) => y.from - x.from);
  let out = raw;
  for (const e of edits) {
    out = out.slice(0, e.from) + e.text + out.slice(e.to);
  }
  return out;
}
function enclosingFunctionIs(sig, idx, names) {
  let depth = 0;
  for (let k = idx - 1; k >= 0; k--) {
    const t = sig[k];
    if (t.type === "punct" && t.value === ")") depth++;
    else if (t.type === "punct" && t.value === "(") {
      if (depth === 0) {
        const fn2 = sig[k - 1];
        return !!fn2 && (fn2.type === "ident" || fn2.type === "keyword") && names.has(tokUpper(fn2));
      }
      depth--;
    }
  }
  return false;
}
function canonicalizeLeafLexemes(raw) {
  if (!raw) return raw;
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  if (sig.length === 0) return raw;
  const upOf = (t) => (t.text ?? t.value).toUpperCase();
  const isW = (t) => !!t && (t.type === "ident" || t.type === "keyword");
  const afterDot = (k) => {
    const p = sig[k - 1];
    return !!p && p.type === "punct" && p.value === ".";
  };
  let out = raw;
  const repls = [];
  for (let k = 0; k < sig.length; k++) {
    const t = sig[k];
    if (!isW(t) || afterDot(k)) continue;
    const u = upOf(t);
    const text2 = t.text ?? t.value;
    if (u === "ISNULL") {
      const nx = sig[k + 1];
      if (nx && nx.type === "punct" && nx.value === "(") {
        repls.push({ pos: t.pos, len: text2.length, to: "\u0415\u0421\u0422\u042CNULL" });
      }
      continue;
    }
    if (u === "IS") {
      const nx = sig[k + 1];
      if (nx && isW(nx) && upOf(nx) === "NULL") {
        repls.push({ pos: t.pos, len: text2.length, to: "\u0415\u0421\u0422\u042C" });
      }
    }
  }
  if (repls.length) {
    repls.sort((a, b) => b.pos - a.pos);
    for (const r of repls) out = out.slice(0, r.pos) + r.to + out.slice(r.pos + r.len);
  }
  if (!out.includes("\n")) {
    let toks2;
    try {
      toks2 = tokenize(out);
    } catch {
      return out;
    }
    const sig2 = toks2.filter((t) => t.type !== "eof");
    for (let k = 1; k < sig2.length - 1; k++) {
      const t = sig2[k];
      if (!isW(t) || upOf(t) !== "\u041D\u0415") continue;
      const nx = sig2[k + 1];
      const nxU = nx ? upOf(nx) : "";
      const isVOp = !!nx && nx.type === "keyword" && (nxU === "\u0412" || nxU === "\u041F\u041E\u0414\u041E\u0411\u041D\u041E");
      if (!isVOp) continue;
      const operandStart = sig2[0].pos;
      if (t.pos <= operandStart) continue;
      const neEnd = t.pos + (t.text ?? t.value).length;
      const before = out.slice(operandStart, t.pos).replace(/\s+$/u, "");
      out = out.slice(0, operandStart) + "\u041D\u0415 " + before + out.slice(neEnd);
      break;
    }
  }
  return out;
}
var CMP_MIRROR = { "<": ">", ">": "<", "<=": ">=", ">=": "<=", "=": "=", "<>": "<>" };
var LITERAL_KEYWORDS = /* @__PURE__ */ new Set(["\u041B\u041E\u0416\u042C", "\u0418\u0421\u0422\u0418\u041D\u0410", "\u041D\u0415\u041E\u041F\u0420\u0415\u0414\u0415\u041B\u0415\u041D\u041E", "NULL"]);
function canonicalizeComparisonOperands(raw) {
  if (!raw || raw.includes("\n")) return raw;
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  if (sig.length < 3) return raw;
  const lhs = sig[0];
  const op2 = sig[1];
  const isLit = lhs.type === "param" || lhs.type === "string" || lhs.type === "number" || lhs.type === "date";
  const isCmpOp = op2.type === "punct" && COMPARISON_PUNCT_SET.has(op2.value);
  if (!isLit || !isCmpOp) return raw;
  for (let k = 2; k < sig.length; k++) {
    const tk = sig[k];
    if ((k - 2) % 2 === 0) {
      if (tk.type !== "ident" && tk.type !== "keyword") return raw;
      if (k === 2 && sig.length === 3 && LITERAL_KEYWORDS.has((tk.text ?? tk.value).toUpperCase())) return raw;
    } else if (!(tk.type === "punct" && tk.value === ".")) {
      return raw;
    }
  }
  if ((sig.length - 2) % 2 !== 1) return raw;
  const rhsText = raw.slice(sig[2].pos).replace(/\s+$/u, "");
  const lhsText = lhs.text ?? lhs.value;
  const opText = CMP_MIRROR[op2.value] ?? op2.value;
  return `${rhsText} ${opText} ${lhsText}`;
}
var ARITH_ADD = /* @__PURE__ */ new Set(["+", "-"]);
var ARITH_MUL = /* @__PURE__ */ new Set(["*", "/", "%"]);
var ARITH_STOP_PUNCT = /* @__PURE__ */ new Set(["<", ">", "=", "<=", ">=", "<>", "[", "]", "?", "@", ";"]);
var ARITH_STOP_WORDS = /* @__PURE__ */ new Set([
  "\u0418\u041B\u0418",
  "\u0418",
  "\u041D\u0415",
  "\u0412\u042B\u0411\u041E\u0420",
  "\u041A\u041E\u0413\u0414\u0410",
  "\u0422\u041E\u0413\u0414\u0410",
  "\u0418\u041D\u0410\u0427\u0415",
  "\u041A\u041E\u041D\u0415\u0426",
  "\u0415\u0421\u0422\u042C",
  "\u041C\u0415\u0416\u0414\u0423",
  "\u0412",
  "\u041F\u041E\u0414\u041E\u0411\u041D\u041E",
  "\u0421\u0421\u042B\u041B\u041A\u0410",
  "\u0421\u041F\u0415\u0426\u0421\u0418\u041C\u0412\u041E\u041B",
  "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418"
]);
var ArithError = class extends Error {
};
var ArithReprinter = class {
  constructor(sig) {
    this.sig = sig;
  }
  i = 0;
  peek() {
    return this.sig[this.i];
  }
  next() {
    return this.sig[this.i++];
  }
  val(t) {
    return t ? t.text ?? t.value : "";
  }
  /** Полный разбор: выражение должно занять все токены. */
  parseAll() {
    const node = this.parseExpr();
    if (this.i !== this.sig.length) throw new ArithError("\u0445\u0432\u043E\u0441\u0442");
    return node.text;
  }
  parseExpr() {
    let left = this.parseTerm();
    while (this.peek() && this.peek().type === "punct" && ARITH_ADD.has(this.peek().value)) {
      const op2 = this.next().value;
      const right = this.parseTerm();
      left = {
        text: `${this.wrap(left, 1, "left", op2)} ${op2} ${this.wrap(right, 1, "right", op2)}`,
        prec: 1,
        bareCast: false
      };
    }
    return left;
  }
  parseTerm() {
    let left = this.parseUnary();
    while (this.peek() && this.peek().type === "punct" && ARITH_MUL.has(this.peek().value)) {
      const op2 = this.next().value;
      const right = this.parseUnary();
      left = {
        text: `${this.wrap(left, 2, "left", op2)} ${op2} ${this.wrap(right, 2, "right", op2)}`,
        prec: 2,
        bareCast: false
      };
    }
    return left;
  }
  parseUnary() {
    const t = this.peek();
    if (t && t.type === "punct" && (t.value === "-" || t.value === "+")) {
      this.next();
      const operand = this.parseUnary();
      return { text: `${t.value}${this.atomText(operand)}`, prec: 3, bareCast: false };
    }
    return this.parsePrimary();
  }
  /** Операнд унарного оператора в скобках, если это бинарная арифметика. */
  atomText(n) {
    return n.bareCast || n.prec < 3 ? `(${n.text})` : n.text;
  }
  parsePrimary() {
    const t = this.peek();
    if (!t) throw new ArithError("\u043A\u043E\u043D\u0435\u0446");
    if (t.type === "punct" && t.value === "(") {
      this.next();
      const inner = this.parseExpr();
      const close = this.next();
      if (!close || !(close.type === "punct" && close.value === ")")) throw new ArithError("\u043D\u0435\u0442 )");
      return inner;
    }
    if (t.type === "number" || t.type === "string" || t.type === "param" || t.type === "date") {
      this.next();
      return { text: this.val(t), prec: 3, bareCast: false };
    }
    if (t.type === "ident" || t.type === "keyword") {
      if (ARITH_STOP_WORDS.has((t.text ?? t.value).toUpperCase())) throw new ArithError("\u0441\u0442\u043E\u043F-\u0441\u043B\u043E\u0432\u043E");
      return this.parseNameOrCall();
    }
    if (t.type === "punct" && ARITH_STOP_PUNCT.has(t.value)) throw new ArithError("\u0441\u0442\u043E\u043F-\u043F\u0443\u043D\u043A\u0442");
    throw new ArithError("\u043D\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043D\u043E");
  }
  /** Точечный путь `Имя(.Имя)*` или вызов `Имя(arg, …)`. */
  parseNameOrCall() {
    const headTok = this.next();
    const head = this.val(headTok);
    let path = head;
    while (this.peek() && this.peek().type === "punct" && this.peek().value === ".") {
      this.next();
      const seg = this.next();
      if (!seg || seg.type !== "ident" && seg.type !== "keyword" && seg.type !== "number") {
        throw new ArithError("\u0441\u0435\u0433\u043C\u0435\u043D\u0442 \u043F\u0443\u0442\u0438");
      }
      path += "." + this.val(seg);
    }
    if (path === head && this.peek() && this.peek().type === "punct" && this.peek().value === "(") {
      this.next();
      const args = this.parseArgList();
      const close = this.next();
      if (!close || !(close.type === "punct" && close.value === ")")) throw new ArithError("\u043D\u0435\u0442 ) \u0432\u044B\u0437\u043E\u0432\u0430");
      const isCast = head.toUpperCase() === "\u0412\u042B\u0420\u0410\u0417\u0418\u0422\u042C";
      return { text: `${head}(${args.join(", ")})`, prec: 3, bareCast: isCast };
    }
    return { text: path, prec: 3, bareCast: false };
  }
  /** Список аргументов вызова: каждый — арифметика, опц. с `КАК <тип>` (ВЫРАЗИТЬ). */
  parseArgList() {
    const args = [];
    if (this.peek() && this.peek().type === "punct" && this.peek().value === ")") return args;
    for (; ; ) {
      args.push(this.parseArg());
      const t = this.peek();
      if (t && t.type === "punct" && t.value === ",") {
        this.next();
        continue;
      }
      break;
    }
    return args;
  }
  /** Аргумент вызова: арифм. выражение и опц. `КАК <тип-выражение>` (приведение). */
  parseArg() {
    const expr = this.parseExpr();
    const t = this.peek();
    if (t && (t.type === "keyword" || t.type === "ident") && (t.text ?? t.value).toUpperCase() === "\u041A\u0410\u041A") {
      this.next();
      const type = this.parseNameOrCall();
      return `${expr.text} \u041A\u0410\u041A ${type.text}`;
    }
    return expr.text;
  }
  /**
   * Решает обрамление дочернего операнда скобками. `parentPrec` — приоритет
   * родительского оператора; `side` — слева/справа от него.
   *   - Голый ВЫРАЗИТЬ-операнд арифметики всегда в скобках (особое правило 1С).
   *   - prec < parentPrec → нужны скобки (защита приоритета).
   *   - prec == parentPrec и правый операнд под `- /` (non-assoc) → скобки.
   */
  wrap(n, parentPrec, side, op2) {
    if (n.bareCast) return `(${n.text})`;
    if (n.prec < parentPrec) return `(${n.text})`;
    if (n.prec === parentPrec && side === "right") {
      return `(${n.text})`;
    }
    return n.text;
  }
};
var PRED_NEIGHBOR_WORDS = /* @__PURE__ */ new Set([
  "\u041D\u0415",
  "\u0418",
  "\u0418\u041B\u0418",
  "\u041A\u041E\u0413\u0414\u0410",
  "\u0422\u041E\u0413\u0414\u0410",
  "\u0418\u041D\u0410\u0427\u0415",
  "\u0415\u0421\u0422\u042C",
  "\u041C\u0415\u0416\u0414\u0423",
  "\u041F\u041E\u0414\u041E\u0411\u041D\u041E",
  "\u0421\u0421\u042B\u041B\u041A\u0410"
]);
var COMPARISON_PUNCT_SET = /* @__PURE__ */ new Set(["=", "<>", "<", ">", "<=", ">="]);
var ARITH_PUNCT_SET = /* @__PURE__ */ new Set(["+", "-", "*", "/", "%"]);
function isCallOpenContext(prev) {
  if (!prev) return false;
  if ((prev.type === "ident" || prev.type === "keyword") && PRED_NEIGHBOR_WORDS.has(prev.value.toUpperCase())) {
    return false;
  }
  if (prev.type === "ident" || prev.type === "param" || prev.type === "number" || prev.type === "string") {
    return true;
  }
  if (prev.type === "punct" && prev.value === ")") return true;
  if (prev.type === "keyword" && FUNCTION_WORDS.has(prev.value.toUpperCase())) return true;
  return false;
}
function stripRedundantLeafParens(raw) {
  if (!raw || raw.includes("\n") || !raw.includes("(")) return raw;
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  if (sig.length < 2) return raw;
  const isPredWord = (t) => !!t && (t.type === "keyword" || t.type === "ident") && PRED_NEIGHBOR_WORDS.has(t.value.toUpperCase());
  const isCmpPunct = (t) => !!t && t.type === "punct" && COMPARISON_PUNCT_SET.has(t.value);
  const isArithPunct = (t) => !!t && t.type === "punct" && ARITH_PUNCT_SET.has(t.value);
  const isOpenParen = (t) => !!t && t.type === "punct" && t.value === "(";
  const leftOk = (prev) => !prev || isCmpPunct(prev) || isPredWord(prev) || isOpenParen(prev);
  const isMembershipWord = (t) => !!t && (t.type === "keyword" || t.type === "ident") && t.value.toUpperCase() === "\u0412";
  const rightOk = (nx) => {
    if (!nx) return true;
    if (nx.type === "punct" && (nx.value === ")" || nx.value === ",")) return true;
    if (nx.type === "keyword" && nx.value.toUpperCase() === "\u041A\u0410\u041A") return true;
    if (isCmpPunct(nx)) return true;
    if (isPredWord(nx)) return true;
    if (isMembershipWord(nx)) return true;
    return false;
  };
  const match = /* @__PURE__ */ new Map();
  const stack = [];
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (t.type === "punct" && t.value === "(") stack.push(i);
    else if (t.type === "punct" && t.value === ")") {
      const o = stack.pop();
      if (o === void 0) return raw;
      match.set(o, i);
    }
  }
  if (stack.length) return raw;
  const drop = /* @__PURE__ */ new Set();
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (!(t.type === "punct" && t.value === "(")) continue;
    if (drop.has(i)) continue;
    const close = match.get(i);
    const prev = i > 0 ? sig[i - 1] : void 0;
    const nx = close + 1 < sig.length ? sig[close + 1] : void 0;
    if (isCallOpenContext(prev)) continue;
    if (close === i + 1) continue;
    let hasTopComma = false;
    let depth = 0;
    for (let k = i + 1; k < close; k++) {
      const c = sig[k];
      if (c.type === "punct" && c.value === "(") depth++;
      else if (c.type === "punct" && c.value === ")") depth--;
      else if (depth === 0 && c.type === "punct" && c.value === ",") {
        hasTopComma = true;
        break;
      }
    }
    if (hasTopComma) continue;
    if (isArithPunct(prev) || isArithPunct(nx)) continue;
    if (!leftOk(prev) || !rightOk(nx)) continue;
    const neighborIsCompare = (t2) => isCmpPunct(t2) || !!t2 && (t2.type === "keyword" || t2.type === "ident") && (/* @__PURE__ */ new Set(["\u0415\u0421\u0422\u042C", "\u041C\u0415\u0416\u0414\u0423", "\u041F\u041E\u0414\u041E\u0411\u041D\u041E", "\u0421\u0421\u042B\u041B\u041A\u0410"])).has(t2.value.toUpperCase());
    if (neighborIsCompare(prev) || neighborIsCompare(nx)) {
      let innerCompare = false;
      let d = 0;
      for (let k = i + 1; k < close; k++) {
        const c = sig[k];
        if (c.type === "punct" && c.value === "(") d++;
        else if (c.type === "punct" && c.value === ")") d--;
        else if (d === 0 && neighborIsCompare(c)) {
          innerCompare = true;
          break;
        }
      }
      if (innerCompare) continue;
    }
    if (isMembershipWord(nx)) {
      let innerBoolCmp = false;
      let d2 = 0;
      for (let k = i + 1; k < close; k++) {
        const c = sig[k];
        if (c.type === "punct" && c.value === "(") d2++;
        else if (c.type === "punct" && c.value === ")") d2--;
        else if (d2 === 0 && (isCmpPunct(c) || isAnd(c) || isOr(c) || neighborIsCompare(c))) {
          innerBoolCmp = true;
          break;
        }
      }
      if (innerBoolCmp) continue;
    }
    drop.add(i);
    drop.add(close);
  }
  if (!drop.size) return raw;
  const positions = [];
  for (const idx of drop) positions.push(sig[idx].pos);
  positions.sort((a, b) => b - a);
  let out = raw;
  for (const p of positions) {
    out = out.slice(0, p) + " " + out.slice(p + 1);
  }
  return out.replace(/\s{2,}/g, " ").replace(/\(\s+/g, "(").replace(/\s+\)/g, ")").replace(/\s+,/g, ",").trim();
}
function stripRedundantCaseClauseParens(content) {
  const t = content.trim();
  if (t.length < 2 || t[0] !== "(" || !t.endsWith(")")) return content;
  let depth = 0;
  let inStr = false;
  for (let i = 0; i < t.length; i++) {
    const ch = t[i];
    if (ch === '"') {
      inStr = !inStr;
      continue;
    }
    if (inStr) continue;
    if (ch === "(") depth++;
    else if (ch === ")") {
      depth--;
      if (depth === 0 && i !== t.length - 1) return content;
    }
  }
  if (depth !== 0) return content;
  const inner = t.slice(1, -1).trim();
  if (inner === "") return content;
  if (/(?:^|[^\p{L}\p{N}_])(ВЫРАЗИТЬ|ВЫБОР|ВЫБРАТЬ)(?:[^\p{L}\p{N}_]|$)/iu.test(inner)) return content;
  if (leafHasTopBoolean(inner)) return content;
  return inner;
}
function reprintLeafArithmetic(raw) {
  if (!raw || raw.includes("\n")) return raw;
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  if (sig.length === 0) return raw;
  const hasArithOp = sig.some(
    (t) => t.type === "punct" && (ARITH_ADD.has(t.value) || ARITH_MUL.has(t.value))
  );
  if (!hasArithOp) return raw;
  try {
    const out = new ArithReprinter(sig).parseAll();
    return out;
  } catch {
    return raw;
  }
}
function reprintLeafComparison(raw) {
  if (!raw || raw.includes("\n") || !raw.includes("(")) return raw;
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  if (sig.length === 0) return raw;
  let depth = 0;
  let cmpIdx = -1;
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (t.type === "punct" && t.value === "(") {
      depth++;
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      depth--;
      continue;
    }
    if (depth !== 0) continue;
    if ((t.type === "keyword" || t.type === "ident") && (/* @__PURE__ */ new Set(["\u0418", "\u0418\u041B\u0418", "\u041D\u0415", "\u0415\u0421\u0422\u042C", "\u041C\u0415\u0416\u0414\u0423", "\u041F\u041E\u0414\u041E\u0411\u041D\u041E", "\u0421\u0421\u042B\u041B\u041A\u0410", "\u0412", "\u041A\u0410\u041A", "\u0412\u042B\u0411\u041E\u0420"])).has((t.text ?? t.value).toUpperCase())) {
      return raw;
    }
    if (t.type === "punct" && COMPARISON_PUNCT_SET.has(t.value)) {
      if (cmpIdx >= 0) return raw;
      cmpIdx = i;
    }
  }
  if (cmpIdx < 0) return raw;
  const leftToks = sig.slice(0, cmpIdx);
  const rightToks = sig.slice(cmpIdx + 1);
  if (leftToks.length === 0 || rightToks.length === 0) return raw;
  try {
    const left = new ArithReprinter(leftToks).parseAll();
    const right = new ArithReprinter(rightToks).parseAll();
    return `${left} ${sig[cmpIdx].value} ${right}`;
  } catch {
    return raw;
  }
}
function normalizeLeafCase(raw) {
  if (!raw) return raw;
  raw = canonicalizeLeafLexemes(raw);
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  const spans = [];
  const prevSig = (idx) => sig[idx - 1];
  const nextSig = (idx) => sig[idx + 1];
  const isWordTok = (t) => !!t && (t.type === "ident" || t.type === "keyword");
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (!isWordTok(t)) continue;
    const prev = prevSig(i);
    if (prev && prev.type === "punct" && prev.value === ".") continue;
    const up3 = tokUpper(t);
    const text2 = t.text ?? t.value;
    if (text2 === up3) continue;
    const next = nextSig(i);
    const followedByParen = !!next && next.type === "punct" && next.value === "(";
    let shouldUpper = false;
    if (FUNCTION_WORDS.has(up3) && followedByParen) shouldUpper = true;
    if (!shouldUpper && LITERAL_WORDS.has(up3)) shouldUpper = true;
    if (!shouldUpper && PRIMITIVE_TYPE_WORDS.has(up3)) {
      const afterKak = !!prev && prev.type === "keyword" && prev.value === "\u041A\u0410\u041A";
      let insideTip = false;
      if (prev && prev.type === "punct" && prev.value === "(") {
        const pp = prevSig(i - 1);
        if (pp && isWordTok(pp) && tokUpper(pp) === "\u0422\u0418\u041F") insideTip = true;
      }
      if (afterKak || insideTip) shouldUpper = true;
    }
    if (!shouldUpper && PERIOD_WORDS.has(up3)) {
      const nextIsDot = !!next && next.type === "punct" && next.value === ".";
      if (!followedByParen && !nextIsDot && enclosingFunctionIs(sig, i, PERIOD_FUNCTIONS)) {
        shouldUpper = true;
      }
    }
    if (!shouldUpper && (up3 === "\u041D\u0415" || up3 === "\u0418\u041B\u0418" || up3 === "\u0415\u0421\u0422\u042C")) shouldUpper = true;
    if (!shouldUpper && t.type === "keyword" && up3 === "\u041A\u0410\u041A") shouldUpper = true;
    if (!shouldUpper && up3 === "\u0421\u0421\u042B\u041B\u041A\u0410") {
      const prevIsExprEnd = !!prev && (prev.type === "number" || prev.type === "string" || prev.type === "punct" && prev.value === ")" || (prev.type === "ident" || prev.type === "keyword") && !(prev.type === "keyword" && prev.value === "\u041A\u0410\u041A"));
      if (prevIsExprEnd && isWordTok(next)) shouldUpper = true;
    }
    if (shouldUpper) spans.push({ pos: t.pos, len: text2.length, up: up3 });
  }
  let out = raw;
  if (spans.length) {
    spans.sort((a, b) => b.pos - a.pos);
    for (const s of spans) {
      out = out.slice(0, s.pos) + s.up + out.slice(s.pos + s.len);
    }
  }
  return normalizeLeafWhitespace(out);
}
function up(t) {
  return t.value.toUpperCase();
}
function isWord(t, w) {
  return (t.type === "ident" || t.type === "keyword") && up(t) === w;
}
function isOr(t) {
  return isWord(t, "\u0418\u041B\u0418");
}
function isAnd(t) {
  return t.type === "keyword" && t.value === "\u0418";
}
function isNot(t) {
  return isWord(t, "\u041D\u0415");
}
function isCase(t) {
  return isWord(t, "\u0412\u042B\u0411\u041E\u0420");
}
function isWhen(t) {
  return isWord(t, "\u041A\u041E\u0413\u0414\u0410");
}
function isThen(t) {
  return isWord(t, "\u0422\u041E\u0413\u0414\u0410");
}
function isElse(t) {
  return isWord(t, "\u0418\u041D\u0410\u0427\u0415");
}
function isEnd(t) {
  return isWord(t, "\u041A\u041E\u041D\u0415\u0426");
}
function isLeafCaseOpenerOp(t) {
  return t.type === "punct" && (COMPARISON_PUNCT.has(t.value) || ARITH_ADD.has(t.value) || ARITH_MUL.has(t.value));
}
function pushOrOperand(operands, op2) {
  if (operands.length === 0) {
    if (op2.kind === "or") {
      operands.push(...op2.operands);
      return;
    }
    if (op2.kind === "group" && op2.child.kind === "or") {
      operands.push(...op2.child.operands);
      return;
    }
  }
  if (op2.kind === "group" && op2.child.kind === "and") {
    operands.push(op2.child);
    return;
  }
  operands.push(op2);
}
var Parser = class {
  toks;
  raw;
  i = 0;
  /**
   * Сплющивать ли многострочные листья в одну строку. Включается только для слота
   * `select` (поля выборки и значения ВЫБОР), где конструктор печатает листовое
   * подвыражение на одной строке. В слотах ГДЕ/ИМЕЮЩИЕ/ПО исторически сохраняется
   * многострочная структура исходника дословно (нулевая регрессия принятых файлов).
   */
  flattenLeaves;
  constructor(raw, flattenLeaves = false) {
    this.raw = raw;
    this.flattenLeaves = flattenLeaves;
    this.toks = tokenize(raw);
  }
  peek() {
    return this.toks[this.i];
  }
  atEof() {
    return this.peek().type === "eof";
  }
  /** Срез исходной строки [from, to) с обрезкой хвостовых пробелов. */
  slice(from, to) {
    return this.raw.slice(from, to).replace(/\s+$/u, "");
  }
  /**
   * Текст листа [from, to): сплющивает многострочный лист в одну строку (конструктор
   * печатает листовые подвыражения на одной строке), затем нормализует регистр и
   * пробелы. Однострочные листья проходят только нормализацию (поведение принятых
   * запросов не меняется).
   */
  leafText(from, to) {
    const raw = this.raw.slice(from, to).replace(/\s+$/u, "");
    const flat = this.flattenLeaves && raw.includes("\n") && !leafHasSubquery(raw) && !leafHasTopBoolean(raw) && !leafHasCase(raw) ? flattenLeafText(raw) : raw;
    return normalizeLeafCase(flat);
  }
  parse() {
    const node = this.parseOr();
    return node;
  }
  /**
   * Дословный хвост: всё от КОНЦА последнего потреблённого токена до конца строки
   * (включая исходные пробелы/переносы перед хвостом). '' если хвоста нет.
   * Сохраняет, например, ошибочно захваченные парсером SDBL `\n\nУПОРЯДОЧИТЬ ПО …`.
   */
  tail() {
    if (this.peek().type === "eof") return "";
    const prev = this.i > 0 ? this.toks[this.i - 1] : void 0;
    const from = prev ? prev.pos + prev.text.length : this.peek().pos;
    return this.raw.slice(from);
  }
  // ИЛИ — низший приоритет
  parseOr() {
    const first = this.parseAnd();
    const operands = [];
    pushOrOperand(operands, first);
    while (!this.atEof() && isOr(this.peek())) {
      this.i++;
      pushOrOperand(operands, this.parseAnd());
    }
    return operands.length === 1 ? operands[0] : { kind: "or", operands };
  }
  parseAnd() {
    const first = this.parseNot();
    const operands = [first];
    while (!this.atEof() && isAnd(this.peek())) {
      this.i++;
      operands.push(this.parseNot());
    }
    return operands.length === 1 ? first : { kind: "and", operands };
  }
  parseNot() {
    if (!this.atEof() && isNot(this.peek())) {
      if (this.notIsStructural()) {
        this.i++;
        return { kind: "not", child: this.parseNot() };
      }
    }
    return this.parsePrimary();
  }
  /**
   * Является ли текущее `НЕ` структурным булевым отрицанием. Структурно — если
   * за ним ВЫБОР или открывающая скобка, чьё содержимое содержит верхнеуровневый
   * И/ИЛИ (булева группа). Иначе `НЕ` — унарный оператор внутри листа (`НЕ a.Флаг`,
   * `НЕ a.X В (…)`), и обрабатывается листом дословно.
   */
  notIsStructural() {
    const next = this.toks[this.i + 1];
    if (!next) return false;
    if (isCase(next)) return true;
    if (next.type === "punct" && next.value === "(") {
      return this.parenHasTopBoolean(this.i + 1);
    }
    return false;
  }
  /** Содержит ли скобочная группа, открытая на индексе `open`, верхнеур. И/ИЛИ. */
  parenHasTopBoolean(open) {
    let depth = 0;
    for (let k = open; k < this.toks.length; k++) {
      const t = this.toks[k];
      if (t.type === "eof") break;
      if (t.type === "punct" && t.value === "(") {
        depth++;
        continue;
      }
      if (t.type === "punct" && t.value === ")") {
        depth--;
        if (depth === 0) break;
        continue;
      }
      if (depth === 1 && (isAnd(t) || isOr(t))) return true;
    }
    return false;
  }
  /**
   * Скобка на индексе `open` обёртывает РОВНО один ВЫБОР…КОНЕЦ (первый значимый
   * токен внутри — ВЫБОР), а ПОСЛЕ её закрывающей `)` сразу идёт оператор сравнения
   * (`= <> < > <= >=`), арифметики (`+ - * / %`) или МЕЖДУ/ПОДОБНО. Используется для
   * снятия избыточной обёртки CASE-операнда (`(ВЫБОР…КОНЕЦ) <> X` → `ВЫБОР…КОНЕЦ <> X`).
   */
  parenWrapsCaseThenCompare(open) {
    const inner = this.toks[open + 1];
    if (!isCase(inner)) return false;
    let depth = 0;
    let closeIdx = -1;
    for (let k = open; k < this.toks.length; k++) {
      const tk = this.toks[k];
      if (tk.type === "eof") break;
      if (tk.type === "punct" && tk.value === "(") {
        depth++;
        continue;
      }
      if (tk.type === "punct" && tk.value === ")") {
        depth--;
        if (depth === 0) {
          closeIdx = k;
          break;
        }
      }
    }
    if (closeIdx < 0) return false;
    const after = this.toks[closeIdx + 1];
    if (!after || after.type === "eof") return false;
    if (after.type === "punct" && (COMPARE_OPS.has(after.value) || ARITH_ADD.has(after.value) || ARITH_MUL.has(after.value))) {
      return true;
    }
    if (isWord(after, "\u041C\u0415\u0416\u0414\u0423") || isWord(after, "\u041F\u041E\u0414\u041E\u0411\u041D\u041E")) return true;
    return false;
  }
  /**
   * Ведущий CASE-операнд сравнения, чей RHS — тоже ВЫБОР (`ВЫБОР…КОНЕЦ <op> ВЫБОР…КОНЕЦ`).
   * `tryParseSimpleCaseTrailing` такую форму бракует (вложенный ВЫБОР в хвосте), а
   * структурный CASE-узел не несёт многоклаузный CASE-RHS. Поэтому, как и зеркальный
   * случай `<лист> <op> ВЫБОР…КОНЕЦ` (который parseLeaf поглощает листом через caseDepth),
   * поглощаем весь сравнительный цепочечный CASE одним ЛИСТОМ — рендер раскладывает обе
   * (и более) ветви ВЫБОР через reindentLeafCase, печатая `КОНЕЦ <op> ВЫБОР` единой
   * строкой (сверено живым оракулом: `КОНЕЦ <> ВЫБОР` на одной строке, RHS-CASE
   * многострочно). Возвращает листовой текст ИЛИ undefined (позицию НЕ двигает).
   */
  tryParseCaseCompareCaseLeaf() {
    const save = this.i;
    const from = this.peek().pos;
    let to = from;
    let caseDepth = 0;
    let chained = false;
    while (!this.atEof()) {
      const t = this.peek();
      if (isCase(t)) {
        caseDepth++;
        to = t.pos + t.text.length;
        this.i++;
        continue;
      }
      if (isEnd(t)) {
        to = t.pos + t.text.length;
        this.i++;
        if (caseDepth > 0) caseDepth--;
        if (caseDepth === 0) {
          const op2 = this.atEof() ? void 0 : this.peek();
          const rhs = this.toks[this.i + 1];
          if (op2 && op2.type === "punct" && COMPARE_OPS.has(op2.value) && rhs && isCase(rhs)) {
            chained = true;
            to = op2.pos + op2.value.length;
            this.i++;
            continue;
          }
          break;
        }
        continue;
      }
      to = t.pos + t.value.length;
      this.i++;
    }
    if (!chained || caseDepth !== 0) {
      this.i = save;
      return void 0;
    }
    return this.leafText(from, to);
  }
  parsePrimary() {
    const t = this.peek();
    if (isCase(t)) {
      const chainLeaf = this.tryParseCaseCompareCaseLeaf();
      if (chainLeaf !== void 0) return { kind: "leaf", text: chainLeaf };
      const caseNode = this.parseCase();
      if (!this.atEof() && caseNode.kind === "case") {
        const t2 = this.peek();
        const boundary = isAnd(t2) || isOr(t2) || isThen(t2) || isElse(t2) || isEnd(t2) || isWhen(t2) || t2.type === "punct" && t2.value === ")";
        if (!boundary) {
          const trailing = this.tryParseSimpleCaseTrailing(true, true);
          if (trailing !== void 0) caseNode.trailing = trailing;
        }
      }
      return caseNode;
    }
    if (t.type === "punct" && t.value === "(" && this.parenIsStructuralGroup(this.i)) {
      if (!this.parenHasTopBoolean(this.i) && this.parenWrapsCaseThenCompare(this.i)) {
        this.i++;
        const caseNode = this.parseCase();
        if (!this.atEof() && this.peek().type === "punct" && this.peek().value === ")") {
          this.i++;
        }
        if (caseNode.kind === "case" && !this.atEof()) {
          const trailing = this.tryParseSimpleCaseTrailing(true, true);
          if (trailing !== void 0) caseNode.trailing = trailing;
        }
        return caseNode;
      }
      this.i++;
      const inner = this.parseOr();
      if (!this.atEof() && this.peek().type === "punct" && this.peek().value === ")") {
        this.i++;
      }
      return { kind: "group", child: inner };
    }
    return this.parseLeaf();
  }
  /**
   * Скобка структурна, если содержит верхнеур. И/ИЛИ или ВЫБОР. Скобка с
   * верхнеуровневой ЗАПЯТОЙ — это КОРТЕЖ-операнд (`(ВЫБОР…КОНЕЦ, ВЫБОР…КОНЕЦ) В (…)`,
   * `(Поле1, Поле2) В (…)`), а НЕ группа вокруг одного выражения: его нельзя
   * раскрывать в под-дерево group/case (иначе renderBool обернёт лишь ПЕРВЫЙ элемент,
   * добавив избыточные `(`…`)` и лишний уровень отступа). Кортеж поглощается листом
   * дословно (фаза 6.16, корпус ЗастрахованныеЛицаСЭДО/ОтчётКомиссионера).
   */
  parenIsStructuralGroup(open) {
    let depth = 0;
    let hasStructural = false;
    for (let k = open; k < this.toks.length; k++) {
      const t = this.toks[k];
      if (t.type === "eof") break;
      if (t.type === "punct" && t.value === "(") {
        depth++;
        continue;
      }
      if (t.type === "punct" && t.value === ")") {
        depth--;
        if (depth === 0) break;
        continue;
      }
      if (depth === 1 && t.type === "punct" && t.value === ",") return false;
      if (depth === 1 && (isAnd(t) || isOr(t) || isCase(t))) hasStructural = true;
    }
    return hasStructural;
  }
  /**
   * Лист: диапазон токенов до следующего верхнеуровневого булева И/ИЛИ, конца,
   * закрывающей скобки или КОГДА/ТОГДА/ИНАЧЕ/КОНЕЦ. Поглощает внутренние скобки,
   * вызовы, МЕЖДУ a И b (И после МЕЖДУ — не разделитель), ЕСТЬ [НЕ] NULL, ПОДОБНО.
   */
  parseLeaf() {
    const startTok = this.peek();
    const from = startTok.pos;
    let to = from;
    let depth = 0;
    let betweenPending = 0;
    let caseDepth = 0;
    let prevSig;
    while (!this.atEof()) {
      const t = this.peek();
      if (t.type === "punct" && t.value === "(") {
        depth++;
        to = t.pos + t.value.length;
        prevSig = t;
        this.i++;
        continue;
      }
      if (t.type === "punct" && t.value === ")") {
        if (depth === 0) break;
        depth--;
        to = t.pos + t.value.length;
        prevSig = t;
        this.i++;
        continue;
      }
      if (depth === 0) {
        if (caseDepth > 0) {
          if (isCase(t)) caseDepth++;
          else if (isEnd(t)) caseDepth--;
          to = t.pos + t.value.length;
          prevSig = t;
          this.i++;
          continue;
        }
        if (isCase(t) && prevSig !== void 0 && isLeafCaseOpenerOp(prevSig)) {
          caseDepth++;
          to = t.pos + t.value.length;
          prevSig = t;
          this.i++;
          continue;
        }
        if (isOr(t)) break;
        if (isAnd(t)) {
          if (betweenPending > 0) {
            betweenPending--;
          } else {
            break;
          }
        }
        if (isThen(t) || isElse(t) || isEnd(t) || isWhen(t)) break;
        if (isWord(t, "\u041C\u0415\u0416\u0414\u0423")) betweenPending++;
      }
      to = t.pos + t.value.length;
      prevSig = t;
      this.i++;
    }
    return { kind: "leaf", text: this.leafText(from, to) };
  }
  parseCase() {
    this.i++;
    let selector;
    if (!this.atEof() && !isWhen(this.peek())) {
      selector = this.parseCaseSelector();
    }
    const clauses = [];
    let elseNode = null;
    while (!this.atEof()) {
      const t = this.peek();
      if (isWhen(t)) {
        this.i++;
        const whenNode = this.parseOr();
        if (!this.atEof() && isThen(this.peek())) this.i++;
        const thenNode = this.parseValue();
        clauses.push({ whenNode, thenNode });
        continue;
      }
      if (isElse(t)) {
        this.i++;
        elseNode = this.parseValue();
        continue;
      }
      if (isEnd(t)) {
        this.i++;
        break;
      }
      break;
    }
    return { kind: "case", clauses, elseExpr: elseNode, selector };
  }
  /**
   * Хвост после `КОНЕЦ` value-слотового ВЫБОР: `<op> value` (`КОНЕЦ <> &П`).
   * Возвращает нормализованный текст хвоста (`<> &П`) ТОЛЬКО для узкой формы —
   * ровно один верхнеуровневый оператор сравнения, листовой операнд, без вложенного
   * ВЫБОР и без верхнеуровневых И/ИЛИ. Иначе undefined (позицию НЕ двигает).
   * Эта форма позволяет CASE идти структурным путём с приклеенным хвостом к КОНЕЦ.
   */
  tryParseSimpleCaseTrailing(allowLeadingArith = false, boolBoundary = false) {
    const save = this.i;
    const startTok = this.peek();
    const leadBetween = isWord(startTok, "\u041C\u0415\u0416\u0414\u0423");
    const leadLike = isWord(startTok, "\u041F\u041E\u0414\u041E\u0411\u041D\u041E");
    const leadOk = startTok.type === "punct" && (COMPARE_OPS.has(startTok.value) || allowLeadingArith && (ARITH_ADD.has(startTok.value) || ARITH_MUL.has(startTok.value))) || leadBetween || leadLike;
    if (!leadOk) return void 0;
    const from = startTok.pos;
    let to = from;
    let depth = 0;
    let cmpCount = 0;
    let betweenPending = leadBetween ? 1 : 0;
    if (leadBetween || leadLike) {
      to = startTok.pos + startTok.text.length;
      this.i++;
    }
    while (!this.atEof()) {
      const t = this.peek();
      if (t.type === "punct" && t.value === "(") {
        depth++;
        to = t.pos + t.value.length;
        this.i++;
        continue;
      }
      if (t.type === "punct" && t.value === ")") {
        if (depth === 0) break;
        depth--;
        to = t.pos + t.value.length;
        this.i++;
        continue;
      }
      if (depth === 0) {
        if (isWhen(t) || isThen(t) || isElse(t) || isEnd(t)) break;
        if (isCase(t)) {
          this.i = save;
          return void 0;
        }
        if (isAnd(t)) {
          if (betweenPending > 0) {
            betweenPending--;
          } else if (leadBetween || leadLike || boolBoundary) break;
          else {
            this.i = save;
            return void 0;
          }
        } else if (isOr(t)) {
          if (leadBetween || leadLike || boolBoundary) break;
          this.i = save;
          return void 0;
        } else if (isWord(t, "\u041C\u0415\u0416\u0414\u0423")) betweenPending++;
        else if (t.type === "punct" && COMPARE_OPS.has(t.value)) cmpCount++;
      }
      to = t.pos + t.value.length;
      this.i++;
    }
    const okShape = leadBetween || leadLike ? cmpCount === 0 : cmpCount === 1;
    if (!okShape) {
      this.i = save;
      return void 0;
    }
    return normalizeLeafWhitespace(this.leafText(from, to));
  }
  /**
   * Селектор формы `ВЫБОР <выражение> КОГДА …` — листовое выражение между ВЫБОР и
   * первым верхнеуровневым КОГДА. Печатается инлайн; нормализуется как лист.
   */
  parseCaseSelector() {
    const startTok = this.peek();
    const from = startTok.pos;
    let to = from;
    let depth = 0;
    while (!this.atEof()) {
      const t = this.peek();
      if (t.type === "punct" && t.value === "(") {
        depth++;
        to = t.pos + t.value.length;
        this.i++;
        continue;
      }
      if (t.type === "punct" && t.value === ")") {
        if (depth === 0) break;
        depth--;
        to = t.pos + t.value.length;
        this.i++;
        continue;
      }
      if (depth === 0 && isWhen(t)) break;
      to = t.pos + t.value.length;
      this.i++;
    }
    return this.leafText(from, to);
  }
  /**
   * Value-слот (после ТОГДА/ИНАЧЕ или поле выборки): либо вложенный ВЫБОР, либо
   * дословный текст до следующего КОГДА/ИНАЧЕ/КОНЕЦ верхнего уровня.
   */
  parseValue() {
    if (!this.atEof() && isCase(this.peek())) {
      const save = this.i;
      const caseNode = this.parseCase();
      if (this.atEof()) return caseNode;
      const t = this.peek();
      const boundary = isWhen(t) || isElse(t) || isEnd(t) || t.type === "punct" && t.value === ")";
      if (boundary) return caseNode;
      const trailing = this.tryParseSimpleCaseTrailing();
      if (trailing !== void 0 && caseNode.kind === "case") {
        caseNode.trailing = trailing;
        return caseNode;
      }
      this.i = save;
    }
    const startTok = this.peek();
    const from = startTok.pos;
    let to = from;
    let depth = 0;
    let caseDepth = 0;
    while (!this.atEof()) {
      const t = this.peek();
      if (t.type === "punct" && t.value === "(") {
        depth++;
        to = t.pos + t.value.length;
        this.i++;
        continue;
      }
      if (t.type === "punct" && t.value === ")") {
        if (depth === 0) break;
        depth--;
        to = t.pos + t.value.length;
        this.i++;
        continue;
      }
      if (depth === 0 && isCase(t)) {
        caseDepth++;
      } else if (depth === 0 && isEnd(t)) {
        if (caseDepth === 0) break;
        caseDepth--;
      } else if (depth === 0 && caseDepth === 0 && (isWhen(t) || isElse(t))) {
        break;
      }
      to = t.pos + t.value.length;
      this.i++;
    }
    return { kind: "leaf", text: this.leafText(from, to) };
  }
};
function treeHasStructure(node) {
  switch (node.kind) {
    case "or":
      return true;
    case "case":
      return true;
    case "and":
      return node.operands.some(treeHasStructure);
    case "not":
      return treeHasStructure(node.child);
    case "group":
      return treeHasStructure(node.child);
    case "leaf":
      return false;
  }
}
function needsFormatting(raw) {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return false;
  let tree;
  try {
    tree = new Parser(trimmed).parse();
  } catch {
    return false;
  }
  return treeHasStructure(tree);
}
function selectColumnNeedsBoolWrap(raw) {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return false;
  let tree;
  try {
    tree = new Parser(trimmed, true).parse();
  } catch {
    return false;
  }
  return (tree.kind === "and" || tree.kind === "or") && tree.operands.length >= 2;
}
function subDelta(orLvl, ctx) {
  return orLvl === 0 ? ctx.subDelta0 ?? 2 : 1;
}
function tabs(n) {
  return TAB.repeat(n);
}
var NEGATED_FIELD_RE = /^\(\s*НЕ\s+([\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*)\s*\)(\s[\s\S]*)?$/u;
function stripNegatedFieldParens(text2) {
  const m = NEGATED_FIELD_RE.exec(text2);
  if (!m) return text2;
  return `\u041D\u0415 ${m[1]}${m[2] ?? ""}`;
}
var NOT_FIELD_PARENS_RE = /(^|[^\p{L}\p{N}_])НЕ\(\s*([\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*)\s*\)/gu;
function stripNotFieldParens(text2) {
  return text2.replace(NOT_FIELD_PARENS_RE, (_m, pre, path) => `${pre}\u041D\u0415 ${path}`);
}
function renderBool(node, ind, andCont, orLvl, ctx, caseE = ind + 1, subInd, leadParenBase) {
  switch (node.kind) {
    case "or": {
      const noWrap = ctx.rootOrNoParens === true;
      ctx.rootOrNoParens = false;
      const orDelta = orLvl === 0 ? 2 : 1;
      const iliInd = Math.max(ind + orDelta, andCont);
      const childAnd = iliInd + 1;
      const lines = [];
      const orOperands = node.operands.map(
        (op2) => op2.kind === "group" && (op2.child.kind === "and" || op2.child.kind === "leaf") ? op2.child : op2
      );
      orOperands.forEach((op2, k) => {
        if (k === 0) {
          const op0CaseE = ctx.caseBoolean && (op2.kind === "leaf" && /(^|[^\p{L}\p{N}_])ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(op2.text) && op2.text.includes("\n") || op2.kind === "case") ? iliInd : ind;
          const sub = renderBool(op2, ind, childAnd, orLvl + 1, ctx, op0CaseE, childAnd, leadParenBase);
          if (!noWrap) sub[0] = "(" + sub[0];
          lines.push(...sub);
        } else {
          const sub = renderBool(op2, iliInd, childAnd, orLvl + 1, ctx, iliInd, childAnd);
          sub[0] = tabs(iliInd) + "\u0418\u041B\u0418 " + sub[0];
          lines.push(...sub);
        }
      });
      if (!noWrap) lines[lines.length - 1] += ")";
      return lines;
    }
    case "and": {
      const lines = [];
      node.operands.forEach((op0, k) => {
        const op2 = k === 0 && op0.kind === "group" && op0.child.kind === "and" ? op0.child : op0;
        if (k === 0) {
          lines.push(...renderBool(op2, ind, andCont, orLvl, ctx, caseE, subInd, leadParenBase));
        } else {
          const condCaseE = orLvl === 0 ? andCont + 1 : andCont;
          const sub = renderBool(op2, andCont, andCont + 1, orLvl, ctx, condCaseE);
          sub[0] = tabs(andCont) + "\u0418 " + sub[0];
          lines.push(...sub);
        }
      });
      return lines;
    }
    case "not": {
      if (node.child.kind === "group") {
        return renderNotGroup(node.child.child, ind, orLvl, ctx);
      }
      const si = (subInd ?? ind + subDelta(orLvl, ctx)) + 1;
      const childCaseE = node.child.kind === "case" ? caseE + 1 : caseE;
      const sub = renderBool(node.child, ind, andCont, orLvl, ctx, childCaseE, si);
      sub[0] = "\u041D\u0415 " + sub[0];
      return sub;
    }
    case "group": {
      const child = node.child;
      if (child.kind === "or") {
        if (leadParenBase !== void 0 && orLvl >= 1) {
          return renderBool(child, leadParenBase, andCont, orLvl, ctx, caseE, subInd, leadParenBase + 1);
        }
        return renderBool(child, ind, andCont, orLvl, ctx, caseE, subInd);
      }
      const childCaseE = child.kind === "case" ? caseE + 1 : caseE;
      const sub = renderBool(
        child,
        ind,
        andCont,
        orLvl,
        ctx,
        childCaseE,
        subInd,
        leadParenBase === void 0 ? void 0 : leadParenBase + 1
      );
      sub[0] = "(" + sub[0];
      sub[sub.length - 1] += ")";
      return sub;
    }
    case "case": {
      return renderCaseE(node, caseE, ctx);
    }
    case "leaf": {
      let t = ctx.stripNotParens ? stripNotFieldParens(stripNegatedFieldParens(flattenMultilineLeaf(node.text))) : flattenMultilineLeaf(node.text);
      t = stripRedundantLeafParens(t);
      t = wrapBareCastOperand(t);
      if (inlineSubqueryReflow && /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(t)) {
        const reflowed = inlineSubqueryReflow(t, subInd ?? ind + subDelta(orLvl, ctx));
        if (reflowed) return reflowed;
      }
      const rebased = reindentLeafSubquery(t, subInd ?? ind + subDelta(orLvl, ctx));
      return [appendIsNotNullTrailingSpace(reindentLeafCase(rebased, caseE, true))];
    }
  }
}
function renderWhenCondition(node, whenInd, ctx) {
  const contInd = whenInd + 2;
  if (node.kind === "not" && node.child.kind === "group") {
    return renderNotGroup(node.child.child, whenInd, 0, ctx);
  }
  switch (node.kind) {
    case "group":
      return renderWhenCondition(node.child, whenInd, ctx);
    case "or": {
      const lines = [];
      const orOps = node.operands.map(
        (op2) => op2.kind === "group" && (op2.child.kind === "and" || op2.child.kind === "leaf") ? op2.child : op2
      );
      orOps.forEach((op2, k) => {
        if (k === 0) {
          const op0HasCase = op2.kind === "case" || op2.kind === "leaf" && leafHasCase(op2.text);
          const op0CaseE = op0HasCase ? contInd : whenInd + 1;
          lines.push(...renderBool(op2, whenInd, contInd + 1, 1, ctx, op0CaseE, contInd + 1, contInd));
        } else {
          const opHasCase = op2.kind === "case" || op2.kind === "leaf" && leafHasCase(op2.text);
          const opCaseE = opHasCase ? contInd : contInd + 1;
          const sub = renderBool(op2, contInd, contInd + 1, 1, ctx, opCaseE, contInd + 1);
          sub[0] = tabs(contInd) + "\u0418\u041B\u0418 " + sub[0];
          lines.push(...sub);
        }
      });
      return lines;
    }
    case "and": {
      const lines = [];
      node.operands.forEach((op2, k) => {
        if (k === 0) {
          const op0HasCase = op2.kind === "case" || op2.kind === "leaf" && leafHasCase(op2.text);
          const op0CaseE = op0HasCase ? contInd : whenInd + 1;
          lines.push(...renderBool(op2, whenInd, contInd, 0, ctx, op0CaseE, contInd + 1, contInd));
        } else {
          const opHasCase = op2.kind === "case" || op2.kind === "leaf" && leafHasCase(op2.text);
          const opCaseE = opHasCase ? contInd : contInd + 1;
          const sub = renderBool(op2, contInd, contInd + 1, 1, ctx, opCaseE, contInd + 1);
          sub[0] = tabs(contInd) + "\u0418 " + sub[0];
          lines.push(...sub);
        }
      });
      return lines;
    }
    default:
      return renderBool(node, whenInd, contInd, 1, ctx, whenInd + 1, whenInd + 2);
  }
}
function renderCase(node, cursorInd, ctx, boolean) {
  return renderCaseE(node, boolean ? cursorInd + 1 : cursorInd, ctx);
}
function valueText(node) {
  return node.kind === "leaf" ? node.text : "";
}
function stripEnclosingParens(text2) {
  const t = text2.trim();
  if (!t.startsWith("(") || !t.endsWith(")")) return t;
  let depth = 0;
  let inStr = false;
  for (let i = 0; i < t.length; i++) {
    const ch = t[i];
    if (ch === '"') {
      inStr = !inStr;
      continue;
    }
    if (inStr) continue;
    if (ch === "(") depth++;
    else if (ch === ")") {
      depth--;
      if (depth === 0 && i !== t.length - 1) return t;
    }
  }
  return depth === 0 ? t.slice(1, -1).trim() : t;
}
function renderOrValueLines(keyword, value, kwInd) {
  let tree;
  try {
    tree = new Parser(value.trim(), false).parse();
  } catch {
    return null;
  }
  if (tree.kind === "and") {
    if (!value.includes("\n")) return null;
  } else if (tree.kind !== "or") {
    return null;
  }
  if (tree.operands.some((op2) => op2.kind === "case" || op2.kind === "group" && op2.child.kind === "case")) {
    return null;
  }
  const op0Word = tree.kind === "or" ? "\u0418\u041B\u0418" : "\u0418";
  const ctx = { cont: 1, caseBoolean: false };
  const contInd = kwInd + 2;
  const lines = [];
  tree.operands.forEach((op2, k) => {
    const keepOrGroup = tree.kind === "and" && op2.kind === "group" && op2.child.kind === "or";
    const bare = keepOrGroup ? op2 : op2.kind === "group" ? op2.child : op2.kind === "leaf" ? { kind: "leaf", text: stripEnclosingParens(op2.text) } : op2;
    const opAndCont = keepOrGroup ? contInd : contInd + 1;
    const sub = renderSelectBool(bare, k === 0 ? kwInd : contInd, opAndCont, 1, ctx, contInd + 1);
    sub[0] = k === 0 ? `${tabs(kwInd)}${keyword} ${sub[0]}` : `${tabs(contInd)}${op0Word} ${sub[0]}`;
    lines.push(...sub);
  });
  return lines;
}
function renderBranchValueLines(keyword, value, kwInd) {
  const orLines = renderOrValueLines(keyword, value, kwInd);
  if (orLines !== null) return orLines;
  const reflowed = reflowLeafSelectorCase(value, kwInd + 2);
  if (reflowed !== null) {
    const parts = reflowed.split("\n");
    return [tabs(kwInd) + keyword + " " + parts[0], ...parts.slice(1)];
  }
  if (value.includes("\n") && (isSingleTopLevelCaseValue(value) || opensWithTopLevelVybor(value) || opensWithVyborInCall(value))) {
    const useFuncParen = !isSingleTopLevelCaseValue(value);
    const reCase = reindentLeafCase(value, kwInd + 1, useFuncParen);
    if (reCase !== value) {
      const parts = reCase.split("\n");
      return [tabs(kwInd) + keyword + " " + wrapBareCastOperand(parts[0]), ...parts.slice(1)];
    }
  }
  const flat = flattenMultilineLeaf(value);
  const bare = reprintLeafComparison(reprintLeafArithmetic(wrapBareCastOperand(stripRedundantCaseClauseParens(flat))));
  if (inlineSubqueryReflow && /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(bare)) {
    const reflowed2 = inlineSubqueryReflow(bare, kwInd + 2);
    if (reflowed2) {
      const head = reflowed2[0].replace(/^\t+/u, "");
      return [tabs(kwInd) + keyword + " " + head, ...reflowed2.slice(1)];
    }
  }
  return [tabs(kwInd) + keyword + " " + reindentLeafSubquery(bare, kwInd + 2)];
}
function renderCaseE(node, E, ctx) {
  const lines = [node.selector ? "\u0412\u042B\u0411\u041E\u0420 " + node.selector : "\u0412\u042B\u0411\u041E\u0420"];
  for (const cl of node.clauses) {
    const whenInd = E + 1;
    const whenLines = renderWhenCondition(cl.whenNode, whenInd, ctx);
    whenLines[0] = tabs(whenInd) + "\u041A\u041E\u0413\u0414\u0410 " + whenLines[0];
    lines.push(...whenLines);
    const thenInd = E + 2;
    if (cl.thenNode.kind === "case") {
      const sub = renderCaseE(cl.thenNode, thenInd + 1, ctx);
      sub[0] = tabs(thenInd) + "\u0422\u041E\u0413\u0414\u0410 " + sub[0];
      lines.push(...sub);
    } else {
      lines.push(...renderBranchValueLines("\u0422\u041E\u0413\u0414\u0410", valueText(cl.thenNode), thenInd));
    }
  }
  if (node.elseExpr) {
    const elseInd = E + 1;
    if (node.elseExpr.kind === "case") {
      const sub = renderCaseE(node.elseExpr, elseInd + 1, ctx);
      sub[0] = tabs(elseInd) + "\u0418\u041D\u0410\u0427\u0415 " + sub[0];
      lines.push(...sub);
    } else {
      lines.push(...renderBranchValueLines("\u0418\u041D\u0410\u0427\u0415", valueText(node.elseExpr), elseInd));
    }
  }
  lines.push(tabs(E) + "\u041A\u041E\u041D\u0415\u0426" + (node.trailing ? " " + node.trailing : ""));
  return lines;
}
function caseHasNestedVyborInWhen(text2) {
  const COMPARE = /* @__PURE__ */ new Set(["<=", ">=", "<>", "=", "<", ">"]);
  for (const line of text2.split("\n")) {
    const m = /(^|[^\p{L}\p{N}_])(<=|>=|<>|=|<|>|\+|-|\*|\/)\s+ВЫБОР\s*$/u.exec(line);
    if (!m) continue;
    if (COMPARE.has(m[2])) return true;
    if (!/^[\t ]*КОГДА(?![\p{L}\p{N}_])/u.test(line)) continue;
    const before = line.slice(0, m.index + m[1].length);
    let depth = 0;
    let inStr = false;
    for (const ch of before) {
      if (ch === '"') inStr = !inStr;
      else if (!inStr && ch === "(") depth++;
      else if (!inStr && ch === ")") depth--;
    }
    if (depth === 0) return true;
  }
  return false;
}
function formatExpression(raw, slot, rootSubDelta) {
  const trimmed = raw.trim();
  const parser = new Parser(trimmed, slot === "select");
  const tree = parser.parse();
  const tail = parser.tail();
  let body;
  if (slot === "where" || slot === "having") {
    const ctx = { cont: 1, caseBoolean: true, stripNotParens: true, subDelta0: rootSubDelta };
    const startOrLvl = slot === "having" || rootSubDelta !== void 0 ? 1 : 0;
    if (tree.kind === "case") {
      const caseBoolean = slot === "where" && rootSubDelta === void 0;
      body = renderCase(tree, ctx.cont, ctx, caseBoolean).join("\n");
    } else if (tree.kind === "not" && tree.child.kind === "group") {
      body = renderNotGroup(tree.child.child, 1, startOrLvl, ctx).join("\n");
    } else {
      if (slot === "having" && rootSubDelta !== void 0) {
        const root = tree.kind === "group" ? tree.child : tree;
        if (root.kind === "or") ctx.rootOrNoParens = true;
      }
      body = renderBool(tree, 1, 1, startOrLvl, ctx).join("\n");
    }
  } else if (slot === "select") {
    const ctx = { cont: 1, caseBoolean: false };
    if (tree.kind === "case" && caseHasNestedVyborInWhen(trimmed)) {
      const flat = flattenMultilineLeaf(trimmed);
      const reindented = reindentLeafCase(flat, ctx.cont);
      if (reindented.includes("\n") && /^ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(reindented)) {
        return appendIsNotNullTrailingSpace(reindented);
      }
    }
    if (tree.kind === "case" && tail.trim() !== "") {
      const flat = flattenMultilineLeaf(trimmed);
      const reindented = reindentLeafCase(flat, ctx.cont, true);
      body = reindented !== flat ? reindented : renderCase(tree, ctx.cont, ctx, false).join("\n") + tail;
      return body;
    }
    if (tree.kind === "case") {
      body = renderCase(tree, ctx.cont, ctx, false).join("\n");
    } else {
      body = renderSelectBool(tree, 1, 2, 0, ctx).join("\n");
    }
  } else {
    const ctx = { cont: 2, caseBoolean: true };
    body = renderJoin(tree, ctx);
  }
  let result = appendIsNotNullTrailingSpace(body) + tail;
  if (/(?:^|[^\p{L}\p{N}_])В\s*\(\s*\n/u.test(tail) && !/(?:^|[^\p{L}\p{N}_])ВЫБРАТЬ(?![\p{L}\p{N}_])/u.test(tail)) {
    result = flattenInlineValueLists(result);
  }
  return result;
}
function renderNotGroup(child, ind, orLvl, ctx) {
  const cont = ind + (orLvl === 0 ? 2 : 1) + 1;
  let lines;
  if (child.kind === "or" || child.kind === "and") {
    const word = child.kind === "or" ? "\u0418\u041B\u0418 " : "\u0418 ";
    lines = [];
    const op0And = child.kind === "or" ? cont + 1 : cont;
    child.operands.forEach((op2, k) => {
      if (k === 0) {
        lines.push(...renderBool(op2, ind, op0And, orLvl + 1, ctx, ind + 1, cont + 1));
      } else {
        const opCaseE = op2.kind === "case" ? cont : cont + 1;
        const sub = renderBool(op2, cont, cont + 1, orLvl + 1, ctx, opCaseE, cont + 1);
        sub[0] = tabs(cont) + word + sub[0];
        lines.push(...sub);
      }
    });
  } else {
    lines = renderBool(child, ind, cont, orLvl + 1, ctx, ind + 1, cont + 1);
  }
  lines[0] = "\u041D\u0415(" + lines[0];
  lines[lines.length - 1] += ")";
  return lines;
}
function isRootNotGroup(raw) {
  const trimmed = (raw ?? "").trim();
  if (!trimmed) return false;
  let tree;
  try {
    tree = new Parser(trimmed).parse();
  } catch {
    return false;
  }
  return tree.kind === "not" && tree.child.kind === "group";
}
function renderSelectBool(node, ind, andCont, orLvl, ctx, subInd) {
  switch (node.kind) {
    case "or": {
      const iliInd = Math.max(ind + 1, andCont);
      const childAnd = iliInd + 1;
      const lines = [];
      const orOperands = node.operands.map(
        (op2) => op2.kind === "group" && (op2.child.kind === "and" || op2.child.kind === "leaf") ? op2.child : op2
      );
      orOperands.forEach((op2, k) => {
        if (k === 0) {
          if (op2.kind === "case") {
            lines.push(...renderCase(op2, ind, ctx, true));
          } else lines.push(...renderSelectBool(op2, ind, childAnd, orLvl + 1, ctx, childAnd));
        } else {
          const sub = renderSelectBool(op2, iliInd, childAnd, orLvl + 1, ctx, childAnd);
          sub[0] = tabs(iliInd) + "\u0418\u041B\u0418 " + sub[0];
          lines.push(...sub);
        }
      });
      return lines;
    }
    case "and": {
      const lines = [];
      node.operands.forEach((op2, k) => {
        if (k === 0) {
          if (op2.kind === "case") {
            lines.push(...renderCase(op2, ind, ctx, true));
          } else lines.push(...renderSelectBool(op2, ind, andCont, orLvl, ctx, subInd));
        } else {
          const sub = renderSelectBool(op2, andCont, andCont + 1, orLvl, ctx);
          sub[0] = tabs(andCont) + "\u0418 " + sub[0];
          lines.push(...sub);
        }
      });
      return lines;
    }
    case "not": {
      const sub = renderSelectBool(node.child, ind, andCont, orLvl, ctx, (subInd ?? ind + 1) + 1);
      sub[0] = "\u041D\u0415 " + sub[0];
      return sub;
    }
    case "group": {
      const sub = renderSelectBool(node.child, ind, andCont, orLvl, ctx, subInd);
      sub[0] = "(" + sub[0];
      sub[sub.length - 1] += ")";
      return sub;
    }
    case "case":
      return renderCase(node, ind, ctx, false);
    case "leaf":
      return [reindentLeafSubquery(wrapBareCastOperand(stripRedundantLeafParens(node.text)), subInd ?? ind + 1)];
  }
}
function renderJoin(tree, ctx) {
  const base = ctx.cont;
  const conjuncts = tree.kind === "and" ? tree.operands : [tree];
  const lines = [];
  conjuncts.forEach((c, k) => {
    const ind = k === 0 ? base : base + 1;
    const orLvl = k === 0 ? 0 : 1;
    const sub = renderJoinConjunct(c, ind, ctx, orLvl);
    if (k > 0) sub[0] = tabs(ind) + "\u0418 " + sub[0];
    lines.push(...sub);
  });
  return lines.join("\n");
}
function formatJoinConjunct(raw, first, base = 2) {
  const parser = new Parser(raw.trim(), true);
  const tree = parser.parse();
  const tail = parser.tail();
  const ctx = { cont: base, caseBoolean: true };
  const ind = first ? base : base + 1;
  const orLvl = first ? 0 : 1;
  if (tree.kind === "case") {
    if (tail.trim() !== "") {
      const leaf = reindentLeafCase(
        reindentLeafSubquery(raw.trim(), base + 2),
        base + 1
      );
      return appendIsNotNullTrailingSpace("(" + leaf + ")");
    }
    const sub = renderCaseE(tree, base + 1, ctx);
    sub[0] = "(" + sub[0];
    sub[sub.length - 1] += ")";
    return appendIsNotNullTrailingSpace(sub.join("\n")) + tail;
  }
  return appendIsNotNullTrailingSpace(renderJoinConjunct(tree, ind, ctx, orLvl).join("\n")) + tail;
}
function renderJoinConjunct(node, ind, ctx, orLvl) {
  switch (node.kind) {
    case "leaf": {
      const flat = flattenMultilineLeaf(node.text);
      if (inlineSubqueryReflow && /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(flat)) {
        const reflowed = inlineSubqueryReflow(flat, ind + subDelta(orLvl, ctx));
        if (reflowed) return reflowed;
      }
      return reindentLeafCase(reindentLeafSubquery(flat, ind + subDelta(orLvl, ctx)), ind).split("\n");
    }
    case "case":
      return renderCase(node, ind, ctx, true);
    case "not": {
      const sub = renderJoinConjunct(node.child, ind, ctx, orLvl);
      sub[0] = "\u041D\u0415 " + sub[0];
      return sub;
    }
    case "group": {
      const child = node.child;
      if (child.kind === "or") {
        return renderBool(child, ind, ind + 1, orLvl, ctx);
      }
      if (child.kind === "case") {
        const caseEnd = orLvl === 0 ? ind + 1 : ind;
        const sub2 = renderCaseE(child, caseEnd, ctx);
        sub2[0] = "(" + sub2[0];
        sub2[sub2.length - 1] += ")";
        return sub2;
      }
      const sub = renderBool(child, ind, ind + 1, orLvl, ctx);
      sub[0] = "(" + sub[0];
      sub[sub.length - 1] += ")";
      return sub;
    }
    case "or":
      return renderBool(node, ind, ind + 1, orLvl, ctx);
    case "and":
      return renderBool(node, ind, ind + 1, orLvl, ctx);
    default:
      return [""];
  }
}

// src/core/query/sdblGenerator.ts
setInlineSubqueryReflow((text2, subBase) => reflowInlineMembershipSubquery(text2, 0, subBase, ""));
var suppressAutoAlias = false;
var inConditionSubquery = false;
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function wrapAggregate(func, expr) {
  switch (func) {
    case "\u0421\u0443\u043C\u043C\u0430":
      return `\u0421\u0423\u041C\u041C\u0410(${expr})`;
    case "\u041A\u043E\u043B\u0438\u0447\u0435\u0441\u0442\u0432\u043E":
      return `\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E(${expr})`;
    case "\u041A\u043E\u043B\u0438\u0447\u0435\u0441\u0442\u0432\u043E\u0420\u0430\u0437\u043B\u0438\u0447\u043D\u044B\u0445":
      return `\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E(\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415 ${expr})`;
    case "\u041C\u0430\u043A\u0441\u0438\u043C\u0443\u043C":
      return `\u041C\u0410\u041A\u0421\u0418\u041C\u0423\u041C(${expr})`;
    case "\u041C\u0438\u043D\u0438\u043C\u0443\u043C":
      return `\u041C\u0418\u041D\u0418\u041C\u0423\u041C(${expr})`;
    case "\u0421\u0440\u0435\u0434\u043D\u0435\u0435":
      return `\u0421\u0420\u0415\u0414\u041D\u0415\u0415(${expr})`;
  }
}
function resolveAliases(tables) {
  const seen = /* @__PURE__ */ new Set();
  const result = /* @__PURE__ */ new Map();
  for (const t of tables) {
    const base = defaultTableAlias(t);
    let alias = base;
    let counter = 1;
    while (seen.has(alias)) {
      alias = base + counter;
      counter++;
    }
    seen.add(alias);
    result.set(t.id, alias);
  }
  return result;
}
function accountingPositions(slice, v) {
  const hasSubconto = v.subconto !== false;
  const keys = accountingPositionKeys(slice, hasSubconto, v.correspondence === true);
  return keys.map((k) => k ? v[k] ?? "" : "");
}
function renderConditionSubquery(subquery, baseTabs, leadingNot = false) {
  const pad = "	".repeat(baseTabs);
  const prev = suppressAutoAlias;
  const prevInSubquery = inConditionSubquery;
  suppressAutoAlias = true;
  inConditionSubquery = true;
  let text2;
  try {
    text2 = generateDocument(subquery);
  } finally {
    suppressAutoAlias = prev;
    inConditionSubquery = prevInSubquery;
  }
  for (const member of subquery.members) {
    for (const t of member.model.tables) {
      if (!t.aliasSynthesized || t.subquery) continue;
      const auto = defaultTableAlias(t);
      if (auto === t.fullName) continue;
      const re = new RegExp(`(^|[^\\p{L}\\p{N}_.])${escapeRegExp(auto)}\\.`, "gu");
      text2 = text2.replace(re, `$1${t.fullName}.`);
    }
  }
  const padBlank = "	".repeat(Math.max(0, baseTabs - 1 - (leadingNot ? 1 : 0)));
  const isUKw = (s) => /^\t*ОБЪЕДИНИТЬ(?:\s+ВСЕ)?\s*$/u.test(s.trim());
  const raw = text2.split("\n");
  const inner = raw.filter((l, k) => {
    if (l.trim() !== "") return true;
    const prevKw = k > 0 && isUKw(raw[k - 1]);
    const nextKw = k + 1 < raw.length && isUKw(raw[k + 1]);
    return prevKw || nextKw;
  });
  return inner.map((l, k) => {
    if (l === "") return padBlank;
    return k === 0 ? `${pad}(${l}` : `${pad}${l}`;
  }).join("\n") + ")";
}
function renderSource(t, bodyTabs = 1) {
  if (t.subquery) {
    const inner = generateDocument(t.subquery).split("\n");
    const pad = "	".repeat(bodyTabs);
    return inner.map((l, k) => k === 0 ? "(" + l : pad + l).join("\n") + ")";
  }
  if (!t.virtual) return t.fullName;
  const v = t.virtual;
  const parts = t.fullName.split(".");
  const kind = parts[0];
  const slice = parts[2];
  if (kind === "\u041A\u0440\u0438\u0442\u0435\u0440\u0438\u0439\u041E\u0442\u0431\u043E\u0440\u0430") {
    if ((v.period ?? "") === "" && !v.hadParens) return t.fullName;
    return `${t.fullName}(${v.period ? normalizeLeafCase(v.period) : ""})`;
  }
  if (kind === "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0411\u0443\u0445\u0433\u0430\u043B\u0442\u0435\u0440\u0438\u0438") {
    let positions2 = accountingPositions(slice, v);
    if (!positions2.some((p) => p !== "") && !v.hadParens) return t.fullName;
    const dcsStateAcc = { k: 0 };
    positions2 = positions2.map((p) => p ? aliasDcsBraceExprs(wrapDcsBraceParam(p), dcsStateAcc) : p);
    const multiline = positions2.some((p) => p && (hasTopLevelBooleanOp(p) || p.includes("\n") && /\(ВЫБРАТЬ/u.test(p)));
    if (multiline) {
      return renderAccountingParams(t.fullName, positions2, v.condition ?? "", bodyTabs);
    }
    return `${t.fullName}(${positions2.map((p) => p ? normalizeLeafCase(p) : p).join(", ")})`;
  }
  if (slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B" || slice === "\u041E\u0441\u0442\u0430\u0442\u043A\u0438\u0418\u041E\u0431\u043E\u0440\u043E\u0442\u044B") {
    const positions2 = slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B" ? [v.startPeriod ?? "", v.endPeriod ?? "", v.periodicity ?? "", v.condition ?? ""] : [v.startPeriod ?? "", v.endPeriod ?? "", v.periodicity ?? "", v.fillMethod ?? "", v.condition ?? ""];
    if (!positions2.some((p) => p !== "") && !v.hadParens) return t.fullName;
    return renderVirtualParams(t.fullName, positions2, v.condition ?? "", bodyTabs);
  }
  const positions = [v.period ?? "", v.condition ?? ""];
  if (!positions.some((p) => p !== "") && !v.hadParens) return t.fullName;
  return renderVirtualParams(t.fullName, positions, v.condition ?? "", bodyTabs);
}
function wrapDcsBraceParam(text2) {
  if (!text2.includes("{")) return text2;
  return text2.replace(/\{([^{}]*)\}/gu, (whole, inner) => {
    const c = inner.trim();
    if (!c.startsWith("&")) return whole;
    if (c.startsWith("(")) return whole;
    if (hasTopLevelComma(c) || /(^|[^\p{L}\p{N}_])КАК([^\p{L}\p{N}_]|$)/iu.test(c)) return whole;
    return `{(${c})}`;
  });
}
function aliasDcsBraceExprs(text2, state) {
  if (!text2.includes("{")) return text2;
  return text2.replace(/\{([^{}]*)\}/gu, (whole, inner) => {
    const c = inner.trim();
    if (/(^|[^\p{L}\p{N}_])КАК([^\p{L}\p{N}_]|$)/iu.test(c)) {
      state.k += 1;
      return whole;
    }
    if (!c.startsWith("(") || !c.endsWith(")")) return whole;
    const innerExpr = c.slice(1, -1).trim();
    if (/^&[\p{L}\p{N}_]+$/u.test(innerExpr)) return whole;
    if (hasTopLevelComma(c)) return whole;
    state.k += 1;
    return `{${c} \u041A\u0410\u041A \u041F\u043E\u043B\u0435${2 * state.k}}`;
  });
}
function mergeDcsBraces(text2) {
  if (!text2.includes("{")) return text2;
  const inners = [];
  let i = 0, count = 0;
  const n = text2.length;
  while (i < n) {
    const c = text2[i];
    if (c === "{") {
      let depth = 0, j = i;
      for (; j < n; j++) {
        if (text2[j] === "{") depth++;
        else if (text2[j] === "}") {
          depth--;
          if (depth === 0) break;
        }
      }
      if (j >= n) return text2;
      inners.push(text2.slice(i + 1, j).replace(/\s+/gu, " ").trim());
      count++;
      i = j + 1;
      continue;
    }
    if (/\s/u.test(c)) {
      i++;
      continue;
    }
    return text2;
  }
  if (count < 2) return text2;
  return `{${inners.join(", ")}}`;
}
function renderVirtualParams(fullName, positions, condition, bodyTabs) {
  positions = positions.map((p) => p ? mergeDcsBraces(p) : p);
  condition = condition ? mergeDcsBraces(condition) : condition;
  positions = positions.map((p) => p ? wrapDcsBraceParam(normalizeLeafCase(p)) : p);
  condition = condition ? wrapDcsBraceParam(normalizeLeafCase(condition)) : condition;
  const dcsState = { k: 0 };
  const condDup = condition !== "" && positions.length > 0 && positions[positions.length - 1] === condition;
  positions = positions.map((p) => p ? aliasDcsBraceExprs(p, dcsState) : p);
  if (condition && condition.includes("{")) {
    condition = condDup ? positions[positions.length - 1] : aliasDcsBraceExprs(condition, dcsState);
  }
  positions = positions.map((p) => p ? flattenMultilineLeaf(p) : p);
  condition = condition ? flattenMultilineLeaf(condition) : condition;
  condition = condition ? stripRedundantLeafParens(condition) : condition;
  if (condition && positions.length > 0 && positions[positions.length - 1]) {
    const li = positions.length - 1;
    positions[li] = stripRedundantLeafParens(flattenMultilineLeaf(positions[li]));
  }
  const condTrim = condition.trim();
  const condIsDcsBrace = condTrim.startsWith("{") && condTrim.endsWith("}") && positions.length > 0 && positions[positions.length - 1].trim() === condTrim;
  if (condIsDcsBrace) {
    return `${fullName}(${positions.join(", ")})`;
  }
  const hasBool = !!condition && hasTopLevelBooleanOp(condition);
  const hasSubquery = !!condition && condition.includes("\n");
  const hasInlineSubquery = !!condition && /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(condition);
  if (!condition || !hasBool && !hasSubquery && !hasInlineSubquery) {
    return `${fullName}(${positions.join(", ")})`;
  }
  if (inConditionSubquery && hasBool) {
    const ibase = bodyTabs;
    const condLines2 = reindentVtCondition(condition.trim(), ibase).split("\n");
    const headInline = positions.slice(0, -1).join(", ");
    condLines2[0] = condLines2[0].replace(/^\t+/u, "");
    return `${fullName}(${headInline}, ${condLines2.join("\n")})`;
  }
  const base = bodyTabs + 2;
  const pad = "	".repeat(base);
  const condFirstLine0 = condition.includes("\n") ? condition.slice(0, condition.indexOf("\n")) : condition;
  const isCaseValueParam = !hasBool && !/\bВЫБРАТЬ\b/iu.test(condition) && // Параметр-CASE: первая строка либо ОКАНЧИВАЕТСЯ словом ВЫБОР (`Имя = ВЫБОР`,
  // корпус СдельныйНаряд), либо НАЧИНАЕТСЯ им (селекторный `ВЫБОР &Парам …` или
  // условный `ВЫБОР КОГДА …`, корпус ПланФактныйАнализПродаж). В обоих случаях это
  // лист-CASE на отступе строки параметра (КОНЕЦ на base), не подзапрос.
  (/(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u.test(condFirstLine0) || /^ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(condition.trim()));
  const inlineCond = !hasBool && !isCaseValueParam && /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(condition) ? reflowInlineMembershipSubquery(condition.trim(), base, base + 1, "") : null;
  if (inlineCond) {
    inlineCond[0] = pad + inlineCond[0].replace(/^\t+/u, "");
    const head0 = positions.slice(0, -1).map((p) => pad + p);
    return `${fullName}(
${[...head0, inlineCond.join("\n")].join(",\n")})`;
  }
  const condText = hasBool ? reindentVtCondition(condition.trim(), base) : isCaseValueParam ? reindentLeafCase(condition.trim(), base) : reindentLeafSubquery(condition.trim(), base + 1);
  const condLines = condText.split("\n");
  condLines[0] = pad + condLines[0].replace(/^\t+/u, "");
  const head = positions.slice(0, -1).map((p) => pad + p);
  return `${fullName}(
${[...head, condLines.join("\n")].join(",\n")})`;
}
function renderAccountingParams(fullName, positions, _condition, bodyTabs) {
  positions = positions.map((p) => p ? normalizeLeafCase(p) : p);
  const base = bodyTabs + 2;
  const pad = "	".repeat(base);
  const renderPos = (p) => {
    if (!p) return pad;
    const hasBool = hasTopLevelBooleanOp(p);
    const text2 = hasBool ? reindentVtCondition(p.trim(), base) : p.includes("\n") && /\(ВЫБРАТЬ/u.test(p) ? reindentLeafSubquery(p.trim(), base + 1) : p.trim();
    const lines = text2.split("\n");
    lines[0] = pad + lines[0].replace(/^\t+/u, "");
    return lines.join("\n");
  };
  return `${fullName}(
${positions.map(renderPos).join(",\n")})`;
}
function splitTopLevelBoolConjuncts(expr) {
  const n = expr.length;
  const isWordChar = (c) => c !== void 0 && /[\p{L}\p{N}_]/u.test(c);
  const parts = [];
  let depth = 0, inStr = false, between = 0, start = 0, op2 = "", caseDepth = 0;
  for (let i = 0; i < n; i++) {
    const c = expr[i];
    if (inStr) {
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === "(") {
      depth++;
      continue;
    }
    if (c === ")") {
      depth--;
      continue;
    }
    if (depth !== 0) continue;
    if (!isWordChar(expr[i - 1])) {
      const up3 = expr.slice(i, i + 6).toUpperCase();
      if (up3.startsWith("\u0412\u042B\u0411\u041E\u0420") && !isWordChar(expr[i + 5])) {
        caseDepth++;
        continue;
      }
      if (up3.startsWith("\u041A\u041E\u041D\u0415\u0426") && !isWordChar(expr[i + 5])) {
        if (caseDepth > 0) caseDepth--;
        continue;
      }
      if (caseDepth > 0) continue;
      if (up3.startsWith("\u041C\u0415\u0416\u0414\u0423") && !isWordChar(expr[i + 5])) {
        between++;
        continue;
      }
      const isIli = up3.startsWith("\u0418\u041B\u0418") && !isWordChar(expr[i + 3]);
      const isI = expr[i].toUpperCase() === "\u0418" && !isWordChar(expr[i + 1]);
      if (isI && between > 0) {
        between--;
        continue;
      }
      if (isIli || isI) {
        parts.push({ op: op2, text: expr.slice(start, i).trim() });
        op2 = isIli ? "\u0418\u041B\u0418" : "\u0418";
        start = i + (isIli ? 3 : 1);
      }
    }
  }
  parts.push({ op: op2, text: expr.slice(start).trim() });
  return parts;
}
function bodyHasUnwrappedBoolOr(inner) {
  const secRe = /(?:^|[^\p{L}\p{N}_])(ГДЕ|ИМЕЮЩИЕ)(?![\p{L}\p{N}_])/gu;
  const nextSec = /(?:^|[^\p{L}\p{N}_])(?:СГРУППИРОВАТЬ|ИМЕЮЩИЕ|УПОРЯДОЧИТЬ|ИНДЕКСИРОВАТЬ|ОБЪЕДИНИТЬ|ИТОГИ|ГДЕ)(?![\p{L}\p{N}_])/u;
  const isW = (c) => c !== void 0 && /[\p{L}\p{N}_]/u.test(c);
  let m;
  while ((m = secRe.exec(inner)) !== null) {
    let seg = inner.slice(m.index + m[0].length);
    const nm = nextSec.exec(seg);
    if (nm) seg = seg.slice(0, nm.index);
    seg = seg.trim();
    if (!seg) continue;
    let depth = 0, inStr = false, topOr = false;
    for (let i = 0; i < seg.length; i++) {
      const ch = seg[i];
      if (inStr) {
        if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') {
        inStr = true;
        continue;
      }
      if (ch === "(") {
        depth++;
        continue;
      }
      if (ch === ")") {
        depth--;
        continue;
      }
      if (depth === 0 && (ch === "\u0418" || ch === "\u0438") && !isW(seg[i - 1]) && /^ИЛИ(?![\p{L}\p{N}_])/iu.test(seg.slice(i))) {
        topOr = true;
        break;
      }
    }
    if (!topOr) continue;
    return true;
  }
  return false;
}
function inlineSelectMembershipReflow(text2) {
  return reflowInlineMembershipSubquery(text2, 0, 2, "");
}
function reflowInlineMembershipSubquery(text2, ind, subBase, prefix) {
  const neMatch = /^((?:НЕ\s+)+)/iu.exec(text2);
  const neCount = neMatch ? (neMatch[1].match(/НЕ/giu) ?? []).length : 0;
  subBase += neCount;
  const n = text2.length;
  let depth = 0, inStr = false;
  const isWord2 = (c) => c !== void 0 && /[\p{L}\p{N}_]/u.test(c);
  for (let i = 0; i < n; i++) {
    const ch = text2[i];
    if (inStr) {
      if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') {
      inStr = true;
      continue;
    }
    if (ch === "(") {
      depth++;
      continue;
    }
    if (ch === ")") {
      depth--;
      continue;
    }
    if (depth !== 0) continue;
    if ((ch === "\u0412" || ch === "\u0432") && !isWord2(text2[i - 1]) && !isWord2(text2[i + 1])) {
      let j = i + 1;
      const restUp = text2.slice(j).replace(/^\s+/u, "").toUpperCase();
      let hier = "";
      if (restUp.startsWith("\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418") && !isWord2(restUp[8])) {
        hier = " \u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418";
        const m = /^\s+ИЕРАРХИИ/iu.exec(text2.slice(j));
        if (m) j += m[0].length;
      }
      while (j < n && /\s/u.test(text2[j])) j++;
      if (text2[j] !== "(") return null;
      const afterParen = text2.slice(j + 1).replace(/^\s+/u, "");
      if (!/^ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(afterParen)) return null;
      let d2 = 0, inS2 = false, close = -1;
      for (let k = j; k < n; k++) {
        const c2 = text2[k];
        if (inS2) {
          if (c2 === '"') inS2 = false;
          continue;
        }
        if (c2 === '"') {
          inS2 = true;
          continue;
        }
        if (c2 === "(") d2++;
        else if (c2 === ")") {
          d2--;
          if (d2 === 0) {
            close = k;
            break;
          }
        }
      }
      if (close < 0) return null;
      if (text2.slice(close + 1).trim() !== "") return null;
      const lhs = text2.slice(0, i).trim();
      const innerText = text2.slice(j + 1, close);
      const gluedJoin = /(?:^|[^\p{L}\p{N}_])\S[^\n]*?[ \t](?:ВНУТРЕННЕЕ|ЛЕВОЕ|ПРАВОЕ|ПОЛНОЕ)(?:[ \t]+ВНЕШНЕЕ)?[ \t]+СОЕДИНЕНИЕ(?:[^\p{L}\p{N}_]|$)/u.test(innerText);
      const isCanonical = innerText.includes("\n") && !/(?:^|[^\p{L}\p{N}_])ИЗ[ \t]+\S/u.test(innerText) && !gluedJoin;
      const hasNestedCaseValue = /(?:^|[^\p{L}\p{N}_])(?:ТОГДА|ИНАЧЕ)[ \t]+ВЫБОР[ \t]*(?:\r?\n|$)/u.test(innerText);
      if (isCanonical && !bodyHasUnwrappedBoolOr(innerText) && !hasNestedCaseValue) return null;
      let doc;
      try {
        doc = parseDocument(innerText);
      } catch {
        return null;
      }
      const block = renderConditionSubquery(doc, subBase).split("\n");
      const lhsFlat = lhs.replace(/[ \t\r\n]+/gu, " ").replace(/\(\s+/gu, "(").replace(/\s+\)/gu, ")").replace(/\s+,/gu, ",").trim();
      const head = "	".repeat(ind) + prefix + lhsFlat + " \u0412" + hier;
      return [head, ...block];
    }
  }
  return null;
}
function breakInlineParenGroup(text2) {
  const t = text2.trimStart();
  if (!t.startsWith("(")) return text2;
  if (/(?:^|[^\p{L}\p{N}_])(?:ВЫБРАТЬ|ВЫБОР)(?:[^\p{L}\p{N}_]|$)/u.test(t)) return text2;
  const lead = text2.slice(0, text2.length - t.length);
  let depth = 0;
  let inStr = false;
  let out = "";
  let changed = false;
  let betweenPending = 0;
  for (let i = 0; i < t.length; i++) {
    const ch = t[i];
    if (inStr) {
      out += ch;
      if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') {
      inStr = true;
      out += ch;
      continue;
    }
    if (ch === "(") {
      depth++;
      out += ch;
      continue;
    }
    if (ch === ")") {
      depth--;
      out += ch;
      continue;
    }
    if ((ch === "\u041C" || ch === "\u043C") && !/[\p{L}\p{N}_]/u.test(t[i - 1] ?? "")) {
      const mm = /^МЕЖДУ(?![\p{L}\p{N}_])/iu.exec(t.slice(i));
      if (mm) {
        betweenPending++;
        out += t.slice(i, i + mm[0].length);
        i += mm[0].length - 1;
        continue;
      }
    }
    if (depth === 1 && (ch === "\u0418" || ch === "\u0438")) {
      const prev = t[i - 1];
      const m = /^(И|ИЛИ)(?![\p{L}\p{N}_])/u.exec(t.slice(i));
      if (m && m[1] === "\u0418" && betweenPending > 0 && (prev === void 0 || !/[\p{L}\p{N}_]/u.test(prev))) {
        betweenPending--;
        out += m[1];
        i += m[1].length - 1;
        continue;
      }
      if (m && (prev === void 0 || !/[\p{L}\p{N}_]/u.test(prev))) {
        out = out.replace(/[ \t]+$/u, "") + "\n" + m[1] + " ";
        i += m[1].length;
        while (i + 1 < t.length && /[ \t]/u.test(t[i + 1])) i++;
        changed = true;
        continue;
      }
    }
    out += ch;
  }
  return changed ? lead + out : text2;
}
function reindentVtCondition(condition, base) {
  const conjuncts = splitTopLevelBoolConjuncts(condition);
  const hasAnyOr = conjuncts.some((c) => c.op === "\u0418\u041B\u0418");
  const out = [];
  conjuncts.forEach((c, k) => {
    const andUnderOr = c.op === "\u0418" && hasAnyOr;
    const ind = k === 0 ? base : andUnderOr ? base + 2 : base + 1;
    const prefix = k === 0 ? "" : `${c.op} `;
    if (c.text.includes("\n")) c = { ...c, text: flattenMultilineLeaf(c.text) };
    if (!c.text.includes("\n")) {
      const broken = breakInlineParenGroup(c.text);
      if (broken !== c.text) c = { ...c, text: broken };
    }
    const inlineReflow = /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(c.text) ? reflowInlineMembershipSubquery(c.text, ind, base + 2, prefix) : null;
    const conjunctIsCase = /^ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(c.text.trim());
    if (inlineReflow) {
      const isUKw = (s) => /^\t*ОБЪЕДИНИТЬ(?:\s+ВСЕ)?\s*$/u.test(s.trim());
      for (let q = 0; q < inlineReflow.length; q++) {
        if (inlineReflow[q].trim() !== "") continue;
        const adj = q > 0 && isUKw(inlineReflow[q - 1]) || q + 1 < inlineReflow.length && isUKw(inlineReflow[q + 1]);
        if (adj) inlineReflow[q] = "	".repeat(base);
      }
      out.push(...inlineReflow);
    } else if (!conjunctIsCase && c.text.includes("\n") && /\(\s*\n\s*ВЫБРАТЬ(?![\p{L}\p{N}_])|\(ВЫБРАТЬ/u.test(c.text)) {
      const r = reindentLeafSubquery(c.text, base + 2).split("\n");
      r[0] = "	".repeat(ind) + prefix + r[0].replace(/^\t+/u, "");
      const isUKw = (s) => /^\t*ОБЪЕДИНИТЬ(?:\s+ВСЕ)?\s*$/u.test(s);
      for (let q = 0; q < r.length; q++) {
        if (r[q].trim() !== "") continue;
        const adj = q > 0 && isUKw(r[q - 1]) || q + 1 < r.length && isUKw(r[q + 1]);
        if (adj) r[q] = "	".repeat(base);
      }
      out.push(...r);
    } else if (c.text.includes("\n") && /(?:^|[^\p{L}\p{N}_])ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(c.text)) {
      const caseBase = conjuncts.length === 1 ? base : base + 1;
      const r = reindentLeafCase(c.text, caseBase).split("\n");
      r[0] = "	".repeat(ind) + prefix + r[0].replace(/^\t+/u, "").replace(/\s+$/u, "");
      out.push(...r);
    } else if (c.text.includes("\n")) {
      const lines = c.text.split("\n");
      const parenDelta = (s) => {
        let d = 0;
        let inS = false;
        for (let p = 0; p < s.length; p++) {
          const ch = s[p];
          if (ch === '"') {
            inS = !inS;
            continue;
          }
          if (inS) continue;
          if (ch === "(") d++;
          else if (ch === ")") d--;
        }
        return d;
      };
      const firstWord = (s) => {
        const m = /^[\t ]*([\p{L}]+)/u.exec(s);
        return m ? m[1].toUpperCase() : "";
      };
      const orLevels = /* @__PURE__ */ new Set();
      let scanLvl = parenDelta(lines[0]);
      for (let j = 1; j < lines.length; j++) {
        if (lines[j].trim() === "") continue;
        const fw = firstWord(lines[j]);
        if (fw === "\u0418" || fw === "\u0418\u041B\u0418") {
          if (fw === "\u0418\u041B\u0418") orLevels.add(scanLvl);
          scanLvl += parenDelta(lines[j]);
        } else break;
      }
      out.push("	".repeat(ind) + prefix + lines[0].trim());
      const headDelta = parenDelta(lines[0]);
      let condParen = headDelta;
      for (let j = 1; j < lines.length; j++) {
        if (headDelta <= 0) {
          out.push("	".repeat(ind + 1) + lines[j].trim());
          continue;
        }
        const fw = firstWord(lines[j]);
        const orShift = fw === "\u0418" && orLevels.has(condParen) ? 1 : 0;
        out.push("	".repeat(ind + condParen + orShift) + lines[j].trim());
        condParen += parenDelta(lines[j]);
      }
    } else {
      const cText = stripNotFieldParens(stripNegatedFieldParens(c.text));
      out.push("	".repeat(ind) + prefix + cText);
    }
  });
  return out.join("\n");
}
function selectionModifiers(selection) {
  if (!selection) return "";
  let m = "";
  if (selection.allowed) m += " \u0420\u0410\u0417\u0420\u0415\u0428\u0415\u041D\u041D\u042B\u0415";
  if (selection.distinct) m += " \u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415";
  if (typeof selection.top === "number" && selection.top >= 0) m += ` \u041F\u0415\u0420\u0412\u042B\u0415 ${selection.top}`;
  return m;
}
function joinKeyword(leftAll, rightAll) {
  if (leftAll && rightAll) return "\u041F\u041E\u041B\u041D\u041E\u0415";
  if (leftAll && !rightAll) return "\u041B\u0415\u0412\u041E\u0415";
  if (!leftAll && rightAll) return "\u041F\u0420\u0410\u0412\u041E\u0415";
  return "\u0412\u041D\u0423\u0422\u0420\u0415\u041D\u041D\u0415\u0415";
}
function hasTopLevelBooleanOp(expr) {
  const n = expr.length;
  const isWordChar = (c) => c !== void 0 && /[\p{L}\p{N}_]/u.test(c);
  let depth = 0;
  let inStr = false;
  let betweenPending = 0;
  for (let i = 0; i < n; i++) {
    const c = expr[i];
    if (inStr) {
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === "(") {
      depth++;
      continue;
    }
    if (c === ")") {
      depth--;
      continue;
    }
    if (depth !== 0) continue;
    if (!isWordChar(expr[i - 1])) {
      const up3 = expr.slice(i, i + 6).toUpperCase();
      if (up3.startsWith("\u041C\u0415\u0416\u0414\u0423") && !isWordChar(expr[i + 5])) {
        betweenPending++;
        continue;
      }
      if (up3.startsWith("\u0418\u041B\u0418") && !isWordChar(expr[i + 3])) return true;
      if (expr[i].toUpperCase() === "\u0418" && !isWordChar(expr[i + 1])) {
        if (betweenPending > 0) {
          betweenPending--;
          continue;
        }
        return true;
      }
    }
  }
  return false;
}
function isPlainFieldComparison(expr) {
  const m = /^([\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*)\s*(?:<>|>=|<=|=|>|<)\s*([\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*)$/u.exec(expr.trim());
  if (!m) return false;
  const LIT = /* @__PURE__ */ new Set(["\u0418\u0421\u0422\u0418\u041D\u0410", "\u041B\u041E\u0416\u042C", "NULL", "\u041D\u0415\u041E\u041F\u0420\u0415\u0414\u0415\u041B\u0415\u041D\u041E"]);
  if (LIT.has(m[1].toUpperCase()) || LIT.has(m[2].toUpperCase())) return false;
  return true;
}
function renderArbitraryConjunct(expr, depth = 0, caseEndBase, fromAndSplit = false) {
  const flatExpr = flattenMultilineLeaf(expr.trim());
  const inlineConj = /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(flatExpr) ? reflowInlineMembershipSubquery(flatExpr, 0, 4 + depth, "") : null;
  if (inlineConj) {
    return appendIsNotNullTrailingSpace("(" + inlineConj.join("\n") + ")");
  }
  let body = reindentLeafSubquery(flatExpr, 4 + depth);
  if (caseEndBase !== void 0 && body.includes("\n")) {
    const bodyLines = body.split("\n");
    const firstLine = bodyLines[0];
    const secondLine = bodyLines.find((l, i) => i > 0 && l.trim() !== "") ?? "";
    const oneCase = (body.match(/(^|[^\p{L}\p{N}_])КОНЕЦ(?=[^\p{L}\p{N}_]|$)/gu) ?? []).length === 1;
    const opensCase = /(^|[^\p{L}\p{N}_])ВЫБОР\s*$/u.test(firstLine) || /[=<>]\s*$/u.test(firstLine) && /^[\t ]*ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(secondLine);
    if (oneCase && opensCase) {
      body = reindentLeafCase(body, caseEndBase);
    }
  }
  const norm = wrapBareCastOperand(normalizeLeafCase(stripLeadingNotOperandParens(body)));
  if (fromAndSplit && !norm.includes("\n") && isPlainFieldComparison(norm)) {
    return appendIsNotNullTrailingSpace(norm);
  }
  if (inConditionSubquery && !norm.includes("\n") && isPlainFieldComparison(norm)) {
    return appendIsNotNullTrailingSpace(norm);
  }
  return appendIsNotNullTrailingSpace(`(${norm})`);
}
function moveNotBeforeTuple(text2) {
  if (text2[0] !== "(") return text2;
  let depth = 0;
  let inStr = false;
  let close = -1;
  for (let i = 0; i < text2.length; i++) {
    const c = text2[i];
    if (inStr) {
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === "(") depth++;
    else if (c === ")") {
      depth--;
      if (depth === 0) {
        close = i;
        break;
      }
    }
  }
  if (close < 0) return text2;
  const tuple = text2.slice(0, close + 1);
  if (!hasTopLevelComma(text2.slice(1, close))) return text2;
  const rest = text2.slice(close + 1);
  const m = /^\s+НЕ\s+(В)(\s+ИЕРАРХИИ)?(?![\p{L}\p{N}_])/u.exec(rest);
  if (!m) return text2;
  const tail = rest.slice(m[0].length);
  return `\u041D\u0415 ${tuple} \u0412${m[2] ?? ""}${tail}`;
}
function hasTopLevelComma(text2) {
  let depth = 0;
  let inStr = false;
  for (let i = 0; i < text2.length; i++) {
    const c = text2[i];
    if (inStr) {
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === "(") depth++;
    else if (c === ")") depth--;
    else if (c === "," && depth === 0) return true;
  }
  return false;
}
function stripLeadingNotOperandParens(text2) {
  if (text2.includes("\n")) return text2;
  const m = /^НЕ\s*\(/iu.exec(text2);
  if (!m) return text2;
  const open = m[0].length - 1;
  let depth = 0;
  let inStr = false;
  for (let i = open; i < text2.length; i++) {
    const c = text2[i];
    if (inStr) {
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === "(") depth++;
    else if (c === ")") {
      depth--;
      if (depth === 0) {
        if (i !== text2.length - 1) return text2;
        const inner = text2.slice(open + 1, i).trim();
        if (hasTopLevelComma(inner) || hasTopLevelBooleanOp(inner)) return text2;
        return `\u041D\u0415 ${inner}`;
      }
    }
  }
  return text2;
}
function renderJoinConjuncts(conditions, aliases, depth = 0, poOwnLine = false, joinParenthesized = true) {
  const lines = [];
  const cont = poOwnLine ? 4 + depth : 3 + depth;
  const expanded = expandAndChainConjuncts(conditions);
  expanded.forEach((c, k) => {
    let sub;
    if (!c.custom) {
      const la = aliases.get(c.leftTableId ?? "") ?? c.leftTableId ?? "";
      const ra = aliases.get(c.rightTableId ?? "") ?? c.rightTableId ?? "";
      const op2 = c.operator ?? "=";
      sub = [`${la}.${c.leftPath ?? ""} ${op2} ${ra}.${c.rightPath ?? ""}`];
    } else if (conjunctNeedsComplexFormat(c)) {
      sub = formatJoinConjunct((c.expression ?? "").trim(), k === 0, 2 + depth).split("\n");
    } else {
      const caseBase = k > 0 ? cont : poOwnLine ? 4 + depth : 3 + depth;
      const standaloneUnwrap = expanded.length === 1 && !joinParenthesized;
      sub = [renderArbitraryConjunct(c.expression ?? "", depth, caseBase, !!c.__fromAndSplit || standaloneUnwrap)];
    }
    if (k > 0) sub[0] = `${"	".repeat(cont)}\u0418 ${sub[0]}`;
    else if (poOwnLine) sub[0] = `${"	".repeat(3 + depth)}${sub[0]}`;
    lines.push(...sub);
  });
  return lines.join("\n");
}
function splitTopLevelAnd(expr) {
  const n = expr.length;
  const isWordChar = (c) => c !== void 0 && /[\p{L}\p{N}_]/u.test(c);
  const parts = [];
  let depth = 0;
  let inStr = false;
  let betweenPending = 0;
  let start = 0;
  for (let i = 0; i < n; i++) {
    const c = expr[i];
    if (inStr) {
      if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === "(") {
      depth++;
      continue;
    }
    if (c === ")") {
      depth--;
      continue;
    }
    if (depth !== 0) continue;
    if (!isWordChar(expr[i - 1])) {
      const up3 = expr.slice(i, i + 5).toUpperCase();
      if (up3.startsWith("\u041C\u0415\u0416\u0414\u0423") && !isWordChar(expr[i + 5])) {
        betweenPending++;
        continue;
      }
      if (expr[i].toUpperCase() === "\u0418" && !isWordChar(expr[i + 1])) {
        if (betweenPending > 0) {
          betweenPending--;
          continue;
        }
        parts.push(expr.slice(start, i).trim());
        start = i + 1;
      }
    }
  }
  parts.push(expr.slice(start).trim());
  return parts;
}
function stripOneEnclosingParen(expr) {
  const e = expr.trim();
  if (!(e.startsWith("(") && e.endsWith(")"))) return e;
  let depth = 0;
  for (let i = 0; i < e.length; i++) {
    if (e[i] === "(") depth++;
    else if (e[i] === ")") {
      depth--;
      if (depth === 0 && i !== e.length - 1) return e;
    }
  }
  return e.slice(1, -1).trim();
}
function expandAndChainConjuncts(conditions) {
  const out = [];
  for (const c of conditions) {
    const e = (c.expression ?? "").trim();
    if (c.custom && e && hasTopLevelBooleanOp(e) && !/(^|[^\p{L}\p{N}_])(ИЛИ|ВЫБОР)([^\p{L}\p{N}_]|$)/iu.test(e)) {
      const parts = splitTopLevelAnd(e);
      if (parts.length > 1) {
        for (const p of parts) out.push({ custom: true, expression: stripOneEnclosingParen(p), __fromAndSplit: true });
        continue;
      }
    }
    out.push(c);
  }
  return out;
}
function conjunctNeedsComplexFormat(c) {
  if (!c.custom) return false;
  const e = (c.expression ?? "").trim();
  return hasTopLevelBooleanOp(e) || needsFormatting(e);
}
function renderJoinCondition(join, aliases, depth = 0, poOwnLine = false) {
  if (join.conditions && join.conditions.length > 0) {
    return renderJoinConjuncts(join.conditions, aliases, depth, poOwnLine, join.parenthesized ?? true);
  }
  if (join.custom) {
    const expr = (join.expression ?? "").trim();
    if (!expr) return "";
    if (hasTopLevelBooleanOp(expr)) return formatExpression(expr, "join");
    if (needsFormatting(expr)) return formatExpression(expr, "join");
    const leaf = normalizeLeafCase(expr);
    const wrap = join.parenthesized || !isPlainFieldComparison(expr);
    const body = wrap ? `(${leaf})` : leaf;
    return poOwnLine ? `${"	".repeat(3 + depth)}${body}` : body;
  }
  const leftAlias = aliases.get(join.leftTableId) ?? join.leftTableId;
  const rightAlias = aliases.get(join.rightTableId) ?? join.rightTableId;
  const op2 = join.operator ?? "=";
  const simple = `${leftAlias}.${join.leftPath ?? ""} ${op2} ${rightAlias}.${join.rightPath ?? ""}`;
  return poOwnLine ? `${"	".repeat(3 + depth)}${simple}` : simple;
}
function renderFrom(model, aliases) {
  const sourceLine = (t, bodyTabs = 1) => {
    if (inConditionSubquery && t.aliasSynthesized && !t.subquery) {
      return renderSource(t, bodyTabs);
    }
    return `${renderSource(t, bodyTabs)} \u041A\u0410\u041A ${aliases.get(t.id) ?? t.id}`;
  };
  const joins = model.joins ?? [];
  if (joins.length === 0) {
    return model.tables.map((t, i) => {
      const comma = i < model.tables.length - 1 ? "," : "";
      return `	${sourceLine(t)}${comma}`;
    });
  }
  const byId = new Map(model.tables.map((t) => [t.id, t]));
  const inChain = /* @__PURE__ */ new Set();
  const chainLines = /* @__PURE__ */ new Map();
  let currentSeedId = "";
  const lines = [];
  const push = (line) => {
    (chainLines.get(currentSeedId) ?? lines).push(line);
  };
  const pendingPo = [];
  const flushPo = (toDepth) => {
    while (pendingPo.length > 0 && pendingPo[pendingPo.length - 1].depth >= toDepth) {
      const p = pendingPo.pop();
      const poOwnLine = inConditionSubquery;
      const cond = renderJoinCondition(p.join, aliases, p.depth, poOwnLine);
      if (!cond) continue;
      const close = optionalBlockEnd.has(p.join) ? "}" : "";
      if (poOwnLine) {
        push(`		${"	".repeat(p.depth)}\u041F\u041E`);
        push(`${cond}${close}`);
      } else {
        push(`		${"	".repeat(p.depth)}\u041F\u041E ${cond}${close}`);
      }
    }
  };
  const optionalBlockStart = /* @__PURE__ */ new Set();
  const optionalBlockEnd = /* @__PURE__ */ new Set();
  {
    let prevWasOpenBlock = false;
    joins.forEach((j, i) => {
      if (!j.optional) {
        prevWasOpenBlock = false;
        return;
      }
      if (!prevWasOpenBlock) optionalBlockStart.add(j);
      const next = joins[i + 1];
      const isLast = j.optionalLast === true || j.optionalLast === void 0 && (!next || !next.optional);
      if (isLast) {
        optionalBlockEnd.add(j);
        prevWasOpenBlock = false;
      } else prevWasOpenBlock = true;
    });
  }
  joins.forEach((join, idx) => {
    const seedId = join.seedTableId ?? join.leftTableId;
    const joinedId = join.joinedTableId ?? join.rightTableId;
    const depth = join.depth ?? 0;
    const keyword = joinKeyword(join.leftAll, join.rightAll);
    const seed = byId.get(seedId);
    const joined = byId.get(joinedId);
    if (!seed || !joined) return;
    flushPo(depth);
    if (idx === 0 || depth === 0 && !inChain.has(seedId)) {
      currentSeedId = seedId;
      chainLines.set(seedId, []);
      push(`	${sourceLine(seed)}`);
      inChain.add(seedId);
    }
    inChain.add(seedId);
    const open = optionalBlockStart.has(join) ? "{" : "";
    push(`		${"	".repeat(depth)}${open}${keyword} \u0421\u041E\u0415\u0414\u0418\u041D\u0415\u041D\u0418\u0415 ${sourceLine(joined, 2 + depth)}`);
    inChain.add(joinedId);
    pendingPo.push({ join, depth });
  });
  flushPo(0);
  const entries = [];
  for (const t of model.tables) {
    if (chainLines.has(t.id)) entries.push(chainLines.get(t.id));
    else if (!inChain.has(t.id)) entries.push([`	${sourceLine(t)}`]);
  }
  const out = [];
  entries.forEach((entry, i) => {
    if (entry.length === 0) return;
    if (i < entries.length - 1) entry[entry.length - 1] += ",";
    out.push(...entry);
  });
  return out;
}
function builderBlock(keyword, fields) {
  if (fields.length === 0) return [];
  const render = (f) => {
    const isMultilineCase = f.condition && f.ref.includes("\n") && /(^|[^\p{L}\p{N}_])ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(f.ref);
    const isMultilineBool = !isMultilineCase && f.condition && f.ref.includes("\n") && hasTopLevelBooleanOp(f.ref) && !/(?:^|[^\p{L}\p{N}_])(?:ВЫБОР|ВЫБРАТЬ)(?:[^\p{L}\p{N}_]|$)/u.test(f.ref) && // Группа `НЕ(…)` несёт лишний +1 (НЕ — отдельный уровень), который reindentLeafBool
    // НЕ учитывает; такие условия не реиндентируем (оставляем геометрию как есть).
    !/(?:^|[^\p{L}\p{N}_])НЕ\s*\(/u.test(f.ref);
    const ref = isMultilineCase ? reindentLeafCase(normalizeLeafCase(f.ref), 2) : isMultilineBool ? reindentLeafBool(normalizeLeafCase(f.ref), 2) : normalizeLeafCase(f.ref);
    return f.condition ? `(${ref})` + (f.child ? ".*" : "") + (f.alias ? " \u041A\u0410\u041A " + f.alias : "") : ref + (f.child ? ".*" : "") + (f.alias ? " \u041A\u0410\u041A " + f.alias : "");
  };
  const lines = ["{" + keyword];
  fields.forEach((f, i) => {
    const last = i === fields.length - 1;
    lines.push("	" + render(f) + (last ? "}" : ","));
  });
  return lines;
}
function reflowCharacteristics(text2) {
  if (!text2.includes("\n")) return text2;
  const lines = text2.split("\n");
  const out = [];
  const endsWithBinaryOp = (s) => {
    const t = s.replace(/\s+$/u, "");
    if (!/[+\-*/]$/u.test(t)) return false;
    if (/\.\*$/u.test(t)) return false;
    let inStr = false;
    for (let i = 0; i < t.length; i++) {
      if (t[i] === '"') inStr = !inStr;
    }
    return !inStr;
  };
  for (const line of lines) {
    if (out.length > 0 && line.trim() !== "" && endsWithBinaryOp(out[out.length - 1])) {
      out[out.length - 1] = out[out.length - 1].replace(/\s+$/u, "") + " " + line.replace(/^[\t ]+/u, "");
    } else {
      out.push(line);
    }
  }
  if (out.length > 0) {
    out[out.length - 1] = out[out.length - 1].replace(/([^\s{])\}$/u, "$1 }");
  }
  return out.join("\n");
}
function buildQueryBlock(model, fieldLines, aliases) {
  const linesBase = fieldLines.map((l, i) => {
    const withComma = i < fieldLines.length - 1 ? l + "," : l;
    const trailing = i < model.fields.length ? model.fields[i]?.commentTrailing : void 0;
    return trailing ? withComma + " " + trailing : withComma;
  });
  const lines = [];
  for (let i = 0; i < linesBase.length; i++) {
    const leading = i < model.fields.length ? model.fields[i]?.commentLeading : void 0;
    if (leading?.length) lines.push(...leading);
    lines.push(linesBase[i]);
  }
  const hasFrom = model.tables.length > 0;
  const fromLines = hasFrom ? ["\u0418\u0417", ...model.comments?.afterFrom ?? [], ...renderFrom(model, aliases)] : [];
  const conditionLines = renderConditions(model.conditions, aliases);
  const sectionSep = inConditionSubquery ? [] : [""];
  const groupingInner = renderGrouping(model.grouping, aliases, model);
  const groupingLines = groupingInner.length ? [...sectionSep, ...groupingInner] : [];
  const havingLines = renderHaving(model.having, aliases);
  const placeLines = model.queryType === "createTemp" && model.tempTableName ? ["\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C " + model.tempTableName] : model.queryType === "appendTemp" && model.tempTableName ? ["\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C " + model.tempTableName] : [];
  const lockLines = model.lockForUpdate?.length || model.lockForUpdateBare ? ["", "\u0414\u041B\u042F \u0418\u0417\u041C\u0415\u041D\u0415\u041D\u0418\u042F", ...(model.lockForUpdate ?? []).map((name) => "	" + name)] : [];
  const builderSelect = builderBlock("\u0412\u042B\u0411\u0420\u0410\u0422\u042C", model.builder?.fields ?? []);
  const builderWhere = builderBlock("\u0413\u0414\u0415", model.builder?.conditions ?? []);
  const builderOrder = builderBlock("\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C \u041F\u041E", model.builder?.order ?? []);
  const builderTotals = builderBlock("\u0418\u0422\u041E\u0413\u0418 \u041F\u041E", model.builder?.totals ?? []);
  return [
    // Вид 3 (beforeSelect) — строки перед `ВЫБРАТЬ`, нулевой отступ.
    ...model.comments?.beforeSelect ?? [],
    "\u0412\u042B\u0411\u0420\u0410\u0422\u042C" + selectionModifiers(model.selection),
    ...lines,
    // {ВЫБРАТЬ …} конструктор печатает ПОСЛЕ ПОМЕСТИТЬ/ДОБАВИТЬ (если те есть),
    // перед ИЗ; без ПОМЕСТИТЬ placeLines пуст и блок идёт сразу за списком полей.
    ...placeLines,
    ...builderSelect,
    ...fromLines,
    ...conditionLines,
    ...builderWhere,
    ...groupingLines,
    ...havingLines,
    ...builderOrder,
    ...builderTotals,
    ...lockLines,
    // Блок характеристик СКД `{ХАРАКТЕРИСТИКИ … }` — почти дословно (байт-в-байт),
    // последним; единственная нормализация — склейка арифметики/конкатенации поля
    // подзапроса, разнесённой разработчиком по строкам (оракул печатает её одной строкой).
    ...model.characteristics ? reflowCharacteristics(model.characteristics).split("\n") : []
  ].join("\n");
}
var BARE_PARAM = /^&([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)$/u;
function isBareParamExpr(expression) {
  return expression !== void 0 && BARE_PARAM.test(expression.trim());
}
var CONST_GROUP_RE = /^("(?:[^"]|"")*"|\d+(?:\.\d+)?|ИСТИНА|ЛОЖЬ|НЕОПРЕДЕЛЕНО|(?:ЗНАЧЕНИЕ|ТИП|ДАТАВРЕМЯ)\s*\([^()]*\))$/iu;
function isConstGroupExpr(expression) {
  if (expression === void 0) return false;
  const e = expression.trim();
  return isBareParamExpr(e) || CONST_GROUP_RE.test(e);
}
function isTabularSectionSource(t) {
  if (!t || t.subquery || t.virtual) return false;
  return t.fullName.split(".").length >= 3;
}
function qualifiedAutoAlias(path, tabularSource) {
  let segs = path.split(".");
  if (tabularSource && segs.length > 1 && segs[0].toUpperCase() === "\u0421\u0421\u042B\u041B\u041A\u0410") {
    segs = segs.slice(1);
  }
  return segs.join("");
}
function synthesizedFieldAlias(model, field) {
  if (field.qualified) {
    if (field.autoAliasDotted) return field.path;
    const t = model.tables.find((tb) => tb.id === field.tableId);
    return qualifiedAutoAlias(field.path, isTabularSectionSource(t));
  }
  return field.path.split(".").pop() ?? field.path;
}
function renderTabProjection(model, tsf, aliases, opts) {
  const tableAlias = aliases.get(tsf.tableId) ?? tsf.tableId;
  const deepPath = tsf.tsName.includes(".");
  const autoColAlias = (alias, fieldName, pos, wasExplicit) => {
    if (alias !== void 0) return alias;
    if (deepPath && !wasExplicit) return `\u041F\u043E\u043B\u0435${pos + 1}`;
    return fieldName.replace(/\./g, "");
  };
  const tsExprLines = (expression, alias, comma) => {
    const rows = formatSelectExpression(expression).split("\n");
    const shifted = rows.map((l, j) => j === 0 ? "		" + l : "	" + l);
    const tail = !opts.suppress && alias !== void 0 ? " \u041A\u0410\u041A " + alias : "";
    shifted[shifted.length - 1] = shifted[shifted.length - 1] + tail + comma;
    return shifted;
  };
  let subLines;
  if (tsf.columns && tsf.columns.length > 0) {
    subLines = tsf.columns.flatMap((c, i) => {
      const comma = i < tsf.columns.length - 1 ? "," : "";
      if (c.kind === "field") {
        const tail = opts.suppress ? "" : ` \u041A\u0410\u041A ${autoColAlias(c.alias, c.field, i, c.aliasExplicit === true)}`;
        return [`		${normalizeLeafCase(c.field)}${tail}${comma}`];
      }
      return tsExprLines(c.expression, c.alias, comma);
    });
  } else if (tsf.exprFields && tsf.exprFields.length > 0) {
    subLines = tsf.exprFields.flatMap((ef, i) => {
      const rows = formatSelectExpression(ef.expression).split("\n");
      const shifted = rows.map((l, j) => j === 0 ? "		" + l : "	" + l);
      const comma = i < tsf.exprFields.length - 1 ? "," : "";
      const tail = opts.suppress ? "" : " \u041A\u0410\u041A " + ef.alias;
      shifted[shifted.length - 1] = shifted[shifted.length - 1] + tail + comma;
      return shifted;
    });
  } else {
    subLines = tsf.fields.map((f, i) => {
      const tail = opts.suppress ? "" : ` \u041A\u0410\u041A ${autoColAlias(tsf.fieldAliases?.[i], f, i, tsf.fieldAliasExplicit?.[i] === true)}`;
      return `		${normalizeLeafCase(f)}${tail}${i < tsf.fields.length - 1 ? "," : ""}`;
    });
  }
  const head = tsf.castPrefix !== void 0 ? tsf.castPrefix : tableAlias;
  const body = `	${head}.${tsf.tsName}.(
${subLines.join("\n")}
	)`;
  if (opts.suppress) return body;
  const tsAlias = opts.outerAlias ? opts.outerAlias(tsf.tsName, tsf.alias) : tsf.alias ?? tsf.tsName;
  return `${body} \u041A\u0410\u041A ${tsAlias}`;
}
function exprAutoAlias(expression, next) {
  const m = BARE_PARAM.exec(expression.trim());
  if (m) return m[1];
  const repr = representationAutoAlias(expression);
  return repr ?? next();
}
function representationAutoAlias(expression) {
  const m = /^(?:ПРЕДСТАВЛЕНИЕ|ПРЕДСТАВЛЕНИЕССЫЛКИ)\s*\(\s*([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_.]*)\s*\)$/iu.exec(expression.trim());
  if (!m) return void 0;
  const lastSeg = m[1].split(".").pop();
  return lastSeg ? `${lastSeg}\u041F\u0440\u0435\u0434\u0441\u0442\u0430\u0432\u043B\u0435\u043D\u0438\u0435` : void 0;
}
function buildFieldLines(model, aliases) {
  const aggregates = model.grouping?.aggregates ?? [];
  const fieldsCarryFunc = model.fields.some((f) => f.func !== void 0) || (model.trailingFields ?? []).some((f) => f.func !== void 0);
  const aggregateFunc = (tableId, path) => fieldsCarryFunc ? void 0 : aggregates.find((a) => a.tableId === tableId && a.path === path)?.func;
  let exprCounter = 0;
  const usedAliases = /* @__PURE__ */ new Set();
  const uniqueAlias = (alias) => {
    if (!usedAliases.has(alias)) {
      usedAliases.add(alias);
      return alias;
    }
    let k = 1;
    while (usedAliases.has(`${alias}${k}`)) k++;
    const out = `${alias}${k}`;
    usedAliases.add(out);
    return out;
  };
  const fieldLine = (f) => {
    if (f.expression) {
      if (suppressAutoAlias && (f.alias === void 0 || /^Поле\d+$/u.test(f.alias))) {
        if (f.exprAliasExplicit) {
          return `	${formatSelectExpression(f.expression)} \u041A\u0410\u041A ${f.exprAliasExplicit}`;
        }
        return `	${formatSelectExpression(f.expression)}`;
      }
      const autoExpr = f.alias === void 0 || /^Поле\d+$/u.test(f.alias);
      const repr = autoExpr ? representationAutoAlias(f.expression) : void 0;
      const alias = repr ?? f.alias ?? exprAutoAlias(f.expression, () => `\u041F\u043E\u043B\u0435${++exprCounter}`);
      usedAliases.add(alias);
      return `	${formatSelectExpression(f.expression)} \u041A\u0410\u041A ${alias}`;
    }
    const tableAlias = aliases.get(f.tableId) ?? f.tableId;
    const func = f.func ?? aggregateFunc(f.tableId, f.path);
    const lhs = func ? wrapAggregate(func, `${tableAlias}.${f.path}`) : `${tableAlias}.${f.path}`;
    let autoAlias;
    if (!suppressAutoAlias) {
      if (!func) {
        autoAlias = synthesizedFieldAlias(model, f);
      } else if (f.func !== void 0 && f.funcOperandQualified) {
        const tbl = model.tables.find((tb) => tb.id === f.tableId);
        autoAlias = qualifiedAutoAlias(f.path, isTabularSectionSource(tbl));
      }
    }
    let effAlias = f.alias ?? autoAlias;
    if (effAlias !== void 0) {
      effAlias = f.alias !== void 0 ? (usedAliases.add(f.alias), f.alias) : uniqueAlias(effAlias);
    }
    return effAlias ? `	${lhs} \u041A\u0410\u041A ${effAlias}` : `	${lhs}`;
  };
  const tsLine = (tsf) => renderTabProjection(model, tsf, aliases, {
    suppress: false,
    // Дедупликация псевдонима всей ТЧ (как раньше): явный — как есть, авто — через
    // наименьший целый суффикс при коллизии.
    outerAlias: (name, explicit) => explicit !== void 0 ? (usedAliases.add(explicit), explicit) : uniqueAlias(name)
  });
  const headLines = model.fields.map(fieldLine);
  const rest = [];
  let seq = 0;
  for (const tsf of model.tabSectionFields ?? []) {
    rest.push({ order: tsf.selectOrder, seq: seq++, render: () => tsLine(tsf) });
  }
  for (const f of model.trailingFields ?? []) {
    rest.push({ order: f.selectOrder, seq: seq++, render: () => fieldLine(f) });
  }
  if (rest.every((it) => it.order !== void 0)) {
    rest.sort((a, b) => a.order - b.order || a.seq - b.seq);
  }
  return [...headLines, ...rest.map((it) => it.render())];
}
function indentStringLiteralNewlines(text2, tabs2) {
  if (tabs2 <= 0 || !text2.includes("\n") || !text2.includes('"')) return text2;
  const pad = "	".repeat(tabs2);
  let out = "";
  let inStr = false;
  for (let i = 0; i < text2.length; i++) {
    const ch = text2[i];
    if (ch === '"') {
      if (inStr && text2[i + 1] === '"') {
        out += '""';
        i++;
        continue;
      }
      inStr = !inStr;
      out += ch;
      continue;
    }
    if (ch === "\n" && inStr) {
      out += "\n" + pad;
      continue;
    }
    out += ch;
  }
  return out;
}
function formatSelectExpression(expression) {
  if (!needsFormatting(expression) && !selectColumnNeedsBoolWrap(expression) && /(?:^|[^\p{L}\p{N}_])В(?:\s+ИЕРАРХИИ)?\s*\(\s*ВЫБРАТЬ(?![\p{L}\p{N}_])/iu.test(expression.trim())) {
    const reflowed = inlineSelectMembershipReflow(expression.trim());
    if (reflowed) return appendIsNotNullTrailingSpace(reflowed.join("\n"));
  }
  return needsFormatting(expression) || selectColumnNeedsBoolWrap(expression) ? formatExpression(expression.trim(), "select") : indentStringLiteralNewlines(appendIsNotNullTrailingSpace(normalizeLeafCase(reprintLeafArithmetic(reindentLeafBool(reindentLeafCase(reindentLeafSubquery(stripRedundantLeafParens(flattenMultilineLeaf(expression)), 2), 1, true), 1)))), 1);
}
function fieldExpr(model, field) {
  if (field.expression) return formatSelectExpression(field.expression);
  const aliases = resolveAliases(model.tables);
  const tableAlias = aliases.get(field.tableId) ?? field.tableId;
  const fieldsCarryFunc = model.fields.some((f) => f.func !== void 0) || (model.trailingFields ?? []).some((f) => f.func !== void 0);
  const func = field.func ?? (fieldsCarryFunc ? void 0 : (model.grouping?.aggregates ?? []).find(
    (a) => a.tableId === field.tableId && a.path === field.path
  )?.func);
  const lhs = `${tableAlias}.${field.path}`;
  return func ? wrapAggregate(func, lhs) : lhs;
}
function selectAliasFor(model, tableId, path) {
  const match = model.fields.find((f) => f.tableId === tableId && f.path === path);
  if (match?.alias) return match.alias;
  return path.split(".").pop() ?? path;
}
function sectionFieldRefText(model, tableAliases, tableId, path, selectAlias) {
  if (selectAlias !== void 0) return selectAlias;
  const match = model.fields.find((f) => f.tableId === tableId && f.path === path);
  if (match) return match.alias ?? (path.split(".").pop() ?? path);
  const alias = tableAliases.get(tableId);
  return alias !== void 0 ? `${alias}.${path}` : path.split(".").pop() ?? path;
}
function renderOrder(order, model, includeAuto = true) {
  if (!order) return [];
  const lines = [];
  if (order.fields.length > 0) {
    const tableAliases = resolveAliases(model.tables);
    lines.push("\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C \u041F\u041E");
    order.fields.forEach((f, i) => {
      const ref = f.expression ? f.expression.trim().startsWith("&") ? f.expression : formatSelectExpression(f.expression) : f.selectAlias !== void 0 ? f.selectAlias : f.qualified ? `${tableAliases.get(f.tableId) ?? f.tableId}.${f.path}` : sectionFieldRefText(model, tableAliases, f.tableId, f.path);
      const lastSeg = f.path.split(".").pop();
      const ownerTable = model.tables.find((t) => t.id === f.tableId);
      const resolvable = ownerTable !== void 0 && ownerTable.subquery === void 0;
      const paramTable = ownerTable !== void 0 && ownerTable.fullName.startsWith("&");
      const metadataTable = resolvable && !paramTable && ownerTable.fullName.includes(".");
      const tempTable = resolvable && !paramTable && !ownerTable.fullName.includes(".");
      const hierKeep = (
        // Резолвимый источник, адресованный псевдонимом выборки (не &параметр): KEEP.
        resolvable && !paramTable && f.selectAlias !== void 0 || // Временная таблица (схемы нет): KEEP.
        tempTable || // Квалифицированная ссылка на метаданные: KEEP лишь для иерарх./`…Ссылка`.
        metadataTable && (ownerTable.hierarchical || lastSeg === "\u0421\u0441\u044B\u043B\u043A\u0430")
      );
      const hierSuffix = f.hierarchy && hierKeep ? " \u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F" : "";
      const suffix = (f.direction === "desc" ? " \u0423\u0411\u042B\u0412" : "") + hierSuffix;
      const comma = i < order.fields.length - 1 ? "," : "";
      lines.push(`	${ref}${suffix}${comma}`);
    });
  }
  if (order.auto && includeAuto) lines.push("\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415");
  return lines;
}
function totalKindSuffix(kind) {
  switch (kind) {
    case "elements":
      return "";
    case "hierarchy":
      return " \u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F";
    case "onlyHierarchy":
      return " \u0422\u041E\u041B\u042C\u041A\u041E \u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F";
  }
}
function renderTotals(totals, model) {
  if (!totals) return [];
  const active = totals.groupFields.length > 0 || totals.grand;
  if (!active) return [];
  const tableAliases = resolveAliases(model.tables);
  const byList = [];
  if (totals.grand) byList.push("\u041E\u0411\u0429\u0418\u0415");
  for (const g of totals.groupFields) {
    const qualifiedSelectMatches = g.qualified && !g.expression ? model.fields.filter((f) => f.tableId === g.tableId && f.path === g.path && f.alias) : [];
    const alias = g.expression ? g.expression : g.selectAlias !== void 0 ? g.selectAlias : qualifiedSelectMatches.length === 1 ? qualifiedSelectMatches[0].alias : g.qualified ? `${tableAliases.get(g.tableId) ?? g.tableId}.${g.path}` : sectionFieldRefText(model, tableAliases, g.tableId, g.path);
    const as = g.alias ? ` \u041A\u0410\u041A ${g.alias}` : "";
    const period = g.periodBy ? ` ${g.periodBy}` : "";
    const ownerTable = model.tables.find((t) => t.id === g.tableId);
    const paramTable = ownerTable !== void 0 && ownerTable.fullName.startsWith("&");
    const kind = paramTable ? "elements" : g.kind;
    byList.push(`${alias}${period}${totalKindSuffix(kind)}${as}`);
  }
  const selectPosByAlias = /* @__PURE__ */ new Map();
  orderedSelectElements(model).forEach((el, i) => {
    const a = elementAlias(el, model).toUpperCase();
    if (a !== "" && !selectPosByAlias.has(a)) selectPosByAlias.set(a, i);
  });
  const renderAgg = (f) => {
    if (f.func && f.operandAlias !== void 0) return wrapAggregate(f.func, f.operandAlias);
    if (f.expression === void 0) return `\u0421\u0423\u041C\u041C\u0410(${selectAliasFor(model, f.tableId, f.path)})`;
    if (f.expression.includes("\n") && /(?:^|[^\p{L}\p{N}_])ВЫБОР(?:[^\p{L}\p{N}_]|$)/u.test(f.expression)) {
      return reindentLeafCase(normalizeLeafCase(f.expression), 1).replace(/^\t+/u, "");
    }
    return normalizeLeafCase(f.expression);
  };
  const NOPOS = Number.MAX_SAFE_INTEGER;
  const posOf = (f) => {
    const key = f.operandAlias ?? f.sortAlias;
    if (key === void 0) return NOPOS;
    const pos = selectPosByAlias.get(key.toUpperCase());
    return pos === void 0 ? NOPOS : pos;
  };
  const ordered = totals.totalFields.map((f, seq) => ({ f, seq, pos: posOf(f) })).sort((a, b) => a.pos - b.pos || a.seq - b.seq);
  const aggList = ordered.map((o) => renderAgg(o.f));
  const withCommas = (items) => items.map((s, i) => `	${s}${i < items.length - 1 ? "," : ""}`);
  if (aggList.length > 0) {
    return ["\u0418\u0422\u041E\u0413\u0418", ...withCommas(aggList), "\u041F\u041E", ...withCommas(byList)];
  }
  return ["\u0418\u0422\u041E\u0413\u0418 \u041F\u041E", ...withCommas(byList)];
}
function renderIndex(indexing, model) {
  if (!indexing || model.queryType !== "createTemp") return [];
  const indexes = indexing.indexes.filter((ix) => ix.fields.length > 0);
  if (indexes.length === 0) return [];
  const tableAliases = resolveAliases(model.tables);
  const aliasOf = (f) => f.expression ? f.expression : f.qualified ? `${tableAliases.get(f.tableId) ?? f.tableId}.${f.path}` : sectionFieldRefText(model, tableAliases, f.tableId, f.path, f.selectAlias);
  if (indexes.length === 1) {
    const fields = indexes[0].fields;
    const lines = fields.map((f, i) => {
      const comma = i < fields.length - 1 ? "," : "";
      return `	${aliasOf(f)}${comma}`;
    });
    return ["\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C \u041F\u041E", ...lines];
  }
  const setLines = [];
  indexes.forEach((ix, idx) => {
    const setComma = idx < indexes.length - 1 ? "," : "";
    const uniq = ix.unique ? " \u0423\u041D\u0418\u041A\u0410\u041B\u042C\u041D\u041E" : "";
    const fields = ix.fields;
    if (fields.length === 1) {
      setLines.push(`	(${aliasOf(fields[0])})${uniq}${setComma}`);
      return;
    }
    fields.forEach((f, i) => {
      const alias = aliasOf(f);
      if (i === 0) setLines.push(`	(${alias},`);
      else if (i < fields.length - 1) setLines.push(`	${alias},`);
      else setLines.push(`	${alias})${uniq}${setComma}`);
    });
  });
  return ["\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C \u041F\u041E \u041D\u0410\u0411\u041E\u0420\u0410\u041C", "(", ...setLines, ")"];
}
function generate(model) {
  if (model.queryType === "dropTemp") {
    return model.tempTableName ? `\u0423\u041D\u0418\u0427\u0422\u041E\u0416\u0418\u0422\u042C ${model.tempTableName}` : "";
  }
  const hasFields = model.fields.length > 0 || (model.tabSectionFields?.length ?? 0) > 0;
  if (model.tables.length === 0 && !hasFields) return "";
  if (!hasFields) {
    const oLines = renderOrder(model.order, model, false);
    const tLines = renderTotals(model.totals, model);
    const iLines = renderIndex(model.indexing, model);
    let tail = "";
    if (oLines.length > 0) tail += "\n\n" + oLines.join("\n");
    if (tLines.length > 0) tail += "\n" + tLines.join("\n");
    if (iLines.length > 0) tail += "\n\n" + iLines.join("\n");
    tail += renderAutoOrder(model.order, oLines.length > 0 || tLines.length > 0 || iLines.length > 0);
    return tail ? "\n\n" + tail.replace(/^\n+/, "") : "";
  }
  const aliases = resolveAliases(model.tables);
  const fieldLines = buildFieldLines(model, aliases);
  let out = buildQueryBlock(model, fieldLines, aliases);
  const orderLines = renderOrder(model.order, model, false);
  if (orderLines.length > 0) out += "\n\n" + orderLines.join("\n");
  const totalsLines = renderTotals(model.totals, model);
  if (totalsLines.length > 0) out += "\n" + totalsLines.join("\n");
  const indexLines = renderIndex(model.indexing, model);
  if (indexLines.length > 0) out += "\n\n" + indexLines.join("\n");
  out += renderAutoOrder(model.order, orderLines.length > 0 || totalsLines.length > 0 || indexLines.length > 0);
  return out;
}
function renderAutoOrder(order, hadSection) {
  if (!order?.auto) return "";
  return "\n\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415";
}
function buildUnionBlocksScalar(members) {
  const columns = deriveUnionColumns(members);
  const head0 = members[0]?.model.fields ?? [];
  return members.map((m, i) => {
    const fieldLines = columns.map((col, ci) => {
      const expr = col.cells[i] ?? "NULL";
      if (i !== 0) return `	${expr}`;
      const a0 = head0[ci]?.alias;
      const explicitAlias = a0 !== void 0 && !/^Поле\d+$/u.test(a0);
      const emitAlias = !suppressAutoAlias || explicitAlias;
      return emitAlias ? `	${expr} \u041A\u0410\u041A ${col.alias}` : `	${expr}`;
    });
    const aliases = resolveAliases(m.model.tables);
    return buildQueryBlock(m.model, fieldLines, aliases);
  });
}
function buildUnionBlocksWithTabSection(members) {
  const memberEls = members.map((m) => orderedSelectElements(m.model));
  const width = memberEls.reduce((w, els) => Math.max(w, els.length), 0);
  const head = memberEls[0] ?? [];
  return members.map((m, i) => {
    const aliases = resolveAliases(m.model.tables);
    const fieldLines = [];
    for (let ci = 0; ci < width; ci++) {
      const el = memberEls[i][ci];
      if (el === void 0) {
        fieldLines.push("	NULL");
        continue;
      }
      if (el.kind === "ts") {
        fieldLines.push(renderTabProjection(m.model, el.tsf, aliases, { suppress: i !== 0 }));
        continue;
      }
      const expr = fieldExpr(m.model, el.field);
      if (i !== 0) {
        fieldLines.push(`	${expr}`);
        continue;
      }
      const alias = elementAlias(el, m.model);
      const explicitAlias = !/^Поле\d+$/u.test(alias);
      const emitAlias = !suppressAutoAlias || explicitAlias;
      fieldLines.push(emitAlias ? `	${expr} \u041A\u0410\u041A ${alias}` : `	${expr}`);
    }
    return buildQueryBlock(m.model, fieldLines, aliases);
  });
}
function generateDocument(doc) {
  const members = doc.members;
  if (members.length === 0) return "";
  if (members.length === 1) return generate(members[0].model);
  const blocks = unionHasTabSection(members) || unionHasTrailing(members) ? buildUnionBlocksWithTabSection(members) : buildUnionBlocksScalar(members);
  let out = blocks[0];
  for (let i = 1; i < blocks.length; i++) {
    const keyword = members[i].distinct ? "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C" : "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C \u0412\u0421\u0415";
    out += `

${keyword}

${blocks[i]}`;
  }
  const last = members[members.length - 1].model;
  const first = members[0].model;
  const orderLines = renderOrder(last.order, first, false);
  if (orderLines.length > 0) out += "\n\n" + orderLines.join("\n");
  const totalsLines = renderTotals(last.totals, first);
  if (totalsLines.length > 0) out += "\n" + totalsLines.join("\n");
  let indexEmitted = false;
  const tempCarrier = members.find((m) => m.model.queryType === "createTemp")?.model;
  if (last.indexing && tempCarrier) {
    const indexLines = renderIndex(last.indexing, { ...tempCarrier, fields: first.fields, tables: first.tables });
    if (indexLines.length > 0) {
      out += "\n\n" + indexLines.join("\n");
      indexEmitted = true;
    }
  }
  out += renderAutoOrder(last.order, orderLines.length > 0 || totalsLines.length > 0 || indexEmitted);
  return out;
}
function fieldRefExpr(f, aliases) {
  if (f.expression) return formatSelectExpression(f.expression);
  const tableAlias = aliases.get(f.tableId) ?? f.tableId;
  return `${tableAlias}.${f.path}`;
}
var AGG_WORDS_GROUP = /* @__PURE__ */ new Set(["\u0421\u0423\u041C\u041C\u0410", "\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E", "\u041C\u0410\u041A\u0421\u0418\u041C\u0423\u041C", "\u041C\u0418\u041D\u0418\u041C\u0423\u041C", "\u0421\u0420\u0415\u0414\u041D\u0415\u0415"]);
var DISPLAY_META_WORDS = /* @__PURE__ */ new Set(["\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415", "\u0422\u0418\u041F", "\u041F\u0420\u0415\u0414\u0421\u0422\u0410\u0412\u041B\u0415\u041D\u0418\u0415", "\u041F\u0420\u0415\u0414\u0421\u0422\u0410\u0412\u041B\u0415\u041D\u0418\u0415\u0421\u0421\u042B\u041B\u041A\u0418"]);
function analyzeGroupExpr(expression) {
  let toks;
  try {
    toks = tokenize(expression);
  } catch {
    return void 0;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  let depth = 0;
  const aggDepths = [];
  const metaDepths = [];
  let hasAgg = false;
  const fields = [];
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (t.type === "punct" && t.value === "(") {
      const head = sig[i - 1];
      const headV = head ? (head.text ?? head.value).toUpperCase() : "";
      depth++;
      if (AGG_WORDS_GROUP.has(headV)) {
        aggDepths.push(depth);
        hasAgg = true;
      } else if (DISPLAY_META_WORDS.has(headV)) metaDepths.push(depth);
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      if (aggDepths.length && aggDepths[aggDepths.length - 1] === depth) aggDepths.pop();
      if (metaDepths.length && metaDepths[metaDepths.length - 1] === depth) metaDepths.pop();
      if (depth > 0) depth--;
      continue;
    }
    if (t.type === "ident" || t.type === "keyword") {
      const prev = sig[i - 1];
      const next = sig[i + 1];
      if (prev && prev.type === "punct" && prev.value === ".") continue;
      const prevV = prev ? (prev.text ?? prev.value).toUpperCase() : "";
      if (prevV === "\u041A\u0410\u041A" || prevV === "\u0421\u0421\u042B\u041B\u041A\u0410") continue;
      const dotted = next && next.type === "punct" && next.value === ".";
      if (!dotted) continue;
      if (aggDepths.length || metaDepths.length) continue;
      let chain = t.text ?? t.value;
      let j = i + 1;
      while (j + 1 < sig.length && sig[j].type === "punct" && sig[j].value === "." && (sig[j + 1].type === "ident" || sig[j + 1].type === "keyword")) {
        chain += "." + (sig[j + 1].text ?? sig[j + 1].value);
        j += 2;
      }
      fields.push(chain);
    }
  }
  return { hasAgg, fields };
}
function appendMissingGroupRefs(model, existing, aliases) {
  const covered = /* @__PURE__ */ new Map();
  const existingFieldTexts = /* @__PURE__ */ new Set();
  for (const f of existing) {
    const key = fieldRefExpr(f, aliases);
    covered.set(key, (covered.get(key) ?? 0) + 1);
    if (f.expression === void 0) existingFieldTexts.add(key);
  }
  const out = [];
  const aggregated = /* @__PURE__ */ new Set();
  for (const a of model.grouping?.aggregates ?? []) {
    aggregated.add(`${a.tableId} ${a.path}`);
  }
  const candidates = [...model.fields, ...model.trailingFields ?? []];
  for (const f of candidates) {
    if (f.func !== void 0) continue;
    if (aggregated.has(`${f.tableId} ${f.path}`)) continue;
    if (f.expression !== void 0) {
      const info = analyzeGroupExpr(f.expression);
      if (!info || info.hasAgg || info.fields.length === 0) continue;
      const ref2 = { tableId: "", path: "", expression: f.expression };
      const key2 = fieldRefExpr(ref2, aliases);
      const need2 = covered.get(key2) ?? 0;
      if (need2 > 0) {
        covered.set(key2, need2 - 1);
        continue;
      }
      const allCovered = info.fields.every((fld) => existingFieldTexts.has(fld));
      if (allCovered) continue;
      out.push(ref2);
      continue;
    }
    if (f.tableId === "" || f.path === "") continue;
    const ref = { tableId: f.tableId, path: f.path };
    const key = fieldRefExpr(ref, aliases);
    const need = covered.get(key) ?? 0;
    if (need > 0) {
      covered.set(key, need - 1);
      continue;
    }
    out.push(ref);
  }
  return out;
}
function clusterGroupDuplicates(fields, explicitCount, appended, aliases) {
  const explicit = fields.slice(0, explicitCount);
  const parserAppended = fields.slice(explicitCount);
  let lastExprIdx = -1;
  for (let i = 0; i < explicit.length; i++) {
    if (explicit[i].expression !== void 0) lastExprIdx = i;
  }
  const exprCounts = /* @__PURE__ */ new Map();
  for (const f of explicit) {
    if (f.expression !== void 0) {
      const k = fieldRefExpr(f, aliases);
      exprCounts.set(k, (exprCounts.get(k) ?? 0) + 1);
    }
  }
  const tailIsUniqueExprsAfter = (i) => {
    let sawExpr = false;
    for (let j = i + 1; j < explicit.length; j++) {
      const f = explicit[j];
      if (f.expression === void 0) return false;
      if ((exprCounts.get(fieldRefExpr(f, aliases)) ?? 0) > 1) return false;
      sawExpr = true;
    }
    return sawExpr;
  };
  const movable = (i) => i > lastExprIdx || tailIsUniqueExprsAfter(i);
  if (appended.length === 0) {
    const seen2 = /* @__PURE__ */ new Set();
    let hasMovableDup = false;
    for (let i = 0; i < explicit.length; i++) {
      const f = explicit[i];
      if (f.expression !== void 0) continue;
      const k = fieldRefExpr(f, aliases);
      if (seen2.has(k) && movable(i)) {
        hasMovableDup = true;
        break;
      }
      seen2.add(k);
    }
    if (!hasMovableDup) return fields;
  }
  const core = [];
  const tail = [];
  const seen = /* @__PURE__ */ new Set();
  for (let i = 0; i < explicit.length; i++) {
    const f = explicit[i];
    if (f.expression !== void 0) {
      core.push(f);
      continue;
    }
    const k = fieldRefExpr(f, aliases);
    if (!seen.has(k)) {
      seen.add(k);
      core.push(f);
    } else if (movable(i)) tail.push(f);
    else core.push(f);
  }
  for (const a of appended) {
    const k = fieldRefExpr(a, aliases);
    let pos = -1;
    for (let i = 0; i < tail.length; i++) {
      if (fieldRefExpr(tail[i], aliases) === k) pos = i;
    }
    if (pos >= 0) tail.splice(pos + 1, 0, a);
    else tail.push(a);
  }
  return [...core, ...tail, ...parserAppended];
}
function selectFieldMultiplicity(model, aliases) {
  const m = /* @__PURE__ */ new Map();
  const aggregated = /* @__PURE__ */ new Set();
  for (const a of model.grouping?.aggregates ?? []) {
    aggregated.add(`${a.tableId} ${a.path}`);
  }
  const candidates = [...model.fields, ...model.trailingFields ?? []];
  for (const f of candidates) {
    if (f.func !== void 0) continue;
    if (f.expression !== void 0) {
      const info = analyzeGroupExpr(f.expression);
      if (info && info.hasAgg) continue;
      const key2 = fieldRefExpr({ tableId: "", path: "", expression: f.expression }, aliases);
      m.set(key2, (m.get(key2) ?? 0) + 1);
      continue;
    }
    if (f.tableId === "" || f.path === "") continue;
    if (aggregated.has(`${f.tableId} ${f.path}`)) continue;
    const key = fieldRefExpr({ tableId: f.tableId, path: f.path }, aliases);
    m.set(key, (m.get(key) ?? 0) + 1);
  }
  return m;
}
function capGroupDuplicatesToSelect(fields, explicitCount, selectMult, aggregatedTexts, aliases) {
  const kept = [];
  const tail = [];
  const seen = /* @__PURE__ */ new Map();
  let changed = false;
  for (let i = 0; i < fields.length; i++) {
    const f = fields[i];
    if (i >= explicitCount) {
      tail.push(f);
      continue;
    }
    const key = fieldRefExpr(f, aliases);
    const cap = selectMult.get(key);
    if (cap === void 0) {
      if (f.expression !== void 0) {
        const info = analyzeGroupExpr(f.expression);
        if (info && !info.hasAgg && info.fields.length > 0 && info.fields.every((fld) => aggregatedTexts.has(fld))) {
          changed = true;
          continue;
        }
      }
      kept.push(f);
      continue;
    }
    const cnt = seen.get(key) ?? 0;
    if (cnt >= cap) {
      changed = true;
      continue;
    }
    seen.set(key, cnt + 1);
    kept.push(f);
  }
  return changed ? [...kept, ...tail] : fields;
}
function renderGrouping(grouping, aliases, model) {
  if (!grouping) return [];
  if (!grouping.multiple) {
    const fieldsRaw = grouping.groupFields.filter((f) => !isConstGroupExpr(f.expression));
    const rawExplicitRaw = grouping.explicitGroupCount ?? grouping.groupFields.length;
    const explicitCountRaw = grouping.groupFields.slice(0, rawExplicitRaw).filter((f) => !isConstGroupExpr(f.expression)).length;
    const selectMult = model ? selectFieldMultiplicity(model, aliases) : /* @__PURE__ */ new Map();
    const aggregatedTexts = /* @__PURE__ */ new Set();
    for (const f of model?.fields ?? []) {
      if (f.func !== void 0 && f.tableId && f.path) {
        aggregatedTexts.add(fieldRefExpr({ tableId: f.tableId, path: f.path }, aliases));
      }
    }
    for (const a of model?.grouping?.aggregates ?? []) {
      aggregatedTexts.add(fieldRefExpr({ tableId: a.tableId, path: a.path }, aliases));
    }
    const fields = model ? capGroupDuplicatesToSelect(fieldsRaw, explicitCountRaw, selectMult, aggregatedTexts, aliases) : fieldsRaw;
    const explicitCount = fields.length === fieldsRaw.length ? explicitCountRaw : explicitCountRaw - (fieldsRaw.length - fields.length) >= 0 ? (
      // все урезанные были в явной части (cap трогает только явную)
      explicitCountRaw - (fieldsRaw.length - fields.length)
    ) : 0;
    const appended = model && fields.length > 0 ? appendMissingGroupRefs(model, fields, aliases) : [];
    const all = clusterGroupDuplicates(fields, explicitCount, appended, aliases);
    if (all.length === 0) return [];
    const lines = all.map((f, i) => {
      const comma = i < all.length - 1 ? "," : "";
      return `	${fieldRefExpr(f, aliases)}${comma}`;
    });
    return ["\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C \u041F\u041E", ...lines];
  }
  const sets = grouping.groupSets.filter((s) => s.length > 0);
  if (sets.length === 0) return [];
  const setLines = sets.map((set, i) => {
    const fields = set.map((f) => fieldRefExpr(f, aliases));
    const inner = fields.map((expr, j) => `	${j === 0 ? "(" : "	"}${expr}${j < fields.length - 1 ? "," : ")"}`).join("\n");
    const comma = i < sets.length - 1 ? "," : "";
    return inner + comma;
  });
  return ["\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C \u041F\u041E \u0413\u0420\u0423\u041F\u041F\u0418\u0420\u0423\u042E\u0429\u0418\u041C \u041D\u0410\u0411\u041E\u0420\u0410\u041C", "(", ...setLines, ")"];
}
function unwrapHavingMaxMin(expr) {
  const flat = expr.trim();
  const m = /^(МАКСИМУМ|МИНИМУМ)\s*\(/iu.exec(flat);
  if (!m) return expr;
  let toks;
  try {
    toks = tokenize(flat);
  } catch {
    return expr;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  if (sig.length < 3 || sig[1].type !== "punct" || sig[1].value !== "(") return expr;
  let depth = 0;
  let closeIdx = -1;
  for (let i = 1; i < sig.length; i++) {
    if (sig[i].type === "punct" && sig[i].value === "(") depth++;
    else if (sig[i].type === "punct" && sig[i].value === ")") {
      depth--;
      if (depth === 0) {
        closeIdx = i;
        break;
      }
    }
  }
  if (closeIdx !== sig.length - 1) return expr;
  const innerStart = sig[1].pos + 1;
  const innerEnd = sig[closeIdx].pos;
  return flat.slice(innerStart, innerEnd).trim();
}
function buildConditionStrings(conditions, aliases, slot = "where") {
  if (!conditions || conditions.length === 0) return [];
  const conds = [];
  for (const c of conditions) {
    if (c.custom && ((c.expression ?? "").trim() || !c.subquery)) {
      let expr = moveNotBeforeTuple((c.expression ?? "").trim());
      if (slot === "having") expr = unwrapHavingMaxMin(expr);
      const subBase = slot === "where" && !inConditionSubquery ? 3 : 2;
      const leadsWithNot = /^НЕ(?![\p{L}\p{N}_])/u.test(flattenMultilineLeaf(expr).trimStart());
      const caseBaseLeaf = subBase - 1 + (leadsWithNot ? 1 : 0);
      const tightenIn = (s) => slot === "where" && !inConditionSubquery ? tightenLeafInOperator(s) : s;
      if (expr) conds.push(needsFormatting(expr) || isRootNotGroup(expr) ? formatExpression(expr, slot, inConditionSubquery ? 1 : void 0) : appendIsNotNullTrailingSpace(tightenIn(stripNotFieldParens(stripNegatedFieldParens(wrapBareCastOperand(stripRedundantLeafParens(normalizeLeafCase(reindentLeafCase(reindentLeafSubquery(canonicalizeComparisonOperands(flattenMultilineLeaf(expr)), subBase), caseBaseLeaf, true)))))))));
      continue;
    }
    if (c.leftExpr && c.subquery) {
      const subBase = (inConditionSubquery ? 2 : 3) + (c.negated ? 1 : 0);
      const negPrefix = c.negated ? "\u041D\u0415 " : "";
      conds.push(`${negPrefix}${normalizeLeafCase(c.leftExpr)} \u0412
${renderConditionSubquery(c.subquery, subBase, c.negated)}`);
      continue;
    }
    if (!c.path) continue;
    const alias = aliases.get(c.tableId ?? "") ?? c.tableId;
    const op2 = c.operator ?? "=";
    if (c.subquery) {
      const opText = c.hierarchy ? `${op2} \u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418` : op2;
      const negPrefix = c.negated ? "\u041D\u0415 " : "";
      const subBase = (inConditionSubquery ? 2 : 3) + (c.negated ? 1 : 0);
      conds.push(`${negPrefix}${alias}.${c.path} ${opText}
${renderConditionSubquery(c.subquery, subBase, c.negated)}`);
      continue;
    }
    const param = normalizeLeafCase(c.param ?? `&${c.path.split(".").pop()}`);
    conds.push(`${alias}.${c.path} ${renderOperatorRhs(op2, param, inConditionSubquery)}`);
  }
  return conds;
}
function renderConditions(conditions, aliases) {
  const conds = buildConditionStrings(conditions, aliases);
  if (conds.length === 0) return [];
  return ["\u0413\u0414\u0415", ...conds.map((c, i) => i === 0 ? `	${c}` : `	\u0418 ${c}`)];
}
function renderHaving(having, aliases) {
  const conds = buildConditionStrings(having, aliases, "having");
  if (conds.length === 0) return [];
  const sep = inConditionSubquery ? [] : [""];
  return [...sep, "\u0418\u041C\u0415\u042E\u0429\u0418\u0415", ...conds.map((c, i) => `	${c}${i < conds.length - 1 ? " \u0418" : ""}`)];
}

// src/core/query/unionModel.ts
function fieldAlias(field, model) {
  if (field.alias) return field.alias;
  if (field.expression) return field.expression;
  if (model) return synthesizedFieldAlias(model, field);
  return field.path.split(".").pop();
}
function orderedSelectElements(model) {
  const head = model.fields.map((field) => ({ kind: "field", field }));
  const rest = [];
  let seq = 0;
  for (const tsf of model.tabSectionFields ?? []) {
    rest.push({ order: tsf.selectOrder, seq: seq++, el: { kind: "ts", tsf } });
  }
  for (const field of model.trailingFields ?? []) {
    rest.push({ order: field.selectOrder, seq: seq++, el: { kind: "field", field } });
  }
  if (rest.every((it) => it.order !== void 0)) {
    rest.sort((a, b) => a.order - b.order || a.seq - b.seq);
  }
  return [...head, ...rest.map((it) => it.el)];
}
function deriveUnionColumns(members) {
  const width = members.reduce((w, m) => Math.max(w, m.model.fields.length), 0);
  const head = members[0]?.model.fields ?? [];
  const columns = [];
  for (let i = 0; i < width; i++) {
    const headField = head[i];
    columns.push({
      alias: headField ? fieldAlias(headField, members[0].model) : `\u041F\u043E\u043B\u0435${i + 1}`,
      cells: members.map((m) => {
        const f = m.model.fields[i];
        return f ? fieldExpr(m.model, f) : null;
      })
    });
  }
  return columns;
}
function unionHasTabSection(members) {
  return members.some((m) => (m.model.tabSectionFields?.length ?? 0) > 0);
}
function unionHasTrailing(members) {
  return members.some((m) => (m.model.trailingFields?.length ?? 0) > 0);
}
function elementAlias(el, model) {
  if (el.kind === "field") return fieldAlias(el.field, model);
  return el.tsf.alias ?? el.tsf.tsName;
}

// src/core/query/commentBinder.ts
function isAutoSeparator(text2) {
  return /^\/+$/.test(text2);
}
function hasCodeBeforeOnLine(toks, line, pos) {
  return toks.some(
    (t) => t.type !== "comment" && t.type !== "eof" && t.line === line && t.pos < pos
  );
}
function extractComments(memberText, model) {
  try {
    const toks = tokenize(memberText, { comments: true });
    let depth = 0;
    let selectIdx = -1;
    let fromIdx = -1;
    let placeIdx = -1;
    for (let i = 0; i < toks.length; i++) {
      const t = toks[i];
      if (t.type === "punct") {
        if (t.value === "(" || t.value === "[") depth++;
        else if (t.value === ")" || t.value === "]") depth = Math.max(0, depth - 1);
        continue;
      }
      if (t.type !== "keyword" || depth !== 0) continue;
      if (selectIdx < 0 && t.value === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C") selectIdx = i;
      else if (selectIdx >= 0 && fromIdx < 0 && t.value === "\u0418\u0417") fromIdx = i;
      else if (selectIdx >= 0 && placeIdx < 0 && (t.value === "\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C" || t.value === "\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C")) {
        placeIdx = i;
      }
    }
    if (selectIdx < 0) return;
    const candidates = [placeIdx, fromIdx].filter((x) => x >= 0);
    const regionEnd = candidates.length ? Math.min(...candidates) : toks.length;
    const segments = [];
    {
      let segDepth = 0;
      let segStart = selectIdx + 1;
      const pushSeg = (endExclusive) => {
        let last = endExclusive - 1;
        while (last >= segStart && (toks[last].type === "comment" || toks[last].type === "eof")) {
          last--;
        }
        let first = segStart;
        while (first <= last && (toks[first].type === "comment" || toks[first].type === "eof")) {
          first++;
        }
        if (first > last) return;
        const seg = { startTok: first, endTok: last };
        let d = 0;
        for (let j = first; j <= last; j++) {
          const tk = toks[j];
          if (tk.type === "punct") {
            if (tk.value === "(" || tk.value === "[") d++;
            else if (tk.value === ")" || tk.value === "]") d = Math.max(0, d - 1);
            continue;
          }
          if (d === 0 && tk.type === "keyword" && tk.value === "\u041A\u0410\u041A") {
            const next = toks[j + 1];
            if (next && (next.type === "ident" || next.type === "keyword")) {
              seg.synonym = next.text;
            }
            break;
          }
        }
        segments.push(seg);
      };
      for (let i = selectIdx + 1; i < regionEnd; i++) {
        const t = toks[i];
        if (t.type === "punct") {
          if (t.value === "(" || t.value === "[") segDepth++;
          else if (t.value === ")" || t.value === "]") segDepth = Math.max(0, segDepth - 1);
          else if (t.value === "," && segDepth === 0) {
            pushSeg(i);
            segStart = i + 1;
          }
        }
      }
      pushSeg(regionEnd);
    }
    const usedFields = /* @__PURE__ */ new Set();
    const fieldForSegment = (segIdx) => {
      const seg = segments[segIdx];
      const syn = seg?.synonym;
      if (syn) {
        let f2 = model.fields.find((fl) => !usedFields.has(fl) && fieldAlias(fl, model) === syn);
        if (!f2) {
          const synLow = syn.toLowerCase();
          f2 = model.fields.find(
            (fl) => !usedFields.has(fl) && fieldAlias(fl, model).toLowerCase() === synLow
          );
        }
        if (f2) {
          usedFields.add(f2);
          return f2;
        }
      }
      const f = model.fields[segIdx];
      if (f) usedFields.add(f);
      return f;
    };
    const segField = segments.map((_, k) => fieldForSegment(k));
    const beforeSelect = [];
    const afterFrom = [];
    for (let ci = 0; ci < toks.length; ci++) {
      const c = toks[ci];
      if (c.type !== "comment") continue;
      const text2 = c.value;
      if (ci < selectIdx) {
        if (!isAutoSeparator(text2)) beforeSelect.push(text2);
        continue;
      }
      if (ci > selectIdx && ci < regionEnd) {
        const trailing = hasCodeBeforeOnLine(toks, c.line, c.pos);
        if (trailing) {
          const segIdx = segments.findIndex((s) => toks[s.endTok].line === c.line);
          const fld = segIdx >= 0 ? segField[segIdx] : void 0;
          if (fld) {
            fld.commentTrailing = fld.commentTrailing ? `${fld.commentTrailing} ${text2}` : text2;
          }
        } else {
          const segIdx = segments.findIndex((s) => toks[s.startTok].pos > c.pos);
          const fld = segIdx >= 0 ? segField[segIdx] : void 0;
          if (fld) {
            (fld.commentLeading ??= []).push(text2);
          }
        }
        continue;
      }
      if (fromIdx >= 0 && ci > fromIdx) {
        if (!hasCodeBeforeOnLine(toks, c.line, c.pos)) afterFrom.push(text2);
        continue;
      }
    }
    if (beforeSelect.length || afterFrom.length) {
      model.comments ??= {};
      if (beforeSelect.length) model.comments.beforeSelect = beforeSelect;
      if (afterFrom.length) model.comments.afterFrom = afterFrom;
    }
  } catch {
  }
}

// src/core/query/accumVirtualFields.ts
var date = (name) => ({ name, kind: "standard", types: [{ primitive: "\u0414\u0430\u0442\u0430" }] });
var num = (name) => ({ name, kind: "standard", types: [{ primitive: "\u0427\u0438\u0441\u043B\u043E" }] });
var recorder = () => ({ name: "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0442\u043E\u0440", kind: "standard", types: [{}] });
var TIME_UNITS = /* @__PURE__ */ new Set([
  "\u0421\u0435\u043A\u0443\u043D\u0434\u0430",
  "\u041C\u0438\u043D\u0443\u0442\u0430",
  "\u0427\u0430\u0441",
  "\u0414\u0435\u043D\u044C",
  "\u041D\u0435\u0434\u0435\u043B\u044F",
  "\u041C\u0435\u0441\u044F\u0446",
  "\u041A\u0432\u0430\u0440\u0442\u0430\u043B",
  "\u0413\u043E\u0434",
  "\u0414\u0435\u043A\u0430\u0434\u0430",
  "\u041F\u043E\u043B\u0443\u0433\u043E\u0434\u0438\u0435"
]);
function accumPeriodFields(periodicity) {
  if (!periodicity) return [];
  if (periodicity === "\u0417\u0430\u043F\u0438\u0441\u044C") return [date("\u041F\u0435\u0440\u0438\u043E\u0434"), recorder(), num("\u041D\u043E\u043C\u0435\u0440\u0421\u0442\u0440\u043E\u043A\u0438")];
  if (periodicity === "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0442\u043E\u0440") return [date("\u041F\u0435\u0440\u0438\u043E\u0434"), recorder()];
  if (TIME_UNITS.has(periodicity)) return [date("\u041F\u0435\u0440\u0438\u043E\u0434")];
  if (periodicity === "\u0410\u0432\u0442\u043E") {
    return [
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u0421\u0435\u043A\u0443\u043D\u0434\u0430"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u041C\u0438\u043D\u0443\u0442\u0430"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u0427\u0430\u0441"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u0414\u0435\u043D\u044C"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u041D\u0435\u0434\u0435\u043B\u044F"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u0414\u0435\u043A\u0430\u0434\u0430"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u041C\u0435\u0441\u044F\u0446"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u041A\u0432\u0430\u0440\u0442\u0430\u043B"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u041F\u043E\u043B\u0443\u0433\u043E\u0434\u0438\u0435"),
      date("\u041F\u0435\u0440\u0438\u043E\u0434\u0413\u043E\u0434"),
      recorder(),
      num("\u041D\u043E\u043C\u0435\u0440\u0421\u0442\u0440\u043E\u043A\u0438")
    ];
  }
  return [];
}

// src/core/query/buildSelectAllModel.ts
var TRAILING_STD = ["\u041F\u0440\u0435\u0434\u043E\u043F\u0440\u0435\u0434\u0435\u043B\u0435\u043D\u043D\u044B\u0439", "\u0418\u043C\u044F\u041F\u0440\u0435\u0434\u043E\u043F\u0440\u0435\u0434\u0435\u043B\u0435\u043D\u043D\u044B\u0445\u0414\u0430\u043D\u043D\u044B\u0445"];
function splitRealObjectFields(t) {
  const std = t.fields.filter((f) => f.kind === "standard" && !TRAILING_STD.includes(f.name));
  const trailingMeta = t.fields.filter((f) => f.kind === "standard" && TRAILING_STD.includes(f.name));
  const rest = t.fields.filter((f) => f.kind !== "standard");
  const toField = (f) => ({ tableId: "t1", path: f.name, alias: f.name });
  return {
    main: [...std, ...rest].map(toField),
    trailing: trailingMeta.map(toField)
  };
}
function accumVtFields(t, periodicity) {
  const dims = t.fields.filter((f) => f.kind === "dimension");
  const resources = t.fields.filter((f) => f.kind === "resource");
  const slice = t.virtual?.slice;
  const periods = slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B" || slice === "\u041E\u0441\u0442\u0430\u0442\u043A\u0438\u0418\u041E\u0431\u043E\u0440\u043E\u0442\u044B" ? accumPeriodFields(periodicity) : [];
  return [...dims, ...periods, ...resources].map((f) => ({ tableId: "t1", path: f.name, alias: f.name }));
}
function accountingVtFields(t, periodicity) {
  const toField = (f) => ({ tableId: "t1", path: f.name, alias: f.name });
  const slice = t.virtual?.slice;
  const needsPeriod = slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B" || slice === "\u041E\u0441\u0442\u0430\u0442\u043A\u0438\u0418\u041E\u0431\u043E\u0440\u043E\u0442\u044B" || slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B\u0414\u0442\u041A\u0442";
  if (needsPeriod) {
    const periods = accumPeriodFields(periodicity);
    return [...periods, ...t.fields].map(toField);
  }
  return t.fields.map(toField);
}
function buildSelectAllModel(t, periodicity) {
  const isAccumVt = !!t.virtual && t.kind === "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u041D\u0430\u043A\u043E\u043F\u043B\u0435\u043D\u0438\u044F" && ["\u041E\u0441\u0442\u0430\u0442\u043A\u0438", "\u041E\u0431\u043E\u0440\u043E\u0442\u044B", "\u041E\u0441\u0442\u0430\u0442\u043A\u0438\u0418\u041E\u0431\u043E\u0440\u043E\u0442\u044B"].includes(t.virtual.slice);
  const isAccountingVt = !!t.virtual && t.kind === "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0411\u0443\u0445\u0433\u0430\u043B\u0442\u0435\u0440\u0438\u0438";
  let fields;
  let trailingFields;
  if (isAccumVt) {
    fields = accumVtFields(t, periodicity);
  } else if (isAccountingVt) {
    fields = accountingVtFields(t, periodicity);
  } else {
    const split = splitRealObjectFields(t);
    fields = split.main;
    trailingFields = split.trailing.length ? split.trailing : void 0;
  }
  const tabSectionFields = (t.tabularSections ?? []).map((ts) => ({
    tableId: "t1",
    tsName: ts.name,
    tsFullName: ts.fullName,
    fields: ts.fields.map((f) => f.name)
  }));
  const slice = t.virtual?.slice;
  const sliceNeedsPeriodicity = slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B" || slice === "\u041E\u0441\u0442\u0430\u0442\u043A\u0438\u0418\u041E\u0431\u043E\u0440\u043E\u0442\u044B" || slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B\u0414\u0442\u041A\u0442";
  const passPeriodicity = sliceNeedsPeriodicity && !!periodicity;
  let virtual;
  if (t.virtual) {
    const params = {};
    if (passPeriodicity) params.periodicity = periodicity;
    if (slice === "\u041E\u0441\u0442\u0430\u0442\u043A\u0438" || slice === "\u0421\u0440\u0435\u0437\u041F\u0435\u0440\u0432\u044B\u0445" || slice === "\u0421\u0440\u0435\u0437\u041F\u043E\u0441\u043B\u0435\u0434\u043D\u0438\u0445") {
      params.period = "&\u041F\u0435\u0440\u0438\u043E\u0434";
    } else if (slice === "\u0414\u0432\u0438\u0436\u0435\u043D\u0438\u044F\u0421\u0421\u0443\u0431\u043A\u043E\u043D\u0442\u043E") {
      params.startPeriod = "&\u041F\u0435\u0440\u0438\u043E\u0434";
    }
    if (isAccountingVt && t.virtual.correspondence !== void 0) {
      params.correspondence = t.virtual.correspondence;
    }
    virtual = params;
  }
  return {
    tables: [{ id: "t1", fullName: t.fullName, ...virtual ? { virtual } : {} }],
    fields,
    ...tabSectionFields.length ? { tabSectionFields } : {},
    ...trailingFields ? { trailingFields } : {}
  };
}

// src/core/query/expandStarFields.ts
function expandStarFields(model, resolver) {
  if (!resolver) return;
  if (!hasStar(model.fields)) return;
  const aliasToFull = /* @__PURE__ */ new Map();
  let soleFull;
  if (model.tables.length === 1 && !model.tables[0].subquery) {
    soleFull = model.tables[0].fullName;
  }
  for (const t of model.tables) {
    if (t.alias && !t.subquery) aliasToFull.set(t.alias.toUpperCase(), t.fullName);
  }
  const reserved = /* @__PURE__ */ new Set();
  for (const f of model.fields) {
    if (parseStar(f)) continue;
    const a = fieldAlias2(f);
    if (a) reserved.add(a.toUpperCase());
  }
  const newFields = [];
  const tabSections = [...model.tabSectionFields ?? []];
  const trailing = [];
  let sawExpandedStar = false;
  let order = 0;
  let headOpen = true;
  const pushAfter = (f) => {
    if (sawExpandedStar) {
      trailing.push({ ...f, selectOrder: order++ });
      headOpen = false;
    } else newFields.push(f);
  };
  const expandOne = (fullName, tableId) => {
    const meta = fullName ? resolver.tableByFullName(fullName) ?? resolver.virtualTableByFullName?.(fullName) : void 0;
    if (!meta || tableId === void 0) return false;
    const expanded = buildSelectAllModel(meta);
    for (const ef of expanded.fields) {
      const fld = makeField(ef, tableId, reserved);
      if (headOpen) newFields.push(fld);
      else trailing.push({ ...fld, selectOrder: order++ });
    }
    for (const ts of expanded.tabSectionFields ?? []) {
      tabSections.push({ ...ts, tableId, selectOrder: order++ });
    }
    for (const ef of expanded.trailingFields ?? []) {
      trailing.push({ ...makeField(ef, tableId, reserved), selectOrder: order++ });
    }
    headOpen = false;
    return true;
  };
  for (const f of model.fields) {
    const star = parseStar(f);
    if (!star) {
      pushAfter(f);
      continue;
    }
    if (star.viaAttribute) continue;
    if (star.alias) {
      const fullName = aliasToFull.get(star.alias.toUpperCase());
      if (expandOne(fullName, findTableId(model, star.alias))) sawExpandedStar = true;
      continue;
    }
    if (soleFull !== void 0) {
      if (expandOne(soleFull, model.tables[0]?.id)) sawExpandedStar = true;
      continue;
    }
    for (const t of model.tables) {
      if (t.subquery) continue;
      if (expandOne(t.fullName, t.id)) sawExpandedStar = true;
    }
  }
  model.fields = newFields;
  if (tabSections.length) model.tabSectionFields = tabSections;
  if (trailing.length) {
    model.trailingFields = [...trailing, ...model.trailingFields ?? []];
  }
}
function makeField(src, tableId, reserved) {
  const base = src.alias ?? src.path;
  let alias = base;
  let n = 0;
  while (reserved.has(alias.toUpperCase())) {
    alias = `${base}${++n}`;
  }
  reserved.add(alias.toUpperCase());
  return { tableId, path: src.path, alias };
}
function hasStar(fields) {
  return fields.some((f) => parseStar(f) !== null);
}
function parseStar(f) {
  if (f.expression === void 0) return null;
  const e = f.expression.trim();
  if (e === "*") return { viaAttribute: false };
  if (!e.endsWith("*")) return null;
  const segs = e.split(".").map((s) => s.trim());
  if (segs.length < 2 || segs[segs.length - 1] !== "*") return null;
  const head = segs.slice(0, -1);
  if (head.some((s) => s === "" || /[^\wА-Яа-яЁё]/.test(s))) return null;
  return { alias: head[0], viaAttribute: head.length > 1 };
}
function fieldAlias2(f) {
  if (f.alias !== void 0) return f.alias;
  if (f.expression !== void 0) return void 0;
  return f.path.split(".").pop() ?? f.path;
}
function findTableId(model, alias) {
  const up3 = alias.toUpperCase();
  return model.tables.find((t) => t.alias?.toUpperCase() === up3)?.id;
}

// src/core/query/expandTabSectionFields.ts
function expandTabSectionFields(model, resolver) {
  if (!resolver) return;
  if (model.fields.length === 0) return;
  if (model.tabSectionFields && model.tabSectionFields.length > 0) return;
  const idToFull = /* @__PURE__ */ new Map();
  for (const t of model.tables) {
    if (!t.subquery) idToFull.set(t.id, t.fullName);
  }
  const tsColumns = (fullName, tsName) => {
    const meta = resolver.tableByFullName(fullName);
    if (!meta || !meta.tabularSections) return void 0;
    const ts = meta.tabularSections.find((s) => s.name.toUpperCase() === tsName.toUpperCase());
    if (!ts) return void 0;
    return ts.fields.map((f) => f.name);
  };
  const convInfo = (f) => {
    if (f.expression !== void 0 || f.func !== void 0) return void 0;
    const segs = f.path.split(".");
    if (segs.length !== 1) return void 0;
    const full = idToFull.get(f.tableId);
    if (!full) return void 0;
    const cols = tsColumns(full, segs[0]);
    return cols ? { tsName: segs[0], columns: cols } : void 0;
  };
  const firstIdx = model.fields.findIndex((f) => convInfo(f) !== void 0);
  if (firstIdx === -1) return;
  const head = model.fields.slice(0, firstIdx);
  const tabSections = [];
  const trailing = [];
  let order = firstIdx;
  for (let i = firstIdx; i < model.fields.length; i++) {
    const f = model.fields[i];
    const conv = convInfo(f);
    if (conv) {
      tabSections.push({
        tableId: f.tableId,
        tsName: conv.tsName,
        tsFullName: `${idToFull.get(f.tableId)}.${conv.tsName}`,
        fields: conv.columns,
        alias: f.alias ?? conv.tsName,
        selectOrder: order++
      });
    } else {
      trailing.push({ ...f, selectOrder: order++ });
    }
  }
  model.fields = head;
  model.tabSectionFields = tabSections;
  if (trailing.length) model.trailingFields = [...trailing, ...model.trailingFields ?? []];
}

// src/core/query/wrapTabSectionAggregates.ts
function wrapTabSectionAggregates(model, resolver) {
  if (!resolver) return;
  if (model.fields.length === 0) return;
  if (model.tabSectionFields && model.tabSectionFields.length > 0) return;
  const aliasToFull = /* @__PURE__ */ new Map();
  for (const t of model.tables) {
    if (t.subquery) continue;
    const a = t.alias ?? t.fullName.split(".").pop() ?? t.fullName;
    aliasToFull.set(a.toUpperCase(), t.fullName);
  }
  const tsNamesOf = (fullName) => {
    const meta = resolver.tableByFullName(fullName);
    const set = /* @__PURE__ */ new Set();
    for (const ts of meta?.tabularSections ?? []) set.add(ts.name.toUpperCase());
    return set;
  };
  const AGG = /* @__PURE__ */ new Set(["\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E", "\u0421\u0423\u041C\u041C\u0410", "\u041C\u0410\u041A\u0421\u0418\u041C\u0423\u041C", "\u041C\u0418\u041D\u0418\u041C\u0423\u041C", "\u0421\u0420\u0415\u0414\u041D\u0415\u0415"]);
  const detect = (expr) => {
    let toks;
    try {
      toks = tokenize(expr).filter((t) => t.type !== "eof");
    } catch {
      return void 0;
    }
    const hits = [];
    for (let k = 0; k < toks.length; k++) {
      const t = toks[k];
      const isAgg = (t.type === "keyword" || t.type === "ident") && AGG.has(t.value.toUpperCase());
      if (!isAgg) continue;
      if (toks[k + 1]?.value !== "(") continue;
      const a = toks[k + 2];
      if (!a || a.type !== "ident") continue;
      if (toks[k + 3]?.value !== ".") continue;
      const seg2 = toks[k + 4];
      if (!seg2 || seg2.type !== "ident") continue;
      if (toks[k + 5]?.value !== ".") continue;
      const full = aliasToFull.get(a.value.toUpperCase());
      if (!full) continue;
      if (!tsNamesOf(full).has(seg2.value.toUpperCase())) continue;
      const tbl = model.tables.find((tt) => {
        const al = tt.alias ?? tt.fullName.split(".").pop() ?? tt.fullName;
        return al.toUpperCase() === a.value.toUpperCase();
      });
      if (!tbl) continue;
      hits.push({ prefix: `${a.value}.${seg2.value}`, tsName: seg2.value, tableId: tbl.id });
    }
    if (hits.length === 0) return void 0;
    const uniq = new Set(hits.map((h) => h.prefix.toUpperCase()));
    if (uniq.size !== 1) return void 0;
    return hits[0];
  };
  const tagged = model.fields.map((f) => ({
    f,
    target: f.expression !== void 0 ? detect(f.expression) : void 0
  }));
  if (!tagged.some((t) => t.target)) return;
  const firstIdx = tagged.findIndex((t) => t.target);
  const head = model.fields.slice(0, firstIdx);
  const tabSections = [];
  const trailing = [];
  let order = firstIdx;
  let i = firstIdx;
  while (i < tagged.length) {
    const cur = tagged[i];
    if (!cur.target) {
      trailing.push({ ...cur.f, selectOrder: order++ });
      i++;
      continue;
    }
    const groupPrefix = cur.target.prefix.toUpperCase();
    const exprFields = [];
    const groupOrder = order++;
    let n = 0;
    while (i < tagged.length && tagged[i].target && tagged[i].target.prefix.toUpperCase() === groupPrefix) {
      exprFields.push({ expression: tagged[i].f.expression, alias: `\u041F\u043E\u043B\u0435${++n}` });
      i++;
    }
    tabSections.push({
      tableId: cur.target.tableId,
      tsName: cur.target.tsName,
      tsFullName: `${aliasToFull.get(cur.target.prefix.split(".")[0].toUpperCase())}.${cur.target.tsName}`,
      fields: [],
      exprFields,
      // Псевдоним проекции = псевдоним ПЕРВОГО исходного поля группы.
      alias: cur.f.alias ?? cur.target.tsName,
      selectOrder: groupOrder
    });
  }
  model.fields = head;
  model.tabSectionFields = tabSections;
  if (trailing.length) model.trailingFields = [...trailing, ...model.trailingFields ?? []];
}

// src/core/query/dropUserIBConditions.ts
var USER_IB_ATTRS = /* @__PURE__ */ new Set([
  "\u0418\u0414\u0415\u041D\u0422\u0418\u0424\u0418\u041A\u0410\u0422\u041E\u0420\u041F\u041E\u041B\u042C\u0417\u041E\u0412\u0410\u0422\u0415\u041B\u042F\u0418\u0411",
  "\u0418\u0414\u0415\u041D\u0422\u0418\u0424\u0418\u041A\u0410\u0422\u041E\u0420\u041F\u041E\u041B\u042C\u0417\u041E\u0412\u0410\u0422\u0415\u041B\u042F\u0421\u0415\u0420\u0412\u0418\u0421\u0410",
  "\u0423\u0414\u0410\u041B\u0418\u0422\u042C\u0421\u0412\u041E\u0419\u0421\u0422\u0412\u0410\u041F\u041E\u041B\u042C\u0417\u041E\u0412\u0410\u0422\u0415\u041B\u042F\u0418\u0411"
]);
var USER_REF_TABLES = /* @__PURE__ */ new Set([
  "\u0421\u041F\u0420\u0410\u0412\u041E\u0427\u041D\u0418\u041A.\u041F\u041E\u041B\u042C\u0417\u041E\u0412\u0410\u0422\u0415\u041B\u0418",
  "\u0421\u041F\u0420\u0410\u0412\u041E\u0427\u041D\u0418\u041A.\u0412\u041D\u0415\u0428\u041D\u0418\u0415\u041F\u041E\u041B\u042C\u0417\u041E\u0412\u0410\u0422\u0415\u041B\u0418"
]);
function dropUserIBConditions(model, resolver) {
  if (!resolver) return;
  if (!model.conditions || model.conditions.length === 0) return;
  const idToFull = /* @__PURE__ */ new Map();
  for (const t of model.tables) {
    if (!t.subquery) idToFull.set(t.id, t.fullName);
  }
  const isUserNavDrop = (c) => {
    if (c.custom) return false;
    if (!c.path || c.tableId === void 0) return false;
    const segs = c.path.split(".");
    if (segs.length !== 2) return false;
    if (!USER_IB_ATTRS.has(segs[1].toUpperCase())) return false;
    const full = idToFull.get(c.tableId);
    if (!full) return false;
    const meta = resolver.tableByFullName(full);
    if (!meta) return false;
    const field = meta.fields.find((f) => f.name.toUpperCase() === segs[0].toUpperCase());
    if (!field) return false;
    return field.types.some(
      (t) => t.ref !== void 0 && USER_REF_TABLES.has(`${t.ref.kind}.${t.ref.name}`.toUpperCase())
    );
  };
  const kept = model.conditions.filter((c) => !isUserNavDrop(c));
  if (kept.length === model.conditions.length) return;
  if (kept.length === 0) delete model.conditions;
  else model.conditions = kept;
}

// src/core/query/dropUnlimitedStringConditions.ts
var UNLIMITED_DROP_OPS = /* @__PURE__ */ new Set(["=", "<>", ">", "<", ">=", "<=", "\u041C\u0415\u0416\u0414\u0423"]);
function isUnlimitedString(t) {
  return t.primitive === "\u0421\u0442\u0440\u043E\u043A\u0430" && t.allowedLength === "Variable" && t.length === 0;
}
function isStringType(t) {
  return t.primitive === "\u0421\u0442\u0440\u043E\u043A\u0430";
}
function isUnlimitedStringField(field) {
  return field.types.length === 1 && isUnlimitedString(field.types[0]);
}
function isCompositeWithNonString(field) {
  return field.types.length >= 2 && field.types.some((t) => !isStringType(t));
}
function dropUnlimitedStringConditions(model, resolver) {
  if (!resolver) return;
  if (!model.conditions || model.conditions.length === 0) return;
  const idToFull = /* @__PURE__ */ new Map();
  for (const t of model.tables) {
    if (!t.subquery) idToFull.set(t.id, t.fullName);
  }
  const fieldOf = (c) => {
    if (c.custom || !c.path || c.tableId === void 0 || !c.operator) return void 0;
    if (c.path.includes(".")) return void 0;
    const full = idToFull.get(c.tableId);
    if (!full) return void 0;
    const meta = resolver.tableByFullName(full);
    if (!meta) return void 0;
    return meta.fields.find((f) => f.name.toUpperCase() === c.path.toUpperCase());
  };
  const shouldDrop = (c) => {
    const field = fieldOf(c);
    if (!field) return false;
    const op2 = c.operator;
    if (c.subquery) return false;
    if (op2 === "\u041F\u041E\u0414\u041E\u0411\u041D\u041E") {
      return isCompositeWithNonString(field);
    }
    if (UNLIMITED_DROP_OPS.has(op2)) {
      return isUnlimitedStringField(field);
    }
    return false;
  };
  const kept = model.conditions.filter((c) => !shouldDrop(c));
  if (kept.length === model.conditions.length) return;
  if (kept.length === 0) delete model.conditions;
  else model.conditions = kept;
}

// src/core/query/qualifyBareFields.ts
var STRUCTURAL = /* @__PURE__ */ new Set([
  "\u0412\u042B\u0411\u041E\u0420",
  "\u041A\u041E\u0413\u0414\u0410",
  "\u0422\u041E\u0413\u0414\u0410",
  "\u0418\u041D\u0410\u0427\u0415",
  "\u041A\u041E\u041D\u0415\u0426",
  "\u0415\u0421\u0422\u042C",
  "\u0418",
  "\u0418\u041B\u0418",
  "\u041D\u0415",
  "\u0412",
  "\u041C\u0415\u0416\u0414\u0423",
  "\u041F\u041E\u0414\u041E\u0411\u041D\u041E",
  "\u0421\u041F\u0415\u0426\u0421\u0418\u041C\u0412\u041E\u041B",
  "\u041A\u0410\u041A",
  "\u0423\u0411\u042B\u0412",
  "\u0412\u041E\u0417\u0420",
  "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418",
  "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F",
  "\u0412\u042B\u0411\u0420\u0410\u0422\u042C",
  "\u0418\u0417",
  "\u0413\u0414\u0415",
  "\u041F\u041E",
  // Модификаторы выборки/агрегата внутри выражений (`КОЛИЧЕСТВО(РАЗЛИЧНЫЕ …)`).
  "\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415",
  "\u0420\u0410\u0417\u0420\u0415\u0428\u0415\u041D\u041D\u042B\u0415",
  "\u041F\u0415\u0420\u0412\u042B\u0415",
  "\u0412\u0421\u0415",
  "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C",
  // Структурные слова СЕКЦИЙ/СОЕДИНЕНИЙ встроенного подзапроса (тело разбирается
  // как `ВЫБРАТЬ … ИЗ … СОЕДИНЕНИЕ … ГДЕ … СГРУППИРОВАТЬ … ПОМЕСТИТЬ`): они не поля.
  "\u041B\u0415\u0412\u041E\u0415",
  "\u041F\u0420\u0410\u0412\u041E\u0415",
  "\u0412\u041D\u0423\u0422\u0420\u0415\u041D\u041D\u0415\u0415",
  "\u041F\u041E\u041B\u041D\u041E\u0415",
  "\u0412\u041D\u0415\u0428\u041D\u0415\u0415",
  "\u0421\u041E\u0415\u0414\u0418\u041D\u0415\u041D\u0418\u0415",
  "\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C",
  "\u0418\u041C\u0415\u042E\u0429\u0418\u0415",
  "\u0418\u0422\u041E\u0413\u0418",
  "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C",
  "\u0414\u041B\u042F",
  "\u0418\u0417\u041C\u0415\u041D\u0415\u041D\u0418\u042F",
  // Английские эквиваленты операторов/литералов (встречаются в нетиповых запросах).
  "IS",
  "NULL",
  "AND",
  "OR",
  "NOT",
  "AS",
  "BETWEEN",
  "LIKE",
  "TRUE",
  "FALSE"
]);
var LITERALS = /* @__PURE__ */ new Set(["\u041D\u0415\u041E\u041F\u0420\u0415\u0414\u0415\u041B\u0415\u041D\u041E", "\u0418\u0421\u0422\u0418\u041D\u0410", "\u041B\u041E\u0416\u042C", "NULL"]);
var PERIOD_WORDS2 = /* @__PURE__ */ new Set([
  "\u0413\u041E\u0414",
  "\u041F\u041E\u041B\u0423\u0413\u041E\u0414\u0418\u0415",
  "\u041A\u0412\u0410\u0420\u0422\u0410\u041B",
  "\u041C\u0415\u0421\u042F\u0426",
  "\u0414\u0415\u041A\u0410\u0414\u0410",
  "\u041D\u0415\u0414\u0415\u041B\u042F",
  "\u0414\u0415\u041D\u042C",
  "\u0427\u0410\u0421",
  "\u041C\u0418\u041D\u0423\u0422\u0410",
  "\u0421\u0415\u041A\u0423\u041D\u0414\u0410"
]);
var PRIMITIVE_TYPES = /* @__PURE__ */ new Set(["\u0421\u0422\u0420\u041E\u041A\u0410", "\u0427\u0418\u0421\u041B\u041E", "\u0414\u0410\u0422\u0410", "\u0411\u0423\u041B\u0415\u0412\u041E"]);
var TYPE_PREFIXES = /* @__PURE__ */ new Set([
  "\u0421\u041F\u0420\u0410\u0412\u041E\u0427\u041D\u0418\u041A",
  "\u0414\u041E\u041A\u0423\u041C\u0415\u041D\u0422",
  "\u041F\u0415\u0420\u0415\u0427\u0418\u0421\u041B\u0415\u041D\u0418\u0415",
  "\u0420\u0415\u0413\u0418\u0421\u0422\u0420\u0421\u0412\u0415\u0414\u0415\u041D\u0418\u0419",
  "\u0420\u0415\u0413\u0418\u0421\u0422\u0420\u041D\u0410\u041A\u041E\u041F\u041B\u0415\u041D\u0418\u042F",
  "\u0420\u0415\u0413\u0418\u0421\u0422\u0420\u0411\u0423\u0425\u0413\u0410\u041B\u0422\u0415\u0420\u0418\u0418",
  "\u0420\u0415\u0413\u0418\u0421\u0422\u0420\u0420\u0410\u0421\u0427\u0415\u0422\u0410",
  "\u041F\u041B\u0410\u041D\u0412\u0418\u0414\u041E\u0412\u0425\u0410\u0420\u0410\u041A\u0422\u0415\u0420\u0418\u0421\u0422\u0418\u041A",
  "\u041F\u041B\u0410\u041D\u0421\u0427\u0415\u0422\u041E\u0412",
  "\u041F\u041B\u0410\u041D\u0412\u0418\u0414\u041E\u0412\u0420\u0410\u0421\u0427\u0415\u0422\u0410",
  "\u0411\u0418\u0417\u041D\u0415\u0421\u041F\u0420\u041E\u0426\u0415\u0421\u0421",
  "\u0417\u0410\u0414\u0410\u0427\u0410",
  "\u041F\u041B\u0410\u041D\u041E\u0411\u041C\u0415\u041D\u0410",
  "\u041A\u041E\u041D\u0421\u0422\u0410\u041D\u0422\u0410",
  "\u041E\u041F\u0420\u0415\u0414\u0415\u041B\u042F\u0415\u041C\u042B\u0419\u0422\u0418\u041F",
  "\u0425\u0420\u0410\u041D\u0418\u041B\u0418\u0429\u0415\u041D\u0410\u0421\u0422\u0420\u041E\u0415\u041A",
  "\u0412\u041D\u0415\u0428\u041D\u0418\u0419\u0418\u0421\u0422\u041E\u0427\u041D\u0418\u041A\u0414\u0410\u041D\u041D\u042B\u0425",
  "\u0422\u0410\u0411\u041B\u0418\u0426\u0410"
]);
var activeParseDoc;
function setSubqueryParser(fn2) {
  activeParseDoc = fn2;
}
function up2(s) {
  return s.toUpperCase();
}
function subqueryColumns(doc) {
  const cols = /* @__PURE__ */ new Set();
  const m0 = doc.members[0]?.model;
  if (!m0) return cols;
  for (const f of m0.fields) {
    const name = f.alias ?? (f.path ? f.path.split(".").pop() : void 0);
    if (name) cols.add(up2(name));
  }
  return cols;
}
function buildContext(model, resolver, outerAliases = /* @__PURE__ */ new Set(), outerSources = []) {
  const sources = [];
  const aliases = /* @__PURE__ */ new Set();
  const aliasSpelling = /* @__PURE__ */ new Map();
  const aliasMap = resolveAliases(model.tables);
  for (const t of model.tables) {
    const alias = aliasMap.get(t.id) ?? t.alias ?? t.fullName;
    if (alias) {
      aliases.add(up2(alias));
      aliasSpelling.set(up2(alias), alias);
    }
    if (t.subquery) {
      const cols = subqueryColumns(t.subquery);
      sources.push({ alias, fields: cols.size > 0 ? cols : void 0, wildcard: cols.size === 0 });
      continue;
    }
    const fullName = t.fullName;
    const lookupName = fullName.startsWith("#") ? fullName.slice(1).replace(/#$/, "") : fullName;
    const meta = resolver && !fullName.startsWith("&") && fullName !== "" ? t.virtual ? resolver.virtualTableByFullName?.(lookupName) : resolver.tableByFullName(lookupName) : void 0;
    if (meta) {
      const names = new Set(meta.fields.map((f) => up2(f.name)));
      for (const ts of meta.tabularSections ?? []) names.add(up2(ts.name));
      sources.push({ alias, fields: names, wildcard: false });
    } else {
      sources.push({ alias, wildcard: true });
    }
  }
  return { aliases, aliasSpelling, outerAliases, outerSources, sources, resolver, parseDoc: activeParseDoc };
}
function ownerAlias(ctx, name, requireMeta) {
  const N = up2(name);
  const owners = ctx.sources.filter((s) => s.fields?.has(N));
  const wildcards = ctx.sources.filter((s) => s.wildcard);
  if (requireMeta) {
    if (owners.length === 1) return owners[0].alias;
    return void 0;
  }
  if (ctx.sources.length === 1) {
    const s = ctx.sources[0];
    if (ctx.outerAliases.size > 0 && s.fields && !s.fields.has(N)) {
      const outerOwners = ctx.outerSources.filter((os) => os.fields?.has(N));
      return outerOwners.length === 1 ? outerOwners[0].alias : void 0;
    }
    return s.alias;
  }
  if (owners.length === 1) return owners[0].alias;
  if (owners.length === 0 && wildcards.length === 1) return wildcards[0].alias;
  return void 0;
}
function matchCloseIndex(sig, openIdx) {
  let d = 0;
  for (let k = openIdx; k < sig.length; k++) {
    const tk = sig[k];
    if (tk.type === "punct" && tk.value === "(") d++;
    else if (tk.type === "punct" && tk.value === ")") {
      d--;
      if (d === 0) return k;
    }
  }
  return -1;
}
function qualifySubquerySpan(innerRaw, outerCtx) {
  const parseDoc = outerCtx.parseDoc;
  if (!parseDoc) return innerRaw;
  let innerDoc;
  try {
    innerDoc = parseDoc(innerRaw, outerCtx.resolver);
  } catch {
    return innerRaw;
  }
  const m0 = innerDoc.members[0]?.model;
  if (!m0) return innerRaw;
  const innerOuterAliases = /* @__PURE__ */ new Set([...outerCtx.outerAliases, ...outerCtx.aliases]);
  const innerOuterSources = [...outerCtx.outerSources, ...outerCtx.sources];
  const innerCtx = buildContext(m0, outerCtx.resolver, innerOuterAliases, innerOuterSources);
  if (innerCtx.sources.length === 0) return innerRaw;
  return qualifyExpression(innerRaw, innerCtx);
}
function qualifyExpression(raw, ctx) {
  if (ctx.sources.length === 0) return raw;
  let toks;
  try {
    toks = tokenize(raw);
  } catch {
    return raw;
  }
  const sig = toks.filter((t) => t.type !== "eof");
  const metaCallDepths = [];
  let depth = 0;
  const edits = [];
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (t.type === "punct" && t.value === "(") {
      const head = sig[i - 1];
      const headV = head ? up2(head.text ?? head.value) : "";
      const nextT = sig[i + 1];
      if (nextT && (nextT.type === "keyword" || nextT.type === "ident") && up2(nextT.text ?? nextT.value) === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C") {
        const close = matchCloseIndex(sig, i);
        if (close > i) {
          const innerStart = sig[i].pos + 1;
          const innerEnd = sig[close].pos;
          const innerRaw = raw.slice(innerStart, innerEnd);
          const rewritten = qualifySubquerySpan(innerRaw, ctx);
          if (rewritten !== innerRaw) edits.push({ start: innerStart, end: innerEnd, text: rewritten });
          i = close;
          continue;
        }
      }
      depth++;
      if (headV === "\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415" || headV === "\u0422\u0418\u041F") metaCallDepths.push(depth);
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      if (metaCallDepths.length > 0 && metaCallDepths[metaCallDepths.length - 1] === depth) {
        metaCallDepths.pop();
      }
      if (depth > 0) depth--;
      continue;
    }
    if (t.type !== "ident" && t.type !== "keyword") continue;
    if (metaCallDepths.length > 0) continue;
    const word = up2(t.text ?? t.value);
    {
      const prevTok = sig[i - 1];
      const nextTok = sig[i + 1];
      const isPathHead = !(prevTok && prevTok.type === "punct" && prevTok.value === ".");
      const hasDot = nextTok && nextTok.type === "punct" && nextTok.value === ".";
      const declared = ctx.aliasSpelling.get(word);
      if (isPathHead && hasDot && (ctx.aliases.has(word) || ctx.outerAliases.has(word)) && declared !== void 0 && declared !== (t.text ?? t.value)) {
        edits.push({ start: t.pos, end: t.pos + (t.text ?? t.value).length, text: declared });
        continue;
      }
    }
    if (STRUCTURAL.has(word) || LITERALS.has(word) || PERIOD_WORDS2.has(word)) continue;
    const prev = sig[i - 1];
    const next = sig[i + 1];
    const prevV = prev ? up2(prev.text ?? prev.value) : "";
    const nextV = next ? next.text ?? next.value : "";
    if (word === "\u0421\u0421\u042B\u041B\u041A\u0410" && next && (next.type === "ident" || next.type === "keyword") && TYPE_PREFIXES.has(up2(next.text ?? next.value))) continue;
    if (prev && prev.type === "punct" && prev.value === ".") continue;
    if (prevV === "\u041A\u0410\u041A") continue;
    if (prevV === "\u0418\u0417" || prevV === "\u0421\u041E\u0415\u0414\u0418\u041D\u0415\u041D\u0418\u0415" || prevV === "\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C") continue;
    if (PRIMITIVE_TYPES.has(word) && (prevV === "\u041A\u0410\u041A" || prevV === "(")) continue;
    if (nextV === "(") continue;
    if (ctx.aliases.has(word) || ctx.outerAliases.has(word)) continue;
    const hasDotAfter = next && next.type === "punct" && next.value === ".";
    const afterRefOp = prevV === "\u0421\u0421\u042B\u041B\u041A\u0410";
    const isSourceField = !afterRefOp && ctx.sources.filter((s) => s.fields?.has(word)).length === 1;
    if (hasDotAfter && TYPE_PREFIXES.has(word) && !isSourceField) continue;
    const alias = ownerAlias(ctx, t.text ?? t.value, !!hasDotAfter);
    if (alias === void 0) continue;
    edits.push({ start: t.pos, end: t.pos, text: alias + "." });
  }
  if (edits.length === 0) return raw;
  edits.sort((a, b) => b.start - a.start);
  let out = raw;
  for (const e of edits) {
    out = out.slice(0, e.start) + e.text + out.slice(e.end);
  }
  return out;
}
function selectOutputAliases(model) {
  const out = /* @__PURE__ */ new Set();
  const addName = (n) => {
    if (n) out.add(up2(n));
  };
  const add = (f) => {
    if (f.alias) {
      addName(f.alias);
      return;
    }
    if (f.expression !== void 0) return;
    addName(f.path.split(".").pop());
  };
  model.fields.forEach(add);
  (model.trailingFields ?? []).forEach(add);
  for (const tsf of model.tabSectionFields ?? []) {
    addName(tsf.alias ?? tsf.tsName);
    for (const c of tsf.columns ?? []) {
      if (c.kind === "field") addName(c.alias ?? c.field);
      else addName(c.alias);
    }
    (tsf.fields ?? []).forEach((f, i) => addName(tsf.fieldAliases?.[i] ?? f));
    for (const ef of tsf.exprFields ?? []) addName(ef.alias);
  }
  return out;
}
function qualifyBareSimpleRef(ref, model, ctx, selectAliases) {
  if (ref.expression !== void 0) return;
  if (ref.qualified) return;
  if (ref.tableId && model.tables.some((t2) => t2.id === ref.tableId)) return;
  if (selectAliases.has(up2(ref.path))) return;
  const segs = ref.path.split(".");
  const head = segs[0];
  if (ctx.aliases.has(up2(head)) || ctx.outerAliases.has(up2(head))) return;
  const alias = ownerAlias(ctx, head, segs.length > 1);
  if (alias === void 0) return;
  const aliasMap = resolveAliases(model.tables);
  const t = model.tables.find((tb) => (aliasMap.get(tb.id) ?? tb.alias ?? tb.fullName) === alias);
  if (!t) return;
  ref.tableId = t.id;
  ref.qualified = true;
}
function processDocument(doc, resolver, outerAliases, outerSources) {
  for (const member of doc.members) processModel(member.model, resolver, outerAliases, outerSources);
}
function processModel(model, resolver, outerAliases, outerSources) {
  const ctx = buildContext(model, resolver, outerAliases, outerSources);
  const innerOuter = /* @__PURE__ */ new Set([...outerAliases, ...ctx.aliases]);
  const innerOuterSources = [...outerSources, ...ctx.sources];
  for (const t of model.tables) {
    if (t.subquery) processDocument(t.subquery, resolver, innerOuter, innerOuterSources);
  }
  for (const c of model.conditions ?? []) {
    if (c.subquery) processDocument(c.subquery, resolver, innerOuter, innerOuterSources);
  }
  for (const c of model.having ?? []) {
    if (c.subquery) processDocument(c.subquery, resolver, innerOuter, innerOuterSources);
  }
  if (ctx.sources.length === 0) return;
  if (outerAliases.size > 0 && ctx.sources.length === 1 && ctx.sources[0].fields) {
    const innerFields = ctx.sources[0].fields;
    const rebind = (f) => {
      if (f.expression !== void 0 || f.qualified) return;
      if (!f.tableId || !model.tables.some((t) => t.id === f.tableId)) return;
      const head = up2(f.path.split(".")[0]);
      if (innerFields.has(head)) return;
      const owners = outerSources.filter((os) => os.fields?.has(head));
      if (owners.length !== 1) return;
      f.tableId = "";
      f.expression = `${owners[0].alias}.${f.path}`;
      f.path = "";
    };
    model.fields.forEach(rebind);
  }
  const doField = (f) => {
    if (f.expression !== void 0) f.expression = qualifyExpression(f.expression, ctx);
  };
  model.fields.forEach(doField);
  (model.trailingFields ?? []).forEach(doField);
  const doCond = (c) => {
    if (c.custom && c.expression !== void 0 && c.expression.trim()) {
      c.expression = qualifyExpression(c.expression, ctx);
    }
  };
  (model.conditions ?? []).forEach(doCond);
  (model.having ?? []).forEach(doCond);
  for (const j of model.joins ?? []) {
    if (j.custom && j.expression !== void 0 && j.expression.trim()) {
      j.expression = qualifyExpression(j.expression, ctx);
    }
    for (const jc of j.conditions ?? []) {
      if (jc.custom && jc.expression !== void 0 && jc.expression.trim()) {
        jc.expression = qualifyExpression(jc.expression, ctx);
      }
    }
  }
  const doFieldRef = (fr) => {
    if (fr.expression !== void 0) fr.expression = qualifyExpression(fr.expression, ctx);
  };
  if (model.grouping) {
    model.grouping.groupFields.forEach(doFieldRef);
    model.grouping.groupSets.forEach((set) => set.forEach(doFieldRef));
    model.grouping.aggregates.forEach(doFieldRef);
  }
  if (model.order) {
    for (const o of model.order.fields) {
      if (o.expression !== void 0) o.expression = qualifyExpression(o.expression, ctx);
    }
  }
  if (model.totals) {
    for (const tg of model.totals.groupFields) {
      if (tg.expression !== void 0) tg.expression = qualifyExpression(tg.expression, ctx);
    }
  }
}
function qualifySectionRefs(doc, resolver, outerAliases = /* @__PURE__ */ new Set()) {
  for (const qd of doc.members) {
    const inner = /* @__PURE__ */ new Set([...outerAliases, ...buildContext(qd.model, resolver).aliases]);
    for (const t of qd.model.tables) if (t.subquery) qualifySectionRefs(t.subquery, resolver, inner);
    for (const c of qd.model.conditions ?? []) if (c.subquery) qualifySectionRefs(c.subquery, resolver, inner);
  }
  if (doc.members.length !== 1) return;
  const model = doc.members[0].model;
  const ctx = buildContext(model, resolver, outerAliases);
  if (ctx.sources.length === 0) return;
  const selectAliases = selectOutputAliases(model);
  if (model.order) {
    for (const o of model.order.fields) {
      if (o.expression === void 0) qualifyBareSimpleRef(o, model, ctx, selectAliases);
    }
  }
  if (model.totals) {
    for (const tg of model.totals.groupFields) {
      if (tg.expression === void 0) qualifyBareSimpleRef(tg, model, ctx, selectAliases);
    }
  }
}
function qualifyBareSectionFields(doc, resolver) {
  qualifySectionRefs(doc, resolver);
}
function qualifyBareFields(model, resolver) {
  processModel(model, resolver, /* @__PURE__ */ new Set(), []);
}

// src/core/query/resolveBuilderStar.ts
function resolveBuilderStar(model, resolver) {
  if (!resolver) return;
  if (!model.builder) return;
  const ctx = new ResolveCtx(model, resolver);
  for (const group of [model.builder.fields, model.builder.conditions, model.builder.order, model.builder.totals]) {
    for (const f of group) {
      if (!f.child) continue;
      if (f.condition) continue;
      const cls = ctx.classify(f.ref);
      if (cls === "scalar" || cls === "parameter") f.child = false;
    }
  }
}
var ResolveCtx = class _ResolveCtx {
  constructor(model, resolver) {
    this.model = model;
    this.resolver = resolver;
    for (const t of model.tables) {
      if (t.alias) this.aliasToTable.set(t.alias.toUpperCase(), t);
    }
    for (const f of model.fields) {
      const a = f.alias ?? f.path;
      if (a) this.selectAlias.set(a.toUpperCase(), f);
    }
  }
  aliasToTable = /* @__PURE__ */ new Map();
  selectAlias = /* @__PURE__ */ new Map();
  /**
   * true — ссылка `ref` ДОКАЗУЕМО резолвится в ссылочное поле (суффикс `.*`
   * сохраняется). При любой неопределённости (нерезолвимый источник/поле) — false.
   */
  /**
   * Решение о суффиксе `.*` для простой ссылки построителя. Возвращает:
   *  - 'reference'    — цепочка ДОКАЗУЕМО резолвится в ссылочное поле → сохранить;
   *  - 'scalar'       — цепочка резолвится в НЕссылочное поле → снять;
   *  - 'parameter'    — источник-параметр `&Имя` → снять (поле нерезолвимо в принципе);
   *  - 'unknown'      — нерезолвимо по иным причинам (ВТ/представление/пробел в
   *                     метаданных) → консервативно сохранить.
   * Снимаем `.*` только при ДОКАЗАННОЙ нессылочности либо источнике-параметре —
   * чтобы пробелы метаданных (нерезолвимые ВТ/регистры) не роняли корректные `.*`.
   */
  classify(ref) {
    const segs = ref.split(".");
    if (segs.length === 0) return "unknown";
    const head = segs[0].toUpperCase();
    const t = this.aliasToTable.get(head);
    if (t) {
      if (t.subquery) {
        const sub = t.subquery.members[0]?.model;
        return sub ? this.fromSubquery(sub, segs.slice(1)) : "unknown";
      }
      if (t.fullName.startsWith("&")) return "parameter";
      const meta = this.metaFor(t.fullName);
      return meta ? this.walk(meta, segs.slice(1)) : "unknown";
    }
    const sel = this.selectAlias.get(head);
    if (sel && !sel.expression) {
      return this.fromSelectField(sel, segs.slice(1));
    }
    return "unknown";
  }
  fromSelectField(sel, rest) {
    const src = this.model.tables.find((x) => x.id === sel.tableId);
    if (!src) return "unknown";
    if (src.subquery) {
      const sub = src.subquery.members[0]?.model;
      return sub ? this.fromSubquery(sub, [...sel.path.split("."), ...rest]) : "unknown";
    }
    if (src.fullName.startsWith("&")) return "parameter";
    const meta = this.metaFor(src.fullName);
    return meta ? this.walk(meta, [...sel.path.split("."), ...rest]) : "unknown";
  }
  /** Резолв сегментов относительно выходных полей подзапроса. */
  fromSubquery(subModel, segs) {
    if (segs.length === 0) return "unknown";
    const ctx = new _ResolveCtx(subModel, this.resolver);
    const out = ctx.selectAlias.get(segs[0].toUpperCase());
    if (!out || out.expression) return "unknown";
    return ctx.fromSelectField(out, segs.slice(1));
  }
  /** Идёт по сегментам от таблицы через ссылочные поля до финального типа. */
  walk(meta, segs) {
    if (segs.length === 0) return hasReference(meta) ? "reference" : "scalar";
    let cur = meta;
    for (let i = 0; i < segs.length; i++) {
      if (!cur) return "unknown";
      const field = findField(cur, segs[i]);
      if (!field) return "unknown";
      const ref = firstRef(field);
      if (i === segs.length - 1) {
        if (ref !== void 0) return "reference";
        return field.types.length === 0 ? "unknown" : "scalar";
      }
      if (!ref) return field.types.length === 0 ? "unknown" : "scalar";
      cur = this.resolver.tableByFullName(`${ref.kind}.${ref.name}`);
    }
    return "unknown";
  }
  /** Метаданные таблицы по fullName с учётом среза виртуальной таблицы регистра. */
  metaFor(fullName) {
    const direct = this.resolver.tableByFullName(fullName);
    if (direct) return direct;
    const m = fullName.match(/^(Регистр\p{L}+\.[^.]+)\.\p{L}+$/u);
    return m ? this.resolver.tableByFullName(m[1]) : void 0;
  }
};
function findField(meta, name) {
  const up3 = name.toUpperCase();
  return meta.fields.find((f) => f.name.toUpperCase() === up3);
}
function firstRef(field) {
  for (const t of field.types) if (t.ref) return t.ref;
  return void 0;
}
function hasReference(meta) {
  const ssylka = findField(meta, "\u0421\u0441\u044B\u043B\u043A\u0430");
  return ssylka !== void 0 && firstRef(ssylka) !== void 0;
}

// src/core/query/dropRedundantGroupDerefs.ts
var AGG_RE = /(?:^|[^\p{L}])(СУММА|КОЛИЧЕСТВО|МАКСИМУМ|МИНИМУМ|СРЕДНЕЕ|SUM|COUNT|MAX|MIN|AVG)\s*\(/iu;
function dropRedundantGroupDerefs(model, resolver) {
  if (!resolver) return;
  const grouping = model.grouping;
  if (!grouping || grouping.multiple) return;
  const fields = grouping.groupFields;
  if (fields.length === 0) return;
  const explicitCount = grouping.explicitGroupCount ?? fields.length;
  const aliasToTable = /* @__PURE__ */ new Map();
  for (const t of model.tables) aliasToTable.set(t.id, t);
  const groupKeyIdx = /* @__PURE__ */ new Map();
  for (let gi = 0; gi < fields.length; gi++) {
    const f = fields[gi];
    if (f.expression !== void 0) continue;
    if (!f.tableId || !f.path) continue;
    const gk = keyOf(f.tableId, f.path);
    if (!groupKeyIdx.has(gk)) groupKeyIdx.set(gk, gi);
  }
  const selectKeys = /* @__PURE__ */ new Set();
  const nonAggSelectExprs = [];
  for (const f of [...model.fields, ...model.trailingFields ?? []]) {
    if (f.expression !== void 0) {
      if (f.func === void 0 && !AGG_RE.test(f.expression)) nonAggSelectExprs.push(f.expression);
      continue;
    }
    if (f.func !== void 0) continue;
    if (!f.tableId || !f.path) continue;
    selectKeys.add(keyOf(f.tableId, f.path));
  }
  const dropIdx = /* @__PURE__ */ new Set();
  for (let i = 0; i < explicitCount && i < fields.length; i++) {
    const f = fields[i];
    if (f.expression !== void 0 || !f.tableId || !f.path) continue;
    if (selectKeys.has(keyOf(f.tableId, f.path))) continue;
    const segs = f.path.split(".");
    if (segs.length < 2) continue;
    {
      const t = aliasToTable.get(f.tableId);
      const rendered = (t ? defaultTableAlias(t) : f.tableId) + "." + f.path;
      if (nonAggSelectExprs.some((e) => derefInResultPosition(e, rendered))) continue;
    }
    let prefixGrouped = "";
    for (let k = segs.length - 1; k >= 1; k--) {
      const prefix = segs.slice(0, k).join(".");
      const pidx = groupKeyIdx.get(keyOf(f.tableId, prefix));
      if (pidx !== void 0 && pidx < i) {
        prefixGrouped = prefix;
        break;
      }
    }
    if (!prefixGrouped) continue;
    if (!prefixResolvesToReference(aliasToTable.get(f.tableId), prefixGrouped, resolver)) continue;
    dropIdx.add(i);
  }
  if (dropIdx.size === 0) return;
  const kept = [];
  let droppedBeforeExplicit = 0;
  for (let i = 0; i < fields.length; i++) {
    if (dropIdx.has(i)) {
      if (i < explicitCount) droppedBeforeExplicit++;
      continue;
    }
    kept.push(fields[i]);
  }
  grouping.groupFields = kept;
  grouping.explicitGroupCount = explicitCount - droppedBeforeExplicit;
}
function moveBeforePrefixGroupDerefToEnd(model, resolver) {
  if (!resolver) return;
  const grouping = model.grouping;
  if (!grouping || grouping.multiple) return;
  const fields = grouping.groupFields;
  if (fields.length < 2) return;
  const explicitCount = grouping.explicitGroupCount ?? fields.length;
  if (explicitCount < 2) return;
  const aliasToTable = /* @__PURE__ */ new Map();
  for (const t of model.tables) aliasToTable.set(t.id, t);
  const groupKeyIdx = /* @__PURE__ */ new Map();
  for (let gi = 0; gi < explicitCount && gi < fields.length; gi++) {
    const f = fields[gi];
    if (f.expression !== void 0 || !f.tableId || !f.path) continue;
    const gk = keyOf(f.tableId, f.path);
    if (!groupKeyIdx.has(gk)) groupKeyIdx.set(gk, gi);
  }
  const selectKeys = /* @__PURE__ */ new Set();
  for (const f of [...model.fields, ...model.trailingFields ?? []]) {
    if (f.expression !== void 0 || f.func !== void 0) continue;
    if (!f.tableId || !f.path) continue;
    selectKeys.add(keyOf(f.tableId, f.path));
  }
  const aggExprTexts = [];
  for (const f of [...model.fields, ...model.trailingFields ?? []]) {
    if (f.expression !== void 0 && AGG_RE.test(f.expression)) aggExprTexts.push(f.expression);
  }
  if (aggExprTexts.length === 0) return;
  let moveIdx = -1;
  for (let i = 0; i < explicitCount && i < fields.length; i++) {
    const f = fields[i];
    if (f.expression !== void 0 || !f.tableId || !f.path) continue;
    if (selectKeys.has(keyOf(f.tableId, f.path))) continue;
    const segs = f.path.split(".");
    if (segs.length < 2) continue;
    let prefixGrouped = "";
    for (let k = segs.length - 1; k >= 1; k--) {
      const prefix = segs.slice(0, k).join(".");
      const pidx = groupKeyIdx.get(keyOf(f.tableId, prefix));
      if (pidx !== void 0 && pidx > i) {
        prefixGrouped = prefix;
        break;
      }
    }
    if (!prefixGrouped) continue;
    if (!prefixResolvesToReference(aliasToTable.get(f.tableId), prefixGrouped, resolver)) continue;
    const table = aliasToTable.get(f.tableId);
    const alias = table ? defaultTableAlias(table) : f.tableId;
    const rendered = alias + "." + f.path;
    const used = aggExprTexts.some((t) => t.includes(rendered));
    if (!used) continue;
    moveIdx = i;
    break;
  }
  if (moveIdx < 0) return;
  const moved = fields[moveIdx];
  const explicit = fields.slice(0, explicitCount);
  const rest = fields.slice(explicitCount);
  explicit.splice(moveIdx, 1);
  explicit.push(moved);
  grouping.groupFields = [...explicit, ...rest];
}
function keyOf(tableId, path) {
  return tableId + "" + path;
}
function normExpr(s) {
  return s.replace(/\s+/gu, " ").trim();
}
function containsFieldRef(expr, rendered) {
  const isWordChar = (c) => c !== void 0 && /[\p{L}\p{N}_.]/u.test(c);
  let from = 0;
  for (; ; ) {
    const idx = expr.indexOf(rendered, from);
    if (idx < 0) return false;
    if (!isWordChar(expr[idx - 1]) && !isWordChar(expr[idx + rendered.length])) return true;
    from = idx + rendered.length;
  }
}
function substituteGroupFieldWithSelectExpr(model, resolver, isSubquery = false) {
  if (!resolver) return;
  if (!isSubquery) return;
  const grouping = model.grouping;
  if (!grouping || grouping.multiple) return;
  const fields = grouping.groupFields;
  if (fields.length < 2) return;
  const explicitCount = grouping.explicitGroupCount ?? fields.length;
  if (explicitCount < 2) return;
  const aliasToTable = /* @__PURE__ */ new Map();
  for (const t of model.tables) aliasToTable.set(t.id, t);
  const selectKeys = /* @__PURE__ */ new Set();
  const exprCols = [];
  for (const f of [...model.fields, ...model.trailingFields ?? []]) {
    if (f.expression !== void 0) {
      if (f.func === void 0 && f.alias && /^ВЫБОР(?![\p{L}\p{N}_])/iu.test(f.expression.trim()) && !AGG_RE.test(f.expression)) {
        exprCols.push({ alias: f.alias, expression: f.expression });
      }
      continue;
    }
    if (f.func !== void 0 || !f.tableId || !f.path) continue;
    selectKeys.add(keyOf(f.tableId, f.path));
  }
  if (exprCols.length === 0) return;
  const groupedExprNorm = /* @__PURE__ */ new Set();
  for (const g of fields) if (g.expression !== void 0) groupedExprNorm.add(normExpr(g.expression));
  const anchorBefore = [];
  let seenAnchor = false;
  for (let i = 0; i < explicitCount && i < fields.length; i++) {
    anchorBefore.push(seenAnchor);
    const f = fields[i];
    if (f.expression === void 0 && f.tableId && f.path && selectKeys.has(keyOf(f.tableId, f.path))) {
      seenAnchor = true;
    }
  }
  for (let i = 0; i < explicitCount && i < fields.length; i++) {
    const f = fields[i];
    if (f.expression !== void 0 || !f.tableId || !f.path) continue;
    if (selectKeys.has(keyOf(f.tableId, f.path))) continue;
    if (!anchorBefore[i]) continue;
    const table = aliasToTable.get(f.tableId);
    const nameUp = f.path.toUpperCase();
    const alias = table ? defaultTableAlias(table) : f.tableId;
    const rendered = alias + "." + f.path;
    const expr = exprCols.find(
      (e) => e.alias.toUpperCase() === nameUp && containsFieldRef(e.expression, rendered) && !groupedExprNorm.has(normExpr(e.expression))
    );
    if (!expr) continue;
    const explicit = fields.slice(0, explicitCount);
    const rest = fields.slice(explicitCount);
    explicit.splice(i, 1);
    explicit.push({ tableId: "", path: "", expression: expr.expression });
    grouping.groupFields = [...explicit, ...rest];
    grouping.explicitGroupCount = explicitCount;
    return;
  }
}
function moveLeadingMovementCaseToEnd(model) {
  const grouping = model.grouping;
  if (!grouping || grouping.multiple) return;
  const fields = grouping.groupFields;
  if (fields.length < 2) return;
  const explicitCount = grouping.explicitGroupCount ?? fields.length;
  if (explicitCount < 2) return;
  const head = fields[0];
  if (head.expression === void 0) return;
  if (!isMovementCaseExpr(head.expression)) return;
  const moved = fields[0];
  const rest = fields.slice(1, explicitCount);
  const appended = fields.slice(explicitCount);
  grouping.groupFields = [...rest, moved, ...appended];
  grouping.explicitGroupCount = explicitCount;
}
function isMovementCaseExpr(expr) {
  const up3 = expr.toUpperCase();
  if (!up3.includes("\u0412\u042B\u0411\u041E\u0420")) return false;
  return /ЗНАЧЕНИЕ\s*\(\s*ВИДДВИЖЕНИЯ(НАКОПЛЕНИЯ|БУХГАЛТЕРИИ)\s*\./u.test(up3);
}
function prefixResolvesToReference(table, path, resolver) {
  if (!table || table.subquery) return false;
  if (!table.fullName || table.fullName.startsWith("&")) return false;
  let cur = metaFor(table.fullName, resolver);
  if (!cur) return false;
  const segs = path.split(".");
  for (let i = 0; i < segs.length; i++) {
    if (!cur) return false;
    const field = findField2(cur, segs[i]);
    if (!field) return false;
    if (i === 0 && (field.kind === "dimension" || field.kind === "resource")) return false;
    const ref = firstRef2(field);
    if (i === segs.length - 1) return ref !== void 0;
    if (!ref) return false;
    cur = resolver.tableByFullName(ref.kind + "." + ref.name);
  }
  return false;
}
function metaFor(fullName, resolver) {
  const direct = resolver.tableByFullName(fullName);
  if (direct) return direct;
  const parts = fullName.split(".");
  if (parts.length === 3 && !parts[0].startsWith("\u0420\u0435\u0433\u0438\u0441\u0442\u0440")) {
    const owner = resolver.tableByFullName(parts[0] + "." + parts[1]);
    const ts = owner?.tabularSections?.find((s) => s.name.toUpperCase() === parts[2].toUpperCase());
    if (ts) return ts;
  }
  const m = fullName.match(/^(Регистр\p{L}+\.[^.]+)\.\p{L}+$/u);
  return m ? resolver.tableByFullName(m[1]) : void 0;
}
function findField2(meta, name) {
  const up3 = name.toUpperCase();
  return meta.fields.find((f) => f.name.toUpperCase() === up3);
}
function firstRef2(field) {
  for (const t of field.types) if (t.ref) return t.ref;
  return void 0;
}
var MOVEMENT_RE = /(?:^|[^\p{L}\p{N}_])(?:ТОГДА|ИНАЧЕ)\s+(?:-\s*)?ЗНАЧЕНИЕ\s*\(\s*ВИДДВИЖЕНИЯ(?:НАКОПЛЕНИЯ|БУХГАЛТЕРИИ)\s*\./iu;
var META_FUNCS = /* @__PURE__ */ new Set(["\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415", "\u0422\u0418\u041F", "\u041F\u0420\u0415\u0414\u0421\u0422\u0410\u0412\u041B\u0415\u041D\u0418\u0415", "\u041F\u0420\u0415\u0414\u0421\u0422\u0410\u0412\u041B\u0415\u041D\u0418\u0415\u0421\u0421\u042B\u041B\u041A\u0418"]);
function extractFieldRefs(expr, aliasUp) {
  let toks;
  try {
    toks = tokenize(expr);
  } catch {
    return /* @__PURE__ */ new Set();
  }
  const sig = toks.filter((t) => t.type !== "eof");
  const refs = /* @__PURE__ */ new Set();
  let depth = 0;
  const metaDepths = [];
  for (let i = 0; i < sig.length; i++) {
    const t = sig[i];
    if (t.type === "punct" && t.value === "(") {
      const head = sig[i - 1];
      const hv = head ? (head.text ?? head.value).toUpperCase() : "";
      depth++;
      if (META_FUNCS.has(hv)) metaDepths.push(depth);
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      if (metaDepths.length && metaDepths[metaDepths.length - 1] === depth) metaDepths.pop();
      depth--;
      continue;
    }
    if (metaDepths.length) continue;
    if (t.type === "ident" || t.type === "keyword") {
      let j = i;
      const parts = [sig[j].value];
      while (j + 2 < sig.length && sig[j + 1].type === "punct" && sig[j + 1].value === "." && (sig[j + 2].type === "ident" || sig[j + 2].type === "keyword")) {
        parts.push(sig[j + 2].value);
        j += 2;
      }
      const after = sig[j + 1];
      const isCall = after && after.type === "punct" && after.value === "(";
      if (parts.length >= 2 && !isCall && aliasUp.has(parts[0].toUpperCase())) {
        refs.add(parts.join("."));
      }
      i = j;
    }
  }
  return refs;
}
function derefInResultPosition(expr, rendered) {
  const re = new RegExp(
    "(?:^|[^\\p{L}\\p{N}_.])(?:\u0422\u041E\u0413\u0414\u0410|\u0418\u041D\u0410\u0427\u0415)\\s+" + rendered.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&") + "(?![\\p{L}\\p{N}_.])",
    "u"
  );
  return re.test(expr);
}
function dropFunctionallyDeterminedMovementCase(model, resolver) {
  if (!resolver) return;
  const grouping = model.grouping;
  if (!grouping || grouping.multiple) return;
  const fields = grouping.groupFields;
  if (fields.length < 2) return;
  const explicitCount = grouping.explicitGroupCount ?? fields.length;
  const aliasUp = /* @__PURE__ */ new Set();
  for (const t of model.tables) aliasUp.add(defaultTableAlias(t).toUpperCase());
  const groupedUp = /* @__PURE__ */ new Set();
  for (let i = 0; i < explicitCount && i < fields.length; i++) {
    const f = fields[i];
    if (f.expression !== void 0 || !f.tableId || !f.path) continue;
    const t = model.tables.find((tb) => tb.id === f.tableId);
    groupedUp.add(((t ? defaultTableAlias(t) : f.tableId) + "." + f.path).toUpperCase());
  }
  const dropIdx = /* @__PURE__ */ new Set();
  for (let i = 0; i < explicitCount && i < fields.length; i++) {
    const f = fields[i];
    if (f.expression === void 0) continue;
    if (!MOVEMENT_RE.test(f.expression)) continue;
    const refs = extractFieldRefs(f.expression, aliasUp);
    if (refs.size === 0) continue;
    let allGrouped = true;
    let navThroughGroupedRef = false;
    for (const r of refs) {
      if (!groupedUp.has(r.toUpperCase())) {
        allGrouped = false;
        break;
      }
      const segs = r.split(".");
      for (let k = 2; k < segs.length; k++) {
        if (groupedUp.has(segs.slice(0, k).join(".").toUpperCase())) {
          navThroughGroupedRef = true;
          break;
        }
      }
    }
    if (allGrouped && !navThroughGroupedRef) dropIdx.add(i);
  }
  if (dropIdx.size === 0) return;
  const kept = [];
  let droppedBeforeExplicit = 0;
  for (let i = 0; i < fields.length; i++) {
    if (dropIdx.has(i)) {
      if (i < explicitCount) droppedBeforeExplicit++;
      continue;
    }
    kept.push(fields[i]);
  }
  grouping.groupFields = kept;
  grouping.explicitGroupCount = explicitCount - droppedBeforeExplicit;
}
function relocateKeptMovementCase(model, resolver) {
  if (!resolver) return;
  const grouping = model.grouping;
  if (!grouping || grouping.multiple) return;
  const fields = grouping.groupFields;
  if (fields.length < 2) return;
  const explicitCount = grouping.explicitGroupCount ?? fields.length;
  if (explicitCount < 2) return;
  const groupedUp = /* @__PURE__ */ new Set();
  for (let i = 0; i < explicitCount && i < fields.length; i++) {
    const f = fields[i];
    if (f.expression !== void 0 || !f.tableId || !f.path) continue;
    const t = model.tables.find((tb) => tb.id === f.tableId);
    groupedUp.add(((t ? defaultTableAlias(t) : f.tableId) + "." + f.path).toUpperCase());
  }
  const aliasUp = /* @__PURE__ */ new Set();
  for (const t of model.tables) aliasUp.add(defaultTableAlias(t).toUpperCase());
  let caseIdx = -1;
  for (let i = 0; i < explicitCount && i < fields.length; i++) {
    const f = fields[i];
    if (f.expression === void 0 || !MOVEMENT_RE.test(f.expression)) continue;
    const refs = extractFieldRefs(f.expression, aliasUp);
    if (refs.size === 0) continue;
    let allGrouped = true, navThroughGroupedRef = false;
    for (const r of refs) {
      if (!groupedUp.has(r.toUpperCase())) {
        allGrouped = false;
        break;
      }
      const segs = r.split(".");
      for (let k = 2; k < segs.length; k++) {
        if (groupedUp.has(segs.slice(0, k).join(".").toUpperCase())) {
          navThroughGroupedRef = true;
          break;
        }
      }
    }
    if (allGrouped && navThroughGroupedRef) {
      caseIdx = i;
      break;
    }
  }
  if (caseIdx < 0) return;
  const moveIdx = [caseIdx];
  for (let i = caseIdx + 1; i < explicitCount && i < fields.length; i++) {
    const f = fields[i];
    if (f.expression !== void 0 || !f.tableId || !f.path) continue;
    const segs = f.path.split(".");
    if (segs.length < 2) continue;
    const t = model.tables.find((tb) => tb.id === f.tableId);
    const alias = t ? defaultTableAlias(t) : f.tableId;
    let prefixGrouped = false;
    for (let k = 1; k < segs.length; k++) {
      if (groupedUp.has((alias + "." + segs.slice(0, k).join(".")).toUpperCase())) {
        prefixGrouped = true;
        break;
      }
    }
    if (prefixGrouped) moveIdx.push(i);
  }
  if (moveIdx.length === 0) return;
  const moveSet = new Set(moveIdx);
  const explicit = fields.slice(0, explicitCount);
  const rest = fields.slice(explicitCount);
  const head = explicit.filter((_, i) => !moveSet.has(i));
  const moved = moveIdx.map((i) => explicit[i]);
  grouping.groupFields = [...head, ...moved, ...rest];
  grouping.explicitGroupCount = explicitCount;
}

// src/core/query/canonicalizeFieldCasing.ts
function canonicalizeFieldCasing(model, resolver) {
  if (!resolver) return;
  const aliasToTable = /* @__PURE__ */ new Map();
  const idToTable = /* @__PURE__ */ new Map();
  for (const t of model.tables) {
    if (t.alias) aliasToTable.set(t.alias.toUpperCase(), t);
    idToTable.set(t.id, t);
  }
  for (const f of model.fields) {
    canonField(f, aliasToTable, resolver);
  }
  for (const c of model.conditions ?? []) canonCondition(c, idToTable, aliasToTable, resolver);
  for (const c of model.having ?? []) canonCondition(c, idToTable, aliasToTable, resolver);
  for (const j of model.joins ?? []) canonJoin(j, idToTable, aliasToTable, resolver);
}
function canonExprText(expr, aliasToTable, resolver) {
  const isWord2 = (c) => c !== void 0 && /[\p{L}\p{N}_]/u.test(c);
  let out = "";
  let inStr = false;
  let i = 0;
  const n = expr.length;
  while (i < n) {
    const c = expr[i];
    if (inStr) {
      out += c;
      if (c === '"') inStr = false;
      i++;
      continue;
    }
    if (c === '"') {
      inStr = true;
      out += c;
      i++;
      continue;
    }
    if (/[\p{L}_]/u.test(c) && !isWord2(expr[i - 1]) && expr[i - 1] !== ".") {
      let j = i;
      while (j < n && isWord2(expr[j])) j++;
      const segs = [expr.slice(i, j)];
      while (j < n && expr[j] === "." && j + 1 < n && /[\p{L}_]/u.test(expr[j + 1])) {
        const s = j + 1;
        let e = s;
        while (e < n && isWord2(expr[e])) e++;
        segs.push(expr.slice(s, e));
        j = e;
      }
      if (segs.length >= 2 && expr[j] !== "(") {
        const head = aliasToTable.get(segs[0].toUpperCase());
        if (head && !head.subquery && head.fullName && !head.fullName.startsWith("&")) {
          const meta = resolver.tableByFullName(head.fullName);
          if (meta) {
            const tailCanon = canonicalizeSegments(meta, segs.slice(1), resolver);
            if (tailCanon) {
              out += segs[0] + "." + tailCanon.join(".");
              i = j;
              continue;
            }
          }
        }
      }
      out += expr.slice(i, j);
      i = j;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}
function canonPath(tableId, path, idToTable, resolver) {
  if (!tableId || !path) return void 0;
  const src = idToTable.get(tableId);
  if (!src || src.subquery || !src.fullName) return void 0;
  if (src.fullName.startsWith("&")) return void 0;
  const meta = resolver.tableByFullName(src.fullName);
  if (!meta) return void 0;
  const canon = canonicalizeSegments(meta, path.split("."), resolver);
  return canon ? canon.join(".") : void 0;
}
function canonCondition(c, idToTable, aliasToTable, resolver) {
  if (c.leftExpr !== void 0) return;
  if (c.custom) {
    if (c.expression !== void 0 && !c.subquery) {
      c.expression = canonExprText(c.expression, aliasToTable, resolver);
    }
    return;
  }
  if (c.expression !== void 0) return;
  const np = canonPath(c.tableId, c.path, idToTable, resolver);
  if (np) c.path = np;
}
function canonJoin(j, idToTable, aliasToTable, resolver) {
  if (j.custom) {
    if (j.expression !== void 0) j.expression = canonExprText(j.expression, aliasToTable, resolver);
  } else if (j.expression === void 0) {
    const nl = canonPath(j.leftTableId, j.leftPath, idToTable, resolver);
    if (nl) j.leftPath = nl;
    const nr = canonPath(j.rightTableId, j.rightPath, idToTable, resolver);
    if (nr) j.rightPath = nr;
  }
  for (const cc of j.conditions ?? []) {
    if (cc.custom) {
      if (cc.expression !== void 0) cc.expression = canonExprText(cc.expression, aliasToTable, resolver);
      continue;
    }
    if (cc.expression !== void 0) continue;
    const nl = canonPath(cc.leftTableId, cc.leftPath, idToTable, resolver);
    if (nl) cc.leftPath = nl;
    const nr = canonPath(cc.rightTableId, cc.rightPath, idToTable, resolver);
    if (nr) cc.rightPath = nr;
  }
}
function canonField(f, aliasToTable, resolver) {
  if (f.expression !== void 0) return;
  if (!f.qualified) return;
  const src = [...aliasToTable.values()].find((x) => x.id === f.tableId);
  if (!src || src.subquery || !src.fullName) return;
  if (src.fullName.startsWith("&")) return;
  const meta = resolver.tableByFullName(src.fullName);
  if (!meta) return;
  const segs = f.path.split(".");
  const canon = canonicalizeSegments(meta, segs, resolver);
  if (canon) f.path = canon.join(".");
}
function canonicalizeSegments(meta, segs, resolver) {
  const out = [];
  let cur = meta;
  let changed = false;
  for (let i = 0; i < segs.length; i++) {
    if (!cur) {
      out.push(...segs.slice(i));
      break;
    }
    const field = findField3(cur, segs[i]);
    if (!field) {
      out.push(...segs.slice(i));
      break;
    }
    if (field.name !== segs[i]) changed = true;
    out.push(field.name);
    if (i === segs.length - 1) break;
    const ref = firstRef3(field);
    if (!ref) {
      out.push(...segs.slice(i + 1));
      break;
    }
    cur = resolver.tableByFullName(`${ref.kind}.${ref.name}`);
  }
  return changed ? out : void 0;
}
function findField3(meta, name) {
  const up3 = name.toUpperCase();
  return meta.fields.find((f) => f.name.toUpperCase() === up3);
}
function firstRef3(field) {
  for (const t of field.types) if (t.ref) return t.ref;
  return void 0;
}

// src/core/query/sdblParser.ts
setSubqueryParser((text2, r) => parseDocument(text2, r));
var sourceResolver;
var subquerySourceDepth = 0;
var AGG_KEYWORD_TO_FUNC = {
  \u0421\u0423\u041C\u041C\u0410: "\u0421\u0443\u043C\u043C\u0430",
  \u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E: "\u041A\u043E\u043B\u0438\u0447\u0435\u0441\u0442\u0432\u043E",
  \u041C\u0410\u041A\u0421\u0418\u041C\u0423\u041C: "\u041C\u0430\u043A\u0441\u0438\u043C\u0443\u043C",
  \u041C\u0418\u041D\u0418\u041C\u0423\u041C: "\u041C\u0438\u043D\u0438\u043C\u0443\u043C",
  \u0421\u0420\u0415\u0414\u041D\u0415\u0415: "\u0421\u0440\u0435\u0434\u043D\u0435\u0435"
};
var METADATA_KINDS = /* @__PURE__ */ new Set([
  "\u0421\u041F\u0420\u0410\u0412\u041E\u0427\u041D\u0418\u041A",
  "\u0414\u041E\u041A\u0423\u041C\u0415\u041D\u0422",
  "\u041A\u041E\u041D\u0421\u0422\u0410\u041D\u0422\u0410",
  "\u041F\u0415\u0420\u0415\u0427\u0418\u0421\u041B\u0415\u041D\u0418\u0415",
  "\u041F\u041B\u0410\u041D\u041E\u0411\u041C\u0415\u041D\u0410",
  "\u041F\u041B\u0410\u041D\u0412\u0418\u0414\u041E\u0412\u0425\u0410\u0420\u0410\u041A\u0422\u0415\u0420\u0418\u0421\u0422\u0418\u041A",
  "\u041F\u041B\u0410\u041D\u0421\u0427\u0415\u0422\u041E\u0412",
  "\u041F\u041B\u0410\u041D\u0412\u0418\u0414\u041E\u0412\u0420\u0410\u0421\u0427\u0415\u0422\u0410",
  "\u0411\u0418\u0417\u041D\u0415\u0421\u041F\u0420\u041E\u0426\u0415\u0421\u0421",
  "\u0417\u0410\u0414\u0410\u0427\u0410",
  "\u0420\u0415\u0413\u0418\u0421\u0422\u0420\u0421\u0412\u0415\u0414\u0415\u041D\u0418\u0419",
  "\u0420\u0415\u0413\u0418\u0421\u0422\u0420\u041D\u0410\u041A\u041E\u041F\u041B\u0415\u041D\u0418\u042F",
  "\u0420\u0415\u0413\u0418\u0421\u0422\u0420\u0411\u0423\u0425\u0413\u0410\u041B\u0422\u0415\u0420\u0418\u0418",
  "\u0420\u0415\u0413\u0418\u0421\u0422\u0420\u0420\u0410\u0421\u0427\u0415\u0422\u0410",
  "\u041F\u041E\u0421\u041B\u0415\u0414\u041E\u0412\u0410\u0422\u0415\u041B\u042C\u041D\u041E\u0421\u0422\u042C",
  "\u0416\u0423\u0420\u041D\u0410\u041B\u0414\u041E\u041A\u0423\u041C\u0415\u041D\u0422\u041E\u0412",
  "\u041A\u0420\u0418\u0422\u0415\u0420\u0418\u0419\u041E\u0422\u0411\u041E\u0420\u0410"
]);
var Cursor = class {
  constructor(tokens, source) {
    this.tokens = tokens;
    this.source = source;
  }
  idx = 0;
  peek(offset = 0) {
    const j = this.idx + offset;
    return this.tokens[Math.min(j, this.tokens.length - 1)];
  }
  /**
   * Все токены среза (включая уже поглощённые). Используется для построения
   * карты «поле → таблица-владелец» по квалифицированным вхождениям (фаза 6.15.4).
   */
  get allTokens() {
    return this.tokens;
  }
  next() {
    const t = this.tokens[this.idx];
    if (this.idx < this.tokens.length - 1) this.idx++;
    return t;
  }
  /** Проверяет, что следующий токен — keyword с данным значением, и поглощает его. */
  expectKeyword(value) {
    const t = this.peek();
    if (t.type !== "keyword" || t.value !== value) {
      throw this.error(`\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u043A\u043B\u044E\u0447\u0435\u0432\u043E\u0435 \u0441\u043B\u043E\u0432\u043E \xAB${value}\xBB`, t);
    }
    return this.next();
  }
  /** Поглощает keyword, если он есть; возвращает true при успехе. */
  matchKeyword(value) {
    const t = this.peek();
    if (t.type === "keyword" && t.value === value) {
      this.next();
      return true;
    }
    return false;
  }
  expectPunct(value) {
    const t = this.peek();
    if (t.type !== "punct" || t.value !== value) {
      throw this.error(`\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u0441\u0438\u043C\u0432\u043E\u043B \xAB${value}\xBB`, t);
    }
    return this.next();
  }
  matchPunct(value) {
    const t = this.peek();
    if (t.type === "punct" && t.value === value) {
      this.next();
      return true;
    }
    return false;
  }
  isPunct(value, offset = 0) {
    const t = this.peek(offset);
    return t.type === "punct" && t.value === value;
  }
  isKeyword(value, offset = 0) {
    const t = this.peek(offset);
    return t.type === "keyword" && t.value === value;
  }
  /** Проверяет, что дальше блок построителя `{<keyword>` (punct `{` + ключевое слово). */
  isBuilderBlock(keyword) {
    return this.isPunct("{") && this.isKeyword(keyword, 1);
  }
  /**
   * Дальше начинается РАСПОЗНАВАЕМЫЙ блок построителя (`{ГДЕ`/`{УПОРЯДОЧИТЬ`/
   * `{ИТОГИ`/`{ВЫБРАТЬ`). Читалки условий (ПО/ГДЕ/ИМЕЮЩИЕ) останавливаются перед
   * ним (фаза 6.15.7); прочие `{…}` (например `{ЛЕВОЕ СОЕДИНЕНИЕ …}`) пока
   * заглатываются как раньше — их разбор не реализован.
   */
  isBuilderStart() {
    return this.isBuilderBlock("\u0413\u0414\u0415") || this.isBuilderBlock("\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C") || this.isBuilderBlock("\u0418\u0422\u041E\u0413\u0418") || this.isBuilderBlock("\u0412\u042B\u0411\u0420\u0410\u0422\u042C");
  }
  /**
   * Дальше начинается ОПЦИОНАЛЬНОЕ соединение построителя `{<вид> СОЕДИНЕНИЕ …}`
   * (фаза 6.15.13): punct `{` + ключевое слово вида соединения
   * (ВНУТРЕННЕЕ/ЛЕВОЕ/ПРАВОЕ/ПОЛНОЕ).
   */
  isBuilderJoinStart() {
    if (!this.isPunct("{")) return false;
    const t = this.peek(1);
    return t.type === "keyword" && JOIN_KEYWORDS.has(t.value);
  }
  error(message, t = this.peek()) {
    return new Error(`\u041E\u0448\u0438\u0431\u043A\u0430 \u0440\u0430\u0437\u0431\u043E\u0440\u0430 ${t.line}:${t.col} \u2014 ${message} (\u043F\u043E\u043B\u0443\u0447\u0435\u043D\u043E \xAB${t.value || "<\u043A\u043E\u043D\u0435\u0446>"}\xBB)`);
  }
  /** Снимок позиции для отката (спекулятивный разбор). */
  mark() {
    return this.idx;
  }
  /** Откат позиции к снимку, снятому `mark()`. */
  reset(m) {
    this.idx = m;
  }
};
var AUTO_ALIAS = /^Поле\d+$/;
var BARE_PARAM_ALIAS = /^&([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)$/u;
function isImplicitSourceHead(tokens, i) {
  const t = tokens[i];
  if (!isNameToken(t)) return false;
  if (!METADATA_KINDS.has(t.text.toUpperCase())) return false;
  const prev = tokens[i - 1];
  if (prev && prev.type === "punct" && prev.value === ".") return false;
  const prevUp = prev && (prev.type === "ident" || prev.type === "keyword") ? prev.text.toUpperCase() : void 0;
  if (prevUp === "\u041A\u0410\u041A" || prevUp === "\u0421\u0421\u042B\u041B\u041A\u0410") return false;
  if (!(tokens[i + 1]?.type === "punct" && tokens[i + 1].value === "." && isNameToken(tokens[i + 2]) && tokens[i + 3]?.type === "punct" && tokens[i + 3].value === ".")) {
    return false;
  }
  const after = tokens[i + 4];
  return isNameToken(after) || after?.type === "punct" && after.value === "*";
}
function synthesizeImplicitFrom(cur) {
  const tokens = cur.allTokens;
  if (!(tokens[0]?.type === "keyword" && tokens[0].value === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C")) return cur;
  let depth = 0;
  let insertBeforePos;
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && (t.value === "(" || t.value === "{")) {
      depth++;
      continue;
    }
    if (t.type === "punct" && (t.value === ")" || t.value === "}")) {
      depth--;
      continue;
    }
    if (depth !== 0) continue;
    if (t.type === "keyword" && t.value === "\u0418\u0417") return cur;
    if (insertBeforePos === void 0 && t.type === "keyword" && SECTION_AFTER_FIELDS.has(t.value)) {
      insertBeforePos = t.pos;
    }
  }
  const tableNames = /* @__PURE__ */ new Map();
  let skipUntilDepth;
  depth = 0;
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && (t.value === "(" || t.value === "{")) {
      depth++;
      continue;
    }
    if (t.type === "punct" && (t.value === ")" || t.value === "}")) {
      depth--;
      if (skipUntilDepth !== void 0 && depth < skipUntilDepth) skipUntilDepth = void 0;
      continue;
    }
    if (skipUntilDepth !== void 0) continue;
    if (!isNameToken(t)) continue;
    const up3 = t.text.toUpperCase();
    if ((up3 === "\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415" || up3 === "\u0422\u0418\u041F") && tokens[i + 1]?.type === "punct" && tokens[i + 1].value === "(") {
      skipUntilDepth = depth + 1;
      continue;
    }
    if (!isImplicitSourceHead(tokens, i)) continue;
    const fullName = `${t.text}.${tokens[i + 2].text}`;
    tableNames.set(fullName.toUpperCase(), fullName);
  }
  if (tableNames.size === 0) return cur;
  const sources = [...tableNames.values()].map((fullName) => ({
    fullName,
    alias: fullName.slice(fullName.indexOf(".") + 1)
  }));
  const aliasSeen = /* @__PURE__ */ new Set();
  for (const s of sources) {
    const a = s.alias.toUpperCase();
    if (aliasSeen.has(a)) return cur;
    aliasSeen.add(a);
  }
  sources.sort((a, b) => a.alias.localeCompare(b.alias, "ru"));
  const start = tokens[0].pos;
  const lastReal = tokens[tokens.length - 1].type === "eof" ? tokens[tokens.length - 2] : tokens[tokens.length - 1];
  const end = lastReal.pos + lastReal.value.length;
  const edits = [];
  depth = 0;
  skipUntilDepth = void 0;
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && (t.value === "(" || t.value === "{")) {
      depth++;
      continue;
    }
    if (t.type === "punct" && (t.value === ")" || t.value === "}")) {
      depth--;
      if (skipUntilDepth !== void 0 && depth < skipUntilDepth) skipUntilDepth = void 0;
      continue;
    }
    if (skipUntilDepth !== void 0) continue;
    if (!isNameToken(t)) continue;
    const up3 = t.text.toUpperCase();
    if ((up3 === "\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415" || up3 === "\u0422\u0418\u041F") && tokens[i + 1]?.type === "punct" && tokens[i + 1].value === "(") {
      skipUntilDepth = depth + 1;
      continue;
    }
    if (!isImplicitSourceHead(tokens, i)) continue;
    if (!tableNames.has(`${t.text}.${tokens[i + 2].text}`.toUpperCase())) continue;
    edits.push({ pos: t.pos, len: tokens[i + 2].pos - t.pos });
  }
  const fromText = "\n\u0418\u0417\n" + sources.map((s) => `	${s.fullName} \u041A\u0410\u041A ${s.alias}`).join(",\n") + "\n";
  const insertAt = insertBeforePos ?? end;
  let out = "";
  let p = start;
  let inserted = false;
  const maybeInsert = (upto) => {
    if (!inserted && insertAt <= upto) {
      out += cur.source.slice(p, insertAt) + fromText;
      p = insertAt;
      inserted = true;
    }
  };
  for (const e of edits) {
    maybeInsert(e.pos);
    out += cur.source.slice(p, e.pos);
    p = e.pos + e.len;
  }
  maybeInsert(end);
  out += cur.source.slice(p, end);
  if (!inserted) out += fromText;
  return new Cursor(tokenize(out), out);
}
function synthesizeTempTableFrom(cur) {
  const tokens = cur.allTokens;
  if (!(tokens[0]?.type === "keyword" && tokens[0].value === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C")) return cur;
  const resolver = sourceResolver;
  if (!resolver) return cur;
  let depth = 0;
  let insertBeforePos;
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && (t.value === "(" || t.value === "{")) {
      depth++;
      continue;
    }
    if (t.type === "punct" && (t.value === ")" || t.value === "}")) {
      depth--;
      continue;
    }
    if (depth !== 0) continue;
    if (t.type === "keyword" && t.value === "\u0418\u0417") return cur;
    if (insertBeforePos === void 0 && t.type === "keyword" && SECTION_AFTER_FIELDS.has(t.value)) {
      insertBeforePos = t.pos;
    }
  }
  const heads = /* @__PURE__ */ new Set();
  depth = 0;
  let skipUntilDepth;
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && (t.value === "(" || t.value === "{")) {
      depth++;
      continue;
    }
    if (t.type === "punct" && (t.value === ")" || t.value === "}")) {
      depth--;
      if (skipUntilDepth !== void 0 && depth < skipUntilDepth) skipUntilDepth = void 0;
      continue;
    }
    if (skipUntilDepth !== void 0) continue;
    if (depth === 0 && t.type === "keyword" && SECTION_AFTER_FIELDS.has(t.value)) break;
    if (!isNameToken(t)) continue;
    const up3 = t.text.toUpperCase();
    if ((up3 === "\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415" || up3 === "\u0422\u0418\u041F") && tokens[i + 1]?.type === "punct" && tokens[i + 1].value === "(") {
      skipUntilDepth = depth + 1;
      continue;
    }
    if (t.type === "keyword" && (up3 === "\u041A\u0410\u041A" || up3 === "\u0421\u0421\u042B\u041B\u041A\u0410")) {
      i++;
      continue;
    }
    if (t.type === "keyword") continue;
    if (depth !== 0) continue;
    const prev = tokens[i - 1];
    if (prev && prev.type === "punct" && prev.value === ".") continue;
    if (tokens[i + 1]?.type === "punct" && tokens[i + 1].value === "(") return cur;
    if (tokens[i + 1]?.type === "punct" && tokens[i + 1].value === "." && isNameToken(tokens[i + 2])) {
      heads.add(t.text);
      continue;
    }
    return cur;
  }
  if (heads.size !== 1) return cur;
  const name = [...heads][0];
  if (name.includes(".")) return cur;
  if (!resolver.tableByFullName(name)) return cur;
  const canonical = resolver.canonicalFullName?.(name) ?? name;
  const start = tokens[0].pos;
  const lastReal = tokens[tokens.length - 1].type === "eof" ? tokens[tokens.length - 2] : tokens[tokens.length - 1];
  const end = lastReal.pos + lastReal.value.length;
  const fromText = `
\u0418\u0417
	${canonical} \u041A\u0410\u041A ${canonical}
`;
  const insertAt = insertBeforePos ?? end;
  const out = cur.source.slice(start, insertAt) + fromText + cur.source.slice(insertAt, end);
  return new Cursor(tokenize(out), out);
}
var SECTION_AFTER_FIELDS = /* @__PURE__ */ new Set([
  "\u0413\u0414\u0415",
  "\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0418\u041C\u0415\u042E\u0429\u0418\u0415",
  "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C",
  "\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415",
  "\u0418\u0422\u041E\u0413\u0418",
  "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0414\u041B\u042F",
  "\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C",
  "\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C"
]);
function parseSingleQuery(cur, inheritedSectionCtx, ctxOut) {
  cur = synthesizeImplicitFrom(cur);
  cur = synthesizeTempTableFrom(cur);
  if (cur.isKeyword("\u0423\u041D\u0418\u0427\u0422\u041E\u0416\u0418\u0422\u042C")) {
    cur.next();
    const name = parseDottedName(cur);
    return { tables: [], fields: [], queryType: "dropTemp", tempTableName: name };
  }
  const builder = { fields: [], conditions: [], order: [], totals: [] };
  cur.expectKeyword("\u0412\u042B\u0411\u0420\u0410\u0422\u042C");
  const selection = parseSelectionModifiers(cur);
  const items = parseFieldList(cur);
  if (cur.isBuilderBlock("\u0412\u042B\u0411\u0420\u0410\u0422\u042C")) {
    builder.fields = parseBuilderBlock(cur, "\u0412\u042B\u0411\u0420\u0410\u0422\u042C");
  }
  let queryType;
  let tempTableName;
  if (cur.matchKeyword("\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C")) {
    queryType = "createTemp";
    tempTableName = parseDottedName(cur);
  } else if (cur.matchKeyword("\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C")) {
    queryType = "appendTemp";
    tempTableName = parseDottedName(cur);
  }
  if (builder.fields.length === 0 && cur.isBuilderBlock("\u0412\u042B\u0411\u0420\u0410\u0422\u042C")) {
    builder.fields = parseBuilderBlock(cur, "\u0412\u042B\u0411\u0420\u0410\u0422\u042C");
  }
  const from = cur.matchKeyword("\u0418\u0417") ? parseFrom(cur) : { tables: [], joins: [] };
  const tables = from.tables;
  const joins = from.joins;
  const aliasToId = /* @__PURE__ */ new Map();
  const aliasSpelling = /* @__PURE__ */ new Map();
  for (const t of tables) {
    if (t.alias) {
      aliasToId.set(t.alias.toUpperCase(), t.id);
      aliasSpelling.set(t.alias.toUpperCase(), t.alias);
    }
  }
  const fields = [];
  const aggregates = [];
  const tabSectionFields = [];
  const trailingFields = [];
  const soleSource = soleSourceOf(tables, joins);
  const fieldOwners = buildFieldOwnerScan(cur.allTokens, aliasToId);
  const tableFullNames = new Map(tables.map((t) => [t.id, t.fullName]));
  const resolveOwner = (head) => {
    if (soleSource) return soleSource.id;
    const owners = fieldOwners.get(head.toUpperCase());
    if (owners && owners.size === 1) return owners.values().next().value;
    if (sourceResolver && (!owners || owners.size === 0)) {
      const up3 = head.toUpperCase();
      let hit;
      let count = 0;
      for (const t of tables) {
        if (t.subquery || !t.fullName || t.fullName.startsWith("&")) continue;
        const meta = sourceResolver.tableByFullName(t.fullName);
        if (meta && meta.fields.some((f) => f.name.toUpperCase() === up3)) {
          count++;
          hit = t.id;
        }
      }
      if (count === 1) return hit;
    }
    return void 0;
  };
  const explicitAliases = /* @__PURE__ */ new Set();
  for (const item of items) {
    if (item.kind === "field" && item.field.alias !== void 0) {
      explicitAliases.add(item.field.alias.toUpperCase());
    } else if (item.kind === "tabSection") {
      if (item.ts.alias) explicitAliases.add(item.ts.alias.toUpperCase());
      for (const col of item.ts.columns) {
        const colAlias = col.kind === "field" ? col.alias ?? col.field : col.alias;
        if (colAlias !== void 0) explicitAliases.add(colAlias.toUpperCase());
      }
    }
  }
  let sawTabSection = false;
  const tagOrder = items.some((it) => it.kind === "tabSection");
  let selectOrder = 0;
  for (const item of items) {
    if (item.kind === "tabSection") {
      const ts = resolveTabSection(item.ts, aliasToId, tables, aliasSpelling);
      if (tagOrder) ts.selectOrder = selectOrder;
      selectOrder++;
      sawTabSection = true;
      tabSectionFields.push(ts);
      continue;
    }
    const target = sawTabSection ? trailingFields : fields;
    const before = target.length;
    interpretField(item.field, aliasToId, target, aggregates, resolveOwner, tableFullNames);
    if (tagOrder) for (let k = before; k < target.length; k++) target[k].selectOrder = selectOrder;
    selectOrder++;
  }
  const resolvedJoins = joins.map((j) => resolveJoin(j, aliasToId, cur.source));
  let conditions;
  if (cur.isKeyword("\u0413\u0414\u0415")) {
    conditions = parseWhere(cur, aliasToId, soleSource, aliasSpelling);
  }
  const readBuilderWhere = () => {
    while (cur.isBuilderBlock("\u0413\u0414\u0415")) {
      const block = parseBuilderBlock(cur, "\u0413\u0414\u0415");
      let exprNo = 0;
      for (const f of block) {
        if (!f.condition) continue;
        if (f.alias || /^&[\p{L}\p{N}_]+$/u.test(f.ref)) continue;
        exprNo += 1;
        f.alias = `\u041F\u043E\u043B\u0435${2 * exprNo}`;
      }
      builder.conditions.push(...block);
    }
  };
  if (cur.isBuilderBlock("\u0413\u0414\u0415")) {
    readBuilderWhere();
  }
  let groupingFromClause;
  if (cur.isKeyword("\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C")) {
    groupingFromClause = parseGroupBy(cur, aliasToId, resolveOwner);
  }
  let having;
  if (cur.isKeyword("\u0418\u041C\u0415\u042E\u0429\u0418\u0415")) {
    having = parseHaving(cur, aliasToId);
  }
  if (builder.conditions.length === 0 && cur.isBuilderBlock("\u0413\u0414\u0415")) {
    readBuilderWhere();
  }
  if (cur.isBuilderBlock("\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C")) {
    builder.order = parseBuilderBlock(cur, "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C");
  }
  if (cur.isBuilderBlock("\u0418\u0422\u041E\u0413\u0418")) {
    builder.totals = parseBuilderBlock(cur, "\u0418\u0422\u041E\u0413\u0418");
  }
  let lockForUpdate;
  if (cur.isKeyword("\u0414\u041B\u042F")) {
    lockForUpdate = parseLockForUpdate(cur);
  }
  const model = { tables, fields };
  if (selection) model.selection = selection;
  if (queryType) {
    model.queryType = queryType;
    if (tempTableName) model.tempTableName = tempTableName;
  }
  if (tabSectionFields.length > 0) model.tabSectionFields = tabSectionFields;
  if (trailingFields.length > 0) model.trailingFields = trailingFields;
  if (resolvedJoins.length > 0) model.joins = resolvedJoins;
  if (conditions && conditions.length > 0) model.conditions = conditions;
  if (having && having.length > 0) model.having = having;
  if (lockForUpdate && lockForUpdate.length > 0) model.lockForUpdate = lockForUpdate;
  else if (lockForUpdate !== void 0) model.lockForUpdateBare = true;
  if (aggregates.length > 0 || groupingFromClause) {
    const grouping = {
      multiple: groupingFromClause?.multiple ?? false,
      groupFields: groupingFromClause?.groupFields ?? [],
      groupSets: groupingFromClause?.groupSets ?? [],
      aggregates,
      // Граница ЯВНОЙ части группировки — до автодописанных ниже расширений выборки.
      explicitGroupCount: groupingFromClause?.groupFields.length ?? 0
    };
    if (!grouping.multiple && groupingFromClause && !groupingFromClause.multiple) {
      const baseRefs = grouping.groupFields.filter((g) => g.expression === void 0);
      const present = new Set(baseRefs.map((g) => `${g.tableId} ${g.path}`));
      const keyedTables = new Set(baseRefs.filter((g) => g.path === "\u0421\u0441\u044B\u043B\u043A\u0430").map((g) => g.tableId));
      const candidates = [...fields, ...model.trailingFields ?? []];
      for (const f of candidates) {
        if (f.func !== void 0 || f.expression !== void 0) continue;
        if (f.tableId === "" || f.path === "") continue;
        const key = `${f.tableId} ${f.path}`;
        if (present.has(key)) continue;
        const isExtension = baseRefs.some(
          (g) => g.tableId === f.tableId && f.path.startsWith(`${g.path}.`)
        );
        const isKeyDependent = keyedTables.has(f.tableId);
        if (!isExtension && !isKeyDependent) continue;
        present.add(key);
        grouping.groupFields.push({ tableId: f.tableId, path: f.path });
      }
    }
    model.grouping = grouping;
  }
  const selectAliasMap = buildSelectAliasMap(model);
  const ownSectionCtx = {
    aliasMap: selectAliasMap,
    aliasToId,
    explicitAliases,
    fields: model.fields,
    resolveOwner
  };
  if (ctxOut) ctxOut.ctx = ownSectionCtx;
  const sectionCtx = inheritedSectionCtx ?? ownSectionCtx;
  if (cur.isKeyword("\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C") || cur.isKeyword("\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415")) {
    model.order = parseOrder(cur, sectionCtx);
  }
  if (cur.isKeyword("\u0418\u0422\u041E\u0413\u0418")) {
    model.totals = parseTotals(cur, sectionCtx);
  }
  if (cur.isKeyword("\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415")) {
    cur.next();
    if (model.order) model.order.auto = true;
    else model.order = { fields: [], auto: true };
  }
  if (cur.isKeyword("\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C")) {
    model.indexing = parseIndex(cur, sectionCtx);
  }
  if (cur.isPunct("{") && cur.peek(1).type === "ident" && cur.peek(1).value.toUpperCase() === "\u0425\u0410\u0420\u0410\u041A\u0422\u0415\u0420\u0418\u0421\u0422\u0418\u041A\u0418") {
    const open = cur.peek();
    let depth = 0;
    let end = open.pos;
    for (; ; ) {
      const t = cur.peek();
      if (t.type === "eof") break;
      if (t.type === "punct" && t.value === "{") depth++;
      else if (t.type === "punct" && t.value === "}") {
        depth--;
        cur.next();
        if (depth === 0) {
          end = t.pos + t.value.length;
          break;
        }
        continue;
      }
      cur.next();
    }
    model.characteristics = cur.source.slice(open.pos, end);
  }
  if (builder.fields.length || builder.conditions.length || builder.order.length || builder.totals.length) {
    model.builder = builder;
  }
  return model;
}
function buildSelectAliasMap(model) {
  const map = /* @__PURE__ */ new Map();
  for (const f of model.fields) {
    if (f.expression) continue;
    if (!f.path) continue;
    const key = f.alias ?? (f.path.split(".").pop() ?? f.path);
    if (!map.has(key)) map.set(key, { tableId: f.tableId, path: f.path });
  }
  return map;
}
function resolveSelectAlias(alias, map) {
  const hit = map.get(alias);
  if (hit) return { tableId: hit.tableId, path: hit.path };
  return { tableId: "", path: alias };
}
function parseSelectionModifiers(cur) {
  const selection = {};
  let any = false;
  for (; ; ) {
    if (selection.allowed === void 0 && cur.matchKeyword("\u0420\u0410\u0417\u0420\u0415\u0428\u0415\u041D\u041D\u042B\u0415")) {
      selection.allowed = true;
      any = true;
      continue;
    }
    if (selection.distinct === void 0 && cur.matchKeyword("\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415")) {
      selection.distinct = true;
      any = true;
      continue;
    }
    if (selection.top === void 0 && cur.matchKeyword("\u041F\u0415\u0420\u0412\u042B\u0415")) {
      const t = cur.peek();
      if (t.type !== "number") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u0447\u0438\u0441\u043B\u043E \u043F\u043E\u0441\u043B\u0435 \u041F\u0415\u0420\u0412\u042B\u0415", t);
      cur.next();
      selection.top = Number(t.value);
      any = true;
      continue;
    }
    break;
  }
  return any ? selection : void 0;
}
function parseFieldList(cur) {
  const items = [];
  for (; ; ) {
    if (cur.isPunct("{") || cur.isKeyword("\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C") || cur.isKeyword("\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C") || cur.isKeyword("\u0418\u0417")) {
      break;
    }
    const ts = tryParseTabSection(cur);
    if (ts) {
      items.push({ kind: "tabSection", ts });
    } else {
      items.push({ kind: "field", field: parseOneField(cur) });
    }
    if (cur.matchPunct(",")) continue;
    break;
  }
  if (items.length === 0) throw cur.error("\u043F\u0443\u0441\u0442\u043E\u0439 \u0441\u043F\u0438\u0441\u043E\u043A \u0432\u044B\u0431\u043E\u0440\u043A\u0438", cur.peek());
  return items;
}
function tryParseCastTabSection(cur) {
  const head = cur.peek(0);
  if (head.type !== "ident" || head.text.toUpperCase() !== "\u0412\u042B\u0420\u0410\u0417\u0418\u0422\u042C") return void 0;
  if (!cur.isPunct("(", 1)) return void 0;
  let off = 1;
  let depth = 0;
  for (; ; ) {
    const t = cur.peek(off);
    if (t.type === "eof") return void 0;
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") {
      depth--;
      if (depth === 0) break;
    }
    off++;
  }
  const castEndOff = off;
  off++;
  if (!(cur.peek(off).type === "punct" && cur.peek(off).value === ".")) return void 0;
  off++;
  let segCount = 0;
  for (; ; ) {
    const nameTok = cur.peek(off);
    if (nameTok.type !== "ident" && nameTok.type !== "keyword") return void 0;
    if (!(cur.peek(off + 1).type === "punct" && cur.peek(off + 1).value === ".")) return void 0;
    segCount++;
    if (cur.peek(off + 2).type === "punct" && cur.peek(off + 2).value === "(") break;
    off += 2;
  }
  if (segCount < 1) return void 0;
  const castStartTok = cur.peek(0);
  const castEndTok = cur.peek(castEndOff);
  const castPrefix = cur.source.slice(castStartTok.pos, castEndTok.pos + castEndTok.value.length);
  for (let k = 0; k <= castEndOff; k++) cur.next();
  cur.expectPunct(".");
  const tsSegs = [];
  for (; ; ) {
    tsSegs.push(cur.next().text);
    cur.expectPunct(".");
    if (cur.isPunct("(")) break;
  }
  const tsName = tsSegs.join(".");
  cur.expectPunct("(");
  const columns = [];
  for (; ; ) {
    columns.push(parseTabColumn(cur, tsName, ""));
    if (cur.matchPunct(",")) continue;
    break;
  }
  cur.expectPunct(")");
  let alias;
  if (cur.matchKeyword("\u041A\u0410\u041A")) {
    const a = cur.peek();
    if (a.type === "ident" || a.type === "keyword") {
      alias = a.text;
      cur.next();
    }
  }
  return { tableAlias: "", tsName, columns, alias, castPrefix };
}
function tryParseTabSection(cur) {
  const cast = tryParseCastTabSection(cur);
  if (cast) return cast;
  if (cur.peek(0).type !== "ident" && cur.peek(0).type !== "keyword") return void 0;
  if (!cur.isPunct(".", 1)) return void 0;
  let off = 0;
  let segCount = 0;
  for (; ; ) {
    const nameTok = cur.peek(off);
    if (nameTok.type !== "ident" && nameTok.type !== "keyword") return void 0;
    if (!cur.isPunct(".", off + 1)) return void 0;
    segCount++;
    if (cur.isPunct("(", off + 2)) {
      if (segCount < 2) return void 0;
      break;
    }
    off += 2;
  }
  const tableAlias = cur.next().text;
  cur.expectPunct(".");
  const tsSegs = [];
  for (; ; ) {
    tsSegs.push(cur.next().text);
    cur.expectPunct(".");
    if (cur.isPunct("(")) break;
  }
  const tsName = tsSegs.join(".");
  cur.expectPunct("(");
  const columns = [];
  for (; ; ) {
    const col = parseTabColumn(cur, tsName, tableAlias);
    columns.push(col);
    if (cur.matchPunct(",")) continue;
    break;
  }
  cur.expectPunct(")");
  let alias;
  if (cur.matchKeyword("\u041A\u0410\u041A")) {
    const a = cur.peek();
    if (a.type === "ident" || a.type === "keyword") {
      alias = a.text;
      cur.next();
    }
  }
  return { tableAlias, tsName, columns, alias };
}
function parseTabColumn(cur, tsName, tableAlias) {
  const start = cur.peek();
  if (start.type === "eof") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u043F\u043E\u043B\u0435 \u0442\u0430\u0431\u043B\u0438\u0447\u043D\u043E\u0439 \u0447\u0430\u0441\u0442\u0438", start);
  const mark = cur.mark();
  if (start.type === "ident" || start.type === "keyword") {
    const segs = [start.text];
    cur.next();
    let ok = true;
    while (cur.isPunct(".")) {
      cur.next();
      const seg = cur.peek();
      if (seg.type !== "ident" && seg.type !== "keyword") {
        ok = false;
        break;
      }
      cur.next();
      segs.push(seg.text);
    }
    const after = cur.peek();
    const atBoundary = after.type === "eof" || after.type === "punct" && (after.value === "," || after.value === ")") || after.type === "keyword" && after.value === "\u041A\u0410\u041A";
    if (ok && atBoundary) {
      let body = segs;
      if (body.length > 1 && body[0].toUpperCase() === tableAlias.toUpperCase()) body = body.slice(1);
      if (body.length > 1 && body[0].toUpperCase() === tsName.toUpperCase()) body = body.slice(1);
      const fieldText = body.join(".");
      let colAlias;
      if (cur.matchKeyword("\u041A\u0410\u041A")) {
        const a = cur.peek();
        if (a.type !== "ident" && a.type !== "keyword") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u043B\u044F \u043F\u043E\u0441\u043B\u0435 \u041A\u0410\u041A", a);
        cur.next();
        colAlias = a.text;
      }
      return {
        kind: "field",
        field: fieldText,
        alias: colAlias !== void 0 && colAlias !== fieldText ? colAlias : void 0,
        aliasExplicit: colAlias !== void 0
      };
    }
  }
  cur.reset(mark);
  const bodyTokens = [];
  let alias;
  let depth = 0;
  for (; ; ) {
    const t = cur.peek();
    if (t.type === "eof") break;
    if (depth === 0) {
      if (t.type === "punct" && (t.value === "," || t.value === ")")) break;
      if (t.type === "keyword" && t.value === "\u041A\u0410\u041A") {
        cur.next();
        const a = cur.peek();
        if (a.type !== "ident" && a.type !== "keyword") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u0441\u043B\u0435 \u041A\u0410\u041A", a);
        cur.next();
        alias = a.text;
        break;
      }
    }
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    bodyTokens.push(cur.next());
  }
  if (bodyTokens.length === 0) throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u043F\u043E\u043B\u0435 \u0442\u0430\u0431\u043B\u0438\u0447\u043D\u043E\u0439 \u0447\u0430\u0441\u0442\u0438", cur.peek());
  return { kind: "expr", rawBody: sliceSource(cur.source, bodyTokens), alias };
}
function parseOneField(cur) {
  const bodyTokens = [];
  let alias;
  let depth = 0;
  for (; ; ) {
    const t = cur.peek();
    if (t.type === "eof") break;
    if (depth === 0) {
      if (t.type === "punct" && t.value === ",") break;
      if (t.type === "punct" && t.value === "{") break;
      if (t.type === "keyword" && (t.value === "\u0418\u0417" || t.value === "\u041F\u041E\u041C\u0415\u0421\u0422\u0418\u0422\u042C" || t.value === "\u0414\u041E\u0411\u0410\u0412\u0418\u0422\u042C")) break;
      if (t.type === "keyword" && (t.value === "\u0413\u0414\u0415" || t.value === "\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C" || t.value === "\u0418\u041C\u0415\u042E\u0429\u0418\u0415" || t.value === "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C" || t.value === "\u0418\u0422\u041E\u0413\u0418" || t.value === "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C" || t.value === "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C" || t.value === "\u0414\u041B\u042F") && !cur.isPunct(".", 1)) break;
      if (t.type === "keyword" && t.value === "\u041A\u0410\u041A") {
        cur.next();
        const a = cur.peek();
        if (a.type !== "ident" && a.type !== "keyword") {
          throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u0441\u043B\u0435 \u041A\u0410\u041A", a);
        }
        cur.next();
        alias = a.text;
        break;
      }
    }
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    bodyTokens.push(cur.next());
  }
  if (bodyTokens.length === 0) {
    throw cur.error("\u043F\u0443\u0441\u0442\u043E\u0439 \u044D\u043B\u0435\u043C\u0435\u043D\u0442 \u0432\u044B\u0431\u043E\u0440\u043A\u0438", cur.peek());
  }
  if (alias === void 0 && bodyTokens.length >= 2 && depth === 0) {
    const last = bodyTokens[bodyTokens.length - 1];
    const prev = bodyTokens[bodyTokens.length - 2];
    const lastIsBareName = last.type === "ident" && !last.value.startsWith("#") && !EXPR_STOP_WORDS.has(last.value.toUpperCase());
    const prevEndsPrimary = prev.type === "string" || prev.type === "number" || prev.type === "date" || prev.type === "param" || prev.type === "ident" || prev.type === "punct" && prev.value === ")";
    if (lastIsBareName && prevEndsPrimary) {
      alias = last.text;
      bodyTokens.pop();
    }
  }
  for (let i = 0; i + 1 < bodyTokens.length; i++) {
    const a = bodyTokens[i];
    const b = bodyTokens[i + 1];
    if (a.type === "ident" && b.type === "ident" && !EXPR_STOP_WORDS.has(a.value.toUpperCase()) && !EXPR_STOP_WORDS.has(b.value.toUpperCase())) {
      throw cur.error("\u0434\u0432\u0430 \u0438\u0434\u0435\u043D\u0442\u0438\u0444\u0438\u043A\u0430\u0442\u043E\u0440\u0430 \u043F\u043E\u0434\u0440\u044F\u0434 \u0432 \u044D\u043B\u0435\u043C\u0435\u043D\u0442\u0435 \u0432\u044B\u0431\u043E\u0440\u043A\u0438 (\u043F\u0440\u043E\u043F\u0443\u0449\u0435\u043D\u044B \u043E\u043F\u0435\u0440\u0430\u0442\u043E\u0440 \u0438\u043B\u0438 \u0442\u043E\u0447\u043A\u0430?)", b);
    }
  }
  if (bodyTokens.length >= 2) {
    const last = bodyTokens[bodyTokens.length - 1];
    const prev = bodyTokens[bodyTokens.length - 2];
    const lastUp = last.type === "ident" ? last.value.toUpperCase() : "";
    const lastIsConnector = last.type === "ident" && EXPR_STOP_WORDS.has(lastUp) && !EXPR_TERMINATOR_WORDS.has(lastUp);
    const prevEndsPrimary = prev.type === "string" || prev.type === "number" || prev.type === "date" || prev.type === "param" || prev.type === "ident" || prev.type === "punct" && prev.value === ")";
    if (lastIsConnector && prevEndsPrimary) {
      throw cur.error("\u043D\u0435\u043A\u043E\u0440\u0440\u0435\u043A\u0442\u043D\u044B\u0439 \u044D\u043B\u0435\u043C\u0435\u043D\u0442 \u0432\u044B\u0431\u043E\u0440\u043A\u0438: \u043B\u0438\u0448\u043D\u0438\u0439 \u0438\u0434\u0435\u043D\u0442\u0438\u0444\u0438\u043A\u0430\u0442\u043E\u0440 \u0438\u043B\u0438 \u043D\u0435\u0437\u0430\u0432\u0435\u0440\u0448\u0451\u043D\u043D\u043E\u0435 \u0432\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435", last);
    }
  }
  const rawBody = sliceSource(cur.source, bodyTokens);
  return { bodyTokens, alias, rawBody };
}
function resolveTabSection(ts, aliasToId, tables, aliasSpelling) {
  const tableId = aliasToId.get(ts.tableAlias.toUpperCase()) ?? "";
  const table = tables.find((t) => t.id === tableId);
  const tsFullName = table ? `${table.fullName}.${ts.tsName}` : ts.tsName;
  if (ts.castPrefix !== void 0) {
    const fields2 = ts.columns.map((c) => c.kind === "field" ? c.field : c.rawBody);
    const fieldAliases2 = ts.columns.map((c) => c.alias);
    const fieldAliasExplicit2 = ts.columns.map((c) => c.kind === "field" ? c.aliasExplicit === true : false);
    return {
      tableId,
      tsName: ts.tsName,
      tsFullName,
      fields: fields2,
      alias: ts.alias,
      castPrefix: ts.castPrefix,
      ...fieldAliases2.some((a) => a !== void 0) ? { fieldAliases: fieldAliases2 } : {},
      ...fieldAliasExplicit2.some(Boolean) ? { fieldAliasExplicit: fieldAliasExplicit2 } : {}
    };
  }
  const hasExpr = ts.columns.some((c) => c.kind === "expr");
  const tableAliasUp = ts.tableAlias.toUpperCase();
  const prefix = `${ts.tableAlias}.${ts.tsName}`;
  const columns = ts.columns.map((c) => {
    if (c.kind === "field") return { kind: "field", field: c.field, alias: c.alias, aliasExplicit: c.aliasExplicit };
    const expression = requalifyTabSectionExpr(c.rawBody, prefix, aliasSpelling, tableAliasUp, ts.tsName);
    return { kind: "expr", expression, alias: c.alias };
  });
  const fields = ts.columns.filter((c) => c.kind === "field").map((c) => c.field);
  const fieldAliases = ts.columns.filter((c) => c.kind === "field").map((c) => c.alias);
  const fieldAliasExplicit = ts.columns.filter((c) => c.kind === "field").map((c) => c.aliasExplicit === true);
  const hasColAlias = fieldAliases.some((a) => a !== void 0);
  const hasExplicit = fieldAliasExplicit.some(Boolean);
  return {
    tableId,
    tsName: ts.tsName,
    tsFullName,
    fields,
    alias: ts.alias,
    ...hasColAlias ? { fieldAliases } : {},
    ...hasExplicit ? { fieldAliasExplicit } : {},
    ...hasExpr ? { columns } : {}
  };
}
function requalifyTabSectionExpr(rawBody, prefix, aliasSpelling, tableAliasUp, tsName) {
  const tokens = tokenize(rawBody).filter((t) => t.type !== "eof");
  if (tokens.length === 0) return rawBody;
  const edits = [];
  let depth = 0;
  let skipUntilDepth;
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && t.value === "(") {
      depth++;
      if (skipUntilDepth === void 0 && tokens[i + 1]?.type === "keyword" && tokens[i + 1].value === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C") {
        skipUntilDepth = depth;
      }
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      depth--;
      if (skipUntilDepth !== void 0 && depth < skipUntilDepth) skipUntilDepth = void 0;
      continue;
    }
    if (skipUntilDepth !== void 0) continue;
    if (!isNameToken(t)) continue;
    const up3 = t.text.toUpperCase();
    if ((up3 === "\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415" || up3 === "\u0422\u0418\u041F") && tokens[i + 1]?.type === "punct" && tokens[i + 1].value === "(") {
      skipUntilDepth = depth + 1;
      continue;
    }
    if (t.type !== "ident") continue;
    const prev = tokens[i - 1];
    if (prev && prev.type === "punct" && prev.value === ".") continue;
    const prevUp = prev && (prev.type === "ident" || prev.type === "keyword") ? prev.text.toUpperCase() : void 0;
    const skipChain = prevUp === "\u041A\u0410\u041A" || prevUp === "\u0421\u0421\u042B\u041B\u041A\u0410" || EXPR_STOP_WORDS.has(up3);
    let j = i;
    while (tokens[j + 1]?.type === "punct" && tokens[j + 1].value === "." && isNameToken(tokens[j + 2])) {
      j += 2;
    }
    const next = tokens[j + 1];
    const isCall = next !== void 0 && next.type === "punct" && next.value === "(";
    if (!skipChain && !isCall) {
      const declared = aliasSpelling.get(up3);
      if (declared !== void 0 || up3 === tableAliasUp) {
        const sp = declared ?? (up3 === tableAliasUp ? prefix.slice(0, prefix.indexOf(".")) : t.text);
        if (sp !== void 0 && t.text !== sp) edits.push({ pos: t.pos, len: t.text.length, text: sp });
      } else if (up3 === tsName.toUpperCase()) {
      } else {
        edits.push({ pos: t.pos, len: 0, text: `${prefix}.` });
      }
    }
    i = j;
  }
  let out = "";
  let p = tokens[0].pos;
  for (const e of edits) {
    out += rawBody.slice(p, e.pos) + e.text;
    p = e.pos + e.len;
  }
  const last = tokens[tokens.length - 1];
  return out + rawBody.slice(p, last.pos + last.value.length);
}
function stripLineComments(text2) {
  if (text2.indexOf("//") === -1) return text2;
  let inString = false;
  let inDate = false;
  let out = "";
  let strippedOnLine = false;
  for (let i = 0; i < text2.length; i++) {
    const ch = text2[i];
    if (inString) {
      out += ch;
      if (ch === '"') {
        if (text2[i + 1] === '"') {
          out += '"';
          i++;
        } else {
          inString = false;
        }
      }
      continue;
    }
    if (inDate) {
      out += ch;
      if (ch === "'") inDate = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      out += ch;
      continue;
    }
    if (ch === "'") {
      inDate = true;
      out += ch;
      continue;
    }
    if (ch === "/" && text2[i + 1] === "/") {
      while (i < text2.length && text2[i] !== "\n") i++;
      i--;
      strippedOnLine = true;
      continue;
    }
    if (ch === "\n") {
      if (strippedOnLine) {
        const lineStart = out.lastIndexOf("\n") + 1;
        const line = out.slice(lineStart);
        if (line.trim() === "") {
          out = out.slice(0, lineStart);
        } else {
          out = out.slice(0, lineStart) + line.replace(/[ \t\r]+$/u, "") + "\n";
        }
      } else {
        out += ch;
      }
      strippedOnLine = false;
      continue;
    }
    out += ch;
  }
  if (strippedOnLine) {
    const lineStart = out.lastIndexOf("\n") + 1;
    const line = out.slice(lineStart);
    out = out.slice(0, lineStart) + line.replace(/[ \t\r]+$/u, "");
  }
  return out;
}
function sliceSource(source, bodyTokens) {
  const first = bodyTokens[0];
  const last = bodyTokens[bodyTokens.length - 1];
  const end = last.pos + last.value.length;
  return stripLineComments(source.slice(first.pos, end));
}
function parseFrom(cur) {
  const tables = [];
  const joins = [];
  let index = 0;
  const readSource = () => {
    const table = parseTableSource(cur, index);
    index++;
    return table;
  };
  let parseBuilderJoins;
  const parseJoinChainFrom = (seedAlias, depth) => {
    let lastAlias = seedAlias;
    while (isJoinKeyword(cur)) {
      const kind = consumeJoinKind(cur);
      const joinedSource = readSource();
      tables.push(joinedSource);
      const joinedHead = joinedSource.alias;
      const raw = {
        kind,
        seedAlias: lastAlias,
        joinedAlias: joinedHead,
        // КОРЕНЬ цепочки (первая по тексту таблица): конструктор 1С при левоассоциа-
        // тивной цепочке считает СТАНДАРТНЫМ условие `<корень>.поле cmp <присоединяемая>.поле`,
        // а не `<предыдущая>.поле …`. Для классификации `ПО` (фаза 6.13) нужен корень,
        // тогда как порядок СЦЕПЛЕНИЯ (seedAlias) — предыдущая таблица. У вложенной
        // подцепочки корень — её собственная затравка (joinedHead).
        chainSeedAlias: seedAlias,
        condTokens: [],
        condText: "",
        depth
      };
      joins.push(raw);
      if (isJoinKeyword(cur)) parseJoinChainFrom(joinedHead, depth + 1);
      if (cur.isBuilderJoinStart()) parseBuilderJoins(joinedHead, depth + 1);
      cur.expectKeyword("\u041F\u041E");
      const { tokens, text: text2 } = readJoinCondition(cur);
      raw.condTokens = tokens;
      raw.condText = text2;
      lastAlias = joinedHead;
    }
  };
  parseBuilderJoins = (rootSeedAlias, depth = 0) => {
    while (cur.isBuilderJoinStart()) {
      cur.expectPunct("{");
      do {
        const kind = consumeJoinKind(cur);
        const joinedSource = readSource();
        tables.push(joinedSource);
        const joinedHead = joinedSource.alias;
        const raw = {
          kind,
          seedAlias: rootSeedAlias,
          joinedAlias: joinedHead,
          chainSeedAlias: rootSeedAlias,
          condTokens: [],
          condText: "",
          depth,
          optional: true
        };
        joins.push(raw);
        if (isJoinKeyword(cur)) parseJoinChainFrom(joinedHead, depth + 1);
        cur.expectKeyword("\u041F\u041E");
        const { tokens, text: text2 } = readJoinCondition(
          cur,
          /* stopOnBrace */
          true
        );
        raw.condTokens = tokens;
        raw.condText = text2;
      } while (isJoinKeyword(cur));
      cur.expectPunct("}");
      joins[joins.length - 1].optionalLast = true;
    }
  };
  const parseAllJoinsFrom = (rootSeed) => {
    while (isJoinKeyword(cur) || cur.isBuilderJoinStart()) {
      parseJoinChainFrom(rootSeed, 0);
      parseBuilderJoins(rootSeed);
    }
  };
  for (; ; ) {
    const seed = readSource();
    tables.push(seed);
    parseAllJoinsFrom(seed.alias);
    if (cur.matchPunct(",")) {
      if (isJoinKeyword(cur) || cur.isBuilderJoinStart()) {
        parseAllJoinsFrom(seed.alias);
        if (cur.matchPunct(",")) continue;
        break;
      }
      continue;
    }
    break;
  }
  return { tables, joins };
}
function parseTableSource(cur, index) {
  if (cur.isPunct("(")) {
    const open = cur.expectPunct("(");
    let depth = 1;
    let close;
    for (; ; ) {
      const t = cur.next();
      if (t.type === "eof") throw cur.error("\u043D\u0435\u0437\u0430\u043A\u0440\u044B\u0442\u044B\u0439 \u043F\u043E\u0434\u0437\u0430\u043F\u0440\u043E\u0441 \u0432 \u0438\u0441\u0442\u043E\u0447\u043D\u0438\u043A\u0435 \u0418\u0417", t);
      if (t.type === "punct" && t.value === "(") depth++;
      else if (t.type === "punct" && t.value === ")") {
        depth--;
        if (depth === 0) {
          close = t;
          break;
        }
      }
    }
    const innerText = cur.source.slice(open.pos + 1, close.pos);
    subquerySourceDepth++;
    let subquery;
    try {
      subquery = parseDocument(innerText, sourceResolver);
    } finally {
      subquerySourceDepth--;
    }
    if (!cur.matchKeyword("\u041A\u0410\u041A")) {
      throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u041A\u0410\u041A <\u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C> \u043F\u043E\u0441\u043B\u0435 \u043F\u043E\u0434\u0437\u0430\u043F\u0440\u043E\u0441\u0430 \u0432 \u0438\u0441\u0442\u043E\u0447\u043D\u0438\u043A\u0435 \u0418\u0417", cur.peek());
    }
    const aliasTok = cur.peek();
    if (aliasTok.type !== "ident" && aliasTok.type !== "keyword") {
      throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u0434\u0437\u0430\u043F\u0440\u043E\u0441\u0430 \u043F\u043E\u0441\u043B\u0435 \u041A\u0410\u041A", aliasTok);
    }
    cur.next();
    return { id: "t" + index, fullName: "", alias: aliasTok.text, subquery };
  }
  const fullName = parseDottedName(cur);
  let virtual;
  if (cur.isPunct("(")) {
    virtual = parseVirtualParams(cur, fullName);
  }
  let alias;
  let aliasSynthesized = false;
  if (cur.matchKeyword("\u041A\u0410\u041A")) {
    const aliasTok = cur.peek();
    if (aliasTok.type !== "ident" && aliasTok.type !== "keyword") {
      throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u0442\u0430\u0431\u043B\u0438\u0446\u044B \u043F\u043E\u0441\u043B\u0435 \u041A\u0410\u041A", aliasTok);
    }
    cur.next();
    alias = aliasTok.text;
  } else if (canBeBareAlias(cur)) {
    alias = cur.next().text;
  } else {
    alias = defaultTableAlias({ id: "", fullName });
    aliasSynthesized = true;
  }
  const table = {
    id: "t" + index,
    fullName,
    alias
  };
  if (aliasSynthesized) table.aliasSynthesized = true;
  if (virtual) table.virtual = virtual;
  return table;
}
function canBeBareAlias(cur) {
  return cur.peek().type === "ident";
}
var JOIN_KEYWORDS = /* @__PURE__ */ new Set(["\u0412\u041D\u0423\u0422\u0420\u0415\u041D\u041D\u0415\u0415", "\u041B\u0415\u0412\u041E\u0415", "\u041F\u0420\u0410\u0412\u041E\u0415", "\u041F\u041E\u041B\u041D\u041E\u0415"]);
function isJoinKeyword(cur) {
  const t = cur.peek();
  return t.type === "keyword" && (JOIN_KEYWORDS.has(t.value) || t.value === "\u0421\u041E\u0415\u0414\u0418\u041D\u0415\u041D\u0418\u0415");
}
function consumeJoinKind(cur) {
  let kind;
  if (cur.peek().value === "\u0421\u041E\u0415\u0414\u0418\u041D\u0415\u041D\u0418\u0415") {
    kind = "\u0412\u041D\u0423\u0422\u0420\u0415\u041D\u041D\u0415\u0415";
  } else {
    kind = cur.next().value;
    const t = cur.peek();
    if (t.type === "ident" && t.value.toUpperCase() === "\u0412\u041D\u0415\u0428\u041D\u0415\u0415") cur.next();
  }
  cur.expectKeyword("\u0421\u041E\u0415\u0414\u0418\u041D\u0415\u041D\u0418\u0415");
  return kind;
}
var JOIN_COND_STOP = /* @__PURE__ */ new Set([
  "\u0413\u0414\u0415",
  "\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0418\u041C\u0415\u042E\u0429\u0418\u0415",
  "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C",
  "\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415",
  "\u0418\u0422\u041E\u0413\u0418",
  "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0414\u041B\u042F",
  "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C",
  "\u0412\u042B\u0411\u0420\u0410\u0422\u042C",
  // `ПО` верхнего уровня завершает условие текущего соединения: это `ПО`
  // внешнего соединения в правовложенной цепочке (`A СОЕД B СОЕД C ПО c1 ПО c2`).
  "\u041F\u041E"
]);
function readJoinCondition(cur, stopOnBrace = false) {
  const tokens = [];
  let depth = 0;
  for (; ; ) {
    const t = cur.peek();
    if (t.type === "eof") break;
    if (depth === 0) {
      if (t.type === "punct" && t.value === ",") break;
      if (t.type === "punct" && t.value === ";") break;
      if (stopOnBrace && t.type === "punct" && t.value === "}") break;
      if (isJoinKeyword(cur)) break;
      if (t.type === "keyword" && JOIN_COND_STOP.has(t.value) && !cur.isPunct(".", 1)) break;
      if (cur.isBuilderStart() || cur.isBuilderJoinStart()) break;
    }
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    tokens.push(cur.next());
  }
  if (tokens.length === 0) throw cur.error("\u043F\u0443\u0441\u0442\u043E\u0435 \u0443\u0441\u043B\u043E\u0432\u0438\u0435 \u0441\u043E\u0435\u0434\u0438\u043D\u0435\u043D\u0438\u044F \u043F\u043E\u0441\u043B\u0435 \u041F\u041E");
  return { tokens, text: sliceSource(cur.source, tokens) };
}
function parseDottedName(cur) {
  const first = cur.peek();
  if (first.type !== "ident" && first.type !== "keyword" && first.type !== "param") {
    throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u0438\u043C\u044F", first);
  }
  let name = cur.next().text;
  while (cur.isPunct(".")) {
    cur.next();
    const seg = cur.peek();
    if (seg.type !== "ident" && seg.type !== "keyword") {
      throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u0441\u0435\u0433\u043C\u0435\u043D\u0442 \u0438\u043C\u0435\u043D\u0438 \u043F\u043E\u0441\u043B\u0435 \xAB.\xBB", seg);
    }
    name += "." + cur.next().text;
  }
  return name;
}
function arg(args, n) {
  return args[n] ?? "";
}
function parseVirtualParams(cur, fullName) {
  const args = parsePositionalArgs(cur);
  const parts = fullName.split(".");
  const kind = parts[0];
  const slice = parts[2];
  const v = {};
  v.hadParens = true;
  const set = (key, value) => {
    if (value !== "") v[key] = value;
  };
  if (kind === "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0411\u0443\u0445\u0433\u0430\u043B\u0442\u0435\u0440\u0438\u0438") {
    v.accountingArgs = args;
    fillAccounting(v, slice, args, set);
    return v;
  }
  if (slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B") {
    set("startPeriod", arg(args, 0));
    set("endPeriod", arg(args, 1));
    set("periodicity", arg(args, 2));
    set("condition", arg(args, 3));
    return v;
  }
  if (slice === "\u041E\u0441\u0442\u0430\u0442\u043A\u0438\u0418\u041E\u0431\u043E\u0440\u043E\u0442\u044B") {
    set("startPeriod", arg(args, 0));
    set("endPeriod", arg(args, 1));
    set("periodicity", arg(args, 2));
    set("fillMethod", arg(args, 3));
    set("condition", arg(args, 4));
    return v;
  }
  set("period", arg(args, 0));
  set("condition", arg(args, 1));
  return v;
}
function fillAccounting(v, slice, args, set) {
  const corr = slice === "\u041E\u0431\u043E\u0440\u043E\u0442\u044B" && args.length >= 8;
  const keys = accountingPositionKeys(slice, true, corr);
  keys.forEach((k, i) => {
    if (k) set(k, arg(args, i));
  });
  if (corr) v.correspondence = true;
}
function parsePositionalArgs(cur) {
  cur.expectPunct("(");
  const args = [];
  let curTokens = [];
  let depth = 0;
  const flush = () => {
    args.push(curTokens.length > 0 ? sliceSource(cur.source, curTokens) : "");
    curTokens = [];
  };
  for (; ; ) {
    const t = cur.peek();
    if (t.type === "eof") throw cur.error("\u043D\u0435\u0437\u0430\u043A\u0440\u044B\u0442\u0430\u044F \u0441\u043A\u043E\u0431\u043A\u0430 \u043F\u0430\u0440\u0430\u043C\u0435\u0442\u0440\u043E\u0432", t);
    if (depth === 0 && t.type === "punct" && t.value === ")") {
      cur.next();
      break;
    }
    if (depth === 0 && t.type === "punct" && t.value === ",") {
      cur.next();
      flush();
      continue;
    }
    if (t.type === "punct" && (t.value === "(" || t.value === "{")) depth++;
    else if (t.type === "punct" && (t.value === ")" || t.value === "}")) depth--;
    curTokens.push(cur.next());
  }
  flush();
  return args;
}
function interpretField(rf, aliasToId, fields, aggregates, resolveOwner, tableFullNames) {
  {
    const bare = tryBareField(rf.bodyTokens, aliasToId);
    const owner = bare ? resolveOwner(bare.head) : void 0;
    if (bare && owner !== void 0) {
      const path = stripOwnerFullName(bare.path, tableFullNames.get(owner));
      const field2 = { tableId: owner, path };
      if (rf.alias !== void 0 && !AUTO_ALIAS.test(rf.alias)) field2.alias = rf.alias;
      fields.push(field2);
      return;
    }
  }
  if (rf.alias !== void 0 && AUTO_ALIAS.test(rf.alias)) {
    const field2 = { tableId: "", path: "", expression: rf.rawBody };
    if (BARE_PARAM_ALIAS.test(rf.rawBody.trim())) field2.alias = rf.alias;
    else {
      field2.alias = rf.alias;
      field2.exprAliasExplicit = rf.alias;
    }
    fields.push(field2);
    return;
  }
  const agg = tryAggregate(rf.bodyTokens, aliasToId, resolveOwner, tableFullNames);
  if (agg) {
    const field2 = { tableId: agg.tableId, path: agg.path, func: agg.func };
    if (agg.operandQualified) field2.funcOperandQualified = true;
    if (rf.alias !== void 0) field2.alias = rf.alias;
    fields.push(field2);
    aggregates.push({ tableId: agg.tableId, path: agg.path, func: agg.func });
    return;
  }
  const simple = trySimpleField(rf.bodyTokens, aliasToId);
  if (simple) {
    const field2 = { tableId: simple.tableId, path: simple.path, qualified: true };
    if (rf.alias !== void 0) field2.alias = rf.alias;
    fields.push(field2);
    return;
  }
  const field = { tableId: "", path: "", expression: rf.rawBody };
  if (rf.alias !== void 0 && !AUTO_ALIAS.test(rf.alias)) {
    field.alias = rf.alias;
  }
  fields.push(field);
}
function tryAggregate(body, aliasToId, resolveOwner, tableFullNames) {
  if (body.length < 4) return void 0;
  const head = body[0];
  if (head.type !== "keyword") return void 0;
  if (!(body[1].type === "punct" && body[1].value === "(")) return void 0;
  const lastTok = body[body.length - 1];
  if (!(lastTok.type === "punct" && lastTok.value === ")")) return void 0;
  let inner = body.slice(2, body.length - 1);
  let func;
  if (head.value === "\u041A\u041E\u041B\u0418\u0427\u0415\u0421\u0422\u0412\u041E" && inner[0]?.type === "keyword" && inner[0].value === "\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415") {
    func = "\u041A\u043E\u043B\u0438\u0447\u0435\u0441\u0442\u0432\u043E\u0420\u0430\u0437\u043B\u0438\u0447\u043D\u044B\u0445";
    inner = inner.slice(1);
  } else {
    func = AGG_KEYWORD_TO_FUNC[head.value];
  }
  if (!func) return void 0;
  const ref = parseFieldRef(inner, aliasToId);
  if (ref) return { tableId: ref.tableId, path: ref.path, func, operandQualified: true };
  const bare = tryBareField(inner, aliasToId);
  if (bare) {
    const owner = resolveOwner(bare.head);
    if (owner !== void 0) return { tableId: owner, path: stripOwnerFullName(bare.path, tableFullNames.get(owner)), func };
  }
  return void 0;
}
function trySimpleField(body, aliasToId) {
  return parseFieldRef(body, aliasToId);
}
function parseFieldRef(tokens, aliasToId) {
  if (tokens.length < 3) return void 0;
  const segs = [];
  for (let k = 0; k < tokens.length; k++) {
    if (k % 2 === 0) {
      const t = tokens[k];
      if (t.type !== "ident" && t.type !== "keyword") return void 0;
      segs.push(t.text);
    } else {
      const t = tokens[k];
      if (!(t.type === "punct" && t.value === ".")) return void 0;
    }
  }
  if (tokens.length % 2 === 0) return void 0;
  const aliasName = segs[0];
  const tableId = aliasToId.get(aliasName.toUpperCase());
  if (tableId === void 0) return void 0;
  const path = segs.slice(1).join(".");
  if (!path) return void 0;
  return { tableId, path };
}
function isNameToken(t) {
  return t !== void 0 && (t.type === "ident" || t.type === "keyword");
}
function buildFieldOwnerScan(tokens, aliasToId) {
  const map = /* @__PURE__ */ new Map();
  let depth = 0;
  let skipUntilDepth;
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && t.value === "(") {
      depth++;
      if (skipUntilDepth === void 0 && tokens[i + 1]?.type === "keyword" && tokens[i + 1].value === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C") {
        skipUntilDepth = depth;
      }
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      depth--;
      if (skipUntilDepth !== void 0 && depth < skipUntilDepth) skipUntilDepth = void 0;
      continue;
    }
    if (skipUntilDepth !== void 0) continue;
    if (!isNameToken(t)) continue;
    const prev = tokens[i - 1];
    if (prev && prev.type === "punct" && prev.value === ".") continue;
    const dot = tokens[i + 1];
    const field = tokens[i + 2];
    if (!dot || !field) continue;
    if (!(dot.type === "punct" && dot.value === ".") || !isNameToken(field)) continue;
    const tableId = aliasToId.get(t.text.toUpperCase());
    if (tableId === void 0) continue;
    const key = field.text.toUpperCase();
    const set = map.get(key) ?? /* @__PURE__ */ new Set();
    set.add(tableId);
    map.set(key, set);
  }
  return map;
}
function soleSourceOf(tables, joins) {
  if (joins.length > 0) return void 0;
  if (tables.length !== 1) return void 0;
  const t = tables[0];
  if (!t.alias) return void 0;
  return { id: t.id, alias: t.alias, fullName: t.fullName };
}
var LITERAL_VALUES = /* @__PURE__ */ new Set(["\u041D\u0415\u041E\u041F\u0420\u0415\u0414\u0415\u041B\u0415\u041D\u041E", "\u0418\u0421\u0422\u0418\u041D\u0410", "\u041B\u041E\u0416\u042C", "NULL"]);
function tryBareField(tokens, aliasToId) {
  if (tokens.length === 0) return void 0;
  const segs = [];
  for (let k = 0; k < tokens.length; k++) {
    if (k % 2 === 0) {
      const t = tokens[k];
      if (t.type !== "ident" && t.type !== "keyword") return void 0;
      segs.push(t.text);
    } else {
      const t = tokens[k];
      if (!(t.type === "punct" && t.value === ".")) return void 0;
    }
  }
  if (tokens.length % 2 === 0) return void 0;
  const head = segs[0];
  if (aliasToId.has(head.toUpperCase())) return void 0;
  if (segs.length === 1 && LITERAL_VALUES.has(head.toUpperCase())) return void 0;
  return { path: segs.join("."), head };
}
function stripOwnerFullName(path, fullName) {
  if (!fullName || !fullName.includes(".")) return path;
  const prefix = fullName + ".";
  return path.toUpperCase().startsWith(prefix.toUpperCase()) ? path.slice(prefix.length) : path;
}
function bareLhsRef(lhs, aliasToId, soleSource) {
  const bare = tryBareField(lhs, aliasToId);
  if (!bare) return void 0;
  return { tableId: soleSource.id, path: stripOwnerFullName(bare.path, soleSource.fullName) };
}
var EXPR_STOP_WORDS = /* @__PURE__ */ new Set([
  "\u0418",
  "\u0418\u041B\u0418",
  "\u041D\u0415",
  "\u0412",
  "\u041C\u0415\u0416\u0414\u0423",
  "\u041F\u041E\u0414\u041E\u0411\u041D\u041E",
  "\u0415\u0421\u0422\u042C",
  "\u0421\u041F\u0415\u0426\u0421\u0418\u041C\u0412\u041E\u041B",
  "NULL",
  "\u0418\u0421\u0422\u0418\u041D\u0410",
  "\u041B\u041E\u0416\u042C",
  "\u041D\u0415\u041E\u041F\u0420\u0415\u0414\u0415\u041B\u0415\u041D\u041E",
  "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418",
  "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F",
  "\u0423\u0411\u042B\u0412",
  "\u0412\u041E\u0417\u0420",
  "\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415",
  "\u041A\u0410\u041A",
  "\u0421\u0421\u042B\u041B\u041A\u0410",
  "\u0412\u042B\u0411\u041E\u0420",
  "\u041A\u041E\u0413\u0414\u0410",
  "\u0422\u041E\u0413\u0414\u0410",
  "\u0418\u041D\u0410\u0427\u0415",
  "\u041A\u041E\u041D\u0415\u0426",
  "\u0413\u041E\u0414",
  "\u041A\u0412\u0410\u0420\u0422\u0410\u041B",
  "\u041C\u0415\u0421\u042F\u0426",
  "\u0414\u0415\u041A\u0410\u0414\u0410",
  "\u041D\u0415\u0414\u0415\u041B\u042F",
  "\u0414\u0415\u041D\u042C",
  "\u0427\u0410\u0421",
  "\u041C\u0418\u041D\u0423\u0422\u0410",
  "\u0421\u0415\u041A\u0423\u041D\u0414\u0410"
]);
var EXPR_TERMINATOR_WORDS = /* @__PURE__ */ new Set([
  "NULL",
  "\u0418\u0421\u0422\u0418\u041D\u0410",
  "\u041B\u041E\u0416\u042C",
  "\u041D\u0415\u041E\u041F\u0420\u0415\u0414\u0415\u041B\u0415\u041D\u041E",
  "\u041A\u041E\u041D\u0415\u0426"
]);
function qualifyBareFieldsInExpression(tokens, source, aliasToId, aliasSpelling, soleAlias) {
  const edits = [];
  let depth = 0;
  let skipUntilDepth;
  let braceDepth = 0;
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && t.value === "{") {
      braceDepth++;
      continue;
    }
    if (t.type === "punct" && t.value === "}") {
      braceDepth--;
      continue;
    }
    if (t.type === "punct" && t.value === "(") {
      depth++;
      if (skipUntilDepth === void 0 && tokens[i + 1]?.type === "keyword" && tokens[i + 1].value === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C") {
        skipUntilDepth = depth;
      }
      continue;
    }
    if (t.type === "punct" && t.value === ")") {
      depth--;
      if (skipUntilDepth !== void 0 && depth < skipUntilDepth) skipUntilDepth = void 0;
      continue;
    }
    if (skipUntilDepth !== void 0 || braceDepth > 0) continue;
    if (!isNameToken(t)) continue;
    const up3 = t.text.toUpperCase();
    if ((up3 === "\u0417\u041D\u0410\u0427\u0415\u041D\u0418\u0415" || up3 === "\u0422\u0418\u041F") && tokens[i + 1]?.type === "punct" && tokens[i + 1].value === "(") {
      skipUntilDepth = depth + 1;
      continue;
    }
    if (t.type !== "ident") continue;
    const prev = tokens[i - 1];
    if (prev && prev.type === "punct" && prev.value === ".") continue;
    const prevUp = prev && (prev.type === "ident" || prev.type === "keyword") ? prev.text.toUpperCase() : void 0;
    const skipChain = prevUp === "\u041A\u0410\u041A" || prevUp === "\u0421\u0421\u042B\u041B\u041A\u0410" || EXPR_STOP_WORDS.has(up3);
    let j = i;
    while (tokens[j + 1]?.type === "punct" && tokens[j + 1].value === "." && isNameToken(tokens[j + 2])) {
      j += 2;
    }
    const next = tokens[j + 1];
    const isCall = next !== void 0 && next.type === "punct" && next.value === "(";
    if (!skipChain && !isCall) {
      const declared = aliasSpelling.get(up3);
      if (declared !== void 0) {
        if (t.text !== declared) edits.push({ pos: t.pos, len: t.text.length, text: declared });
      } else if (soleAlias !== void 0 && j === i) {
        edits.push({ pos: t.pos, len: 0, text: `${soleAlias}.` });
      }
    }
    i = j;
  }
  const start = tokens[0].pos;
  const last = tokens[tokens.length - 1];
  const end = last.pos + last.value.length;
  let out = "";
  let p = start;
  for (const e of edits) {
    out += source.slice(p, e.pos) + e.text;
    p = e.pos + e.len;
  }
  return out + source.slice(p, end);
}
var COND_OPERATORS = /* @__PURE__ */ new Set(["=", "<>", ">", ">=", "<", "<=", "\u0412", "\u041C\u0415\u0416\u0414\u0423", "\u041F\u041E\u0414\u041E\u0411\u041D\u041E"]);
function parseWhere(cur, aliasToId, soleSource, aliasSpelling) {
  cur.expectKeyword("\u0413\u0414\u0415");
  const source = cur.source;
  const segments = splitConditionSegments(cur, WHERE_STOP);
  return segments.map((seg) => interpretCondition(seg, source, aliasToId, soleSource, aliasSpelling));
}
var WHERE_STOP = /* @__PURE__ */ new Set([
  "\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  // Секция УПОРЯДОЧИТЬ ПО, идущая после ГДЕ в запросе без группировки. Без неё
  // parseWhere дословно затягивал хвост (`…\nУПОРЯДОЧИТЬ ПО …`) в param последнего
  // условия, и УПОРЯДОЧИТЬ воспроизводилось как сырой текст (теряя нормализацию
  // отступов конструктора). Остановка здесь передаёт управление штатному parseOrder.
  "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C",
  "\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415",
  "\u0418\u0422\u041E\u0413\u0418",
  "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C",
  "\u0414\u041B\u042F",
  // ИМЕЮЩИЕ может идти сразу за ГДЕ без СГРУППИРОВАТЬ, когда в выборке есть
  // агрегат (`ВЫБРАТЬ МАКСИМУМ(…) … ГДЕ … ИМЕЮЩИЕ МАКСИМУМ(…) ЕСТЬ НЕ NULL`).
  // Без остановки хвост затягивался в param последнего условия ГДЕ.
  "\u0418\u041C\u0415\u042E\u0429\u0418\u0415"
]);
var HAVING_STOP = /* @__PURE__ */ new Set(["\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C", "\u0418\u0422\u041E\u0413\u0418", "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C", "\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415", "\u0414\u041B\u042F"]);
function parseHaving(cur, aliasToId) {
  cur.expectKeyword("\u0418\u041C\u0415\u042E\u0429\u0418\u0415");
  const source = cur.source;
  const segments = splitConditionSegments(cur, HAVING_STOP);
  return segments.map((seg) => interpretCondition(seg, source, aliasToId));
}
function splitConditionSegments(cur, stop) {
  const tokens = collectConditionTokens(cur, stop);
  return segmentConditionTokens(tokens);
}
function collectConditionTokens(cur, stop) {
  const tokens = [];
  let depth = 0;
  let caseDepth = 0;
  const isIdentWord = (t, w) => (t.type === "ident" || t.type === "keyword") && t.value.toUpperCase() === w;
  for (; ; ) {
    const t = cur.peek();
    if (t.type === "eof") break;
    if (depth === 0 && caseDepth === 0 && t.type === "keyword" && stop.has(t.value)) break;
    if (depth === 0 && caseDepth === 0 && cur.isBuilderStart()) break;
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    else if (isIdentWord(t, "\u0412\u042B\u0411\u041E\u0420")) caseDepth++;
    else if (isIdentWord(t, "\u041A\u041E\u041D\u0415\u0426") && caseDepth > 0) caseDepth--;
    tokens.push(cur.next());
  }
  return tokens;
}
function hasTopLevelOr(tokens) {
  let depth = 0;
  let caseDepth = 0;
  const isIdentWord = (t, w) => (t.type === "ident" || t.type === "keyword") && t.value.toUpperCase() === w;
  for (const t of tokens) {
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    else if (isIdentWord(t, "\u0412\u042B\u0411\u041E\u0420")) caseDepth++;
    else if (isIdentWord(t, "\u041A\u041E\u041D\u0415\u0426") && caseDepth > 0) caseDepth--;
    else if (depth === 0 && caseDepth === 0 && isIdentWord(t, "\u0418\u041B\u0418")) return true;
  }
  return false;
}
function segmentConditionTokens(tokens) {
  if (hasTopLevelOr(tokens)) return tokens.length > 0 ? [tokens] : [];
  const out = [];
  for (const seg of splitJoinConjuncts(tokens)) {
    if (hasBalancedOuterParens(seg)) {
      const inner = seg.slice(1, -1);
      if (inner.length > 0 && !hasTopLevelOr(inner)) {
        out.push(...segmentConditionTokens(inner));
        continue;
      }
    }
    out.push(seg);
  }
  return out;
}
function interpretCondition(tokens, source, aliasToId, soleSource, aliasSpelling) {
  if (soleSource) {
    const bare = tryBareField(tokens, aliasToId);
    if (bare) {
      return { custom: true, expression: `${soleSource.alias}.${bare.path}` };
    }
    if (tokens.length > 1 && isNotToken(tokens[0])) {
      const negBare = tryBareField(tokens.slice(1), aliasToId);
      if (negBare) {
        return { custom: true, expression: `\u041D\u0415 ${soleSource.alias}.${negBare.path}` };
      }
    }
  }
  const customText = () => soleSource && aliasSpelling ? qualifyBareFieldsInExpression(tokens, source, aliasToId, aliasSpelling, soleSource.alias) : sliceSource(source, tokens);
  if (tokens.length === 3 && tokens[0].type === "punct" && tokens[0].value === "(" && tokens[1].type === "param" && tokens[2].type === "punct" && tokens[2].value === ")") {
    return { custom: true, expression: tokens[1].text };
  }
  if (hasTopLevelOr(tokens)) {
    return { custom: true, expression: customText() };
  }
  if (tokens.length > 1 && isNotToken(tokens[0])) {
    const inner = trySimpleCondition(tokens.slice(1), source, aliasToId, soleSource, aliasSpelling);
    if (inner && inner.subquery) return { ...inner, negated: true };
  }
  const simple = trySimpleCondition(tokens, source, aliasToId, soleSource, aliasSpelling);
  if (simple) return simple;
  return { custom: true, expression: customText() };
}
function trySimpleCondition(tokens, source, aliasToId, soleSource, aliasSpelling) {
  let opIdx = -1;
  let depth = 0;
  for (let k = 0; k < tokens.length; k++) {
    const t = tokens[k];
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    else if (depth === 0 && isCondOperatorToken(t)) {
      opIdx = k;
      break;
    }
  }
  if (opIdx <= 0 || opIdx >= tokens.length - 1) return void 0;
  const lhs = tokens.slice(0, opIdx);
  const direct = parseFieldRef(lhs, aliasToId);
  const ref = direct ?? (soleSource ? bareLhsRef(lhs, aliasToId, soleSource) : void 0);
  if (!ref) {
    const opTok = tokens[opIdx].value;
    if (opTok === "\u0412") {
      const subTokens = tokens.slice(opIdx + 1);
      const inner = subqueryInnerText(subTokens, source);
      if (inner !== void 0 && (isCompactSubquerySource(inner) || hasRedundantHavingOrParens(inner))) {
        const sub = trySubqueryParam(subTokens, source);
        if (sub) {
          return { custom: true, leftExpr: sliceSource(source, lhs), subquery: sub };
        }
      }
    }
    return void 0;
  }
  const op2 = tokens[opIdx].value;
  const paramTokens = tokens.slice(opIdx + 1);
  if (paramTokens.length === 0) return void 0;
  const param = sliceSource(source, paramTokens);
  const base = { tableId: ref.tableId, path: ref.path, operator: op2, param };
  if (op2 === "\u0412") {
    let subTokens = paramTokens;
    let hierarchy = false;
    const head = subTokens[0];
    if (head && (head.type === "ident" || head.type === "keyword") && head.text.toUpperCase() === "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418") {
      subTokens = subTokens.slice(1);
      hierarchy = true;
    }
    const sub = trySubqueryParam(subTokens, source);
    if (sub) {
      return { custom: true, ...base, subquery: sub, ...hierarchy ? { hierarchy: true } : {} };
    }
  }
  if (isParamRhs(op2, paramTokens)) {
    return { custom: false, ...base };
  }
  if (!direct && ref.path.includes(".")) return void 0;
  const lhsAlias = direct ? aliasSpelling?.get(lhs[0].text.toUpperCase()) ?? lhs[0].text : soleSource.alias;
  const rhsText = aliasSpelling ? qualifyBareFieldsInExpression(paramTokens, source, aliasToId, aliasSpelling, soleSource?.alias) : param;
  const expr = `${lhsAlias}.${ref.path} ${renderOperatorRhs(op2, normalizeLeafCase(rhsText))}`;
  if (needsFormatting(expr) || isRootNotGroup(expr)) {
    return { custom: false, ...base };
  }
  return { custom: true, ...base, expression: expr };
}
function isParamRhs(op2, paramTokens) {
  if (op2 === "\u041C\u0415\u0416\u0414\u0423") {
    const iIdx = paramTokens.findIndex(
      (t) => (t.type === "ident" || t.type === "keyword") && t.text.toUpperCase() === "\u0418"
    );
    if (iIdx <= 0) return false;
    return isParamChain(paramTokens.slice(0, iIdx)) && isParamChain(paramTokens.slice(iIdx + 1));
  }
  let toks = paramTokens;
  if (op2 === "\u0412") {
    const head = toks[0];
    if (head && (head.type === "ident" || head.type === "keyword") && head.text.toUpperCase() === "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u0418") {
      toks = toks.slice(1);
    }
    const first = toks[0];
    const last = toks[toks.length - 1];
    if (first && first.type === "punct" && first.value === "(") {
      if (!(last && last.type === "punct" && last.value === ")")) return false;
      toks = toks.slice(1, -1);
    }
  }
  return isParamChain(toks);
}
function isParamChain(toks) {
  if (toks.length === 0 || toks[0].type !== "param") return false;
  for (let k = 1; k < toks.length; k++) {
    if (k % 2 === 1) {
      if (!(toks[k].type === "punct" && toks[k].value === ".")) return false;
    } else if (toks[k].type !== "ident" && toks[k].type !== "keyword") {
      return false;
    }
  }
  return toks.length % 2 === 1;
}
function isNotToken(t) {
  return (t.type === "ident" || t.type === "keyword") && t.text.toUpperCase() === "\u041D\u0415";
}
function isCondOperatorToken(t) {
  if (t.type === "punct") return COND_OPERATORS.has(t.value);
  if (t.type === "keyword") return COND_OPERATORS.has(t.value);
  return false;
}
function subqueryInnerText(paramTokens, source) {
  const first = paramTokens[0];
  if (!first || first.type !== "punct" || first.value !== "(") return void 0;
  let depth = 0;
  let closeIdx = -1;
  for (let k = 0; k < paramTokens.length; k++) {
    const t = paramTokens[k];
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") {
      depth--;
      if (depth === 0) {
        closeIdx = k;
        break;
      }
    }
  }
  if (closeIdx !== paramTokens.length - 1) return void 0;
  const inner = paramTokens[1];
  if (!inner || !(inner.type === "keyword" && inner.value === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C")) return void 0;
  return source.slice(paramTokens[0].pos + 1, paramTokens[closeIdx].pos);
}
function isCompactSubquerySource(inner) {
  const re = /(?:^|[^\p{L}\p{N}_])ВЫБРАТЬ(?:[^\p{L}\p{N}_].*?)(?:^|[^\p{L}\p{N}_])ИЗ(?:[^\p{L}\p{N}_]|$)/u;
  return inner.split("\n").some((l) => re.test(l));
}
function hasRedundantHavingOrParens(inner) {
  const m = /(?:^|[^\p{L}\p{N}_])ИМЕЮЩИЕ(?![\p{L}\p{N}_])/u.exec(inner);
  if (!m) return false;
  let rest = inner.slice(m.index + m[0].length);
  const tailKw = /(?:^|[^\p{L}\p{N}_])(?:ИНДЕКСИРОВАТЬ|УПОРЯДОЧИТЬ|ОБЪЕДИНИТЬ|ИТОГИ)(?![\p{L}\p{N}_])/u.exec(rest);
  if (tailKw) rest = rest.slice(0, tailKw.index);
  let depth = 0, inStr = false;
  const isW = (c) => c !== void 0 && /[\p{L}\p{N}_]/u.test(c);
  for (let i = 0; i < rest.length; i++) {
    const ch = rest[i];
    if (inStr) {
      if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') {
      inStr = true;
      continue;
    }
    if (ch === "(") {
      depth++;
      continue;
    }
    if (ch === ")") {
      depth--;
      continue;
    }
    if (depth === 0 && (ch === "\u0418" || ch === "\u0438") && !isW(rest[i - 1]) && /^ИЛИ(?![\p{L}\p{N}_])/iu.test(rest.slice(i))) {
      return true;
    }
  }
  return false;
}
function trySubqueryParam(paramTokens, source) {
  const first = paramTokens[0];
  if (!first || first.type !== "punct" || first.value !== "(") return void 0;
  let depth = 0;
  let closeIdx = -1;
  for (let k = 0; k < paramTokens.length; k++) {
    const t = paramTokens[k];
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") {
      depth--;
      if (depth === 0) {
        closeIdx = k;
        break;
      }
    }
  }
  if (closeIdx !== paramTokens.length - 1) return void 0;
  const inner = paramTokens[1];
  if (!inner || !(inner.type === "keyword" && inner.value === "\u0412\u042B\u0411\u0420\u0410\u0422\u042C")) return void 0;
  const open = paramTokens[0];
  const close = paramTokens[closeIdx];
  const innerText = source.slice(open.pos + 1, close.pos);
  try {
    return parseDocument(innerText);
  } catch {
    return void 0;
  }
}
function joinFlags(kind) {
  switch (kind) {
    case "\u0412\u041D\u0423\u0422\u0420\u0415\u041D\u041D\u0415\u0415":
      return { leftAll: false, rightAll: false };
    case "\u041B\u0415\u0412\u041E\u0415":
      return { leftAll: true, rightAll: false };
    case "\u041F\u0420\u0410\u0412\u041E\u0415":
      return { leftAll: false, rightAll: true };
    case "\u041F\u041E\u041B\u041D\u041E\u0415":
      return { leftAll: true, rightAll: true };
  }
}
var STD_JOIN_OPERATORS = /* @__PURE__ */ new Set(["=", "<>", ">", ">=", "<", "<="]);
function splitJoinConjuncts(tokens) {
  const segments = [];
  let current = [];
  let depth = 0;
  let caseDepth = 0;
  let betweenPending = 0;
  const isIdentWord = (t, w) => (t.type === "ident" || t.type === "keyword") && t.value.toUpperCase() === w;
  const flush = () => {
    if (current.length > 0) segments.push(current);
    current = [];
  };
  for (const t of tokens) {
    if (depth === 0 && caseDepth === 0) {
      if (t.type === "keyword" && t.value === "\u0418") {
        if (betweenPending > 0) {
          betweenPending--;
        } else {
          flush();
          continue;
        }
      }
      if (isIdentWord(t, "\u041C\u0415\u0416\u0414\u0423")) betweenPending++;
    }
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    else if (isIdentWord(t, "\u0412\u042B\u0411\u041E\u0420")) caseDepth++;
    else if (isIdentWord(t, "\u041A\u041E\u041D\u0415\u0426") && caseDepth > 0) caseDepth--;
    current.push(t);
  }
  flush();
  return segments;
}
function classifyJoinConjunct(tokens, source, aliasToId, seedId, joinedId) {
  const arbitrary = () => {
    let text2 = sliceSource(source, tokens);
    for (let s = stripOuterParens(text2); s !== text2; s = stripOuterParens(text2)) text2 = s;
    return { custom: true, expression: text2 };
  };
  let inner = tokens;
  while (hasBalancedOuterParens(inner)) inner = inner.slice(1, -1);
  let opIdx = -1;
  let depth = 0;
  for (let k = 0; k < inner.length; k++) {
    const t = inner[k];
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    else if (depth === 0 && isCondOperatorToken(t)) {
      opIdx = k;
      break;
    }
  }
  if (opIdx <= 0 || opIdx >= inner.length - 1) return arbitrary();
  const op2 = inner[opIdx].value;
  if (!STD_JOIN_OPERATORS.has(op2)) return arbitrary();
  const left = parseFieldRef(inner.slice(0, opIdx), aliasToId);
  const right = parseFieldRef(inner.slice(opIdx + 1), aliasToId);
  if (!left || !right) return arbitrary();
  if (left.tableId !== seedId || right.tableId !== joinedId) return arbitrary();
  return {
    custom: false,
    leftTableId: left.tableId,
    leftPath: left.path,
    operator: op2,
    rightTableId: right.tableId,
    rightPath: right.path
  };
}
function resolveJoin(raw, aliasToId, source) {
  const { leftAll, rightAll } = joinFlags(raw.kind);
  const seedId = aliasToId.get(raw.seedAlias.toUpperCase()) ?? raw.seedAlias;
  const joinedId = aliasToId.get(raw.joinedAlias.toUpperCase()) ?? raw.joinedAlias;
  const parenthesized = hasBalancedOuterParens(raw.condTokens);
  const chainSeedId = aliasToId.get(raw.chainSeedAlias.toUpperCase()) ?? raw.chainSeedAlias;
  let condInner = raw.condTokens;
  while (hasBalancedOuterParens(condInner)) condInner = condInner.slice(1, -1);
  const conjunctTokens = hasTopLevelOr(condInner) ? [condInner] : splitJoinConjuncts(condInner);
  const conditions = conjunctTokens.map(
    (seg) => classifyJoinConjunct(seg, source, aliasToId, chainSeedId, joinedId)
  );
  const simple = trySimpleJoinCondition(raw.condTokens, aliasToId);
  if (simple) {
    return {
      leftTableId: simple.leftTableId,
      rightTableId: simple.rightTableId,
      leftAll,
      rightAll,
      custom: false,
      leftPath: simple.leftPath,
      operator: simple.operator,
      rightPath: simple.rightPath,
      seedTableId: seedId,
      joinedTableId: joinedId,
      conditions,
      // depth добавляется только у вложенных — плоские модели не меняются.
      ...raw.depth > 0 ? { depth: raw.depth } : {},
      ...raw.optional ? { optional: true } : {},
      ...raw.optionalLast ? { optionalLast: true } : {}
    };
  }
  return {
    leftTableId: seedId,
    rightTableId: joinedId,
    leftAll,
    rightAll,
    custom: true,
    expression: stripOuterParens(raw.condText),
    parenthesized,
    seedTableId: seedId,
    joinedTableId: joinedId,
    conditions,
    ...raw.depth > 0 ? { depth: raw.depth } : {},
    ...raw.optional ? { optional: true } : {},
    ...raw.optionalLast ? { optionalLast: true } : {}
  };
}
function hasBalancedOuterParens(tokens) {
  if (tokens.length < 2) return false;
  const first = tokens[0];
  const last = tokens[tokens.length - 1];
  if (!(first.type === "punct" && first.value === "(")) return false;
  if (!(last.type === "punct" && last.value === ")")) return false;
  let depth = 0;
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") {
      depth--;
      if (depth === 0) return i === tokens.length - 1;
    }
  }
  return false;
}
function trySimpleJoinCondition(tokens, aliasToId) {
  if (tokens.length > 0 && tokens[0].type === "punct" && tokens[0].value === "(") return void 0;
  let opIdx = -1;
  let depth = 0;
  for (let k = 0; k < tokens.length; k++) {
    const t = tokens[k];
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    else if (depth === 0 && isCondOperatorToken(t)) {
      opIdx = k;
      break;
    }
  }
  if (opIdx <= 0 || opIdx >= tokens.length - 1) return void 0;
  const left = parseFieldRef(tokens.slice(0, opIdx), aliasToId);
  const right = parseFieldRef(tokens.slice(opIdx + 1), aliasToId);
  if (!left || !right) return void 0;
  return {
    leftTableId: left.tableId,
    leftPath: left.path,
    operator: tokens[opIdx].value,
    rightTableId: right.tableId,
    rightPath: right.path
  };
}
function stripOuterParens(text2) {
  const s = text2.trim();
  if (!s.startsWith("(") || !s.endsWith(")")) return s;
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "(") depth++;
    else if (s[i] === ")") {
      depth--;
      if (depth === 0) return i === s.length - 1 ? s.slice(1, -1).trim() : s;
    }
  }
  return s;
}
function parseGroupBy(cur, aliasToId, resolveOwner) {
  cur.expectKeyword("\u0421\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u041E\u0412\u0410\u0422\u042C");
  cur.expectKeyword("\u041F\u041E");
  if (cur.matchKeyword("\u0413\u0420\u0423\u041F\u041F\u0418\u0420\u0423\u042E\u0429\u0418\u041C")) {
    cur.expectKeyword("\u041D\u0410\u0411\u041E\u0420\u0410\u041C");
    const groupSets = parseGroupingSets(cur, aliasToId, resolveOwner);
    return { multiple: true, groupFields: [], groupSets };
  }
  const groupFields = [];
  for (; ; ) {
    const ref = parseGroupFieldRef(cur, aliasToId, resolveOwner);
    groupFields.push(ref);
    if (cur.matchPunct(",")) continue;
    break;
  }
  return { multiple: false, groupFields, groupSets: [] };
}
function parseGroupingSets(cur, aliasToId, resolveOwner) {
  cur.expectPunct("(");
  const sets = [];
  for (; ; ) {
    cur.expectPunct("(");
    const set = [];
    for (; ; ) {
      set.push(parseGroupFieldRef(cur, aliasToId, resolveOwner));
      if (cur.matchPunct(",")) continue;
      break;
    }
    cur.expectPunct(")");
    sets.push(set);
    if (cur.matchPunct(",")) continue;
    break;
  }
  cur.expectPunct(")");
  return sets;
}
function parseGroupFieldRef(cur, aliasToId, resolveOwner) {
  const tokens = [];
  let depth = 0;
  for (; ; ) {
    const t = cur.peek();
    if (depth === 0) {
      if (t.type === "keyword" && isSectionKeyword(t.value) && !cur.isPunct(".", 1)) break;
      if (t.type === "punct" && (t.value === "," || t.value === ";" || t.value === "{" || t.value === "}")) break;
      if (t.type === "eof") break;
    }
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") {
      if (depth === 0) break;
      depth--;
    }
    tokens.push(cur.next());
  }
  if (tokens.length === 0) {
    throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0430\u0441\u044C \u0441\u0441\u044B\u043B\u043A\u0430 \u043D\u0430 \u043F\u043E\u043B\u0435 \u0433\u0440\u0443\u043F\u043F\u0438\u0440\u043E\u0432\u043A\u0438", cur.peek());
  }
  const ref = parseFieldRef(tokens, aliasToId);
  if (ref) return { tableId: ref.tableId, path: ref.path };
  const bare = tryBareField(tokens, aliasToId);
  if (bare) {
    const owner = resolveOwner(bare.head);
    if (owner !== void 0) return { tableId: owner, path: bare.path };
  }
  return { tableId: "", path: "", expression: sliceSource(cur.source, tokens) };
}
function parseOrderModifiers(cur) {
  let direction = "asc";
  if (cur.matchKeyword("\u0423\u0411\u042B\u0412")) {
    direction = "desc";
  } else {
    const t = cur.peek();
    if ((t.type === "ident" || t.type === "keyword") && t.value.toUpperCase() === "\u0412\u041E\u0417\u0420") {
      cur.next();
    }
  }
  const hierarchy = cur.matchKeyword("\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F");
  return { direction, hierarchy };
}
function sectionBareOwner(segs, ctx) {
  const headUp = segs[0].toUpperCase();
  if (ctx.aliasToId.has(headUp)) return void 0;
  if (ctx.explicitAliases.has(headUp)) return void 0;
  if (segs.length === 1 && LITERAL_VALUES.has(headUp)) return void 0;
  return ctx.resolveOwner(segs[0]);
}
function parseOrder(cur, ctx) {
  const { aliasMap, aliasToId } = ctx;
  const fields = [];
  let auto = false;
  if (cur.matchKeyword("\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C")) {
    cur.expectKeyword("\u041F\u041E");
    for (; ; ) {
      const headTok = cur.peek();
      if (headTok.type === "param") {
        cur.next();
        const { direction: dir, hierarchy: hierarchy2 } = parseOrderModifiers(cur);
        fields.push({ tableId: "", path: "", direction: dir, expression: headTok.text, ...hierarchy2 ? { hierarchy: hierarchy2 } : {} });
        if (cur.matchPunct(",")) continue;
        break;
      }
      if (headTok.type !== "ident" && headTok.type !== "keyword") {
        throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u043B\u044F \u0443\u043F\u043E\u0440\u044F\u0434\u043E\u0447\u0438\u0432\u0430\u043D\u0438\u044F", headTok);
      }
      if (headTok.value.toUpperCase() === "\u0412\u042B\u0411\u041E\u0420") {
        const exprTokens = [cur.next()];
        let depth = 0;
        let caseDepth = 1;
        for (; ; ) {
          const t = cur.peek();
          if (t.type === "eof") break;
          if (depth === 0 && caseDepth === 0) {
            if (t.type === "keyword" && (isSectionKeyword(t.value) || t.value === "\u0423\u0411\u042B\u0412" || t.value === "\u0412\u041E\u0417\u0420" || t.value === "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F")) break;
            if (t.type === "ident" && t.text.toUpperCase() === "\u0412\u041E\u0417\u0420") break;
            if (t.type === "punct" && (t.value === "," || t.value === ";" || t.value === "{" || t.value === "}")) break;
          }
          if (t.type === "punct" && t.value === "(") depth++;
          else if (t.type === "punct" && t.value === ")") depth--;
          else if ((t.type === "ident" || t.type === "keyword") && t.value.toUpperCase() === "\u0412\u042B\u0411\u041E\u0420") caseDepth++;
          else if ((t.type === "ident" || t.type === "keyword") && t.value.toUpperCase() === "\u041A\u041E\u041D\u0415\u0426" && caseDepth > 0) caseDepth--;
          exprTokens.push(cur.next());
        }
        const { direction: caseDir, hierarchy: caseHier } = parseOrderModifiers(cur);
        fields.push({
          tableId: "",
          path: "",
          direction: caseDir,
          expression: sliceSource(cur.source, exprTokens),
          ...caseHier ? { hierarchy: true } : {}
        });
        if (cur.matchPunct(",")) continue;
        break;
      }
      cur.next();
      const segs = [headTok.text];
      while (cur.isPunct(".")) {
        cur.next();
        const seg = cur.peek();
        if (seg.type !== "ident" && seg.type !== "keyword") {
          throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u0441\u0435\u0433\u043C\u0435\u043D\u0442 \u0438\u043C\u0435\u043D\u0438 \u043F\u043E\u0441\u043B\u0435 \xAB.\xBB", seg);
        }
        segs.push(cur.next().text);
      }
      if (cur.isPunct("(")) {
        const exprTokens = [headTok];
        let depth = 0;
        for (; ; ) {
          const t = cur.peek();
          if (depth === 0) {
            if (t.type === "keyword" && (isSectionKeyword(t.value) || t.value === "\u0423\u0411\u042B\u0412" || t.value === "\u0412\u041E\u0417\u0420" || t.value === "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F")) break;
            if (t.type === "ident" && t.text.toUpperCase() === "\u0412\u041E\u0417\u0420") break;
            if (t.type === "punct" && (t.value === "," || t.value === ";" || t.value === "{" || t.value === "}")) break;
            if (t.type === "eof") break;
          }
          if (t.type === "punct" && t.value === "(") depth++;
          else if (t.type === "punct" && t.value === ")") {
            if (depth === 0) break;
            depth--;
          }
          exprTokens.push(cur.next());
        }
        const { direction: exprDir, hierarchy: exprHier } = parseOrderModifiers(cur);
        fields.push({
          tableId: "",
          path: "",
          direction: exprDir,
          expression: sliceSource(cur.source, exprTokens),
          ...exprHier ? { hierarchy: true } : {}
        });
        if (cur.matchPunct(",")) continue;
        break;
      }
      const cmpOp = (() => {
        const t = cur.peek();
        return t.type === "punct" && (t.value === "=" || t.value === "<>" || t.value === ">" || t.value === "<" || t.value === ">=" || t.value === "<=");
      })();
      if (cmpOp) {
        const pathText = segs.join(".");
        const rhsTokens = [];
        let depth = 0;
        for (; ; ) {
          const t = cur.peek();
          if (depth === 0) {
            if (t.type === "keyword" && (isSectionKeyword(t.value) || t.value === "\u0423\u0411\u042B\u0412" || t.value === "\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F")) break;
            if ((t.type === "ident" || t.type === "keyword") && t.value.toUpperCase() === "\u0412\u041E\u0417\u0420") break;
            if (t.type === "punct" && (t.value === "," || t.value === ";" || t.value === "{" || t.value === "}")) break;
            if (t.type === "eof") break;
          }
          if (t.type === "punct" && t.value === "(") depth++;
          else if (t.type === "punct" && t.value === ")") {
            if (depth > 0) depth--;
          }
          rhsTokens.push(cur.next());
        }
        const { direction: cmpDir, hierarchy: cmpHier } = parseOrderModifiers(cur);
        fields.push({
          tableId: "",
          path: "",
          direction: cmpDir,
          expression: `${pathText} ${sliceSource(cur.source, rhsTokens)}`,
          ...cmpHier ? { hierarchy: true } : {}
        });
        if (cur.matchPunct(",")) continue;
        break;
      }
      const peekIsEst = () => {
        const t = cur.peek();
        return (t.type === "ident" || t.type === "keyword") && t.value.toUpperCase() === "\u0415\u0421\u0422\u042C";
      };
      if (peekIsEst()) {
        cur.next();
        const nt = cur.peek();
        const neg = (nt.type === "ident" || nt.type === "keyword") && nt.value.toUpperCase() === "\u041D\u0415";
        if (neg) cur.next();
        const ntn = cur.peek();
        if ((ntn.type === "ident" || ntn.type === "keyword") && ntn.value.toUpperCase() === "NULL") cur.next();
        const { direction: nullDir, hierarchy: nullHier } = parseOrderModifiers(cur);
        fields.push({
          tableId: "",
          path: "",
          direction: nullDir,
          expression: `${segs.join(".")} \u0415\u0421\u0422\u042C ${neg ? "\u041D\u0415 " : ""}NULL`,
          ...nullHier ? { hierarchy: true } : {}
        });
        if (cur.matchPunct(",")) continue;
        break;
      }
      const { direction, hierarchy } = parseOrderModifiers(cur);
      const hier = hierarchy ? { hierarchy } : {};
      const bareOwner = sectionBareOwner(segs, ctx);
      if (segs.length > 1 && aliasToId.has(segs[0].toUpperCase())) {
        fields.push({
          tableId: aliasToId.get(segs[0].toUpperCase()),
          path: segs.slice(1).join("."),
          direction,
          qualified: true,
          ...hier
        });
      } else if (bareOwner !== void 0) {
        fields.push({ tableId: bareOwner, path: segs.join("."), direction, qualified: true, ...hier });
      } else {
        const aliasKey = segs.join(".");
        const ref = resolveSelectAlias(aliasKey, aliasMap);
        const isSelectAlias = aliasMap.has(aliasKey);
        fields.push({
          tableId: ref.tableId,
          path: ref.path,
          direction,
          ...isSelectAlias ? { selectAlias: aliasKey } : {},
          ...hier
        });
      }
      if (cur.matchPunct(",")) continue;
      break;
    }
  }
  if (cur.matchKeyword("\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415")) auto = true;
  return { fields, auto };
}
function parseTotals(cur, ctx) {
  cur.expectKeyword("\u0418\u0422\u041E\u0413\u0418");
  const totalFields = [];
  if (!cur.isKeyword("\u041F\u041E")) {
    for (; ; ) {
      totalFields.push(parseTotalAggregate(cur, ctx));
      if (cur.matchPunct(",")) continue;
      break;
    }
  }
  cur.expectKeyword("\u041F\u041E");
  const groupFields = [];
  let grand = false;
  for (; ; ) {
    if (cur.matchKeyword("\u041E\u0411\u0429\u0418\u0415")) {
      grand = true;
    } else {
      groupFields.push(parseTotalGroupField(cur, ctx));
    }
    if (cur.matchPunct(",")) continue;
    break;
  }
  return { groupFields, totalFields, grand };
}
function parseTotalAggregate(cur, ctx) {
  const aliasMap = ctx.aliasMap;
  const tokens = [];
  let depth = 0;
  for (; ; ) {
    const t = cur.peek();
    if (t.type === "eof") break;
    if (depth === 0) {
      if (t.type === "punct" && t.value === ",") break;
      if (t.type === "keyword" && t.value === "\u041F\u041E") break;
    }
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    tokens.push(cur.next());
  }
  if (tokens.length === 0) throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u043E\u0441\u044C \u0432\u044B\u0440\u0430\u0436\u0435\u043D\u0438\u0435 \u0430\u0433\u0440\u0435\u0433\u0430\u0442\u0430 \u0438\u0442\u043E\u0433\u043E\u0432", cur.peek());
  const hasTailKak = tokens.length >= 2 && tokens[tokens.length - 2].type === "keyword" && tokens[tokens.length - 2].value === "\u041A\u0410\u041A" && (tokens[tokens.length - 1].type === "ident" || tokens[tokens.length - 1].type === "keyword");
  const tailAlias = hasTailKak ? tokens[tokens.length - 1].text : void 0;
  const stripped = hasTailKak ? tokens.slice(0, tokens.length - 2) : tokens;
  const simple = matchSimpleAggregate(stripped);
  if (simple) {
    const alias = resolveAggregateOperand(simple.operand, ctx, cur.source);
    if (alias !== void 0) {
      const expr = sliceSource(cur.source, stripped);
      return { tableId: "", path: "", func: simple.func, operandAlias: alias, expression: expr };
    }
  }
  const expression = sliceSource(cur.source, tokens);
  const inner = matchSumAlias(tokens);
  if (inner) {
    const ref = aliasMap.get(inner);
    if (ref) return { tableId: ref.tableId, path: ref.path, expression, sortAlias: tailAlias };
  }
  return { tableId: "", path: "", expression, sortAlias: tailAlias };
}
function matchSimpleAggregate(tokens) {
  if (tokens.length < 4) return void 0;
  const head = tokens[0];
  if (head.type !== "keyword") return void 0;
  const func = AGG_KEYWORD_TO_FUNC[head.value];
  if (!func) return void 0;
  if (!(tokens[1].type === "punct" && tokens[1].value === "(")) return void 0;
  const last = tokens[tokens.length - 1];
  if (!(last.type === "punct" && last.value === ")")) return void 0;
  let depth = 0;
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") {
      depth--;
      if (depth === 0 && i !== tokens.length - 1) return void 0;
    }
  }
  let operand = tokens.slice(2, tokens.length - 1);
  let resolvedFunc = func;
  if (operand[0]?.type === "keyword" && operand[0].value === "\u0420\u0410\u0417\u041B\u0418\u0427\u041D\u042B\u0415") {
    operand = operand.slice(1);
    if (func === "\u041A\u043E\u043B\u0438\u0447\u0435\u0441\u0442\u0432\u043E") resolvedFunc = "\u041A\u043E\u043B\u0438\u0447\u0435\u0441\u0442\u0432\u043E\u0420\u0430\u0437\u043B\u0438\u0447\u043D\u044B\u0445";
  }
  if (operand.length === 0) return void 0;
  return { func: resolvedFunc, operand };
}
function normTotalsExpr(s) {
  return s.replace(/\s+/gu, " ").trim().toUpperCase();
}
function resolveAggregateOperand(operand, ctx, source) {
  const aliasOfField = (f) => f.alias ?? (f.path ? f.path.split(".").pop() ?? f.path : "");
  const isNameLike = operand.every(
    (t, i) => t.type === "ident" || t.type === "keyword" || t.type === "punct" && t.value === "." && i > 0 && i < operand.length - 1
  );
  if (isNameLike) {
    const segs = [];
    for (const t of operand) {
      if (t.type === "punct") continue;
      segs.push(t.text);
    }
    if (segs.length === 0) return void 0;
    const nameUp = segs.join(".").toUpperCase();
    if (segs.length === 1) {
      const byAlias = ctx.fields.find((f) => aliasOfField(f).toUpperCase() === nameUp);
      if (byAlias) return aliasOfField(byAlias);
    }
    const ref = resolveTotalsFieldRef(segs, ctx);
    if (!ref.qualified) {
      const col2 = ctx.fields.find(
        (f) => !f.expression && f.tableId === ref.tableId && f.path === ref.path
      );
      if (col2) return aliasOfField(col2);
    }
    return void 0;
  }
  const exprText = normTotalsExpr(sliceSource(source, operand));
  const col = ctx.fields.find(
    (f) => f.expression !== void 0 && normTotalsExpr(f.expression) === exprText
  );
  if (col) return aliasOfField(col);
  return void 0;
}
function matchSumAlias(tokens) {
  if (tokens.length !== 4) return void 0;
  if (!(tokens[0].type === "keyword" && tokens[0].value === "\u0421\u0423\u041C\u041C\u0410")) return void 0;
  if (!(tokens[1].type === "punct" && tokens[1].value === "(")) return void 0;
  if (tokens[2].type !== "ident" && tokens[2].type !== "keyword") return void 0;
  if (!(tokens[3].type === "punct" && tokens[3].value === ")")) return void 0;
  return tokens[2].text;
}
function resolveTotalsFieldRef(segs, ctx) {
  if (segs.length > 1 && ctx.aliasToId.has(segs[0].toUpperCase())) {
    const tableId = ctx.aliasToId.get(segs[0].toUpperCase());
    const path = segs.slice(1).join(".");
    const isColumn = ctx.fields.some((f) => !f.expression && f.tableId === tableId && f.path === path);
    return isColumn ? { tableId, path } : { tableId, path, qualified: true };
  }
  const name = segs.join(".");
  const hit = ctx.aliasMap.get(name);
  if (hit) return { tableId: hit.tableId, path: hit.path };
  if (segs.length === 1) {
    const up3 = segs[0].toUpperCase();
    const col = ctx.fields.find(
      (f) => !f.expression && !!f.path && (f.path.split(".").pop() ?? "").toUpperCase() === up3
    );
    if (col) return { tableId: col.tableId, path: col.path };
  }
  const owner = sectionBareOwner(segs, ctx);
  if (owner !== void 0) {
    return { tableId: owner, path: name, qualified: true };
  }
  return { tableId: "", path: name };
}
function matchPeriodBy(cur) {
  const head = cur.peek();
  if (head.type !== "ident" || head.text.toUpperCase() !== "\u041F\u0415\u0420\u0418\u041E\u0414\u0410\u041C\u0418") return void 0;
  if (!cur.isPunct("(", 1)) return void 0;
  cur.next();
  cur.expectPunct("(");
  const args = [];
  let curArg = [];
  let depth = 0;
  for (; ; ) {
    const t = cur.peek();
    if (t.type === "eof") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u0441\u0438\u043C\u0432\u043E\u043B \xAB)\xBB \u0432 \u041F\u0415\u0420\u0418\u041E\u0414\u0410\u041C\u0418(\u2026)", t);
    if (depth === 0 && t.type === "punct" && t.value === ")") {
      cur.next();
      break;
    }
    if (depth === 0 && t.type === "punct" && t.value === ",") {
      cur.next();
      args.push(sliceSource(cur.source, curArg));
      curArg = [];
      continue;
    }
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    curArg.push(cur.next());
  }
  if (curArg.length) args.push(sliceSource(cur.source, curArg));
  if (args.length) args[0] = args[0].toUpperCase();
  return `\u041F\u0415\u0420\u0418\u041E\u0414\u0410\u041C\u0418(${args.join(", ")})`;
}
function parseTotalGroupField(cur, ctx) {
  const aliasTok = cur.peek();
  if (aliasTok.type === "param") {
    cur.next();
    return { tableId: "", path: "", kind: "elements", expression: aliasTok.text };
  }
  const segs = readDottedPath(cur);
  if (!segs) throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u0433\u0440\u0443\u043F\u043F\u0438\u0440\u043E\u0432\u043E\u0447\u043D\u043E\u0433\u043E \u043F\u043E\u043B\u044F \u0438\u0442\u043E\u0433\u043E\u0432", aliasTok);
  const ref = resolveTotalsFieldRef(segs, ctx);
  const periodBy = matchPeriodBy(cur);
  let kind = "elements";
  if (cur.matchKeyword("\u0422\u041E\u041B\u042C\u041A\u041E")) {
    cur.expectKeyword("\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F");
    kind = "onlyHierarchy";
  } else if (cur.matchKeyword("\u0418\u0415\u0420\u0410\u0420\u0425\u0418\u042F")) {
    kind = "hierarchy";
  }
  const field = { tableId: ref.tableId, path: ref.path, kind };
  if (ref.qualified) field.qualified = true;
  if (segs.length === 1 && ctx.aliasMap.has(segs[0])) field.selectAlias = segs[0];
  if (periodBy) field.periodBy = periodBy;
  if (cur.matchKeyword("\u041A\u0410\u041A")) {
    const a = cur.peek();
    if (a.type !== "ident" && a.type !== "keyword") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u0441\u043B\u0435 \u041A\u0410\u041A", a);
    cur.next();
    field.alias = a.text;
  }
  return field;
}
function parseIndex(cur, ctx) {
  cur.expectKeyword("\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C");
  cur.expectKeyword("\u041F\u041E");
  if (cur.matchKeyword("\u041D\u0410\u0411\u041E\u0420\u0410\u041C")) {
    cur.expectPunct("(");
    const indexes = [];
    for (; ; ) {
      cur.expectPunct("(");
      const fields2 = [];
      for (; ; ) {
        fields2.push(parseIndexField(cur, ctx));
        if (cur.matchPunct(",")) continue;
        break;
      }
      cur.expectPunct(")");
      const unique = cur.matchKeyword("\u0423\u041D\u0418\u041A\u0410\u041B\u042C\u041D\u041E");
      indexes.push({ unique, fields: fields2 });
      if (cur.matchPunct(",")) continue;
      break;
    }
    cur.expectPunct(")");
    return { indexes };
  }
  const fields = [];
  for (; ; ) {
    fields.push(parseIndexField(cur, ctx));
    if (cur.matchPunct(",")) continue;
    break;
  }
  return { indexes: [{ unique: false, fields }] };
}
function readDottedPath(cur) {
  const head = cur.peek();
  if (head.type !== "ident" && head.type !== "keyword") return void 0;
  cur.next();
  const segs = [head.text];
  while (cur.isPunct(".")) {
    cur.next();
    const seg = cur.peek();
    if (seg.type !== "ident" && seg.type !== "keyword") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u0441\u0435\u0433\u043C\u0435\u043D\u0442 \u0438\u043C\u0435\u043D\u0438 \u043F\u043E\u0441\u043B\u0435 \xAB.\xBB", seg);
    segs.push(cur.next().text);
  }
  return segs;
}
function resolveSectionFieldRef(segs, ctx) {
  if (segs.length > 1 && ctx.aliasToId.has(segs[0].toUpperCase())) {
    return { tableId: ctx.aliasToId.get(segs[0].toUpperCase()), path: segs.slice(1).join("."), qualified: true };
  }
  const owner = sectionBareOwner(segs, ctx);
  if (owner !== void 0) {
    return { tableId: owner, path: segs.join("."), qualified: true };
  }
  const aliasKey = segs.join(".");
  const ref = resolveSelectAlias(aliasKey, ctx.aliasMap);
  const firstSame = ctx.fields.find((f) => f.tableId === ref.tableId && f.path === ref.path && !f.expression);
  const firstAlias = firstSame?.alias ?? (ref.path.split(".").pop() ?? ref.path);
  if (ctx.aliasMap.has(aliasKey) && aliasKey !== firstAlias) {
    return { tableId: ref.tableId, path: ref.path, selectAlias: aliasKey };
  }
  return { tableId: ref.tableId, path: ref.path };
}
function parseIndexField(cur, ctx) {
  const t = cur.peek();
  if (t.type === "param") {
    cur.next();
    return { tableId: "", path: "", expression: t.text };
  }
  const head = cur.peek();
  if ((head.type === "ident" || head.type === "keyword") && cur.peek(1).type === "punct" && cur.peek(1).value === "(") {
    const exprTokens = [cur.next()];
    let depth = 0;
    for (; ; ) {
      const tk = cur.peek();
      if (depth === 0) {
        if (tk.type === "keyword" && isSectionKeyword(tk.value)) break;
        if (tk.type === "punct" && (tk.value === "," || tk.value === ";" || tk.value === "{" || tk.value === "}")) break;
        if (tk.type === "eof") break;
      }
      if (tk.type === "punct" && tk.value === "(") depth++;
      else if (tk.type === "punct" && tk.value === ")") {
        if (depth === 0) break;
        depth--;
      }
      exprTokens.push(cur.next());
    }
    return { tableId: "", path: "", expression: sliceSource(cur.source, exprTokens) };
  }
  const segs = readDottedPath(cur);
  if (!segs) throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u043B\u044F \u0438\u043D\u0434\u0435\u043A\u0441\u0430", t);
  return resolveSectionFieldRef(segs, ctx);
}
function parseLockForUpdate(cur) {
  cur.expectKeyword("\u0414\u041B\u042F");
  cur.expectKeyword("\u0418\u0417\u041C\u0415\u041D\u0415\u041D\u0418\u042F");
  const names = [];
  while (cur.peek().type === "ident" || cur.peek().type === "keyword" && !isSectionKeyword(cur.peek().value)) {
    names.push(parseDottedName(cur));
  }
  return names;
}
var SECTION_KEYWORDS = /* @__PURE__ */ new Set(["\u0418\u041C\u0415\u042E\u0429\u0418\u0415", "\u0418\u041D\u0414\u0415\u041A\u0421\u0418\u0420\u041E\u0412\u0410\u0422\u042C", "\u0418\u0422\u041E\u0413\u0418", "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C", "\u0410\u0412\u0422\u041E\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0412\u0410\u041D\u0418\u0415", "\u0414\u041B\u042F"]);
function isSectionKeyword(value) {
  return SECTION_KEYWORDS.has(value);
}
function parseBuilderBlock(cur, keyword) {
  cur.expectPunct("{");
  cur.expectKeyword(keyword);
  if (keyword === "\u0423\u041F\u041E\u0420\u042F\u0414\u041E\u0427\u0418\u0422\u042C" || keyword === "\u0418\u0422\u041E\u0413\u0418") {
    cur.expectKeyword("\u041F\u041E");
  }
  const fields = [];
  for (; ; ) {
    fields.push(parseBuilderField(cur, keyword === "\u0413\u0414\u0415"));
    if (cur.matchPunct(",")) continue;
    break;
  }
  cur.expectPunct("}");
  return fields;
}
function parseBuilderCondition(cur) {
  const tokens = [];
  let depth = 0;
  for (; ; ) {
    const t = cur.peek();
    if (t.type === "eof") break;
    if (depth === 0) {
      if (t.type === "punct" && (t.value === "," || t.value === "}")) break;
      if (t.type === "keyword" && t.value === "\u041A\u0410\u041A") break;
    }
    if (t.type === "punct" && t.value === "(") depth++;
    else if (t.type === "punct" && t.value === ")") depth--;
    tokens.push(cur.next());
  }
  if (tokens.length === 0) throw cur.error("\u043F\u0443\u0441\u0442\u043E\u0435 \u0443\u0441\u043B\u043E\u0432\u0438\u0435 \u043F\u043E\u0441\u0442\u0440\u043E\u0438\u0442\u0435\u043B\u044F");
  let child = false;
  if (tokens.length >= 2 && tokens[tokens.length - 1].type === "punct" && tokens[tokens.length - 1].value === "*" && tokens[tokens.length - 2].type === "punct" && tokens[tokens.length - 2].value === ".") {
    child = true;
    tokens.length -= 2;
  }
  const field = {
    ref: stripOuterParens(sliceSource(cur.source, tokens)),
    child,
    condition: true
  };
  if (cur.matchKeyword("\u041A\u0410\u041A")) {
    const a = cur.peek();
    if (a.type !== "ident" && a.type !== "keyword") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u0441\u043B\u0435 \u041A\u0410\u041A", a);
    cur.next();
    field.alias = a.text;
  }
  return field;
}
function parseBuilderField(cur, allowCondition = false) {
  const first = cur.peek();
  if (allowCondition && (first.type !== "ident" && first.type !== "keyword" || first.value === "\u041D\u0415")) {
    return parseBuilderCondition(cur);
  }
  if (first.type !== "ident" && first.type !== "keyword") {
    throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0430\u0441\u044C \u0441\u0441\u044B\u043B\u043A\u0430 \u043F\u043E\u043B\u044F \u043F\u043E\u0441\u0442\u0440\u043E\u0438\u0442\u0435\u043B\u044F", first);
  }
  const mark = cur.mark();
  let ref = cur.next().text;
  let child = false;
  while (cur.isPunct(".")) {
    cur.next();
    if (cur.isPunct("*")) {
      cur.next();
      child = true;
      break;
    }
    const seg = cur.peek();
    if (seg.type !== "ident" && seg.type !== "keyword") {
      throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u0441\u0435\u0433\u043C\u0435\u043D\u0442 \u0441\u0441\u044B\u043B\u043A\u0438 \u043F\u043E\u0441\u0442\u0440\u043E\u0438\u0442\u0435\u043B\u044F \u043F\u043E\u0441\u043B\u0435 \xAB.\xBB", seg);
    }
    ref += "." + cur.next().text;
  }
  if (allowCondition && !child) {
    const after = cur.peek();
    const refComplete = after.type === "punct" && (after.value === "," || after.value === "}") || after.type === "keyword" && after.value === "\u041A\u0410\u041A";
    if (!refComplete) {
      cur.reset(mark);
      return parseBuilderCondition(cur);
    }
  }
  const field = { ref, child };
  if (cur.matchKeyword("\u041A\u0410\u041A")) {
    const a = cur.peek();
    if (a.type !== "ident" && a.type !== "keyword") throw cur.error("\u043E\u0436\u0438\u0434\u0430\u043B\u0441\u044F \u043F\u0441\u0435\u0432\u0434\u043E\u043D\u0438\u043C \u043F\u043E\u0441\u043B\u0435 \u041A\u0410\u041A", a);
    cur.next();
    field.alias = a.text;
  }
  return field;
}
function splitUnionMembers(tokens, source) {
  const members = [];
  let current = [];
  let nextDistinct = false;
  let parenDepth = 0;
  let braceDepth = 0;
  const flush = (distinct) => {
    const last = current[current.length - 1];
    const eofPos = last ? last.pos + last.value.length : 0;
    const eofTok = { type: "eof", value: "", text: "", pos: eofPos, line: last?.line ?? 1, col: last?.col ?? 1 };
    members.push({ tokens: [...current, eofTok], distinct });
    current = [];
  };
  for (const t of tokens) {
    if (t.type === "eof") break;
    if (t.type === "punct") {
      if (t.value === "(") parenDepth++;
      else if (t.value === ")") parenDepth--;
      else if (t.value === "{") braceDepth++;
      else if (t.value === "}") braceDepth--;
    }
    if (t.type === "keyword" && t.value === "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C" && parenDepth === 0 && braceDepth === 0) {
      flush(nextDistinct);
      nextDistinct = true;
      continue;
    }
    if (t.type === "keyword" && t.value === "\u0412\u0421\u0415" && parenDepth === 0 && braceDepth === 0 && current.length === 0) {
      nextDistinct = false;
      continue;
    }
    current.push(t);
  }
  flush(nextDistinct);
  return members;
}
function splitUnionMemberTexts(text2) {
  const tokens = tokenize(text2);
  const slices = [];
  let segStart = 0;
  let parenDepth = 0;
  let braceDepth = 0;
  let i = 0;
  while (i < tokens.length) {
    const t = tokens[i];
    if (t.type === "eof") break;
    if (t.type === "punct") {
      if (t.value === "(") parenDepth++;
      else if (t.value === ")") parenDepth--;
      else if (t.value === "{") braceDepth++;
      else if (t.value === "}") braceDepth--;
    }
    if (t.type === "keyword" && t.value === "\u041E\u0411\u042A\u0415\u0414\u0418\u041D\u0418\u0422\u042C" && parenDepth === 0 && braceDepth === 0) {
      slices.push(text2.slice(segStart, t.pos));
      let sepEnd = t.pos + t.text.length;
      let j = i + 1;
      const nxt = tokens[j];
      if (nxt && nxt.type === "keyword" && nxt.value === "\u0412\u0421\u0415") {
        sepEnd = nxt.pos + nxt.text.length;
        j++;
      }
      segStart = sepEnd;
      i = j;
      continue;
    }
    i++;
  }
  slices.push(text2.slice(segStart));
  return slices;
}
function extractDocComments(text2, doc) {
  if (doc.members.length === 0) return;
  if (doc.members.length === 1) {
    try {
      extractComments(text2, doc.members[0].model);
    } catch {
    }
    return;
  }
  const slices = splitUnionMemberTexts(text2);
  if (slices.length !== doc.members.length) return;
  doc.members.forEach((m, i) => {
    try {
      extractComments(slices[i], m.model);
    } catch {
    }
  });
}
function parseDocument(text2, resolver, opts) {
  const prevSourceResolver = sourceResolver;
  sourceResolver = resolver;
  try {
    const doc = parseDocumentInner(text2, resolver);
    if (opts?.preserveComments) {
      extractDocComments(text2, doc);
    }
    return doc;
  } finally {
    sourceResolver = prevSourceResolver;
  }
}
function parseDocumentInner(text2, resolver) {
  const tokens = tokenize(text2);
  const raw = splitUnionMembers(tokens, text2);
  let firstCtx;
  const models = raw.map((r, i) => {
    const ctxOut = {};
    const model = parseSingleQuery(new Cursor(r.tokens, text2), i > 0 ? firstCtx : void 0, ctxOut);
    if (i === 0) firstCtx = ctxOut.ctx;
    if (resolver?.canonicalFullName) {
      for (const t of model.tables) {
        if (t.subquery || !t.fullName) continue;
        const canon = resolver.canonicalFullName(t.fullName);
        if (canon && canon !== t.fullName) t.fullName = canon;
      }
    }
    canonicalizeFieldCasing(model, resolver);
    expandStarFields(model, resolver);
    expandTabSectionFields(model, resolver);
    wrapTabSectionAggregates(model, resolver);
    dropUserIBConditions(model, resolver);
    dropUnlimitedStringConditions(model, resolver);
    resolveBuilderStar(model, resolver);
    qualifyBareFields(model, resolver);
    markDottedAutoAlias(model, resolver);
    dropRedundantGroupDerefs(model, resolver);
    moveBeforePrefixGroupDerefToEnd(model, resolver);
    moveLeadingMovementCaseToEnd(model);
    dropFunctionallyDeterminedMovementCase(model, resolver);
    relocateKeptMovementCase(model, resolver);
    substituteGroupFieldWithSelectExpr(model, resolver, subquerySourceDepth > 0);
    if (resolver) {
      for (const t of model.tables) {
        if (t.subquery || !t.fullName) continue;
        if (resolver.tableByFullName(t.fullName)?.hierarchical) t.hierarchical = true;
      }
      applyAccountingMeta(model, resolver);
    }
    for (const t of model.tables) {
      if (t.virtual?.accountingArgs) delete t.virtual.accountingArgs;
    }
    return model;
  });
  models.forEach(assignExpressionFieldAliases);
  const columnAliases = models.length > 0 ? models[0].fields.map((f) => fieldAlias(f, models[0])) : [];
  const members = models.map((model, i) => {
    if (i > 0) rewriteMemberAliases(model, columnAliases);
    return { name: `\u0417\u0430\u043F\u0440\u043E\u0441 ${i + 1}`, distinct: raw[i].distinct, model };
  });
  const doc = { members };
  qualifyBareSectionFields(doc, resolver);
  return doc;
}
function markDottedAutoAlias(model, resolver) {
  if (!resolver) return;
  for (const f of model.fields) {
    if (!f.qualified || f.alias !== void 0) continue;
    const segs = f.path.split(".");
    if (segs.length < 2) continue;
    const t = model.tables.find((tb) => tb.id === f.tableId);
    if (!t || t.subquery || t.virtual || !t.fullName) continue;
    if (t.fullName.split(".").length !== 1) continue;
    const meta = resolver.tableByFullName(t.fullName);
    const leadIsColumn = !!meta && meta.fields.some(
      (mf) => mf.name.toUpperCase() === segs[0].toUpperCase()
    );
    if (!leadIsColumn) f.autoAliasDotted = true;
  }
}
function assignExpressionFieldAliases(model) {
  let exprCounter = 0;
  for (const f of model.fields) {
    if (f.expression === void 0) continue;
    if (f.alias !== void 0) continue;
    const m = BARE_PARAM_ALIAS.exec(f.expression.trim());
    f.alias = m ? m[1] : `\u041F\u043E\u043B\u0435${++exprCounter}`;
  }
}
function applyAccountingMeta(model, resolver) {
  const ACC_KEYS = [
    "period",
    "startPeriod",
    "endPeriod",
    "periodicity",
    "fillMethod",
    "condition",
    "accountCondition",
    "corrAccountCondition",
    "accountDtCondition",
    "accountKtCondition",
    "order",
    "top"
  ];
  for (const t of model.tables) {
    const v = t.virtual;
    if (!v?.accountingArgs || t.subquery || !t.fullName) continue;
    const parts = t.fullName.split(".");
    if (parts[0] !== "\u0420\u0435\u0433\u0438\u0441\u0442\u0440\u0411\u0443\u0445\u0433\u0430\u043B\u0442\u0435\u0440\u0438\u0438") continue;
    const slice = parts[2];
    const base = resolver.tableByFullName(`${parts[0]}.${parts[1]}`);
    const hasSubconto = (base?.subcontoCount ?? 0) > 0;
    const corr = base?.correspondence === true;
    const args = v.accountingArgs;
    for (const k of ACC_KEYS) delete v[k];
    accountingPositionKeys(slice, hasSubconto, corr).forEach((k, i) => {
      const val = args[i] ?? "";
      if (k && val !== "") v[k] = val;
    });
    v.subconto = hasSubconto;
    if (corr) v.correspondence = true;
    delete v.accountingArgs;
  }
}
function isNullCell(f) {
  return f.expression !== void 0 && f.expression.trim().toUpperCase() === "NULL";
}
function rewriteMemberAliases(model, columnAliases) {
  const rewritten = [];
  model.fields.forEach((f, k) => {
    if (isNullCell(f)) {
      rewritten.push(f);
      return;
    }
    const alias = columnAliases[k];
    if (alias === void 0) {
      rewritten.push(f);
      return;
    }
    rewritten.push({ ...f, alias });
  });
  model.fields = rewritten;
}
var BATCH_SEPARATOR_RE = /[ \t]*;[ \t]*(?:\/{4,}[ \t]*)?(?:\n(?:[ \t]*\n)*(?:\/{4,}[ \t]*(?:\n(?:[ \t]*\n)*|$))?)?/gu;
function stringLiteralRanges(text2) {
  const ranges = [];
  let i = 0;
  while (i < text2.length) {
    const ch = text2[i];
    if (ch === '"') {
      const start = i;
      i += 1;
      while (i < text2.length) {
        if (text2[i] === '"') {
          if (text2[i + 1] === '"') {
            i += 2;
            continue;
          }
          i += 1;
          break;
        }
        i += 1;
      }
      ranges.push([start, i]);
      continue;
    }
    if (ch === "/" && text2[i + 1] === "/") {
      const start = i;
      while (i < text2.length && text2[i] !== "\n") i += 1;
      ranges.push([start, i]);
      continue;
    }
    i += 1;
  }
  return ranges;
}
function splitBatchText(text2) {
  const ranges = stringLiteralRanges(text2);
  const insideString = (pos) => ranges.some(([s, e]) => pos >= s && pos < e);
  const chunks = [];
  let last = 0;
  BATCH_SEPARATOR_RE.lastIndex = 0;
  for (let m = BATCH_SEPARATOR_RE.exec(text2); m !== null; m = BATCH_SEPARATOR_RE.exec(text2)) {
    if (insideString(m.index)) {
      BATCH_SEPARATOR_RE.lastIndex = m.index + 1;
      continue;
    }
    chunks.push(text2.slice(last, m.index));
    last = m.index + m[0].length;
  }
  chunks.push(text2.slice(last));
  return chunks;
}
function attachBatchComments(chunks, members) {
  if (chunks.length !== members.length) return;
  members.forEach((doc, i) => extractDocComments(chunks[i], doc));
}
function parseBatch(text2, resolver, opts) {
  const normalized = text2.replace(/\s*;\s*$/u, "");
  const chunks = splitBatchText(normalized).filter((c) => c.trim() !== "");
  const tempTables = /* @__PURE__ */ new Map();
  const members = chunks.map((c) => {
    const doc = parseDocument(c, augmentResolverWithTempTables(resolver, tempTables));
    registerTempTables(doc, tempTables);
    return doc;
  });
  const inf = inferUndefinedTempTables(chunks, members, resolver);
  if (inf.tables.size === 0) {
    if (opts?.preserveComments) attachBatchComments(chunks, members);
    return { members };
  }
  const tempTables2 = /* @__PURE__ */ new Map();
  const members2 = chunks.map((c, i) => {
    const visible = /* @__PURE__ */ new Map();
    for (const [up3, t] of inf.tables) {
      const first = inf.firstRefChunk.get(up3);
      if (first !== void 0 && first < i) visible.set(up3, t);
    }
    const doc = parseDocument(
      c,
      augmentResolverWithTempTables(resolver, tempTables2, visible.size ? visible : void 0)
    );
    registerTempTables(doc, tempTables2);
    return doc;
  });
  if (opts?.preserveComments) attachBatchComments(chunks, members2);
  return { members: members2 };
}
function inferUndefinedTempTables(chunks, members, resolver) {
  const defineChunk = /* @__PURE__ */ new Map();
  members.forEach((doc, i) => {
    const m0 = doc.members[0]?.model;
    if (m0?.queryType === "createTemp" && m0.tempTableName) {
      const up3 = m0.tempTableName.toUpperCase();
      if (!defineChunk.has(up3)) defineChunk.set(up3, i);
    }
  });
  const candidates = /* @__PURE__ */ new Set();
  const aliasToTempPerChunk = members.map((doc, i) => {
    const map = /* @__PURE__ */ new Map();
    for (const m of doc.members) {
      for (const t of m.model.tables) {
        if (t.subquery || t.virtual || !t.fullName) continue;
        if (t.fullName.includes(".")) continue;
        const up3 = t.fullName.toUpperCase();
        const def = defineChunk.get(up3);
        if (def !== void 0 && def <= i) continue;
        if (resolver?.tableByFullName?.(t.fullName)) continue;
        if (resolver?.virtualTableByFullName?.(t.fullName)) continue;
        const alias = (t.alias ?? t.fullName).toUpperCase();
        map.set(alias, up3);
        candidates.add(up3);
      }
    }
    return map;
  });
  if (candidates.size === 0) return { tables: /* @__PURE__ */ new Map(), firstRefChunk: /* @__PURE__ */ new Map() };
  const cols = /* @__PURE__ */ new Map();
  const seen = /* @__PURE__ */ new Map();
  const firstRefChunk = /* @__PURE__ */ new Map();
  for (const c of candidates) {
    cols.set(c, []);
    seen.set(c, /* @__PURE__ */ new Set());
  }
  const ref = /([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\.([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)(\.)?/gu;
  chunks.forEach((chunk, i) => {
    const aliasMap = aliasToTempPerChunk[i];
    if (aliasMap.size === 0) return;
    let mt;
    ref.lastIndex = 0;
    while ((mt = ref.exec(chunk)) !== null) {
      const tempName = aliasMap.get(mt[1].toUpperCase());
      if (!tempName) continue;
      if (!firstRefChunk.has(tempName)) firstRefChunk.set(tempName, i);
      if (mt[3]) continue;
      const colUp = mt[2].toUpperCase();
      const s = seen.get(tempName);
      if (s.has(colUp)) continue;
      s.add(colUp);
      cols.get(tempName).push(mt[2]);
    }
  });
  const starred = /* @__PURE__ */ new Set();
  const dotStar = /([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\.\*/gu;
  const bareStar = /(^|[,(\n\r\t ])\*(?=\s*(?:,|$|\r|\n))/gmu;
  chunks.forEach((chunk, i) => {
    const aliasMap = aliasToTempPerChunk[i];
    if (aliasMap.size === 0) return;
    let m;
    dotStar.lastIndex = 0;
    while ((m = dotStar.exec(chunk)) !== null) {
      const t = aliasMap.get(m[1].toUpperCase());
      if (t) starred.add(t);
    }
    if (bareStar.test(chunk)) {
      for (const t of aliasMap.values()) starred.add(t);
    }
  });
  const out = /* @__PURE__ */ new Map();
  for (const [up3, columns] of cols) {
    if (columns.length === 0) continue;
    if (!starred.has(up3)) continue;
    let name = up3;
    outer: for (const doc of members) {
      for (const m of doc.members) {
        for (const t of m.model.tables) {
          if (t.fullName && t.fullName.toUpperCase() === up3) {
            name = t.fullName;
            break outer;
          }
        }
      }
    }
    const fields = columns.map((c) => ({ name: c, kind: "attribute", types: [] }));
    out.set(up3, { kind: "\u0421\u043F\u0440\u0430\u0432\u043E\u0447\u043D\u0438\u043A", name, fullName: name, fields });
  }
  return { tables: out, firstRefChunk };
}
function isScalarLiteralExpr(expr) {
  if (expr === void 0) return false;
  const s = expr.trim();
  if (s === "") return false;
  if (/^"(?:[^"]|"")*"$/.test(s)) return true;
  if (/^-?\d+(?:[.,]\d+)?$/.test(s)) return true;
  if (/^(?:ИСТИНА|ЛОЖЬ)$/iu.test(s)) return true;
  return false;
}
function registerTempTables(doc, tempTables) {
  const m0 = doc.members[0]?.model;
  if (!m0 || m0.queryType !== "createTemp" || !m0.tempTableName) return;
  const cols = [];
  const seen = /* @__PURE__ */ new Set();
  for (const f of m0.fields) {
    const a = fieldAlias(f, m0);
    if (!a || a === "*") continue;
    let alias = a;
    let n = 0;
    while (seen.has(alias.toUpperCase())) alias = `${a}${++n}`;
    seen.add(alias.toUpperCase());
    cols.push({ alias, scalar: isScalarLiteralExpr(f.expression) });
  }
  if (cols.length === 0) return;
  const fields = cols.map(({ alias, scalar }) => ({
    name: alias,
    kind: "attribute",
    types: scalar ? [{ primitive: "\u0421\u0442\u0440\u043E\u043A\u0430" }] : []
  }));
  tempTables.set(m0.tempTableName.toUpperCase(), {
    kind: "\u0421\u043F\u0440\u0430\u0432\u043E\u0447\u043D\u0438\u043A",
    // вид не используется развёрткой ВТ (нет ТЧ/виртуальных полей)
    name: m0.tempTableName,
    fullName: m0.tempTableName,
    fields
  });
}
function augmentResolverWithTempTables(base, tempTables, inferred) {
  if (tempTables.size === 0 && (!inferred || inferred.size === 0)) return base;
  const lookup = (fullName) => {
    const up3 = fullName.toUpperCase();
    return tempTables.get(up3) ?? base?.tableByFullName(fullName) ?? inferred?.get(up3);
  };
  return {
    tableByFullName: lookup,
    // Виртуальный слой пробрасываем как есть — ВТ виртуальных таблиц не имеют.
    virtualTableByFullName: (fullName) => base?.virtualTableByFullName?.(fullName),
    // Канонизация ИМЕНИ источника-ВТ к написанию её определения `ПОМЕСТИТЬ <имя>`
    // (фаза 6.16.76): `ВтВзносыБезОкругления`→`ВТВзносыБезОкругления`. ВТ
    // нечувствительны к регистру; реестр хранит каноническое имя из определения.
    canonicalFullName: (fullName) => tempTables.get(fullName.toUpperCase())?.name ?? base?.canonicalFullName?.(fullName)
  };
}

// ../../../../tmp/tmp.Q5PgKXQI6O/entry.ts
var text = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => text += d);
process.stdin.on("end", () => {
  try {
    process.stdout.write(JSON.stringify(parseBatch(text)));
  } catch (e) {
    process.stdout.write(JSON.stringify({ error: String(e) }));
  }
});
