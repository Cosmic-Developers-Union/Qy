from typing import List
from typing import List, Iterator
import unicodedata
import pathlib
import re


class symbol:
    def __init__(self, name, value=None) -> None:
        self.name = name
        self.value = value

    def __repr__(self) -> str:
        return f'<symbol {self.name}>'

    def __str__(self) -> str:
        return self.name


class symbolprefix(symbol):
    def __repr__(self) -> str:
        return f'<symbol-prefix {self.name}>'


class Token:
    def __init__(self, type: str, value: str) -> None:
        self.type = type
        self.value = value

    def __repr__(self) -> str:
        return f'<{self.type} "{self.value}">'


def tokenize(source: str) -> Iterator[Token]:
    source = unicodedata.normalize('NFKC', source)
    buffer: List[str] = []
    in_string = False
    i = 0

    while i < len(source):
        char = source[i]

        if in_string:
            if char == '"' and source[i-1] != '\\':
                buffer.append(char)
                yield Token('string', ''.join(buffer))
                buffer.clear()
                in_string = False
            else:
                buffer.append(char)
        else:
            if char.isspace():
                if buffer:
                    yield Token('atom', ''.join(buffer))
                    buffer.clear()
                yield Token('whitespace', char)
            elif char in '()':
                if buffer:
                    yield Token('atom', ''.join(buffer))
                    buffer.clear()
                yield Token('paren', char)
            elif char == '"':
                if buffer:
                    yield Token('atom', ''.join(buffer))
                    buffer.clear()
                buffer.append(char)
                in_string = True
            elif char == "'":
                if buffer:
                    yield Token('atom', ''.join(buffer))
                    buffer.clear()
                yield Token('quote', char)
            elif char == ';':
                if buffer:
                    yield Token('atom', ''.join(buffer))
                    buffer.clear()
                comment_buffer = [char]
                i += 1
                while i < len(source) and source[i] != '\n':
                    comment_buffer.append(source[i])
                    i += 1
                if i < len(source):  # include the newline in the comment
                    comment_buffer.append(source[i])
                yield Token('comment', ''.join(comment_buffer))
            else:
                buffer.append(char)

        i += 1

    if buffer:
        if in_string:
            yield Token('string', ''.join(buffer))
        else:
            yield Token('atom', ''.join(buffer))


def untokenize(tokens: List[Token]) -> str:
    result = []
    indent_level = 0
    need_space = False

    for i, token in enumerate(tokens):
        if token.type == 'whitespace':
            if '\n' in token.value:
                result.append('\n' + '  ' * indent_level)
                need_space = False
            elif need_space:
                result.append(' ')
                need_space = False
        elif token.type == 'comment':
            result.append(token.value)
            need_space = False
        elif token.type == 'string':
            if need_space:
                result.append(' ')
            result.append(token.value)
            need_space = True
        elif token.type == 'paren':
            if token.value == '(':
                if need_space:
                    result.append(' ')
                result.append(token.value)
                indent_level += 1
                need_space = False
            elif token.value == ')':
                indent_level = max(0, indent_level - 1)
                result.append(token.value)
                need_space = True
        elif token.type == 'quote':
            if need_space:
                result.append(' ')
            result.append(token.value)
            need_space = False
        elif token.type == 'atom':
            if need_space:
                result.append(' ')
            result.append(token.value)
            need_space = True

        # Handle special cases for improved formatting
        if i < len(tokens) - 1:
            next_token = tokens[i+1]
            if token.type == 'paren' and token.value == '(' and next_token.type == 'paren' and next_token.value == ')':
                need_space = False
            elif token.type == 'quote' and next_token.type != 'whitespace':
                need_space = False

    return ''.join(result).strip()


def parse(tokens):
    buffer = []
    for token in tokens:
        if token == '(':
            buffer.append([])
        elif token == ')':
            if buffer:
                yield tuple(buffer.pop())
        else:
            buffer.append(token)


def main():
    EXAMPLES = pathlib.Path(__file__).parent.parent / 'examples'
    source = (EXAMPLES / 'basic.qy').read_text(encoding='utf-8')
    tokens = tokenize(source)
    tokens = list(tokens)
    print(tokens)
    print(''.join(untokenize(tokens)))
    print(parse(tokens))


if __name__ == '__main__':
    main()
