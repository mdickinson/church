"""
Lambda expressions, complete with bindings from names to binding points.
"""
import itertools

import church.ast as ast
from church.ast import AstToken


class Parameter:
    def __init__(self, name):
        self.name = name


def lookup(bindings, name):
    for parameter_name, parameter in reversed(bindings):
        if parameter_name == name:
            return parameter
    raise ValueError("Failed lookup")


class Expr:
    def flatten(self):
        """
        Convert an Expr into a series of tokens.
        """
        to_do = [("PROCESS", self)]
        while to_do:
            action, arg = to_do.pop()
            if action == "PROCESS":
                to_do.extend(reversed(arg._pieces()))
            elif action == "YIELD":
                yield arg
            else:
                assert False, "shouldn't get here"

    def bitstring(self):
        """
        Convert an expr to its corresponding encoding as a bit string.
        """
        bindings = {}
        bits = []
        for piece, arg in self.flatten():
            if piece == "APPLY":
                bits.append("01")
            elif piece == "FUNCTION":
                bits.append("00")
                assert arg not in bindings
                bindings[arg] = len(bindings)
            elif piece == "CLOSE_FUNCTION":
                level = bindings.pop(arg)
                assert level == len(bindings)
            elif piece == "NAME":
                index = len(bindings) - 1 - bindings[arg]
                bits.append("1")
                bits.append("1" * index)
                bits.append("0")
        return ''.join(bits)

    def __eq__(self, other):
        return (
            type(self) == type(other)
            and self.bitstring() == other.bitstring()
        )


class ApplyExpr(Expr):
    def __init__(self, function, argument):
        if not isinstance(function, Expr):
            raise TypeError("function should be an instance of Expr")
        if not isinstance(argument, Expr):
            raise TypeError("argument should be an instance of Expr")
        self.function = function
        self.argument = argument

    def _pieces(self):
        return [
            ("YIELD", ("APPLY", None)),
            ("PROCESS", self.function),
            ("PROCESS", self.argument),
            ("YIELD", ("CLOSE_APPLY", None)),
        ]


class FunctionExpr(Expr):
    def __init__(self, parameter, body):
        if not isinstance(parameter, Parameter):
            raise TypeError("parameter should be an instance of Parameter")
        if not isinstance(body, Expr):
            raise TypeError(
                "body should be an instance of Expr, not {!r}".format(
                    type(body)))
        self.parameter = parameter
        self.body = body

    def __call__(self, argument):
        result_stack = []
        replacements = {self.parameter: argument}

        for piece, arg in self.body.flatten():
            if piece == "CLOSE_APPLY":
                argument = result_stack.pop()
                function = result_stack.pop()
                result_stack.append(ApplyExpr(function, argument))
            elif piece == "FUNCTION":
                new_parameter = Parameter(arg.name)
                assert arg not in replacements
                replacements[arg] = ParameterReference(new_parameter)
            elif piece == "CLOSE_FUNCTION":
                new_parameter = replacements.pop(arg).parameter
                body = result_stack.pop()
                result_stack.append(FunctionExpr(new_parameter, body))
            elif piece == "NAME":
                result_stack.append(replacements[arg])
        result = result_stack.pop()
        assert not result_stack
        return result

    def _pieces(self):
        return [
            ("YIELD", ("FUNCTION", self.parameter)),
            ("PROCESS", self.body),
            ("YIELD", ("CLOSE_FUNCTION", self.parameter)),
        ]


class ParameterReference(Expr):
    def __init__(self, parameter):
        if not isinstance(parameter, Parameter):
            raise TypeError("parameter should be an instance of Parameter")
        self.parameter = parameter

    def _pieces(self):
        return [
            ("YIELD", ("NAME", self.parameter)),
        ]


NAME = "name"
OPEN_FUNCTION = "open_function"
CLOSE_FUNCTION = "close_function"
OPEN_APPLY = "open_apply"
CLOSE_APPLY = "close_apply"

YIELD = "yield"
PROCESS = "process"


def bind(ast):
    """
    Match names to function parameters in the given Ast instance.
    """
    expr_stack = []
    bindings = []

    for action, arg in ast.flatten():
        if action == AstToken.NAME:
            parameter = lookup(bindings, arg)
            expr_stack.append(
                ParameterReference(parameter)
            )
        elif action == AstToken.OPEN_FUNCTION:
            parameter = Parameter(arg)
            bindings.append((arg, parameter))
        elif action == AstToken.CLOSE_FUNCTION:
            name, parameter = bindings.pop()
            expr_stack.append(FunctionExpr(parameter, expr_stack.pop()))
        elif action == AstToken.OPEN_APPLY:
            pass
        elif action == AstToken.CLOSE_APPLY:
            arg = expr_stack.pop()
            fn = expr_stack.pop()
            expr_stack.append(ApplyExpr(fn, arg))
        else:
            assert False, "never get here"

    result = expr_stack.pop()
    assert len(expr_stack) == 0
    return result


DIGITS = "0123456789"


def variants(base_name):
    for suffix_length in itertools.count():
        for suffix in itertools.product(DIGITS, repeat=suffix_length):
            yield base_name + ''.join(suffix)


def name_avoiding(names_to_avoid, base_name):
    for variant in variants(base_name):
        if variant not in names_to_avoid:
            return variant


def unbind(expr):
    """
    Turn an Expr back into an AST expression, renaming names
    as we go to avoid potential clashes.
    """
    # Store for partially processed results.
    result_stack = []
    # Mapping from parameters to names to use in the AST.
    replacements = {}
    # Parameter names currently in scope; these must be avoided
    # when choosing a new name.
    names_in_scope = set()

    for piece, arg in expr.flatten():
        if piece == "CLOSE_APPLY":
            argument = result_stack.pop()
            function = result_stack.pop()
            result_stack.append(ast.Apply(function, argument))
        elif piece == "FUNCTION":
            name = name_avoiding(names_in_scope, arg.name)
            assert name not in names_in_scope
            assert arg not in replacements
            names_in_scope.add(name)
            replacements[arg] = name
            result_stack.append(name)
        elif piece == "CLOSE_FUNCTION":
            body = result_stack.pop()
            name = result_stack.pop()
            result_stack.append(ast.Function(name, body))
            replacements.pop(arg)
            names_in_scope.remove(name)
        elif piece == "NAME":
            result_stack.append(ast.Name(replacements[arg]))

    result = result_stack.pop()
    assert not result_stack
    assert not replacements
    assert not names_in_scope
    return result
