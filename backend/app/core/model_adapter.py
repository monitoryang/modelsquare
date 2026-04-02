"""Unified model adapter layer for video/stream inference pipelines.

Provides a common interface (ModelAdapter) that encapsulates model-specific
inference logic (preprocessing, single-frame inference, batch inference,
result metadata) so that the video pipeline can be model-agnostic.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.models.model import NetworkType

logger = logging.getLogger(__name__)


class ModelAdapter(ABC):
    """Abstract base class for all inference model adapters.

    Subclasses encapsulate model-specific inference calls while exposing
    a uniform interface consumed by ``VideoInferenceService`` and
    ``StreamInferenceService``.
    """

    model_type: str  # "yolo" | "owl" | "detr" | "sam"
    default_conf_threshold: float
    default_iou_threshold: float
    supports_batch: bool = False
    render_mode: str = "boxes"  # "boxes" | "masks" | "boxes+masks"

    # ------------------------------------------------------------------ #
    # Abstract methods — must be implemented by every adapter
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def prepare(self) -> None:
        """One-time preparation before frame processing starts.

        For example, OWL encodes text prompts here.  YOLO is a no-op.
        """
        ...

    @abstractmethod
    async def infer_frame(
        self,
        image_bytes: bytes,
        conf_threshold: float,
        iou_threshold: float,
    ) -> Dict[str, Any]:
        """Run inference on a single frame.

        Returns the standardised result dict::

            {
                "boxes": [[x1, y1, x2, y2], ...],
                "scores": [float, ...],
                "labels": [int, ...],
                "class_names": [str, ...],
            }
        """
        ...

    # ------------------------------------------------------------------ #
    # Default implementations — override in subclasses when needed
    # ------------------------------------------------------------------ #

    def infer_frame_sync(
        self,
        image_bytes: bytes,
        conf_threshold: float,
        iou_threshold: float,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for use with ``asyncio.to_thread``.

        Creates a disposable event loop, runs :meth:`infer_frame`, and
        tears the loop down.  Subclasses generally do **not** need to
        override this.
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.infer_frame(image_bytes, conf_threshold, iou_threshold)
            )
        finally:
            loop.close()

    async def infer_batch(
        self,
        images_bytes_list: List[bytes],
        conf_threshold: float,
        iou_threshold: float,
    ) -> List[Dict[str, Any]]:
        """Batch inference.  Default falls back to sequential per-frame calls."""
        results = []
        for img in images_bytes_list:
            results.append(
                await self.infer_frame(img, conf_threshold, iou_threshold)
            )
        return results

    def extra_result_metadata(self) -> Dict[str, Any]:
        """Return model-specific fields to merge into ``result.json``."""
        return {}


# ====================================================================== #
# Concrete adapters
# ====================================================================== #


class YOLOModelAdapter(ModelAdapter):
    """Adapter for YOLO family models (YOLOv8, YOLO11, etc.)."""

    model_type = "yolo"
    default_conf_threshold = 0.25
    default_iou_threshold = 0.45
    supports_batch = True
    render_mode = "boxes"

    def __init__(
        self,
        triton_model_name: str,
        class_names: Optional[List[str]] = None,
    ):
        self.triton_model_name = triton_model_name
        self.class_names = class_names

    async def prepare(self) -> None:
        pass  # YOLO needs no preparation step

    async def infer_frame(
        self,
        image_bytes: bytes,
        conf_threshold: float,
        iou_threshold: float,
    ) -> Dict[str, Any]:
        from app.core.triton import yolo_inference_service

        return await yolo_inference_service.infer(
            model_name=self.triton_model_name,
            image_bytes=image_bytes,
            class_names=self.class_names,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )

    async def infer_batch(
        self,
        images_bytes_list: List[bytes],
        conf_threshold: float,
        iou_threshold: float,
    ) -> List[Dict[str, Any]]:
        from app.core.triton import yolo_inference_service

        return await yolo_inference_service.infer_batch(
            model_name=self.triton_model_name,
            images_bytes_list=images_bytes_list,
            class_names=self.class_names,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )


class OwlModelAdapter(ModelAdapter):
    """Adapter for OWLv2 open-vocabulary detection models."""

    model_type = "owl"
    default_conf_threshold = 0.1
    default_iou_threshold = 0.3
    supports_batch = False
    render_mode = "boxes"

    def __init__(
        self,
        text_prompts: List[str],
        owl_variant: str = "owlv2-base-patch16",
    ):
        self.text_prompts = text_prompts
        self.owl_variant = owl_variant
        self.text_embeds = None  # populated by prepare()

    async def prepare(self) -> None:
        from app.core.owl_inference import owl_inference_service

        self.text_embeds = await owl_inference_service.encode_text(
            self.text_prompts, variant=self.owl_variant,
        )
        logger.info(
            "OWL text prompts encoded: %d prompts, variant=%s",
            len(self.text_prompts),
            self.owl_variant,
        )

    async def infer_frame(
        self,
        image_bytes: bytes,
        conf_threshold: float,
        iou_threshold: float,
    ) -> Dict[str, Any]:
        from app.core.owl_inference import owl_inference_service

        return await owl_inference_service.infer_frame(
            image_bytes=image_bytes,
            text_prompts=self.text_prompts,
            text_embeds=self.text_embeds,
            variant=self.owl_variant,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )

    def update_prompts(
        self,
        text_prompts: List[str],
        text_embeds: Any,
        owl_variant: Optional[str] = None,
    ) -> None:
        """Atomically update prompts and pre-encoded embeddings."""
        self.text_prompts = text_prompts
        self.text_embeds = text_embeds
        if owl_variant:
            self.owl_variant = owl_variant

    def extra_result_metadata(self) -> Dict[str, Any]:
        return {
            "text_prompts": self.text_prompts,
            "owl_variant": self.owl_variant,
        }


# ====================================================================== #
# Factory
# ====================================================================== #


def create_adapter(
    network_type: NetworkType,
    *,
    triton_model_name: Optional[str] = None,
    class_names: Optional[List[str]] = None,
    text_prompts: Optional[List[str]] = None,
    owl_variant: Optional[str] = None,
) -> ModelAdapter:
    """Create the appropriate :class:`ModelAdapter` for *network_type*.

    When *text_prompts* is provided, an :class:`OwlModelAdapter` is
    returned regardless of *network_type* (OWL override via prompts).
    """
    if network_type == NetworkType.OWLv2 or text_prompts:
        if not text_prompts:
            raise ValueError(
                "OWLv2 adapter requires text_prompts but none were provided"
            )
        return OwlModelAdapter(
            text_prompts=text_prompts,
            owl_variant=owl_variant or "owlv2-base-patch16",
        )

    # Default: YOLO family (YOLOv8, YOLO11, future variants)
    if not triton_model_name:
        raise ValueError(
            "YOLO adapter requires triton_model_name but none was provided"
        )
    return YOLOModelAdapter(
        triton_model_name=triton_model_name,
        class_names=class_names,
    )
