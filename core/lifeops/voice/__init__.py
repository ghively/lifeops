"""Voice provider adapters (BUILD_SPEC sections 27-29, phase 5).

Hermes and LifeOps Core never talk to ElevenLabs directly; everything routes
through the ``TTSProvider`` abstraction in ``provider.py`` so a local RTX
model can replace it later (phase 6) without a caller changing.
"""
