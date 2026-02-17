#!/usr/bin/env python3
"""
Unity C# to Visual Scripting Converter
======================================
Converts Unity C# Scripts (.cs) to Unity Visual Scripting/Bolt Graphs (.asset)

Based on research of Unity Visual Scripting serialization format:
- Uses JSON-based graph serialization
- Supports Flow Graphs (Script Graphs) with nodes (units) and connections
- Compatible with Unity 2021.1+ (built-in Visual Scripting) and Bolt (Asset Store)

Author: AI Assistant
Date: 2026-02-18
"""

import re
import json
import uuid
import os
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
from pathlib import Path


class NodeType(Enum):
    """Types of Visual Scripting nodes"""
    EVENT = "event"
    FLOW = "flow"
    DATA = "data"
    INVOKE = "invoke"
    GET_MEMBER = "get_member"
    SET_MEMBER = "set_member"
    VARIABLE = "variable"
    OPERATOR = "operator"


class PortType(Enum):
    """Port types for connections"""
    CONTROL_INPUT = "control_input"
    CONTROL_OUTPUT = "control_output"
    VALUE_INPUT = "value_input"
    VALUE_OUTPUT = "value_output"


@dataclass
class Port:
    """Represents a node port"""
    name: str
    port_type: PortType
    data_type: Optional[str] = None
    default_value: Any = None


@dataclass
class Node:
    """Represents a Visual Scripting node (unit)"""
    guid: str
    node_type: str
    position: Tuple[float, float]
    category: NodeType
    ports: List[Port] = field(default_factory=list)
    default_values: Dict[str, Any] = field(default_factory=dict)
    member_info: Optional[Dict] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict:
        result = {
            "guid": self.guid,
            "$type": self.node_type,
            "$version": "A",
            "$id": str(abs(hash(self.guid)) % 10000),
            "position": {
                "x": self.position[0],
                "y": self.position[1]
            },
            "defaultValues": self.default_values
        }

        if self.description:
            result["summary"] = self.description

        if self.member_info:
            result["member"] = self.member_info
            result["chainable"] = False
            result["parameterNames"] = self.member_info.get("parameterNames", [])

        if self.node_type == "Unity.VisualScripting.Literal":
            if "type" in self.default_values:
                result["type"] = self.default_values["type"]
                result["value"] = self.default_values.get("value", {"$content": None, "$type": "System.Object"})

        return result


@dataclass
class Connection:
    """Represents a connection between nodes"""
    guid: str
    source_unit_id: str
    source_key: str
    destination_unit_id: str
    destination_key: str
    connection_type: str

    def to_dict(self) -> Dict:
        return {
            "guid": self.guid,
            "$type": self.connection_type,
            "sourceUnit": {"$ref": self.source_unit_id},
            "sourceKey": self.source_key,
            "destinationUnit": {"$ref": self.destination_unit_id},
            "destinationKey": self.destination_key
        }


@dataclass
class Variable:
    """Represents a graph variable"""
    name: str
    variable_type: str
    default_value: Any = None
    is_exposed: bool = False


