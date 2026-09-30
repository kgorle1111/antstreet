# Harvested: a Haiku worker's product (rerun1 run, firm arm, rep1); fails hidden checks: malformed_tokens.
class Node:
    pass


class NumberNode(Node):
    def __init__(self, value):
        self.value = value
        self.is_float = isinstance(value, float)


class BinaryOpNode(Node):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right


class UnaryOpNode(Node):
    def __init__(self, op, operand):
        self.op = op
        self.operand = operand


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def current_token(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def consume(self):
        token = self.current_token()
        if token is None:
            raise ValueError("Unexpected end of input")
        self.pos += 1
        return token

    def parse_expression(self):
        left = self.parse_term()

        while self.current_token() and self.current_token()[0] in ['+', '-']:
            op = self.current_token()[0]
            self.consume()
            right = self.parse_term()
            left = BinaryOpNode(left, op, right)

        return left

    def parse_term(self):
        left = self.parse_factor()

        while self.current_token() and self.current_token()[0] in ['*', '/']:
            op = self.current_token()[0]
            self.consume()
            right = self.parse_factor()
            left = BinaryOpNode(left, op, right)

        return left

    def parse_factor(self):
        unary_ops = []
        while self.current_token() and self.current_token()[0] in ['+', '-']:
            unary_ops.append(self.current_token()[0])
            self.consume()

        primary = self.parse_primary()

        for op in reversed(unary_ops):
            primary = UnaryOpNode(op, primary)

        return primary

    def parse_primary(self):
        token = self.current_token()

        if token is None:
            raise ValueError("Unexpected end of input")

        if token[0] == 'NUMBER':
            self.consume()
            return NumberNode(token[1])
        elif token[0] == '(':
            self.consume()
            expr = self.parse_expression()
            if self.current_token() is None or self.current_token()[0] != ')':
                raise ValueError("Unbalanced parentheses")
            self.consume()
            return expr
        else:
            raise ValueError(f"Unexpected token: {token[0]}")


def tokenize(expression):
    tokens = []
    i = 0

    while i < len(expression):
        if expression[i] in ' \t\n\r':
            i += 1
            continue

        if expression[i].isdigit():
            start = i
            while i < len(expression) and expression[i].isdigit():
                i += 1

            if i < len(expression) and expression[i] == '.':
                i += 1
                if i >= len(expression) or not expression[i].isdigit():
                    raise ValueError("Invalid literal")
                while i < len(expression) and expression[i].isdigit():
                    i += 1
                tokens.append(('NUMBER', float(expression[start:i])))
            else:
                tokens.append(('NUMBER', int(expression[start:i])))
            continue

        if expression[i] in '+-*/()':
            tokens.append((expression[i], expression[i]))
            i += 1
            continue

        raise ValueError(f"Invalid character: {expression[i]}")

    return tokens


def evaluate_node(root):
    stack = [(root, False)]
    results = {}

    while stack:
        node, processed = stack.pop()

        if isinstance(node, NumberNode):
            results[id(node)] = node.value
        elif isinstance(node, UnaryOpNode):
            if not processed:
                stack.append((node, True))
                stack.append((node.operand, False))
            else:
                operand = results[id(node.operand)]
                if node.op == '+':
                    results[id(node)] = operand
                else:
                    results[id(node)] = -operand
        elif isinstance(node, BinaryOpNode):
            if not processed:
                stack.append((node, True))
                stack.append((node.right, False))
                stack.append((node.left, False))
            else:
                left = results[id(node.left)]
                right = results[id(node.right)]
                if node.op == '+':
                    result = left + right
                elif node.op == '-':
                    result = left - right
                elif node.op == '*':
                    result = left * right
                elif node.op == '/':
                    if right == 0:
                        raise ZeroDivisionError("Division by zero")
                    result = left / right
                results[id(node)] = result

    return results[id(root)]


def has_decimal_or_division(node):
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, NumberNode):
            if current.is_float:
                return True
        elif isinstance(current, BinaryOpNode):
            if current.op == '/':
                return True
            stack.append(current.right)
            stack.append(current.left)
        elif isinstance(current, UnaryOpNode):
            stack.append(current.operand)
    return False


def evaluate(expression: str) -> int | float:
    if not isinstance(expression, str):
        raise ValueError("Argument must be a string")

    tokens = tokenize(expression)

    if not tokens:
        raise ValueError("Empty expression")

    parser = Parser(tokens)
    ast = parser.parse_expression()

    if parser.pos < len(tokens):
        raise ValueError("Unexpected token")

    is_float = has_decimal_or_division(ast)

    result = evaluate_node(ast)

    if is_float:
        return float(result)
    else:
        return int(result)
