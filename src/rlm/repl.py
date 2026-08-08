"""Safe REPL executor using RestrictedPython."""

import io
import re
import sys
from typing import Dict, Any, Optional
from RestrictedPython import compile_restricted_exec, safe_globals, limited_builtins, utility_builtins
from RestrictedPython.Guards import guarded_iter_unpack_sequence, safer_getattr
from RestrictedPython.PrintCollector import PrintCollector


class REPLError(Exception):
    """Error during REPL execution."""
    pass


class REPLExecutor:
    """Safe Python code executor."""

    def __init__(self, timeout: int = 5, max_output_chars: int = 2000):
        """
        Initialize REPL executor.

        Args:
            timeout: Execution timeout in seconds (not currently enforced)
            max_output_chars: Maximum characters to return (truncate if longer)
        """
        self.timeout = timeout
        self.max_output_chars = max_output_chars

    def execute(self, code: str, env: Dict[str, Any]) -> str:
        """
        Execute Python code in restricted environment.

        Args:
            code: Python code to execute
            env: Environment with context, query, recursive_llm, etc.

        Returns:
            String result of execution (stdout or last expression)

        Raises:
            REPLError: If code execution fails
        """
        # Filter out code blocks if present (LLM might wrap code)
        code = self._extract_code(code)

        if not code.strip():
            return "No code to execute"

        # Build restricted globals
        restricted_globals = self._build_globals(env)

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()

        try:
            # Compile with RestrictedPython
            byte_code = compile_restricted_exec(code)

            if byte_code.errors:
                raise REPLError(f"Compilation error: {', '.join(byte_code.errors)}")

            # Execute
            exec(byte_code.code, restricted_globals, env)

            # Get output from stdout
            output = captured_output.getvalue()

            # Get output from PrintCollector if available
            if '_print' in env and hasattr(env['_print'], '__call__'):
                # PrintCollector stores prints in its txt attribute
                print_collector = env['_print']
                if hasattr(print_collector, 'txt'):
                    output += ''.join(print_collector.txt)

            # Check if last line was an expression (try to get its value)
            # This handles cases like: error_count (should return its value)
            lines = code.strip().split('\n')
            if lines:
                last_line = lines[-1].strip()
                # Only re-read a variable name. Re-evaluating an arbitrary call
                # such as db.execute(...) would execute the tool twice.
                if re.fullmatch(r"[A-Za-z_]\w*", last_line):
                    try:
                        # Return a previously assigned value without side effects.
                        result = eval(last_line, restricted_globals, env)
                        if result is not None:
                            output += str(result) + '\n'
                    except:
                        pass  # Not an expression, ignore

            if not output:
                return "Code executed successfully (no output)"

            # Truncate output if too long (as per paper: "truncated version of output")
            if len(output) > self.max_output_chars:
                truncated = output[:self.max_output_chars]
                return f"{truncated}\n\n[Output truncated: {len(output)} chars total, showing first {self.max_output_chars}]"

            return output.strip()

        except Exception as e:
            raise REPLError(f"Execution error: {str(e)}")

        finally:
            sys.stdout = old_stdout

    def _extract_code(self, text: str) -> str:
        """
        Extract code from markdown code blocks if present.

        Args:
            text: Raw text that might contain code

        Returns:
            Extracted code
        """
        # Execute every fenced Python block in order. Historically only the
        # first block ran, silently discarding later db.execute calls while the
        # model assumed they had produced observations.
        python_blocks = re.findall(
            r"```python\s*\n([\s\S]*?)\n```",
            text,
            flags=re.IGNORECASE,
        )
        if python_blocks:
            unique_blocks = []
            for block in python_blocks:
                block = block.strip()
                if block and (not unique_blocks or block != unique_blocks[-1]):
                    unique_blocks.append(block)
            return "\n".join(unique_blocks)

        generic_blocks = re.findall(r"```\s*\n([\s\S]*?)\n```", text)
        if generic_blocks:
            return "\n".join(block.strip() for block in generic_blocks if block.strip())

        return text

    def _build_globals(self, env: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build restricted globals for safe execution.

        Args:
            env: User environment

        Returns:
            Safe globals dict
        """
        restricted_globals = safe_globals.copy()
        restricted_globals.update(limited_builtins)
        restricted_globals.update(utility_builtins)

        # Add guards
        restricted_globals['_iter_unpack_sequence_'] = guarded_iter_unpack_sequence
        restricted_globals['_getattr_'] = safer_getattr
        restricted_globals['_getitem_'] = lambda obj, index: obj[index]
        restricted_globals['_getiter_'] = iter
        restricted_globals['_print_'] = PrintCollector

        # Add additional safe builtins
        restricted_globals.update({
            # Types
            'len': len,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'frozenset': frozenset,
            'bytes': bytes,
            'bytearray': bytearray,

            # Iteration
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'reversed': reversed,
            'iter': iter,
            'next': next,

            # Aggregation
            'sorted': sorted,
            'sum': sum,
            'min': min,
            'max': max,
            'any': any,
            'all': all,

            # Math
            'abs': abs,
            'round': round,
            'pow': pow,
            'divmod': divmod,

            # String/repr
            'chr': chr,
            'ord': ord,
            'hex': hex,
            'oct': oct,
            'bin': bin,
            'repr': repr,
            'ascii': ascii,
            'format': format,

            # Type checking
            'isinstance': isinstance,
            'issubclass': issubclass,
            'callable': callable,
            'type': type,
            'hasattr': hasattr,

            # Constants
            'True': True,
            'False': False,
            'None': None,
        })

        # Add safe standard library modules
        # These are read-only and don't allow file/network access
        import re
        import json
        import math
        from datetime import datetime, timedelta
        from collections import Counter, defaultdict

        restricted_globals.update({
            're': re,               # Regex (read-only)
            'json': json,           # JSON parsing (read-only)
            'math': math,           # Math functions
            'datetime': datetime,   # Date parsing
            'timedelta': timedelta, # Time deltas
            'Counter': Counter,     # Counting helper
            'defaultdict': defaultdict,  # Dict with defaults
        })

        return restricted_globals
