"""Core RLM implementation."""

import asyncio
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Optional, Dict, Any, List

import litellm

from .types import Message
from .repl import REPLExecutor, REPLError
from .prompts import build_system_prompt
from .parser import parse_response, is_final


class RLMError(Exception):
    """Base error for RLM."""
    pass


class MaxIterationsError(RLMError):
    """Max iterations exceeded."""
    pass


class MaxDepthError(RLMError):
    """Max recursion depth exceeded."""
    pass


class RLM:
    """Recursive Language Model."""

    def __init__(
        self,
        model: str,
        recursive_model: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        max_depth: int = 5,
        max_iterations: int = 30,
        _current_depth: int = 0,
        **llm_kwargs: Any
    ):
        """
        Initialize RLM.

        Args:
            model: Model name (e.g., "gpt-4o", "claude-sonnet-4", "ollama/llama3.2")
            recursive_model: Optional cheaper model for recursive calls
            api_base: Optional API base URL
            api_key: Optional API key
            max_depth: Maximum recursion depth
            max_iterations: Maximum REPL iterations per call
            _current_depth: Internal current depth tracker
            **llm_kwargs: Additional LiteLLM parameters
        """
        self.model = model
        self.recursive_model = recursive_model or model
        self.api_base = api_base
        self.api_key = api_key
        self.max_depth = max_depth
        self.max_iterations = max_iterations
        self._current_depth = _current_depth
        self.llm_kwargs = llm_kwargs

        self.repl = REPLExecutor()

        # Stats
        self._llm_calls = 0
        self._iterations = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def complete(
        self,
        query: str = "",
        context: str = "",
        **kwargs: Any
    ) -> str:
        """
        Sync wrapper for acomplete.

        Args:
            query: User query (optional if query is in context)
            context: Context to process (optional, can pass query here)
            **kwargs: Additional LiteLLM parameters

        Returns:
            Final answer string

        Examples:
            # Standard usage
            rlm.complete(query="Summarize this", context=document)

            # Query in context (RLM will extract task)
            rlm.complete(context="Summarize this document: ...")

            # Single string (treat as context)
            rlm.complete("Process this text and extract dates")
        """
        # If only one argument provided, treat it as context
        if query and not context:
            context = query
            query = ""

        return asyncio.run(self.acomplete(query, context, **kwargs))

    async def acomplete(
        self,
        query: str = "",
        context: str = "",
        **kwargs: Any
    ) -> str:
        """
        Main async complete method.

        Args:
            query: User query (optional if query is in context)
            context: Context to process (optional, can pass query here)
            **kwargs: Additional LiteLLM parameters

        Returns:
            Final answer string

        Raises:
            MaxIterationsError: If max iterations exceeded
            MaxDepthError: If max recursion depth exceeded

        Examples:
            # Explicit query and context
            await rlm.acomplete(query="What is this?", context=doc)

            # Query embedded in context
            await rlm.acomplete(context="Extract all dates from: ...")

            # LLM will figure out the task
            await rlm.acomplete(context=document_with_instructions)
        """
        # If only query provided, treat it as context
        if query and not context:
            context = query
            query = ""
        if self._current_depth > self.max_depth:
            raise MaxDepthError(f"Max recursion depth ({self.max_depth}) exceeded")

        # Initialize REPL environment
        repl_env = self._build_repl_env(query, context)

        # Build initial messages
        system_prompt = build_system_prompt(len(context), self._current_depth)
        messages: List[Message] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]

        # Main loop
        for iteration in range(self.max_iterations):
            self._iterations = iteration + 1

            # Call LLM
            response = await self._call_llm(messages, **kwargs)
            print("\n" + "=" * 80)
            print(f"RLM ITERATION {iteration}")
            print("MODEL RESPONSE:")
            print(response)
            print("=" * 80 + "\n")

            # Check for FINAL
            if is_final(response):
                answer = parse_response(response, repl_env)
                if answer is not None:
                    return answer
