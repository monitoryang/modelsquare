"""OWL model probe for DeepStream pipelines.

Extracts frames from the GPU pipeline, runs asynchronous OWL inference,
and injects detection metadata back into the pipeline for OSD rendering.

This is a placeholder implementation. The full OWL integration requires:
1. BufferRetriever to extract GPU frames as numpy arrays
2. Async queue to send frames to the OWL inference backend
3. Metadata injection (pyds.nvds_add_obj_meta_to_frame) for OSD rendering
"""

import logging
import time
from collections import deque
from typing import Any, Deque, Dict, List

from pyservicemaker import BatchMetadataOperator

logger = logging.getLogger(__name__)


class OwlFrameExtractor(BatchMetadataOperator):
    """Extract frames from pipeline for OWL inference.

    In the full implementation, this operator would:
    1. Use BufferRetriever to get frame data from GPU buffers
    2. Send frames to an async inference queue
    3. Receive OWL detection results
    4. Inject NvDsObjectMeta entries back into the frame_meta
    5. The downstream nvdsosd element then renders the boxes

    Currently this is a placeholder that logs frame processing stats.
    """

    def __init__(self, session_id: str, owl_prompts: List[str] = None,
                 owl_variant: str = "owlv2-base-patch16"):
        super().__init__()
        self.session_id = session_id
        self.owl_prompts = owl_prompts or []
        self.owl_variant = owl_variant
        self.frames_processed = 0
        self._latency_window: Deque[float] = deque(maxlen=100)

    def handle_metadata(self, batch_meta: Any) -> None:
        """Process each batch frame for OWL inference."""
        for frame_meta in batch_meta.frame_items:
            self.frames_processed += 1

            # TODO: Full implementation:
            # 1. Extract frame from GPU buffer via BufferRetriever
            # 2. Convert to numpy array (RGB format)
            # 3. Send to OWL inference (async queue)
            # 4. On result callback, inject NvDsObjectMeta:
            #    - pyds.nvds_add_obj_meta_to_frame(frame_meta, obj_meta)
            #    - Set rect_params (left, top, width, height)
            #    - Set class_id, confidence, text_params (label)
            # 5. nvdsosd downstream will render the boxes

            if self.frames_processed % 100 == 0:
                logger.info(
                    f"OWL probe [{self.session_id}]: processed {self.frames_processed} frames"
                )

    def update_prompts(self, prompts: List[str]) -> None:
        """Update OWL text prompts (hot-reload without pipeline restart)."""
        self.owl_prompts = prompts
        logger.info(f"OWL prompts updated for {self.session_id}: {prompts}")
