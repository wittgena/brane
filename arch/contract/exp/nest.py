# arch.contract.exp.nest
## @lineage: arch.code.exp.nest
## @lineage: nexus.exp.nest
## @lineage: arch.code.frag.nest
import ast
import sys
from functools import reduce

class NestedAttr:
    """AST를 활용하여 중첩된 객체, 딕셔너리, 리스트의 속성을 문자열 경로로 동적 접근(Get/Set/Delete)하는 유틸리티"""
    _AST_TYPES = (ast.Name, ast.Attribute, ast.Subscript, ast.Call)
    _STRING_TYPE = str

    @staticmethod
    def get(obj, attr, **kwargs):
        for chunk in NestedAttr._parse(attr):
            try:
                obj = NestedAttr._lookup(obj, chunk)
            except Exception as ex:
                if "default" in kwargs:
                    return kwargs["default"]
                else:
                    raise ex
        return obj

    @staticmethod
    def set(obj, attr, val):
        obj, attr_or_key, is_subscript = NestedAttr.lookup(obj, attr)
        if is_subscript:
            obj[attr_or_key] = val
        else:
            setattr(obj, attr_or_key, val)

    @staticmethod
    def delete(obj, attr):
        obj, attr_or_key, is_subscript = NestedAttr.lookup(obj, attr)
        if is_subscript:
            del obj[attr_or_key]
        else:
            delattr(obj, attr_or_key)

    @staticmethod
    def lookup(obj, attr):
        nodes = tuple(NestedAttr._parse(attr))
        if len(nodes) > 1:
            obj = reduce(NestedAttr._lookup, nodes[:-1], obj)
            node = nodes[-1]
        else:
            node = nodes[0]
            
        if isinstance(node, ast.Attribute):
            return obj, node.attr, False
        elif isinstance(node, ast.Subscript):
            return obj, NestedAttr._lookup_subscript_value(node.slice), True
        elif isinstance(node, ast.Name):
            return obj, node.id, False
        raise NotImplementedError(f"Node is not supported: {node}")

    @staticmethod
    def _parse(attr):
        if not isinstance(attr, NestedAttr._STRING_TYPE):
            raise TypeError("Attribute name must be a string")
        nodes = ast.parse(attr).body
        if not nodes or not isinstance(nodes[0], ast.Expr):
            raise ValueError(f"Invalid expression: {attr}")
        return reversed([n for n in ast.walk(nodes[0]) if isinstance(n, NestedAttr._AST_TYPES)])

    @staticmethod
    def _lookup_subscript_value(node):
        if isinstance(node, ast.Index):
            node = node.value

        if isinstance(node, ast.Constant):
            return node.value

        if sys.version_info < (3, 14):
            if hasattr(ast, "Num") and isinstance(node, ast.Num):
                return node.n
            elif hasattr(ast, "Str") and isinstance(node, ast.Str):
                return node.s

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            operand = node.operand
            if isinstance(operand, ast.Constant):
                return -operand.value
            elif sys.version_info < (3, 14) and hasattr(ast, "Num") and isinstance(operand, ast.Num):
                return -operand.n

        raise NotImplementedError(f"Subscript node is not supported: {ast.dump(node)}")

    @staticmethod
    def _lookup(obj, node):
        if isinstance(node, ast.Attribute):
            return getattr(obj, node.attr)
        elif isinstance(node, ast.Subscript):
            return obj[NestedAttr._lookup_subscript_value(node.slice)]
        elif isinstance(node, ast.Name):
            return getattr(obj, node.id)
        elif isinstance(node, ast.Call):
            raise ValueError("Function calls are not allowed.")
        raise NotImplementedError(f"Node is not supported: {node}")