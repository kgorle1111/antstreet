# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: division_by_zero, malformed_tokens, result_types, tokens, unary.
def evaluate(expression: str) -> int | float:
    if not isinstance(expression, str):
        raise ValueError("Input must be a string")

    tokens = tokenize(expression)
    tokens = mark_unary_operators(tokens)
    validate_syntax(tokens)
    postfix = infix_to_postfix(tokens)
    result = evaluate_postfix(postfix)

    return result


def tokenize(expression: str):
    tokens = []
    i = 0

    while i < len(expression):
        while i < len(expression) and expression[i] in ' \t\n\r':
            i += 1
        if i >= len(expression):
            break

        ch = expression[i]

        if ch in '()+-*/':
            tokens.append(ch)
            i += 1
        elif ch.isdigit():
            j = i
            while j < len(expression) and expression[j].isdigit():
                j += 1

            if j < len(expression) and expression[j] == '.':
                j += 1
                if j >= len(expression) or not expression[j].isdigit():
                    raise ValueError("Invalid number")
                while j < len(expression) and expression[j].isdigit():
                    j += 1

            tokens.append(expression[i:j])
            i = j
        elif ch == '.':
            raise ValueError("Invalid number")
        else:
            raise ValueError(f"Invalid character: {ch}")

    return tokens


def mark_unary_operators(tokens):
    if not tokens:
        raise ValueError("Empty expression")

    marked = []
    for i, token in enumerate(tokens):
        if token in '+-':
            if i == 0 or tokens[i-1] in '(+-*/':
                marked.append(('UNARY', token))
            else:
                marked.append(token)
        else:
            marked.append(token)

    return marked


def validate_syntax(tokens):
    if not tokens:
        raise ValueError("Empty expression")

    paren_depth = 0
    expect_operand_or_unary = True

    for token in tokens:
        if isinstance(token, tuple) and token[0] == 'UNARY':
            if not expect_operand_or_unary:
                raise ValueError("Unexpected unary operator")
        elif token == '(':
            if not expect_operand_or_unary:
                raise ValueError("Unexpected '('")
            paren_depth += 1
            expect_operand_or_unary = True
        elif token == ')':
            if expect_operand_or_unary:
                raise ValueError("Expected operand before ')'")
            paren_depth -= 1
            if paren_depth < 0:
                raise ValueError("Unbalanced parentheses")
            expect_operand_or_unary = False
        elif token in '+-*/':
            if expect_operand_or_unary:
                raise ValueError("Expected operand before binary operator")
            expect_operand_or_unary = True
        else:
            if not expect_operand_or_unary:
                raise ValueError("Two operands in a row")
            expect_operand_or_unary = False

    if paren_depth != 0:
        raise ValueError("Unbalanced parentheses")

    if expect_operand_or_unary:
        raise ValueError("Expected operand at end")


def infix_to_postfix(tokens):
    output = []
    operator_stack = []

    precedence = {'+': 1, '-': 1, '*': 2, '/': 2}

    for token in tokens:
        if isinstance(token, tuple) and token[0] == 'UNARY':
            operator_stack.append(token)
        elif token not in '()+-*/':
            output.append(token)
        elif token == '(':
            operator_stack.append(token)
        elif token == ')':
            while operator_stack and operator_stack[-1] != '(':
                output.append(operator_stack.pop())
            if not operator_stack:
                raise ValueError("Unbalanced parentheses")
            operator_stack.pop()
        elif token in '+-*/':
            prec = precedence[token]
            while (operator_stack and
                   operator_stack[-1] != '(' and
                   isinstance(operator_stack[-1], str) and
                   operator_stack[-1] in precedence and
                   precedence[operator_stack[-1]] >= prec):
                output.append(operator_stack.pop())
            operator_stack.append(token)

    while operator_stack:
        if operator_stack[-1] in '()':
            raise ValueError("Unbalanced parentheses")
        output.append(operator_stack.pop())

    return output


def evaluate_postfix(postfix):
    stack = []
    has_float = False

    for token in postfix:
        if isinstance(token, tuple) and token[0] == 'UNARY':
            if not stack:
                raise ValueError("Invalid unary operator")
            val = stack.pop()
            op = token[1]
            if op == '-':
                stack.append(-val)
            else:
                stack.append(val)
        elif token not in '+-*/':
            if '.' in token:
                val = float(token)
                has_float = True
            else:
                val = int(token)
            stack.append(val)
        elif token == '/':
            if len(stack) < 2:
                raise ValueError("Invalid expression")
            b = stack.pop()
            a = stack.pop()
            if b == 0:
                raise ZeroDivisionError("division by zero")
            stack.append(a / b)
            has_float = True
        elif token in '+-*':
            if len(stack) < 2:
                raise ValueError("Invalid expression")
            b = stack.pop()
            a = stack.pop()
            if token == '+':
                stack.append(a + b)
            elif token == '-':
                stack.append(a - b)
            elif token == '*':
                stack.append(a * b)

    if len(stack) != 1:
        raise ValueError("Invalid expression")

    result = stack[0]

    if has_float:
        return float(result)
    else:
        return int(result)
