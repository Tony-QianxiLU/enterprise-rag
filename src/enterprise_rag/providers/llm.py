from typing import Protocol

from enterprise_rag.config import Settings


class LLMProvider(Protocol):
    def generate(self, *, system_prompt: str, user_prompt: str) -> str: ...


class TemplateLLMProvider:
    """Deterministic fallback: assembles an answer from retrieved context without an LLM call.

    Keeps the app fully demoable and testable without a paid API key. The
    provider boundary is what makes this swappable for a real model with zero
    changes to the RAG pipeline or API layer.
    """

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return (
            "Relevant context was retrieved from the uploaded documents. "
            "Configure OPENAI_API_KEY to enable LLM-generated answers.\n\n"
            f"{user_prompt}"
        )


class OpenAILLMProvider:
    def __init__(self, model: str) -> None:
        from langchain_openai import ChatOpenAI

        self._model = ChatOpenAI(model=model, temperature=0.1)

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = self._model.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        return str(response.content)


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.openai_api_key:
        return OpenAILLMProvider(model=settings.openai_model)
    return TemplateLLMProvider()
