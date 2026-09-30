# Harvested: a Haiku worker's product (pilot run, single arm, rep1); fails hidden checks: malformed_tokens.
def evaluate(expression: str) -> int | float:
    if not isinstance(expression, str):
        raise ValueError()

    if not expression or all(c in ' \t\n\r' for c in expression):
        raise ValueError()

    tokens = tokenize(expression)
    parser = Parser(tokens)
    ast, has_float, has_division = parser.parse()

    result = eval_ast(ast)

    if has_float or has_division:
        return float(result)
    else:
        return int(result)


def tokenize(expression: str):
    tokens = []
    i = 0

    while i < len(expression):
        if expression[i] in ' \t\n\r':
            i += 1
            continue

        if expression[i].isdigit():
            j = i
            has_dot = False
            while j < len(expression) and (expression[j].isdigit() or expression[j] == '.'):
                if expression[j] == '.':
                    if has_dot:
                        raise ValueError()
                    has_dot = True
                    if j + 1 >= len(expression) or not expression[j + 1].isdigit():
                        raise ValueError()
                j += 1

            num_str = expression[i:j]
            tokens.append(Token('NUMBER', num_str))
            i = j
            continue

        if expression[i] in '+-*/()':
            tokens.append(Token(expression[i], expression[i]))
            i += 1
            continue

        raise ValueError()

    return tokens


class Token:
    def __init__(self, type, value):
        self.type = type
        self.value = value


class Number:
    def __init__(self, value):
        self.value = value


class BinOp:
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right


class UnaryOp:
    def __init__(self, op, operand):
        self.op = op
        self.operand = operand


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.has_float = False
        self.has_division = False

    def parse(self):
        if not self.tokens:
            raise ValueError()

        ast = self.parse_expression()

        if self.pos < len(self.tokens):
            raise ValueError()

        return ast, self.has_float, self.has_division

    def parse_expression(self):
        left = self.parse_term()

        while self.pos < len(self.tokens) and self.peek().type in '+-':
            op = self.peek().type
            self.advance()
            right = self.parse_term()
            left = BinOp(left, op, right)

        return left

    def parse_term(self):
        left = self.parse_factor()

        while self.pos < len(self.tokens) and self.peek().type in '*/':
            op = self.peek().type
            if op == '/':
                self.has_division = True
            self.advance()
            right = self.parse_factor()
            left = BinOp(left, op, right)

        return left

    def parse_factor(self):
        return self.parse_unary()

    def parse_unary(self):
        if self.pos < len(self.tokens) and self.peek().type in '+-':
            op = self.peek().type
            self.advance()
            operand = self.parse_unary()
            return UnaryOp(op, operand)

        return self.parse_primary()

    def parse_primary(self):
        if self.pos >= len(self.tokens):
            raise ValueError()

        token = self.peek()

        if token.type == 'NUMBER':
            self.advance()
            num_str = token.value
            if '.' in num_str:
                self.has_float = True
                value = float(num_str)
            else:
                value = int(num_str)
            return Number(value)

        elif token.type == '(':
            self.advance()
            result = self.parse_expression()
            if self.pos >= len(self.tokens) or self.peek().type != ')':
                raise ValueError()
            self.advance()
            return result

        else:
            raise ValueError()

    def peek(self):
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def advance(self):
        self.pos += 1


def eval_ast(ast):
    postorder = collect_postorder(ast)

    stack = []
    for node in postorder:
        if isinstance(node, Number):
            stack.append(node.value)
        elif isinstance(node, BinOp):
            right = stack.pop()
            left = stack.pop()
            if node.op == '+':
                stack.append(left + right)
            elif node.op == '-':
                stack.append(left - right)
            elif node.op == '*':
                stack.append(left * right)
            elif node.op == '/':
                if right == 0:
                    raise ZeroDivisionError()
                stack.append(left / right)
        elif isinstance(node, UnaryOp):
            operand = stack.pop()
            if node.op == '-':
                stack.append(-operand)
            else:
                stack.append(operand)

    return stack[0]


def collect_postorder(node):
    result = []
    stack = [(node, False)]

    while stack:
        node, visited = stack.pop()
        if visited:
            result.append(node)
        else:
            stack.append((node, True))
            if isinstance(node, BinOp):
                stack.append((node.right, False))
                stack.append((node.left, False))
            elif isinstance(node, UnaryOp):
                stack.append((node.operand, False))

    return result
