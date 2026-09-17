// 交换格式 JSON 的精确解析器。
//
// 为什么不用 `JSON.parse`：`qy export` 产出的 JSON 直接内嵌 Python int
// （`qy/backend/vm/bytecode.py::serialize_bytecode_json` 里的
// `{"type": "int", "value": <int>}`），而 Python `IntValue` 是任意精度。
// `JSON.parse` 在词法阶段就把超过 2^53 的整数字面量四舍五入成 double，
// reviver 无法恢复精度。这里手写一个最小 JSON 解析器：
//
//   - 整数 token（无 `.` / `e`）在安全整数范围内返回 `number`
//     （保持寄存器下标、function index 等既有用法不变），
//     超出范围返回 `bigint`；
//   - 浮点 token（含 `.` 或 `e` / `E`）返回 `number`；
//   - 字符串 / 布尔 / null / 数组 / 对象与 `JSON.parse` 一致。
//
// 这不是第二套语义实现：它只负责把交换格式的字节无损地搬进宿主。

export type JsonValue =
  | null
  | boolean
  | number
  | bigint
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

const NUMBER_RE = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/;
const MIN_SAFE = BigInt(Number.MIN_SAFE_INTEGER);
const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER);

class JsonParser {
  private index = 0;

  constructor(private readonly text: string) {}

  parse(): JsonValue {
    const value = this.parseValue();
    this.skipWhitespace();
    if (this.index !== this.text.length) {
      throw new SyntaxError(`unexpected trailing JSON content at offset ${this.index}`);
    }
    return value;
  }

  private skipWhitespace(): void {
    while (this.index < this.text.length) {
      const ch = this.text[this.index];
      if (ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r') this.index += 1;
      else break;
    }
  }

  private parseValue(): JsonValue {
    this.skipWhitespace();
    if (this.index >= this.text.length) throw new SyntaxError('unexpected end of JSON input');
    const ch = this.text[this.index];
    if (ch === '{') return this.parseObject();
    if (ch === '[') return this.parseArray();
    if (ch === '"') return this.parseString();
    if (ch === 't') {
      this.expect('true');
      return true;
    }
    if (ch === 'f') {
      this.expect('false');
      return false;
    }
    if (ch === 'n') {
      this.expect('null');
      return null;
    }
    return this.parseNumber();
  }

  private expect(token: string): void {
    if (this.text.slice(this.index, this.index + token.length) !== token) {
      throw new SyntaxError(`invalid JSON token at offset ${this.index}`);
    }
    this.index += token.length;
  }

  private parseNumber(): number | bigint {
    const match = NUMBER_RE.exec(this.text.slice(this.index));
    if (match === null) throw new SyntaxError(`invalid JSON number at offset ${this.index}`);
    const token = match[0];
    this.index += token.length;
    if (token.includes('.') || token.includes('e') || token.includes('E')) {
      return Number(token);
    }
    const exact = BigInt(token);
    if (exact >= MIN_SAFE && exact <= MAX_SAFE) return Number(exact);
    return exact;
  }

  private parseString(): string {
    // 调用点保证当前字符是 `"`
    this.index += 1;
    let out = '';
    for (;;) {
      if (this.index >= this.text.length) throw new SyntaxError('unterminated JSON string');
      const ch = this.text[this.index];
      if (ch === '"') {
        this.index += 1;
        return out;
      }
      if (ch !== '\\') {
        out += ch;
        this.index += 1;
        continue;
      }
      this.index += 1;
      const esc = this.text[this.index];
      this.index += 1;
      switch (esc) {
        case '"':
          out += '"';
          break;
        case '\\':
          out += '\\';
          break;
        case '/':
          out += '/';
          break;
        case 'b':
          out += '\b';
          break;
        case 'f':
          out += '\f';
          break;
        case 'n':
          out += '\n';
          break;
        case 'r':
          out += '\r';
          break;
        case 't':
          out += '\t';
          break;
        case 'u': {
          const hex = this.text.slice(this.index, this.index + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) {
            throw new SyntaxError(`invalid JSON unicode escape at offset ${this.index}`);
          }
          out += String.fromCharCode(Number.parseInt(hex, 16));
          this.index += 4;
          break;
        }
        default:
          throw new SyntaxError(`invalid JSON escape '\\${String(esc)}'`);
      }
    }
  }

  private parseArray(): JsonValue[] {
    this.index += 1; // [
    const items: JsonValue[] = [];
    this.skipWhitespace();
    if (this.text[this.index] === ']') {
      this.index += 1;
      return items;
    }
    for (;;) {
      items.push(this.parseValue());
      this.skipWhitespace();
      const ch = this.text[this.index];
      if (ch === ',') {
        this.index += 1;
        continue;
      }
      if (ch === ']') {
        this.index += 1;
        return items;
      }
      throw new SyntaxError(`invalid JSON array at offset ${this.index}`);
    }
  }

  private parseObject(): { [key: string]: JsonValue } {
    this.index += 1; // {
    const result: { [key: string]: JsonValue } = {};
    this.skipWhitespace();
    if (this.text[this.index] === '}') {
      this.index += 1;
      return result;
    }
    for (;;) {
      this.skipWhitespace();
      if (this.text[this.index] !== '"') {
        throw new SyntaxError(`invalid JSON object key at offset ${this.index}`);
      }
      const key = this.parseString();
      this.skipWhitespace();
      if (this.text[this.index] !== ':') {
        throw new SyntaxError(`invalid JSON object at offset ${this.index}`);
      }
      this.index += 1;
      result[key] = this.parseValue();
      this.skipWhitespace();
      const ch = this.text[this.index];
      if (ch === ',') {
        this.index += 1;
        continue;
      }
      if (ch === '}') {
        this.index += 1;
        return result;
      }
      throw new SyntaxError(`invalid JSON object at offset ${this.index}`);
    }
  }
}

/** 精确解析 JSON：整数在安全范围外保留为 `bigint`。 */
export function parseJsonExact(text: string): JsonValue {
  return new JsonParser(text).parse();
}
