"""Voice pipeline (optional extension).

This module defines the VoicePipeline protocol. The reference Speechmatics
+ ElevenLabs implementation requires the [voice] extra. See
docs/architecture.md §2.18.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from sovereign_agent.discovery import DiscoverySchema
from sovereign_agent.session.directory import Session


@runtime_checkable
class VoicePipeline(Protocol):
    name: str

    async def listen(self, session: Session) -> str:
        """Capture one utterance from the user, return transcribed text."""

    async def speak(self, session: Session, text: str) -> Path:
        """Synthesize speech for `text`, write to session extras/voice/,
        return the audio file path."""

    def discover(self) -> DiscoverySchema: ...


class SpeechmaticsVoicePipeline:
    """Reference voice pipeline. Requires sovereign-agent[voice].

    Skeleton: import-gated; the actual ASR/TTS wiring is TODO in a lesson.
    """

    name = "speechmatics+elevenlabs"

    def __init__(self, asr_api_key: str | None = None, tts_api_key: str | None = None) -> None:
        from sovereign_agent._internal.extras import requires_extra

        requires_extra("voice", "speechmatics", "elevenlabs")
        self.asr_api_key = asr_api_key
        self.tts_api_key = tts_api_key

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "observability",  # nearest kind in the enum; voice isn't a first-class kind
            "description": "Speechmatics ASR + ElevenLabs TTS reference pipeline.",
            "parameters": {"type": "object"},
            "returns": {"type": "object"},
            "error_codes": ["SA_EXT_SERVICE_UNAVAILABLE"],
            "examples": [{"input": {}, "output": {"ok": True}}],
            "version": "0.1.0",
            "metadata": {},
        }

    async def listen(self, session: Session) -> str:  # pragma: no cover
        raise NotImplementedError(
            "SpeechmaticsVoicePipeline.listen is a skeleton. See lessons/ for real implementations."
        )

    async def speak(self, session: Session, text: str) -> Path:  # pragma: no cover
        raise NotImplementedError(
            "SpeechmaticsVoicePipeline.speak is a skeleton. See lessons/ for real implementations."
        )


__all__ = ["VoicePipeline", "SpeechmaticsVoicePipeline"]
