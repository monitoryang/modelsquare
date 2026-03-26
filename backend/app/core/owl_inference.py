"""OWL open-vocabulary detection inference service via Triton

Supports OWLv2 models (base-patch16 and large-patch14) for zero-shot
object detection with text prompts. Image encoder runs as TensorRT engine,
text encoder runs as ONNX on Triton.

Reference: /mnt/14TB/yangwen/project/6-sma/3rd/JoAIEngine/detector/Owl.cpp
"""

import hashlib
import io
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import tritonclient.grpc as grpcclient
from PIL import Image
from tritonclient.utils import InferenceServerException

from app.core.config import settings
from app.core.gpu_array import ensure_numpy, get_array_module, to_gpu, xp
from app.core.triton import TritonClient
from app.core.triton_repository import (
    OWL_MODEL_VARIANTS,
    OWL_TEXT_ENCODER_TRITON_NAME,
    triton_repository,
)

logger = logging.getLogger(__name__)

# ImageNet normalization constants (CLIP/OWL uses these)
IMAGENET_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
IMAGENET_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

# GPU versions for accelerated preprocessing
IMAGENET_MEAN_GPU = xp.array([0.48145466, 0.4578275, 0.40821073], dtype=xp.float32)
IMAGENET_STD_GPU = xp.array([0.26862954, 0.26130258, 0.27577711], dtype=xp.float32)

# Maximum cached text embeddings
MAX_TEXT_EMBED_CACHE = 100