class CSharpParser:
    """Parses C# code and extracts relevant constructs"""

    def __init__(self, code: str):
        self.code = code
        self.usings = []
        self.namespace = None
        self.class_name = None
        self.base_class = None
        self.fields = []
        self.properties = []
        self.methods = []
        self._parse()

    def _parse(self):
        self.usings = re.findall(r'using\s+([^;]+);', self.code)

        ns_match = re.search(r'namespace\s+([^{\s]+)', self.code)
        if ns_match:
            self.namespace = ns_match.group(1)

        class_pattern = r'class\s+(\w+)\s*(?::\s*(\w+))?'
        class_match = re.search(class_pattern, self.code)
        if class_match:
            self.class_name = class_match.group(1)
            self.base_class = class_match.group(2)

        self._extract_fields()
        self._extract_methods()

    def _extract_fields(self):
        field_pattern = r'(?:\[(?:[^\]]+)\])?\s*(public|private|protected|internal)?\s*(static)?\s*(readonly)?\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*(?:=\s*([^;]+))?;'

        for match in re.finditer(field_pattern, self.code):
            access = match.group(1) or "private"
            is_static = match.group(2) is not None
            is_readonly = match.group(3) is not None
            field_type = match.group(4)
            field_name = match.group(5)
            default_value = match.group(6)

            self.fields.append({
                "access": access,
                "static": is_static,
                "readonly": is_readonly,
                "type": field_type,
                "name": field_name,
                "default": default_value
            })

    def _extract_methods(self):
        method_pattern = r'(?:\[(?:[^\]]+)\])?\s*(public|private|protected|internal)?\s*(static)?\s*(virtual|override|abstract)?\s*(async)?\s*(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)\s*\{'

        for match in re.finditer(method_pattern, self.code):
            access = match.group(1) or "private"
            is_static = match.group(2) is not None
            modifier = match.group(3)
            is_async = match.group(4) is not None
            return_type = match.group(5)
            method_name = match.group(6)
            parameters_str = match.group(7)

            parameters = []
            if parameters_str.strip():
                param_parts = [p.strip() for p in parameters_str.split(',')]
                for part in param_parts:
                    if ' ' in part:
                        parts = part.rsplit(' ', 1)
                        param_type = parts[0]
                        param_name = parts[1]
                        parameters.append({"type": param_type, "name": param_name})

            start_pos = match.end() - 1
            body = self._extract_body(start_pos)
            
            # Check if it's a coroutine
            is_coroutine = "IEnumerator" in return_type

            # Extract comments from method
            comments = self._extract_method_comments(match.start())

            self.methods.append({
                "access": access,
                "static": is_static,
                "modifier": modifier,
                "async": is_async,
                "return_type": return_type,
                "name": method_name,
                "parameters": parameters,
                "body": body,
                "is_coroutine": is_coroutine,
                "comments": comments
            })

    def _extract_method_comments(self, method_pos: int) -> str:
        """Extract comments before a method"""
        # Look backwards for comments
        lines_before = self.code[:method_pos].split('\n')
        comments = []
        for line in reversed(lines_before[-5:]):  # Check last 5 lines
            line = line.strip()
            if line.startswith('//'):
                comments.insert(0, line[2:].strip())
            elif line.startswith('/*') or line.startswith('*'):
                comments.insert(0, line.lstrip('/*').rstrip('*/').strip())
            elif line and not line.startswith('['):  # Stop at non-comment, non-attribute
                break
        return ' '.join(comments) if comments else ""

    def _extract_body(self, start_pos: int) -> str:
        depth = 0
        end_pos = start_pos
        for i, char in enumerate(self.code[start_pos:]):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end_pos = start_pos + i + 1
                    break
        return self.code[start_pos:end_pos]


