from __future__ import annotations

import json
from types import SimpleNamespace


class FakeResponseStream:
    def __init__(self, response) -> None:
        self._response = response
        self._events = []
        if getattr(response, "output_text", ""):
            self._events.append(
                SimpleNamespace(
                    type="response.output_text.delta",
                    delta=response.output_text,
                )
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_response(self):
        return self._response


class FakeOpenAI:
    response_counter = 0
    conversation_counter = 0
    poison_conversation_ids: set[str] = set()
    poison_previous_response_ids: set[str] = set()
    poisoned_once: set[str] = set()
    tool_output_answer_text = "Grounded answer from cached folder content. [source_1]"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.embeddings = SimpleNamespace(create=self._create_embeddings)
        self.responses = SimpleNamespace(
            stream=self._stream_response,
        )
        self.conversations = SimpleNamespace(create=self._create_conversation)

    def _create_embeddings(self, model: str, input):
        if isinstance(input, str):
            input = [input]
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[1.0, 0.0, 0.0]) for _ in input]
        )

    def _create_conversation(self, metadata=None):
        FakeOpenAI.conversation_counter += 1
        return SimpleNamespace(id=f"conversation-{FakeOpenAI.conversation_counter}")

    def _stream_response(self, **kwargs):
        if kwargs.get("conversation") and kwargs.get("previous_response_id"):
            raise AssertionError(
                "Responses API should not receive both conversation and previous_response_id."
            )
        conversation_id = kwargs.get("conversation")
        if (
            isinstance(conversation_id, str)
            and conversation_id in FakeOpenAI.poison_conversation_ids
            and conversation_id not in FakeOpenAI.poisoned_once
        ):
            FakeOpenAI.poisoned_once.add(conversation_id)
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': 'No tool output found for function call call_stale.', 'type': 'invalid_request_error', 'param': 'input', 'code': None}}"
            )
        FakeOpenAI.response_counter += 1
        input_payload = kwargs.get("input")
        if isinstance(input_payload, list):
            if not kwargs.get("previous_response_id"):
                raise AssertionError(
                    "Tool outputs must be sent with previous_response_id set to the parent response."
                )
            response = SimpleNamespace(
                id=f"response-{FakeOpenAI.response_counter}",
                output=[],
                output_text=FakeOpenAI.tool_output_answer_text,
            )
            return FakeResponseStream(response)

        # User message: may use conversation (first turn) or previous_response_id (follow-up).
        if not kwargs.get("conversation") and not kwargs.get("previous_response_id"):
            raise AssertionError(
                "User turns must use either conversation (first turn) or previous_response_id (follow-up)."
            )
        prev_id = kwargs.get("previous_response_id")
        if (
            isinstance(prev_id, str)
            and prev_id in FakeOpenAI.poison_previous_response_ids
            and prev_id not in FakeOpenAI.poisoned_once
        ):
            FakeOpenAI.poisoned_once.add(prev_id)
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': 'No tool output found for function call call_stale.', 'type': 'invalid_request_error', 'param': 'input', 'code': None}}"
            )
        # Follow-up user message (previous_response_id): return final answer directly.
        if kwargs.get("previous_response_id"):
            response = SimpleNamespace(
                id=f"response-{FakeOpenAI.response_counter}",
                output=[],
                output_text=FakeOpenAI.tool_output_answer_text,
            )
            return FakeResponseStream(response)
        search_arguments = json.dumps({"query": str(input_payload), "top_k": 5})
        response = SimpleNamespace(
            id=f"response-{FakeOpenAI.response_counter}",
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="search_folder",
                    call_id="call-search-1",
                    arguments=search_arguments,
                )
            ],
            output_text="",
        )
        return FakeResponseStream(response)

    @classmethod
    def reset(cls) -> None:
        cls.response_counter = 0
        cls.conversation_counter = 0
        cls.poison_conversation_ids = set()
        cls.poison_previous_response_ids = set()
        cls.poisoned_once = set()
        cls.tool_output_answer_text = "Grounded answer from cached folder content. [source_1]"