class OwlInferenceService:
    """Service for OWLv2 open-vocabulary detection via Triton"""

    def __init__(self):
        self.triton_client = TritonClient()
        self._tokenizer = None
        self._text_embed_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._initialized = False

    async def initialize(self, variant: str = "owlv2-base-patch16") -> None:
        """
        Initialize the OWL service: deploy models to Triton and load tokenizer.

        Args:
            variant: Model variant to deploy
        """
        if self._initialized:
            return

        # Deploy OWL models to Triton
        result = await triton_repository.deploy_owl_models(variant=variant)
        if not result.get("success"):
            logger.warning(
                f"OWL model deployment incomplete: {result}. "
                "Models may need manual deployment."
            )

        # Load tokenizer
        self._init_tokenizer()
        self._initialized = True
        logger.info("OWL inference service initialized")

    def _init_tokenizer(self) -> None:
        """Load CLIPTokenizer from local tokenizer files"""
        try:
            from transformers import CLIPTokenizer

            self._tokenizer = CLIPTokenizer.from_pretrained(
                settings.OWL_TOKENIZER_PATH
            )
            logger.info(
                f"Loaded CLIPTokenizer from {settings.OWL_TOKENIZER_PATH}"
            )
        except Exception as e:
            logger.error(f"Failed to load CLIPTokenizer: {e}")
            raise

    # ---- Text Processing ----

    def tokenize(self, texts: List[str]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Tokenize text prompts using CLIPTokenizer.

        Args:
            texts: List of text prompts, e.g. ["person", "car", "dog"]

        Returns:
            Tuple of (input_ids [N, max_len], attention_mask [N, max_len]) as int64
        """
        if self._tokenizer is None:
            self._init_tokenizer()

        encoding = self._tokenizer(
            texts,
            padding="max_length",
            max_length=settings.OWL_MAX_TEXT_LENGTH,
            truncation=True,
            return_tensors="np",
        )

        input_ids = encoding["input_ids"].astype(np.int64)
        attention_mask = encoding["attention_mask"].astype(np.int64)
        return input_ids, attention_mask

    def _cache_key(self, texts: List[str], variant: str = "") -> str:
        """Generate a cache key for a list of text prompts and variant"""
        joined = "|".join(sorted(texts)) + "||" + variant
        return hashlib.md5(joined.encode()).hexdigest()

    async def encode_text(
        self, texts: List[str], variant: str = "owlv2-base-patch16"
    ) -> np.ndarray:
        """
        Encode text prompts via Triton text encoder, with LRU caching.

        Args:
            texts: List of text prompts
            variant: Model variant key, determines which text encoder to use

        Returns:
            text_embeds: np.ndarray [N, D] where D is embedding dimension
        """
        cache_key = self._cache_key(texts, variant)

        # Check cache
        if cache_key in self._text_embed_cache:
            self._text_embed_cache.move_to_end(cache_key)
            return self._text_embed_cache[cache_key]

        # Tokenize
        input_ids, attention_mask = self.tokenize(texts)

        # Use variant-specific text encoder
        variant_config = OWL_MODEL_VARIANTS.get(variant)
        if variant_config and "text_encoder_triton_name" in variant_config:
            model_name = variant_config["text_encoder_triton_name"]
        else:
            model_name = OWL_TEXT_ENCODER_TRITON_NAME
        batch_size, seq_len = input_ids.shape

        inputs = [
            grpcclient.InferInput("input_ids", [batch_size, seq_len], "INT64"),
            grpcclient.InferInput(
                "attention_mask", [batch_size, seq_len], "INT64"
            ),
        ]
        inputs[0].set_data_from_numpy(input_ids)
        inputs[1].set_data_from_numpy(attention_mask)

        outputs = [grpcclient.InferRequestedOutput("text_embeds")]

        try:
            response = self.triton_client.client.infer(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs,
            )
        except InferenceServerException as e:
            raise RuntimeError(f"OWL text encoding failed: {e}")

        text_embeds = response.as_numpy("text_embeds")

        # Store in LRU cache
        self._text_embed_cache[cache_key] = text_embeds
        if len(self._text_embed_cache) > MAX_TEXT_EMBED_CACHE:
            self._text_embed_cache.popitem(last=False)

        return text_embeds

    # ---- Image Processing ----

    def preprocess_image(
        self, image_bytes: bytes, image_size: int = 960
    ) -> Tuple[np.ndarray, Tuple[int, int]]:
        """
        Preprocess image for OWL inference.

        Unlike YOLO letterbox, OWL uses direct resize + ImageNet normalization.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG)
            image_size: Target size (square), e.g. 960 or 1008

        Returns:
            Tuple of (pixel_values [1, 3, H, W], original_size (w, h))
        """
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != "RGB":
            image = image.convert("RGB")

        original_size = image.size  # (width, height)

        # Direct resize to square (no letterbox)
        image_resized = image.resize((image_size, image_size), Image.BILINEAR)
        image.close()

        # Convert to float32 and normalize (GPU-accelerated)
        img_array = xp.array(
            np.array(image_resized, dtype=np.float32)
        ) / 255.0
        image_resized.close()

        # ImageNet normalization (GPU)
        img_array = (img_array - IMAGENET_MEAN_GPU) / IMAGENET_STD_GPU

        # HWC -> CHW, add batch dimension (GPU)
        img_array = img_array.transpose(2, 0, 1)
        pixel_values = img_array[xp.newaxis, ...]  # [1, 3, H, W]

        return ensure_numpy(pixel_values), original_size

    async def encode_image(
        self, pixel_values: np.ndarray, variant: str = "owlv2-base-patch16"
    ) -> Dict[str, np.ndarray]:
        """
        Encode image via Triton image encoder.

        Args:
            pixel_values: Preprocessed image [1, 3, H, W] float32
            variant: Model variant key

        Returns:
            Dict with keys: image_embeds, image_class_embeds, logit_shift,
                           logit_scale, pred_boxes
        """
        variant_config = OWL_MODEL_VARIANTS.get(variant)
        if not variant_config:
            raise ValueError(f"Unknown OWL variant: {variant}")

        model_name = variant_config["image_encoder_triton_name"]

        # Prepare input
        inputs = [
            grpcclient.InferInput(
                "image", list(pixel_values.shape), "FP32"
            )
        ]
        inputs[0].set_data_from_numpy(pixel_values)

        # Request all outputs
        output_names = [
            "image_embeds",
            "image_class_embeds",
            "logit_shift",
            "logit_scale",
            "pred_boxes",
        ]
        outputs = [
            grpcclient.InferRequestedOutput(name) for name in output_names
        ]

        try:
            response = self.triton_client.client.infer(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs,
            )
        except InferenceServerException as e:
            raise RuntimeError(f"OWL image encoding failed: {e}")

        return {name: response.as_numpy(name) for name in output_names}

    # ---- Decode (GPU-accelerated, reference: Owl.cpp decode()) ----

    def decode(
        self,
        image_outputs: Dict[str, np.ndarray],
        text_embeds: np.ndarray,
        original_size: Tuple[int, int],
        conf_threshold: float = 0.1,
        nms_threshold: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Decode OWL outputs into detection results.

        Uses CuPy (GPU) when available for L2 norm, matmul, sigmoid, and NMS.
        Falls back to NumPy transparently.

        Args:
            image_outputs: Dict from encode_image()
            text_embeds: Text embeddings [N_classes, D]
            original_size: Original image (width, height)
            conf_threshold: Confidence threshold
            nms_threshold: NMS IoU threshold

        Returns:
            Dict with boxes, scores, labels, class_names
        """
        # Transfer to GPU for accelerated decode
        image_class_embeds = to_gpu(image_outputs["image_class_embeds"])  # [1, P, 512]
        logit_shift = to_gpu(image_outputs["logit_shift"])  # [1, P, 1]
        logit_scale = to_gpu(image_outputs["logit_scale"])  # [1, P, 1]
        pred_boxes = to_gpu(image_outputs["pred_boxes"])  # [1, P, 4]
        text_embeds_g = to_gpu(text_embeds)

        # Remove batch dimension
        image_class_embeds = image_class_embeds[0]  # [P, 512]
        logit_shift = logit_shift[0]  # [P, 1]
        logit_scale = logit_scale[0]  # [P, 1]
        pred_boxes = pred_boxes[0]  # [P, 4]

        # Ensure text_embeds is 2D
        if text_embeds_g.ndim == 3:
            text_embeds_g = text_embeds_g[0]  # [N_classes, D]

        # L2 normalize (GPU: cuBLAS-backed linalg.norm)
        image_class_embeds = image_class_embeds / (
            xp.linalg.norm(image_class_embeds, axis=-1, keepdims=True) + 1e-6
        )
        text_embeds_norm = text_embeds_g / (
            xp.linalg.norm(text_embeds_g, axis=-1, keepdims=True) + 1e-6
        )

        # Cosine similarity: [P, N_classes] (GPU: cuBLAS matmul)
        logits = image_class_embeds @ text_embeds_norm.T

        # Apply logit shift and scale
        logits = (logits + logit_shift) * logit_scale

        # Sigmoid activation (GPU)
        scores = 1.0 / (1.0 + xp.exp(-logits))  # [P, N_classes]

        # Get max score and label per patch (GPU)
        max_scores = scores.max(axis=-1)  # [P]
        max_labels = scores.argmax(axis=-1)  # [P]

        # Threshold filtering (GPU)
        mask = (max_scores >= conf_threshold) & (max_scores < 0.999)
        filtered_scores = max_scores[mask]
        filtered_labels = max_labels[mask]
        filtered_boxes = pred_boxes[mask]  # [K, 4]

        if len(filtered_scores) == 0:
            return {
                "boxes": [],
                "scores": [],
                "labels": [],
                "class_names": [],
            }

        # pred_boxes is already in (x1, y1, x2, y2) from the ONNX model
        boxes_xyxy = filtered_boxes.copy()

        # Scale from normalized [0,1] to original pixel coordinates (GPU)
        orig_w, orig_h = original_size
        boxes_xyxy[:, [0, 2]] *= orig_w
        boxes_xyxy[:, [1, 3]] *= orig_h

        # Clip to image bounds (GPU)
        boxes_xyxy[:, [0, 2]] = xp.clip(boxes_xyxy[:, [0, 2]], 0, orig_w)
        boxes_xyxy[:, [1, 3]] = xp.clip(boxes_xyxy[:, [1, 3]], 0, orig_h)

        # Per-class NMS (GPU-accelerated vectorized ops within each iteration)
        keep = self._per_class_nms(
            boxes_xyxy, filtered_scores, filtered_labels, nms_threshold
        )
        boxes_xyxy = boxes_xyxy[keep]
        filtered_scores = filtered_scores[keep]
        filtered_labels = filtered_labels[keep]

        # Transfer back to CPU only for JSON serialization
        return {
            "boxes": ensure_numpy(boxes_xyxy).tolist(),
            "scores": ensure_numpy(filtered_scores).tolist(),
            "labels": ensure_numpy(filtered_labels).tolist(),
            "class_names": [],  # Filled by caller with text_prompts
        }

    @staticmethod
    def _center_to_corners(boxes):
        """Convert (cx, cy, w, h) to (x1, y1, x2, y2)"""
        ap = get_array_module(boxes)
        xyxy = ap.zeros_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2  # x1
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2  # y1
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2  # x2
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2  # y2
        return xyxy

    @staticmethod
    def _nms_inner(boxes, scores, iou_threshold: float) -> List[int]:
        """Containment-based suppression that keeps inner (smaller) boxes.

        For each pair of overlapping boxes, if the intersection covers a
        significant fraction of the smaller box (containment ratio >
        iou_threshold), suppress the larger one and keep the smaller one.

        Supports both NumPy and CuPy arrays (GPU-accelerated vectorized ops).
        """
        if len(boxes) == 0:
            return []

        ap = get_array_module(boxes)

        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]

        areas = (x2 - x1) * (y2 - y1)
        # Sort by area ascending – process smallest boxes first
        order = areas.argsort()

        keep: List[int] = []
        while order.size > 0:
            i = order[0]
            keep.append(int(i))

            if order.size == 1:
                break

            xx1 = ap.maximum(x1[i], x1[order[1:]])
            yy1 = ap.maximum(y1[i], y1[order[1:]])
            xx2 = ap.minimum(x2[i], x2[order[1:]])
            yy2 = ap.minimum(y2[i], y2[order[1:]])

            w = ap.maximum(0, xx2 - xx1)
            h = ap.maximum(0, yy2 - yy1)
            inter = w * h

            min_area = ap.minimum(areas[i], areas[order[1:]]) + 1e-6
            containment = inter / min_area

            inds = ap.where(containment <= iou_threshold)[0]
            order = order[inds + 1]

        return keep

    @staticmethod
    def _per_class_nms(boxes, scores, labels, iou_threshold: float) -> List[int]:
        """Run NMS independently per class, preferring inner boxes.

        Supports both NumPy and CuPy arrays.
        """
        if len(boxes) == 0:
            return []

        ap = get_array_module(boxes)

        keep: List[int] = []
        for cls_id in ap.unique(labels):
            cls_mask = labels == cls_id
            cls_indices = ap.where(cls_mask)[0]

            cls_keep = OwlInferenceService._nms_inner(
                boxes[cls_indices], scores[cls_indices], iou_threshold
            )
            keep.extend(int(cls_indices[k]) for k in cls_keep)

        # Sort by score descending for consistent output ordering
        keep.sort(key=lambda idx: -float(scores[idx]))
        return keep

    # ---- Inference Entry Points ----

    async def infer(
        self,
        image_bytes: bytes,
        text_prompts: List[str],
        variant: str = "owlv2-base-patch16",
        conf_threshold: float = 0.1,
        iou_threshold: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Full OWL inference pipeline: text encoding + image encoding + decode.

        Args:
            image_bytes: Raw image bytes
            text_prompts: Detection target texts, e.g. ["person", "car"]
            variant: Model variant key
            conf_threshold: Confidence threshold
            iou_threshold: NMS IoU threshold

        Returns:
            Detection results dict
        """
        variant_config = OWL_MODEL_VARIANTS.get(variant)
        if not variant_config:
            raise ValueError(f"Unknown OWL variant: {variant}")

        image_size = variant_config["image_size"]

        # Encode text (with caching, using variant-specific text encoder)
        text_embeds = await self.encode_text(text_prompts, variant)

        # Preprocess and encode image
        pixel_values, original_size = self.preprocess_image(
            image_bytes, image_size
        )
        image_outputs = await self.encode_image(pixel_values, variant)
        del pixel_values  # free ~10MB array immediately

        # Decode
        result = self.decode(
            image_outputs, text_embeds, original_size, conf_threshold, iou_threshold
        )
        del image_outputs  # free encoder output arrays

        # Fill class names from text_prompts
        result["class_names"] = [
            text_prompts[label] if label < len(text_prompts) else f"class_{label}"
            for label in result["labels"]
        ]

        # Add metadata
        result["image_size"] = {
            "width": original_size[0],
            "height": original_size[1],
        }

        return result

    async def infer_frame(
        self,
        image_bytes: bytes,
        text_prompts: List[str],
        text_embeds: np.ndarray,
        variant: str = "owlv2-base-patch16",
        conf_threshold: float = 0.1,
        iou_threshold: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Frame inference with pre-encoded text embeddings.

        Used for video/stream inference where text_embeds is encoded once
        and reused across all frames.

        Args:
            image_bytes: Raw image bytes
            text_prompts: Original text prompts (for class name mapping)
            text_embeds: Pre-encoded text embeddings
            variant: Model variant key
            conf_threshold: Confidence threshold
            iou_threshold: NMS IoU threshold

        Returns:
            Detection results dict
        """
        variant_config = OWL_MODEL_VARIANTS.get(variant)
        if not variant_config:
            raise ValueError(f"Unknown OWL variant: {variant}")

        image_size = variant_config["image_size"]

        # Preprocess and encode image
        pixel_values, original_size = self.preprocess_image(
            image_bytes, image_size
        )
        image_outputs = await self.encode_image(pixel_values, variant)
        del pixel_values  # free ~10MB array immediately

        # Decode with pre-encoded text
        result = self.decode(
            image_outputs, text_embeds, original_size, conf_threshold, iou_threshold
        )
        del image_outputs  # free encoder output arrays

        # Fill class names
        result["class_names"] = [
            text_prompts[label] if label < len(text_prompts) else f"class_{label}"
            for label in result["labels"]
        ]

        result["image_size"] = {
            "width": original_size[0],
            "height": original_size[1],
        }

        return result


# Singleton instance
owl_inference_service = OwlInferenceService()