class VisualScriptingGenerator:
    """Generates Visual Scripting graph from parsed C# code"""

    UNITY_EVENTS = {
        "Start": "Unity.VisualScripting.Start",
        "Update": "Unity.VisualScripting.Update",
        "Awake": "Unity.VisualScripting.Awake",
        "OnEnable": "Unity.VisualScripting.OnEnable",
        "OnDisable": "Unity.VisualScripting.OnDisable",
        "OnDestroy": "Unity.VisualScripting.OnDestroy",
        "FixedUpdate": "Unity.VisualScripting.FixedUpdate",
        "LateUpdate": "Unity.VisualScripting.LateUpdate",
        "OnTriggerEnter": "Unity.VisualScripting.OnTriggerEnter",
        "OnTriggerExit": "Unity.VisualScripting.OnTriggerExit",
        "OnTriggerStay": "Unity.VisualScripting.OnTriggerStay",
        "OnCollisionEnter": "Unity.VisualScripting.OnCollisionEnter",
        "OnCollisionExit": "Unity.VisualScripting.OnCollisionExit",
        "OnCollisionStay": "Unity.VisualScripting.OnCollisionStay",
    }

    TYPE_MAPPINGS = {
        "int": "System.Int32",
        "float": "System.Single",
        "double": "System.Double",
        "bool": "System.Boolean",
        "string": "System.String",
        "Vector2": "UnityEngine.Vector2",
        "Vector3": "UnityEngine.Vector3",
        "Quaternion": "UnityEngine.Quaternion",
        "GameObject": "UnityEngine.GameObject",
        "Transform": "UnityEngine.Transform",
    }

    def __init__(self, parser: CSharpParser):
        self.parser = parser
        self.nodes: List[Node] = []
        self.connections: List[Connection] = []
        self.variables: List[Variable] = []
        self._position_x = 0
        self._position_y = 0

    def _new_guid(self) -> str:
        return str(uuid.uuid4())

    def _next_position(self) -> Tuple[float, float]:
        x = self._position_x
        y = self._position_y
        self._position_x += 250
        if self._position_x > 1000:
            self._position_x = 0
            self._position_y += 150
        return (x, y)

    def _create_event_node(self, event_name: str) -> Node:
        event_type = self.UNITY_EVENTS.get(event_name, "Unity.VisualScripting.Start")
        return Node(
            guid=self._new_guid(),
            node_type=event_type,
            position=self._next_position(),
            category=NodeType.EVENT,
            ports=[Port("trigger", PortType.CONTROL_OUTPUT)]
        )

    def _create_invoke_node(self, method_name: str, target_type: str, 
                            parameters: List[Dict], return_type: Optional[str] = None) -> Node:
        param_types = [p["type"] for p in parameters]
        param_names = [p["name"] for p in parameters]

        member_info = {
            "name": method_name,
            "parameterTypes": param_types,
            "targetType": target_type,
            "targetTypeName": target_type,
            "$version": "A"
        }

        ports = [
            Port("enter", PortType.CONTROL_INPUT),
            Port("exit", PortType.CONTROL_OUTPUT)
        ]

        for i, param in enumerate(parameters):
            ports.append(Port(str(i), PortType.VALUE_INPUT, param["type"]))

        if return_type and return_type != "void":
            ports.append(Port("result", PortType.VALUE_OUTPUT, return_type))

        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.InvokeMember",
            position=self._next_position(),
            category=NodeType.INVOKE,
            ports=ports,
            member_info=member_info
        )

    def _create_literal_node(self, value: Any, value_type: str) -> Node:
        mapped_type = self.TYPE_MAPPINGS.get(value_type, value_type)

        default_values = {
            "type": mapped_type,
            "value": {
                "$content": value,
                "$type": mapped_type
            }
        }

        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.Literal",
            position=self._next_position(),
            category=NodeType.DATA,
            ports=[Port("output", PortType.VALUE_OUTPUT, mapped_type)],
            default_values=default_values
        )

    def _create_if_node(self) -> Node:
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.If",
            position=self._next_position(),
            category=NodeType.FLOW,
            ports=[
                Port("enter", PortType.CONTROL_INPUT),
                Port("condition", PortType.VALUE_INPUT, "System.Boolean"),
                Port("true", PortType.CONTROL_OUTPUT),
                Port("false", PortType.CONTROL_OUTPUT)
            ]
        )

    def _create_for_node(self) -> Node:
        """Create a For loop node"""
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.For",
            position=self._next_position(),
            category=NodeType.FLOW,
            ports=[
                Port("enter", PortType.CONTROL_INPUT),
                Port("firstIndex", PortType.VALUE_INPUT, "System.Int32"),
                Port("lastIndex", PortType.VALUE_INPUT, "System.Int32"),
                Port("step", PortType.VALUE_INPUT, "System.Int32"),
                Port("body", PortType.CONTROL_OUTPUT),
                Port("exit", PortType.CONTROL_OUTPUT),
                Port("currentIndex", PortType.VALUE_OUTPUT, "System.Int32")
            ]
        )

    def _create_while_node(self) -> Node:
        """Create a While loop node"""
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.While",
            position=self._next_position(),
            category=NodeType.FLOW,
            ports=[
                Port("enter", PortType.CONTROL_INPUT),
                Port("condition", PortType.VALUE_INPUT, "System.Boolean"),
                Port("body", PortType.CONTROL_OUTPUT),
                Port("exit", PortType.CONTROL_OUTPUT)
            ]
        )

    def _create_foreach_node(self, collection_type: str = "System.Collections.IEnumerable") -> Node:
        """Create a ForEach loop node"""
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.ForEach",
            position=self._next_position(),
            category=NodeType.FLOW,
            ports=[
                Port("enter", PortType.CONTROL_INPUT),
                Port("collection", PortType.VALUE_INPUT, collection_type),
                Port("body", PortType.CONTROL_OUTPUT),
                Port("exit", PortType.CONTROL_OUTPUT),
                Port("currentItem", PortType.VALUE_OUTPUT, "System.Object")
            ]
        )

    def _create_switch_node(self, num_cases: int = 2) -> Node:
        """Create a Switch node"""
        ports = [
            Port("enter", PortType.CONTROL_INPUT),
            Port("selector", PortType.VALUE_INPUT, "System.Int32")
        ]
        
        for i in range(num_cases):
            ports.append(Port(str(i), PortType.CONTROL_OUTPUT))
        
        ports.append(Port("default", PortType.CONTROL_OUTPUT))
        
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.SwitchOnInteger",
            position=self._next_position(),
            category=NodeType.FLOW,
            ports=ports
        )

    def _create_arithmetic_node(self, operation: str) -> Node:
        """Create an arithmetic operation node"""
        operation_map = {
            "+": ("Unity.VisualScripting.GenericAdd", "Add"),
            "-": ("Unity.VisualScripting.GenericSubtract", "Subtract"),
            "*": ("Unity.VisualScripting.GenericMultiply", "Multiply"),
            "/": ("Unity.VisualScripting.GenericDivide", "Divide"),
            "%": ("Unity.VisualScripting.GenericModulo", "Modulo")
        }
        
        node_type, op_name = operation_map.get(operation, ("Unity.VisualScripting.GenericAdd", "Add"))
        
        return Node(
            guid=self._new_guid(),
            node_type=node_type,
            position=self._next_position(),
            category=NodeType.OPERATOR,
            ports=[
                Port("a", PortType.VALUE_INPUT, "System.Object"),
                Port("b", PortType.VALUE_INPUT, "System.Object"),
                Port("result", PortType.VALUE_OUTPUT, "System.Object")
            ]
        )

    def _create_comparison_node(self, operation: str) -> Node:
        """Create a comparison operation node"""
        operation_map = {
            "==": "Unity.VisualScripting.GenericEqual",
            "!=": "Unity.VisualScripting.GenericNotEqual",
            "<": "Unity.VisualScripting.GenericLess",
            ">": "Unity.VisualScripting.GenericGreater",
            "<=": "Unity.VisualScripting.GenericLessOrEqual",
            ">=": "Unity.VisualScripting.GenericGreaterOrEqual"
        }
        
        node_type = operation_map.get(operation, "Unity.VisualScripting.GenericEqual")
        
        return Node(
            guid=self._new_guid(),
            node_type=node_type,
            position=self._next_position(),
            category=NodeType.OPERATOR,
            ports=[
                Port("a", PortType.VALUE_INPUT, "System.Object"),
                Port("b", PortType.VALUE_INPUT, "System.Object"),
                Port("result", PortType.VALUE_OUTPUT, "System.Boolean")
            ]
        )

    def _create_yield_return_node(self) -> Node:
        """Create a yield return node for coroutines"""
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.YieldReturn",
            position=self._next_position(),
            category=NodeType.FLOW,
            ports=[
                Port("enter", PortType.CONTROL_INPUT),
                Port("exit", PortType.CONTROL_OUTPUT),
                Port("instruction", PortType.VALUE_INPUT, "UnityEngine.YieldInstruction")
            ]
        )

    def _create_wait_for_seconds_node(self, seconds: float = 1.0) -> Node:
        """Create a WaitForSeconds node"""
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.WaitForSeconds",
            position=self._next_position(),
            category=NodeType.DATA,
            ports=[
                Port("seconds", PortType.VALUE_INPUT, "System.Single"),
                Port("result", PortType.VALUE_OUTPUT, "UnityEngine.WaitForSeconds")
            ],
            default_values={"seconds": seconds}
        )

    def _create_custom_invoke_node(self, method_name: str, target_type: str,
                                   parameters: List[Dict], return_type: Optional[str] = None,
                                   is_static: bool = False) -> Node:
        """Create a node for custom method invocation"""
        param_types = [self.TYPE_MAPPINGS.get(p["type"], p["type"]) for p in parameters]
        param_names = [p["name"] for p in parameters]

        member_info = {
            "name": method_name,
            "parameterTypes": param_types,
            "targetType": target_type,
            "targetTypeName": target_type,
            "parameterNames": param_names,
            "$version": "A"
        }

        ports = [
            Port("enter", PortType.CONTROL_INPUT),
            Port("exit", PortType.CONTROL_OUTPUT)
        ]

        if not is_static:
            ports.append(Port("target", PortType.VALUE_INPUT, target_type))

        for i, param in enumerate(parameters):
            mapped_type = self.TYPE_MAPPINGS.get(param["type"], param["type"])
            ports.append(Port(f"%{param['name']}", PortType.VALUE_INPUT, mapped_type))

        if return_type and return_type != "void":
            mapped_return = self.TYPE_MAPPINGS.get(return_type, return_type)
            ports.append(Port("result", PortType.VALUE_OUTPUT, mapped_return))

        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.InvokeMember",
            position=self._next_position(),
            category=NodeType.INVOKE,
            ports=ports,
            member_info=member_info
        )

    def _create_set_variable_node(self, var_name: str, var_type: str) -> Node:
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.SetVariable",
            position=self._next_position(),
            category=NodeType.VARIABLE,
            ports=[
                Port("enter", PortType.CONTROL_INPUT),
                Port("exit", PortType.CONTROL_OUTPUT),
                Port("input", PortType.VALUE_INPUT, var_type)
            ],
            default_values={"name": var_name}
        )

    def _create_get_variable_node(self, var_name: str, var_type: str) -> Node:
        return Node(
            guid=self._new_guid(),
            node_type="Unity.VisualScripting.GetVariable",
            position=self._next_position(),
            category=NodeType.VARIABLE,
            ports=[Port("output", PortType.VALUE_OUTPUT, var_type)],
            default_values={"name": var_name}
        )

    def _create_connection(self, source_node: Node, source_key: str,
                          dest_node: Node, dest_key: str, 
                          is_control: bool = True) -> Connection:
        conn_type = "Unity.VisualScripting.ControlConnection" if is_control else "Unity.VisualScripting.ValueConnection"

        return Connection(
            guid=self._new_guid(),
            source_unit_id=source_node.to_dict()["$id"],
            source_key=source_key,
            destination_unit_id=dest_node.to_dict()["$id"],
            destination_key=dest_key,
            connection_type=conn_type
        )

    def generate_graph(self) -> Dict:
        elements = []

        for method in self.parser.methods:
            method_nodes, method_connections = self._process_method(method)
            self.nodes.extend(method_nodes)
            self.connections.extend(method_connections)

        for node in self.nodes:
            elements.append(node.to_dict())

        for conn in self.connections:
            elements.append(conn.to_dict())

        graph = {
            "nest": {
                "source": "Embed",
                "macro": None,
                "embed": {
                    "variables": {
                        "Kind": "Flow",
                        "collection": {
                            "$content": [],
                            "$version": "A"
                        },
                        "$version": "A"
                    },
                    "controlInputDefinitions": [],
                    "controlOutputDefinitions": [],
                    "valueInputDefinitions": [],
                    "valueOutputDefinitions": [],
                    "title": self.parser.class_name or "ConvertedGraph",
                    "summary": f"Converted from {self.parser.class_name}.cs" if self.parser.class_name else "Converted Graph",
                    "pan": {"x": 0.0, "y": 0.0},
                    "zoom": 1.0,
                    "elements": elements,
                    "$version": "A"
                }
            }
        }

        return graph

    def _process_method(self, method: Dict) -> Tuple[List[Node], List[Connection]]:
        nodes = []
        connections = []
        last_node = None

        event_node = None
        if method["name"] in self.UNITY_EVENTS:
            event_node = self._create_event_node(method["name"])
            nodes.append(event_node)
            last_node = event_node

        body = method["body"]

        # Process for loops
        for_pattern = r'for\s*\(\s*(?:int|var)\s+(\w+)\s*=\s*([^;]+);\s*\1\s*([<>]=?)\s*([^;]+);\s*\1\s*(\+\+|--|\+=\s*\d+|-=\s*\d+)\s*\)'
        for match in re.finditer(for_pattern, body):
            var_name = match.group(1)
            start_val = match.group(2).strip()
            operator = match.group(3)
            end_val = match.group(4).strip()
            increment = match.group(5).strip()
            
            for_node = self._create_for_node()
            nodes.append(for_node)
            
            # Create literal nodes for start and end values
            start_literal = self._create_literal_node(int(start_val) if start_val.isdigit() else 0, "int")
            nodes.append(start_literal)
            
            end_literal = self._create_literal_node(int(end_val) if end_val.isdigit() else 10, "int")
            nodes.append(end_literal)
            
            # Connect event to for loop
            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    for_node, "enter"
                )
                connections.append(conn)
                
            # Connect literals to for loop
            conn = self._create_connection(start_literal, "output", for_node, "%firstIndex", is_control=False)
            connections.append(conn)
            conn = self._create_connection(end_literal, "output", for_node, "%lastIndex", is_control=False)
            connections.append(conn)
            
            last_node = for_node

        # Process while loops
        while_pattern = r'while\s*\(([^)]+)\)'
        for match in re.finditer(while_pattern, body):
            condition = match.group(1).strip()
            
            while_node = self._create_while_node()
            nodes.append(while_node)
            
            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    while_node, "enter"
                )
                connections.append(conn)
            
            last_node = while_node

        # Process foreach loops
        foreach_pattern = r'foreach\s*\(\s*(?:var|(\w+))\s+(\w+)\s+in\s+([^)]+)\)'
        for match in re.finditer(foreach_pattern, body):
            item_type = match.group(1) or "var"
            item_name = match.group(2)
            collection = match.group(3).strip()
            
            foreach_node = self._create_foreach_node()
            nodes.append(foreach_node)
            
            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    foreach_node, "enter"
                )
                connections.append(conn)
            
            last_node = foreach_node

        # Process switch statements
        switch_pattern = r'switch\s*\(([^)]+)\)\s*\{'
        for match in re.finditer(switch_pattern, body):
            selector = match.group(1).strip()
            
            # Count cases
            switch_start = match.end()
            switch_body = self._extract_switch_body(body, switch_start)
            num_cases = len(re.findall(r'case\s+\d+:', switch_body))
            
            switch_node = self._create_switch_node(num_cases)
            nodes.append(switch_node)
            
            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    switch_node, "enter"
                )
                connections.append(conn)
            
            last_node = switch_node

        # Process Debug.Log calls
        debug_log_pattern = r'Debug\.Log\s*\(([^)]+)\)'
        for match in re.finditer(debug_log_pattern, body):
            log_arg = match.group(1).strip()

            debug_node = self._create_invoke_node(
                "Log",
                "UnityEngine.Debug",
                [{"type": "System.Object", "name": "message"}]
            )
            nodes.append(debug_node)

            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    debug_node, "enter"
                )
                connections.append(conn)

            if log_arg.startswith('"') and log_arg.endswith('"'):
                literal_value = log_arg[1:-1]
                literal_node = self._create_literal_node(literal_value, "string")
                nodes.append(literal_node)

                conn = self._create_connection(
                    literal_node, "output",
                    debug_node, "%message",
                    is_control=False
                )
                connections.append(conn)
            
            last_node = debug_node

        # Process if statements
        if_pattern = r'if\s*\(([^)]+)\)'
        for match in re.finditer(if_pattern, body):
            condition = match.group(1).strip()

            if_node = self._create_if_node()
            nodes.append(if_node)

            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    if_node, "enter"
                )
                connections.append(conn)
            
            # Parse and create comparison node if needed
            comparison_ops = ['<=', '>=', '==', '!=', '<', '>']
            for op in comparison_ops:
                if op in condition:
                    parts = condition.split(op, 1)
                    if len(parts) == 2:
                        comp_node = self._create_comparison_node(op)
                        nodes.append(comp_node)
                        
                        conn = self._create_connection(
                            comp_node, "result",
                            if_node, "%condition",
                            is_control=False
                        )
                        connections.append(conn)
                    break
            
            last_node = if_node

        # Process variable assignments
        assignment_pattern = r'(\w+)\s*=\s*([^;]+);'
        for match in re.finditer(assignment_pattern, body):
            var_name = match.group(1)
            var_value = match.group(2).strip()

            set_var_node = self._create_set_variable_node(var_name, "System.Object")
            nodes.append(set_var_node)

            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    set_var_node, "enter"
                )
                connections.append(conn)
            
            # Check for arithmetic operations in the value
            arithmetic_ops = ['+', '-', '*', '/', '%']
            for op in arithmetic_ops:
                if op in var_value and not var_value.startswith('"'):
                    parts = var_value.split(op, 1)
                    if len(parts) == 2:
                        arith_node = self._create_arithmetic_node(op)
                        nodes.append(arith_node)
                        
                        conn = self._create_connection(
                            arith_node, "result",
                            set_var_node, "%input",
                            is_control=False
                        )
                        connections.append(conn)
                    break
            
            last_node = set_var_node

        # Process yield return statements (for coroutines)
        yield_pattern = r'yield\s+return\s+(?:new\s+)?(\w+)\s*(?:\(([^)]*)\))?'
        for match in re.finditer(yield_pattern, body):
            yield_type = match.group(1)
            yield_args = match.group(2)
            
            yield_node = self._create_yield_return_node()
            nodes.append(yield_node)
            
            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    yield_node, "enter"
                )
                connections.append(conn)
            
            # Handle WaitForSeconds
            if yield_type == "WaitForSeconds" and yield_args:
                try:
                    seconds = float(yield_args.strip())
                    wait_node = self._create_wait_for_seconds_node(seconds)
                    nodes.append(wait_node)
                    
                    conn = self._create_connection(
                        wait_node, "result",
                        yield_node, "%instruction",
                        is_control=False
                    )
                    connections.append(conn)
                except ValueError:
                    pass
            
            last_node = yield_node

        # Process custom method calls (not Debug.Log)
        method_call_pattern = r'(\w+)\.(\w+)\s*\(([^)]*)\)'
        for match in re.finditer(method_call_pattern, body):
            target_obj = match.group(1)
            method_name = match.group(2)
            args_str = match.group(3).strip()
            
            # Skip Debug.Log as it's already handled
            if target_obj == "Debug" and method_name == "Log":
                continue
            
            # Skip if this is part of a variable declaration or assignment
            pre_context = body[max(0, match.start() - 20):match.start()]
            if '=' in pre_context.split('\n')[-1]:
                continue
            
            # Determine target type
            target_type = f"UnityEngine.{target_obj}" if target_obj in ["GameObject", "Transform", "Rigidbody"] else target_obj
            
            # Parse arguments
            parameters = []
            if args_str:
                # Simple parsing - just count arguments for now
                arg_count = len([a.strip() for a in args_str.split(',') if a.strip()])
                for i in range(arg_count):
                    parameters.append({"type": "System.Object", "name": f"arg{i}"})
            
            custom_node = self._create_custom_invoke_node(
                method_name,
                target_type,
                parameters,
                return_type="void",
                is_static=False
            )
            nodes.append(custom_node)
            
            if last_node:
                conn = self._create_connection(
                    last_node, "trigger" if last_node == event_node else "exit",
                    custom_node, "enter"
                )
                connections.append(conn)
            
            last_node = custom_node

        # Add method comment as description to first node if available
        if method.get("comments") and nodes:
            if event_node:
                event_node.description = method["comments"]

        return nodes, connections

    def _extract_switch_body(self, code: str, start_pos: int) -> str:
        """Extract the body of a switch statement"""
        depth = 0
        end_pos = start_pos
        for i, char in enumerate(code[start_pos:]):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end_pos = start_pos + i
                    break
        return code[start_pos:end_pos]