# --- AZIZ PATCH: Clean Markdown formatting ---
            # --- AZIZ PATCH: Strip Markdown so the REPL doesn't crash ---
            clean_response = response.replace("```python\n", "").replace("```python", "").replace("```", "").strip()

            # Execute code in REPL
            try:
                exec_result = self.repl.execute(clean_response, repl_env)
            except REPLError as e:
                exec_result = f"Error: {str(e)}"
            except Exception as e:
                exec_result = f"Unexpected error: {str(e)}"

            # --- AZIZ PATCH: X-Ray Vision (Print the sandbox output for us) ---
            print("REPL OBSERVATION (What the AI sees):")
            print(exec_result)
            print("-" * 80 + "\n")

            # Add to conversation
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": exec_result})

        raise MaxIterationsError(
            f"Max iterations ({self.max_iterations}) exceeded without FINAL()"
        )

    async def _call_llm(
        self,
        messages: List[Message],
        **kwargs: Any
    ) -> str:
        """
        Call LLM API.

        Args:
            messages: Conversation messages
            **kwargs: Additional parameters (can override model here)

        Returns:
            LLM response text
        """
        self._llm_calls += 1

        # Choose model based on depth
        default_model = self.model if self._current_depth == 0 else self.recursive_model

        # Allow override via kwargs
        model = kwargs.pop('model', default_model)

        # Merge kwargs
        call_kwargs = {**self.llm_kwargs, **kwargs}
        if self.api_base:
            call_kwargs['api_base'] = self.api_base
        if self.api_key:
            call_kwargs['api_key'] = self.api_key

        if model.startswith("azure/"):
            return await self._call_azure_chat(model, messages, call_kwargs)

        # Call LiteLLM
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            **call_kwargs
        )

        usage = getattr(response, "usage", None)
        self._input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        self._output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        # Extract text
        return response.choices[0].message.content

    async def _call_azure_chat(
        self,
        model: str,
        messages: List[Message],
        call_kwargs: Dict[str, Any],
    ) -> str:
        api_base = str(call_kwargs.get("api_base") or self.api_base or "").rstrip("/")
        api_key = str(call_kwargs.get("api_key") or self.api_key or "")
        api_version = str(call_kwargs.get("api_version") or "2024-12-01-preview")
        deployment = str(
            call_kwargs.get("azure_deployment")
            or call_kwargs.get("deployment")
            or model.removeprefix("azure/")
        )
        temperature = call_kwargs.get("temperature", 1)
        max_tokens = call_kwargs.get("max_completion_tokens", call_kwargs.get("max_tokens"))

        if not api_base or not api_key or not deployment:
            raise RuntimeError(
                "Azure RLM call requires api_base, api_key, and deployment."
            )

        url = (
            f"{api_base}/openai/deployments/{deployment}/chat/completions"
            f"?api-version={api_version}"
        )
        payload: Dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_completion_tokens"] = max_tokens

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "api-key": api_key},
            method="POST",
        )

        def do_request() -> str:
            try:
                with urlopen(request, timeout=300) as response:
                    result = json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                details = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Azure OpenAI request failed ({error.code}): {details}"
                ) from error
            except URLError as error:
                raise RuntimeError(
                    f"Cannot connect to Azure OpenAI at {api_base}. "
                    "Check api_base and api_version."
                ) from error

            try:
                usage = result.get("usage") or {}
                self._input_tokens += int(usage.get("prompt_tokens") or 0)
                self._output_tokens += int(usage.get("completion_tokens") or 0)
                return result["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as error:
                raise RuntimeError(f"Unexpected Azure OpenAI response: {result}") from error

        return await asyncio.to_thread(do_request)

    def _build_repl_env(self, query: str, context: str) -> Dict[str, Any]:
        """
        Build REPL environment.

        Args:
            query: User query
            context: Context string

        Returns:
            Environment dict
        """
        env: Dict[str, Any] = {
            'context': context,
            'query': query,
            'recursive_llm': self._make_recursive_fn(),
            're': re,  # Whitelist re module
        }
        return env

    def _make_recursive_fn(self) -> Any:
        """
        Create recursive LLM function for REPL.

        Returns:
            Async function that can be called from REPL
        """
        async def recursive_llm(sub_query: str, sub_context: str) -> str:
            """
            Recursively process sub-context.

            Args:
                sub_query: Query for sub-context
                sub_context: Sub-context to process

            Returns:
                Answer from recursive call
            """
            if self._current_depth + 1 > self.max_depth:
                return f"Max recursion depth ({self.max_depth}) reached"

            # Create sub-RLM with increased depth
            sub_rlm = RLM(
                model=self.recursive_model,
                recursive_model=self.recursive_model,
                api_base=self.api_base,
                api_key=self.api_key,
                max_depth=self.max_depth,
                max_iterations=self.max_iterations,
                _current_depth=self._current_depth + 1,
                **self.llm_kwargs
            )

            return await sub_rlm.acomplete(sub_query, sub_context)

        # Wrap in sync function for REPL compatibility
        def sync_recursive_llm(sub_query: str, sub_context: str) -> str:
            """Sync wrapper for recursive_llm."""
            # Check if we're in an async context
            try:
                loop = asyncio.get_running_loop()
                # We're in async context, but REPL is sync
                # Create a new thread to run async code
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        recursive_llm(sub_query, sub_context)
                    )
                    return future.result()
            except RuntimeError:
                # No running loop, safe to use asyncio.run
                return asyncio.run(recursive_llm(sub_query, sub_context))

        return sync_recursive_llm

    @property
    def stats(self) -> Dict[str, int]:
        """Get execution statistics."""
        return {
            'llm_calls': self._llm_calls,
            'iterations': self._iterations,
            'depth': self._current_depth,
            'input_tokens': self._input_tokens,
            'output_tokens': self._output_tokens,
        }
