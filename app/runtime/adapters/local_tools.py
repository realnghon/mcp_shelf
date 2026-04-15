"""Local Python tools available to all agents."""

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class EchoInput(BaseModel):
    message: str = Field(description="Message to echo back")


async def _echo(message: str) -> str:
    return f"Echo: {message}"


class CalculatorInput(BaseModel):
    expression: str = Field(description="Mathematical expression to evaluate")


async def _calculator(expression: str) -> str:
    """Safely evaluate a mathematical expression."""
    import ast
    import operator

    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            return ops[type(node.op)](_eval(node.left), _eval(node.right))
        elif isinstance(node, ast.UnaryOp):
            return ops[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported operation: {type(node)}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def get_local_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            coroutine=_echo,
            name="echo",
            description="Echo back the provided message. Useful for testing.",
            args_schema=EchoInput,
        ),
        StructuredTool.from_function(
            coroutine=_calculator,
            name="calculator",
            description="Evaluate a mathematical expression safely.",
            args_schema=CalculatorInput,
        ),
    ]