class CS_to_VisualScripting_Converter:
    """Main converter class"""

    def __init__(self):
        self.parser = None
        self.generator = None

    def convert(self, cs_code: str) -> str:
        self.parser = CSharpParser(cs_code)
        self.generator = VisualScriptingGenerator(self.parser)
        graph = self.generator.generate_graph()
        return json.dumps(graph, indent=4)

    def convert_file(self, input_path: str, output_path: str):
        with open(input_path, 'r', encoding='utf-8') as f:
            cs_code = f.read()

        json_output = self.convert(cs_code)

        yaml_header = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!114 &11400000
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_GameObject: {fileID: 0}
  m_Enabled: 1
  m_EditorHideFlags: 0
  m_Script: {fileID: 11500000, guid: d2dc886499c26824283350fa532d087d, type: 3}
  m_Name: 
  m_EditorClassIdentifier: 
  _data:
    _json: '"""

        yaml_footer = """
    _objectReferences: []
"""

        escaped_json = json_output.replace('\\', '\\\\').replace('"', '\\"').replace("'", "''")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(yaml_header)
            f.write(escaped_json)
            f.write(yaml_footer)

        print(f"Converted: {input_path} -> {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert Unity C# Scripts to Visual Scripting Graphs'
    )
    parser.add_argument('input', help='Input C# file or directory')
    parser.add_argument('-o', '--output', help='Output directory (default: same as input)')
    parser.add_argument('-r', '--recursive', action='store_true', help='Process directories recursively')

    args = parser.parse_args()

    converter = CS_to_VisualScripting_Converter()

    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else input_path.parent

    if input_path.is_file():
        if input_path.suffix == '.cs':
            output_path = output_dir / (input_path.stem + '.asset')
            converter.convert_file(str(input_path), str(output_path))
        else:
            print("Error: Input file must be a .cs file")
            sys.exit(1)

    elif input_path.is_dir():
        pattern = '**/*.cs' if args.recursive else '*.cs'
        cs_files = list(input_path.glob(pattern))

        if not cs_files:
            print(f"No .cs files found in {input_path}")
            sys.exit(1)

        for cs_file in cs_files:
            rel_path = cs_file.relative_to(input_path)
            out_file = output_dir / rel_path.with_suffix('.asset')
            out_file.parent.mkdir(parents=True, exist_ok=True)
            converter.convert_file(str(cs_file), str(out_file))

        print(f"\nConverted {len(cs_files)} file(s)")

    else:
        print(f"Error: Input path does not exist: {input_path}")
        sys.exit(1)


if __name__ == '__main__':
    main()
