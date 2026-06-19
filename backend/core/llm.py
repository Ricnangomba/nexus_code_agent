"""
Nexus LLM Module
Handles integration with multiple LLM providers (Ollama, OpenAI, Claude, etc.)
"""

import os
import json
import aiohttp
import logging
import asyncio
import time
from typing import Optional, List, Dict, Any, AsyncGenerator
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Chat message structure"""
    role: str  # "user", "assistant", "system"
    content: str


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    @abstractmethod
    async def chat(self, messages: List[Message], **kwargs) -> str:
        """Send chat request and get response"""
        pass
    
    @abstractmethod
    async def stream_chat(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        """Send chat request and stream response"""
        pass

    async def close(self):
        """Optional cleanup for provider (close sessions)"""
        return


class OllamaProvider(LLMProvider):
    """Ollama LLM Provider"""
    
    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "llama2", api_key: str = None, timeout_seconds: int = 300, retries: int = 2, **kwargs):
        self.endpoint = endpoint
        self.model = model
        self.chat_endpoint = f"{endpoint}/api/chat"
        self.timeout_seconds = int(timeout_seconds)
        self.retries = int(retries)
        self.session = aiohttp.ClientSession()
    
    async def chat(self, messages: List[Message], **kwargs) -> str:
        """Send chat request to Ollama"""
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            **kwargs
        }

        attempt = 0
        while attempt <= self.retries:
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                async with self.session.post(self.chat_endpoint, json=payload, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("message", {}).get("content", "")
                    else:
                        logger.error(f"Ollama error: {resp.status}")
                        # Treat non-200 as retryable up to limit
                        attempt += 1
                        await asyncio.sleep(1 + attempt)
            except Exception as e:
                logger.error(f"Ollama request failed (attempt {attempt}): {e}")
                attempt += 1
                await asyncio.sleep(0.5 * attempt)

        return ""

    async def close(self):
        try:
            await self.session.close()
        except Exception:
            pass
    
    async def stream_chat(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        """Stream chat response from Ollama"""
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            **kwargs
        }

        attempt = 0
        while attempt <= self.retries:
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                async with self.session.post(self.chat_endpoint, json=payload, timeout=timeout) as resp:
                    if resp.status == 200:
                        async for raw_chunk in resp.content:
                            if not raw_chunk:
                                continue
                            text = raw_chunk.decode(errors="ignore").strip()
                            # Some Ollama streams may send JSON per line
                            try:
                                data = json.loads(text)
                                content = data.get("message", {}).get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                # fallback: yield raw text
                                if text:
                                    yield text
                        return
                    else:
                        logger.error(f"Ollama stream error: {resp.status}")
                        attempt += 1
                        await asyncio.sleep(1 + attempt)
            except Exception as e:
                logger.error(f"Ollama stream failed (attempt {attempt}): {e}")
                attempt += 1
                await asyncio.sleep(0.5 * attempt)
        return


class OpenAIProvider(LLMProvider):
    """OpenAI LLM Provider"""
    
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo", endpoint: str = "https://api.openai.com/v1/chat/completions", timeout_seconds: int = 60, retries: int = 1, **kwargs):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = int(timeout_seconds)
        self.retries = int(retries)
        self.session = aiohttp.ClientSession()
    
    async def chat(self, messages: List[Message], **kwargs) -> str:
        """Send chat request to OpenAI"""
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            **kwargs
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        attempt = 0
        while attempt <= self.retries:
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                async with self.session.post(self.endpoint, json=payload, headers=headers, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    else:
                        logger.error(f"OpenAI error: {resp.status}")
                        attempt += 1
                        await asyncio.sleep(1 + attempt)
            except Exception as e:
                logger.error(f"OpenAI request failed (attempt {attempt}): {e}")
                attempt += 1
                await asyncio.sleep(0.5 * attempt)

        return ""

    async def close(self):
        try:
            await self.session.close()
        except Exception:
            pass
    
    async def stream_chat(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        """Stream chat response from OpenAI"""
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            **kwargs
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        attempt = 0
        while attempt <= self.retries:
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
                async with self.session.post(self.endpoint, json=payload, headers=headers, timeout=timeout) as resp:
                    if resp.status == 200:
                        async for raw in resp.content:
                            if not raw:
                                continue
                            text = raw.decode().strip()
                            if text.startswith("data: "):
                                data_str = text[6:]
                                if data_str != "[DONE]":
                                    try:
                                        data = json.loads(data_str)
                                        delta = data.get("choices", [{}])[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                    except Exception:
                                        # fallback: yield raw chunk
                                        if data_str:
                                            yield data_str
                        return
                    else:
                        logger.error(f"OpenAI stream error: {resp.status}")
                        attempt += 1
                        await asyncio.sleep(1 + attempt)
            except Exception as e:
                logger.error(f"OpenAI stream failed (attempt {attempt}): {e}")
                attempt += 1
                await asyncio.sleep(0.5 * attempt)
        return


class LLMFactory:
    """Factory for creating LLM providers"""
    
    _providers = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
    }
    
    @classmethod
    def create(cls, provider: str, **kwargs) -> LLMProvider:
        """Create an LLM provider instance"""
        provider_class = cls._providers.get(provider.lower())
        if not provider_class:
            raise ValueError(f"Unknown LLM provider: {provider}")
        return provider_class(**kwargs)
    
    @classmethod
    def register(cls, name: str, provider_class: type):
        """Register a new LLM provider"""
        cls._providers[name.lower()] = provider_class


# --- Metrics and queued wrapper ---
class Metrics:
    def __init__(self):
        self.requests = 0
        self.errors = 0
        self.latency_sum = 0.0
        self.latency_count = 0

    def record(self, latency: float, error: bool = False):
        self.requests += 1
        if error:
            self.errors += 1
        self.latency_sum += latency
        self.latency_count += 1


_GLOBAL_METRICS: Dict[str, Metrics] = {}
_QUEUE_SIZE_TRACKERS: Dict[str, Any] = {}


def _get_metrics_for(key: str) -> Metrics:
    if key not in _GLOBAL_METRICS:
        _GLOBAL_METRICS[key] = Metrics()
    return _GLOBAL_METRICS[key]


def _register_queue_size(key: str, tracker):
    _QUEUE_SIZE_TRACKERS[key] = tracker


def get_prometheus_metrics() -> str:
    lines = []
    lines.append('# HELP nexus_llm_requests_total Total LLM requests')
    lines.append('# TYPE nexus_llm_requests_total counter')
    lines.append('# HELP nexus_llm_errors_total Total LLM errors')
    lines.append('# TYPE nexus_llm_errors_total counter')
    lines.append('# HELP nexus_llm_latency_seconds_sum Sum of request latencies')
    lines.append('# TYPE nexus_llm_latency_seconds_sum counter')
    lines.append('# HELP nexus_llm_latency_seconds_count Count of latency observations')
    lines.append('# TYPE nexus_llm_latency_seconds_count counter')
    lines.append('# HELP nexus_llm_queue_size Current queued LLM requests')
    lines.append('# TYPE nexus_llm_queue_size gauge')

    for key, m in _GLOBAL_METRICS.items():
        provider, model = key.split('||') if '||' in key else (key, '')
        labels = f'provider="{provider}",model="{model}"'
        lines.append(f'nexus_llm_requests_total{{{labels}}} {m.requests}')
        lines.append(f'nexus_llm_errors_total{{{labels}}} {m.errors}')
        lines.append(f'nexus_llm_latency_seconds_sum{{{labels}}} {m.latency_sum}')
        lines.append(f'nexus_llm_latency_seconds_count{{{labels}}} {m.latency_count}')

    for key, tracker in _QUEUE_SIZE_TRACKERS.items():
        provider, model = key.split('||') if '||' in key else (key, '')
        labels = f'provider="{provider}",model="{model}"'
        lines.append(f'nexus_llm_queue_size{{{labels}}} {tracker()}')

    return "\n".join(lines)


class LLMRequest:
    def __init__(self, messages: List[Message], kwargs: Dict[str, Any]):
        self.messages = messages
        self.kwargs = kwargs
        self.future = asyncio.get_event_loop().create_future()


class QueuedBatchLLM(LLMProvider):
    """Queue-based LLM wrapper with worker processing and metrics"""
    def __init__(self, provider: LLMProvider, concurrency: int = 2, max_queue: int = 100):
        self.provider = provider
        self.queue = asyncio.Queue(maxsize=max_queue)
        self.workers = [asyncio.create_task(self._worker_loop()) for _ in range(concurrency)]
        prov_name = getattr(provider, '__class__', type(provider)).__name__.lower()
        model = getattr(provider, 'model', '')
        self._metrics_key = f"{prov_name}||{model}"
        _get_metrics_for(self._metrics_key)
        _register_queue_size(self._metrics_key, self.queue.qsize)

    async def _worker_loop(self):
        while True:
            request = await self.queue.get()
            if request is None:
                self.queue.task_done()
                break

            start = time.time()
            try:
                result = await self.provider.chat(request.messages, **request.kwargs)
                request.future.set_result(result)
                _get_metrics_for(self._metrics_key).record(time.time() - start, error=False)
            except Exception as exc:
                request.future.set_exception(exc)
                _get_metrics_for(self._metrics_key).record(time.time() - start, error=True)
            finally:
                self.queue.task_done()

    async def chat(self, messages: List[Message], **kwargs) -> str:
        request = LLMRequest(messages, kwargs)
        await self.queue.put(request)
        return await request.future

    async def stream_chat(self, messages: List[Message], **kwargs) -> AsyncGenerator[str, None]:
        # Streamed chat bypasses queueing and uses provider directly to preserve generator semantics.
        start = time.time()
        error = False
        try:
            async for chunk in self.provider.stream_chat(messages, **kwargs):
                yield chunk
            _get_metrics_for(self._metrics_key).record(time.time() - start, error=error)
        except Exception:
            error = True
            _get_metrics_for(self._metrics_key).record(time.time() - start, error=True)
            raise

    async def close(self):
        for _ in self.workers:
            await self.queue.put(None)
        await asyncio.gather(*self.workers)
        if hasattr(self.provider, 'close'):
            await self.provider.close()

    def queue_size(self) -> int:
        return self.queue.qsize()
