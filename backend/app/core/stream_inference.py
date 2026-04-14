"""Stream inference service - thin proxy for DeepStream pipeline results.

With the DeepStream migration, all frame decoding, inference, OSD rendering,
and video output happen inside the DeepStream GPU pipeline. This module is
retained as a lightweight helper for reading latest results from Redis
(published by the DeepStream metadata extractor).
"""

import json
import logging
from typing import Any, Dict, Optional

from app.core.redis import get_redis_pool

logger = logging.getLogger(__name__)


class StreamInferenceService:
    """Thin proxy that reads DeepStream inference results from Redis."""

    async def get_latest_result(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest inference result for a session from Redis."""
        redis = await get_redis_pool()
        result_key = f"stream_result:{session_id}:latest"
        result_json = await redis.get(result_key)

        if result_json:
            return json.loads(result_json)

        return None


# Global singleton (kept for backward compatibility with any remaining imports)
stream_inference_service = StreamInferenceService()
