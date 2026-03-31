"""Triton Inference Server client for YOLO models

Supports both single-image and batch inference for video processing pipelines.
"""

import io
import logging
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from PIL import Image

import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException

from app.core.config import settings
from app.core.gpu_array import ensure_numpy, get_array_module, to_gpu, xp

logger = logging.getLogger(__name__)


class TritonClient:
    """Client for communicating with Triton Inference Server"""
    
    def __init__(self, url: str = None):
        self.url = url or settings.TRITON_URL
        self._client = None
    
    @property
    def client(self) -> grpcclient.InferenceServerClient:
        """Get or create Triton client"""
        if self._client is None:
            self._client = grpcclient.InferenceServerClient(
                url=self.url,
                verbose=False,
            )
        return self._client
    
    def is_server_live(self) -> bool:
        """Check if Triton server is live"""
        try:
            return self.client.is_server_live()
        except InferenceServerException:
            return False
    
    def is_server_ready(self) -> bool:
        """Check if Triton server is ready"""
        try:
            return self.client.is_server_ready()
        except InferenceServerException:
            return False
    
    def is_model_ready(self, model_name: str) -> bool:
        """Check if a specific model is ready"""
        try:
            return self.client.is_model_ready(model_name)
        except InferenceServerException:
            return False
    
    def get_model_metadata(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get model metadata"""
        try:
            metadata = self.client.get_model_metadata(model_name)
            return {
                "name": metadata.name,
                "versions": metadata.versions,
                "inputs": [
                    {"name": inp.name, "datatype": inp.datatype, "shape": list(inp.shape)}
                    for inp in metadata.inputs
                ],
                "outputs": [
                    {"name": out.name, "datatype": out.datatype, "shape": list(out.shape)}
                    for out in metadata.outputs
                ],
            }
        except InferenceServerException:
            return None


class YOLOPreprocessor:
    """Preprocessor for YOLO models"""
    
    def __init__(self, input_size: Tuple[int, int] = (640, 640)):
        self.input_size = input_size
    
    def preprocess(self, image_bytes: bytes, input_size: Tuple[int, int] = None) -> Tuple[np.ndarray, Tuple[int, int], Tuple[float, float]]:
        """
        Preprocess image for YOLO inference
        
        Args:
            image_bytes: Raw image bytes
            input_size: Override input size (height, width)
            
        Returns:
            Tuple of (preprocessed_array, original_size, scale_factors)
        """
        target_size = input_size or self.input_size
        
        # Load image
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        original_size = image.size  # (width, height)
        
        # Resize with letterbox - target_size is (height, width), convert to (width, height)
        target_wh = (target_size[1], target_size[0])
        img_resized, scale = self._letterbox(image, target_wh)
        image.close()
        
        # Convert to float32 and normalize (GPU-accelerated)
        img_array = xp.array(
            np.array(img_resized, dtype=np.float32)
        ) / 255.0
        img_resized.close()
        
        # HWC -> CHW (GPU)
        img_array = img_array.transpose(2, 0, 1)
        
        return ensure_numpy(img_array), original_size, scale
    
    def _letterbox(
        self, 
        image: Image.Image, 
        target_size: Tuple[int, int],
        color: Tuple[int, int, int] = (114, 114, 114)
    ) -> Tuple[Image.Image, Tuple[float, float]]:
        """
        Resize image with letterbox padding
        
        Args:
            image: PIL Image
            target_size: Target (width, height)
            color: Padding color
            
        Returns:
            Tuple of (resized_image, scale_factors)
        """
        iw, ih = image.size
        tw, th = target_size
        
        # Calculate scale
        scale = min(tw / iw, th / ih)
        nw = int(iw * scale)
        nh = int(ih * scale)
        
        # Resize image
        image_resized = image.resize((nw, nh), Image.BILINEAR)
        
        # Create padded image
        new_image = Image.new('RGB', target_size, color)
        
        # Paste resized image at center
        paste_x = (tw - nw) // 2
        paste_y = (th - nh) // 2
        new_image.paste(image_resized, (paste_x, paste_y))
        image_resized.close()
        
        return new_image, (scale, scale)

    def preprocess_batch(
        self,
        images_bytes_list: List[bytes],
        input_size: Tuple[int, int] = None,
    ) -> Tuple[np.ndarray, List[Tuple[int, int]], List[Tuple[float, float]]]:
        """Batch preprocess: N images -> [N, C, H, W] tensor

        Args:
            images_bytes_list: List of raw image bytes
            input_size: Override input size (height, width)

        Returns:
            Tuple of (batch_array [N,C,H,W], original_sizes, scale_factors)
        """
        arrays: List[np.ndarray] = []
        original_sizes: List[Tuple[int, int]] = []
        scales: List[Tuple[float, float]] = []
        for img_bytes in images_bytes_list:
            arr, orig_size, scale = self.preprocess(img_bytes, input_size)
            arrays.append(arr)
            original_sizes.append(orig_size)
            scales.append(scale)
        batch_array = np.stack(arrays, axis=0)  # [N, C, H, W]
        return batch_array, original_sizes, scales


class YOLOPostprocessor:
    """Postprocessor for YOLO detection models"""
    
    def __init__(
        self, 
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        input_size: Tuple[int, int] = (640, 640)
    ):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.input_size = input_size
    
    def postprocess(
        self,
        output: np.ndarray,
        original_size: Tuple[int, int],
        scale: Tuple[float, float],
        class_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Postprocess YOLO output (GPU-accelerated when CuPy available)
        
        Args:
            output: Raw model output [batch, 84, 8400] or [batch, num_detections, 6]
            original_size: Original image (width, height)
            scale: Scale factors used during preprocessing
            class_names: Optional list of class names
            
        Returns:
            Detection results with boxes, scores, labels
        """
        # Transfer to GPU for accelerated postprocessing
        output = to_gpu(output)
        
        # Handle different output formats
        if len(output.shape) == 3:
            # YOLO11 format: [batch, 84, 8400] -> transpose to [batch, 8400, 84]
            if output.shape[1] < output.shape[2]:
                output = output.transpose(0, 2, 1)
            output = output[0]  # Remove batch dimension
        elif len(output.shape) == 2:
            pass  # Already [num_detections, features]
        
        # Extract boxes and class scores (GPU)
        boxes = output[:, :4]  # x_center, y_center, width, height
        class_scores = output[:, 4:]
        
        # Get class predictions (GPU)
        class_ids = xp.argmax(class_scores, axis=1)
        confidences = xp.max(class_scores, axis=1)
        
        # Filter by confidence (GPU)
        mask = confidences > self.conf_threshold
        boxes = boxes[mask]
        class_ids = class_ids[mask]
        confidences = confidences[mask]
        
        if len(boxes) == 0:
            return {
                "boxes": [],
                "scores": [],
                "labels": [],
                "class_names": []
            }
        
        # Convert xywh to xyxy (GPU)
        boxes_xyxy = self._xywh_to_xyxy(boxes)
        
        # Apply NMS (GPU-accelerated vectorized ops)
        keep_indices = self._nms(boxes_xyxy, confidences, self.iou_threshold)
        
        boxes_xyxy = boxes_xyxy[keep_indices]
        class_ids = class_ids[keep_indices]
        confidences = confidences[keep_indices]
        
        # Scale boxes back to original image size (GPU)
        boxes_scaled = self._scale_boxes(
            boxes_xyxy, 
            self.input_size, 
            original_size, 
            scale
        )
        
        # Transfer back to CPU for JSON serialization
        boxes_cpu = ensure_numpy(boxes_scaled)
        class_ids_cpu = ensure_numpy(class_ids)
        confidences_cpu = ensure_numpy(confidences)
        
        # Prepare result
        result_class_names = []
        if class_names:
            result_class_names = [
                class_names[cid] if cid < len(class_names) else f"class_{cid}"
                for cid in class_ids_cpu
            ]
        
        return {
            "boxes": boxes_cpu.tolist(),
            "scores": confidences_cpu.tolist(),
            "labels": class_ids_cpu.tolist(),
            "class_names": result_class_names
        }
    
    def _xywh_to_xyxy(self, boxes):
        """Convert xywh format to xyxy format (supports CuPy/NumPy)"""
        ap = get_array_module(boxes)
        xyxy = ap.zeros_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2  # x1
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2  # y1
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2  # x2
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2  # y2
        return xyxy
    
    def _scale_boxes(
        self,
        boxes,
        input_size: Tuple[int, int],
        original_size: Tuple[int, int],
        scale: Tuple[float, float]
    ):
        """Scale boxes from input size to original image size (supports CuPy/NumPy)"""
        ap = get_array_module(boxes)
        iw, ih = input_size
        ow, oh = original_size
        
        # Calculate padding
        scale_factor = scale[0]
        nw = int(ow * scale_factor)
        nh = int(oh * scale_factor)
        pad_x = (iw - nw) // 2
        pad_y = (ih - nh) // 2
        
        # Remove padding and rescale
        boxes_scaled = boxes.copy()
        boxes_scaled[:, [0, 2]] -= pad_x
        boxes_scaled[:, [1, 3]] -= pad_y
        boxes_scaled[:, [0, 2]] /= scale_factor
        boxes_scaled[:, [1, 3]] /= scale_factor
        
        # Clip to image bounds
        boxes_scaled[:, [0, 2]] = ap.clip(boxes_scaled[:, [0, 2]], 0, ow)
        boxes_scaled[:, [1, 3]] = ap.clip(boxes_scaled[:, [1, 3]], 0, oh)
        
        return boxes_scaled
    
    def _nms(self, boxes, scores, iou_threshold: float) -> List[int]:
        """Non-Maximum Suppression (supports CuPy/NumPy)"""
        if len(boxes) == 0:
            return []
        
        ap = get_array_module(boxes)
        
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        
        keep = []
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
            iou = inter / (areas[i] + areas[order[1:]] - inter)
            
            inds = ap.where(iou <= iou_threshold)[0]
            order = order[inds + 1]
        
        return keep


class YOLOInferenceService:
    """Service for running YOLO inference via Triton"""
    
    def __init__(self):
        self.triton_client = TritonClient()
        self.preprocessor = YOLOPreprocessor()
        self.postprocessor = YOLOPostprocessor()
        self._model_metadata_cache: Dict[str, Dict[str, Any]] = {}
    
    def _get_model_metadata(self, model_name: str) -> Dict[str, Any]:
        """Get model metadata with caching"""
        if model_name not in self._model_metadata_cache:
            metadata = self.triton_client.get_model_metadata(model_name)
            if metadata:
                self._model_metadata_cache[model_name] = metadata
            else:
                raise RuntimeError(f"Failed to get metadata for model {model_name}")
        return self._model_metadata_cache[model_name]
    
    async def infer(
        self,
        model_name: str,
        image_bytes: bytes,
        class_names: Optional[List[str]] = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45
    ) -> Dict[str, Any]:
        """
        Run YOLO inference on an image
        
        Args:
            model_name: Name of the model in Triton
            image_bytes: Raw image bytes
            class_names: Optional list of class names
            conf_threshold: Confidence threshold
            iou_threshold: IoU threshold for NMS
            
        Returns:
            Detection results with metadata
        """
        # Get model metadata to determine input shape
        metadata = self._get_model_metadata(model_name)
        
        # Extract input info
        input_info = metadata["inputs"][0]
        input_name = input_info["name"]
        input_shape = input_info["shape"]  # e.g., [1, 3, 384, 640]
        input_dtype = input_info["datatype"]  # e.g., "FP32"
        
        # Determine input size (height, width) from shape [batch, channels, height, width]
        input_height = input_shape[2]
        input_width = input_shape[3]
        input_size = (input_height, input_width)
        
        # Update postprocessor thresholds and input size
        self.postprocessor.conf_threshold = conf_threshold
        self.postprocessor.iou_threshold = iou_threshold
        self.postprocessor.input_size = (input_width, input_height)  # (width, height)
        
        # Preprocess with dynamic input size
        img_array, original_size, scale = self.preprocessor.preprocess(image_bytes, input_size)
        
        # Prepare input with dynamic shape
        inputs = [
            grpcclient.InferInput(input_name, input_shape, input_dtype)
        ]
        inputs[0].set_data_from_numpy(img_array[np.newaxis, ...])
        
        # Get output info
        output_info = metadata["outputs"][0]
        output_name = output_info["name"]
        
        # Prepare output
        outputs = [
            grpcclient.InferRequestedOutput(output_name)
        ]
        
        # Run inference
        try:
            response = self.triton_client.client.infer(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs
            )
        except InferenceServerException as e:
            raise RuntimeError(f"Triton inference failed: {e}")
        
        # Get output
        output = response.as_numpy(output_name)
        
        # Postprocess
        results = self.postprocessor.postprocess(
            output, original_size, scale, class_names
        )
        
        # Add metadata to results
        results["image_size"] = {
            "width": original_size[0],
            "height": original_size[1]
        }
        results["input_size"] = {
            "width": input_width,
            "height": input_height
        }
        
        return results

    async def infer_batch(
        self,
        model_name: str,
        images_bytes_list: List[bytes],
        class_names: Optional[List[str]] = None,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
    ) -> List[Dict[str, Any]]:
        """Run YOLO batch inference: N images in a single Triton request.

        Uses client-side batching — stacks N preprocessed images into a
        [N, C, H, W] tensor and sends as one gRPC call.  Falls back to
        smaller batches on GPU OOM (RESOURCE_EXHAUSTED).

        Args:
            model_name: Name of the model in Triton
            images_bytes_list: List of raw image bytes (JPEG/PNG)
            class_names: Optional list of class names
            conf_threshold: Confidence threshold
            iou_threshold: IoU threshold for NMS

        Returns:
            List of detection result dicts, one per input image
        """
        if not images_bytes_list:
            return []

        # Single image — delegate to existing path
        if len(images_bytes_list) == 1:
            result = await self.infer(
                model_name, images_bytes_list[0],
                class_names, conf_threshold, iou_threshold,
            )
            return [result]

        metadata = self._get_model_metadata(model_name)
        input_info = metadata["inputs"][0]
        input_shape = input_info["shape"]  # [1, 3, H, W]
        input_dtype = input_info["datatype"]
        input_height, input_width = input_shape[2], input_shape[3]
        input_size = (input_height, input_width)

        output_info = metadata["outputs"][0]
        output_name = output_info["name"]

        # Batch preprocess
        batch_array, original_sizes, scales = self.preprocessor.preprocess_batch(
            images_bytes_list, input_size,
        )
        N = len(images_bytes_list)

        all_results: List[Optional[Dict[str, Any]]] = [None] * N

        # Check if model supports dynamic batching (input_shape[0] == -1 or > 1)
        # If input_shape[0] == 1, the model only accepts one image per request
        max_model_batch = input_shape[0]  # -1 means dynamic, 1 means fixed single
        supports_batching = max_model_batch != 1

        if not supports_batching:
            logger.info(
                "[BatchInfer] Model %s has fixed batch=1, using sequential per-image inference for %d images",
                model_name, N,
            )

        # Determine effective max batch size per request
        current_batch_size = N if supports_batching else 1

        start = 0
        while start < N:
            end = min(start + current_batch_size, N)
            sub_batch = batch_array[start:end]
            sub_n = end - start

            # Shape: [sub_n, C, H, W] — or [1, C, H, W] when model doesn't support batching
            batch_shape = [sub_n, input_shape[1], input_shape[2], input_shape[3]]
            inputs = [grpcclient.InferInput(input_info["name"], batch_shape, input_dtype)]
            inputs[0].set_data_from_numpy(sub_batch)
            outputs = [grpcclient.InferRequestedOutput(output_name)]

            try:
                response = self.triton_client.client.infer(
                    model_name=model_name,
                    inputs=inputs,
                    outputs=outputs,
                )
            except InferenceServerException as e:
                err_msg = str(e).lower()
                if ("resource_exhausted" in err_msg or "out of memory" in err_msg) and current_batch_size > 1:
                    current_batch_size = max(1, current_batch_size // 2)
                    logger.warning(
                        "[BatchInfer] OOM at batch_size=%d, retrying with batch_size=%d",
                        sub_n, current_batch_size,
                    )
                    continue  # retry from same `start`
                if "invalid_argument" in err_msg and "unexpected shape" in err_msg and current_batch_size > 1:
                    # Model doesn't support the batch size we tried — fall back to 1
                    current_batch_size = 1
                    logger.warning(
                        "[BatchInfer] Shape mismatch at batch_size=%d, falling back to batch_size=1",
                        sub_n,
                    )
                    continue  # retry from same `start`
                raise RuntimeError(f"Triton batch inference failed: {e}")

            output_tensor = response.as_numpy(output_name)  # [sub_n, ...]

            # Per-image postprocessing
            for i in range(sub_n):
                postprocessor = YOLOPostprocessor(
                    conf_threshold=conf_threshold,
                    iou_threshold=iou_threshold,
                    input_size=(input_width, input_height),
                )
                result = postprocessor.postprocess(
                    output_tensor[i:i + 1],
                    original_sizes[start + i],
                    scales[start + i],
                    class_names,
                )
                result["image_size"] = {
                    "width": original_sizes[start + i][0],
                    "height": original_sizes[start + i][1],
                }
                result["input_size"] = {
                    "width": input_width,
                    "height": input_height,
                }
                all_results[start + i] = result

            start = end

        return all_results


# Singleton instance
yolo_inference_service = YOLOInferenceService()
