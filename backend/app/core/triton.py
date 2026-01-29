"""Triton Inference Server client for YOLO models"""

import io
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from PIL import Image

import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException

from app.core.config import settings


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
    
    def preprocess(self, image_bytes: bytes) -> Tuple[np.ndarray, Tuple[int, int], Tuple[float, float]]:
        """
        Preprocess image for YOLO inference
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Tuple of (preprocessed_array, original_size, scale_factors)
        """
        # Load image
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        original_size = image.size  # (width, height)
        
        # Resize with letterbox
        img_resized, scale = self._letterbox(image, self.input_size)
        
        # Convert to numpy and normalize
        img_array = np.array(img_resized, dtype=np.float32)
        img_array = img_array / 255.0  # Normalize to [0, 1]
        
        # HWC -> CHW
        img_array = img_array.transpose(2, 0, 1)
        
        return img_array, original_size, scale
    
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
        
        return new_image, (scale, scale)


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
        Postprocess YOLO output
        
        Args:
            output: Raw model output [batch, 84, 8400] or [batch, num_detections, 6]
            original_size: Original image (width, height)
            scale: Scale factors used during preprocessing
            class_names: Optional list of class names
            
        Returns:
            Detection results with boxes, scores, labels
        """
        # Handle different output formats
        if len(output.shape) == 3:
            # YOLO11 format: [batch, 84, 8400] -> transpose to [batch, 8400, 84]
            if output.shape[1] < output.shape[2]:
                output = output.transpose(0, 2, 1)
            output = output[0]  # Remove batch dimension
        elif len(output.shape) == 2:
            pass  # Already [num_detections, features]
        
        # Extract boxes and class scores
        boxes = output[:, :4]  # x_center, y_center, width, height
        class_scores = output[:, 4:]
        
        # Get class predictions
        class_ids = np.argmax(class_scores, axis=1)
        confidences = np.max(class_scores, axis=1)
        
        # Filter by confidence
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
        
        # Convert xywh to xyxy
        boxes_xyxy = self._xywh_to_xyxy(boxes)
        
        # Apply NMS
        keep_indices = self._nms(boxes_xyxy, confidences, self.iou_threshold)
        
        boxes_xyxy = boxes_xyxy[keep_indices]
        class_ids = class_ids[keep_indices]
        confidences = confidences[keep_indices]
        
        # Scale boxes back to original image size
        boxes_scaled = self._scale_boxes(
            boxes_xyxy, 
            self.input_size, 
            original_size, 
            scale
        )
        
        # Prepare result
        result_class_names = []
        if class_names:
            result_class_names = [
                class_names[cid] if cid < len(class_names) else f"class_{cid}"
                for cid in class_ids
            ]
        
        return {
            "boxes": boxes_scaled.tolist(),
            "scores": confidences.tolist(),
            "labels": class_ids.tolist(),
            "class_names": result_class_names
        }
    
    def _xywh_to_xyxy(self, boxes: np.ndarray) -> np.ndarray:
        """Convert xywh format to xyxy format"""
        xyxy = np.zeros_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2  # x1
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2  # y1
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2  # x2
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2  # y2
        return xyxy
    
    def _scale_boxes(
        self,
        boxes: np.ndarray,
        input_size: Tuple[int, int],
        original_size: Tuple[int, int],
        scale: Tuple[float, float]
    ) -> np.ndarray:
        """Scale boxes from input size to original image size"""
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
        boxes_scaled[:, [0, 2]] = np.clip(boxes_scaled[:, [0, 2]], 0, ow)
        boxes_scaled[:, [1, 3]] = np.clip(boxes_scaled[:, [1, 3]], 0, oh)
        
        return boxes_scaled
    
    def _nms(
        self, 
        boxes: np.ndarray, 
        scores: np.ndarray, 
        iou_threshold: float
    ) -> List[int]:
        """Non-Maximum Suppression"""
        if len(boxes) == 0:
            return []
        
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            
            if order.size == 1:
                break
            
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            
            w = np.maximum(0, xx2 - xx1)
            h = np.maximum(0, yy2 - yy1)
            
            inter = w * h
            iou = inter / (areas[i] + areas[order[1:]] - inter)
            
            inds = np.where(iou <= iou_threshold)[0]
            order = order[inds + 1]
        
        return keep


class YOLOInferenceService:
    """Service for YOLO model inference via Triton"""
    
    def __init__(self):
        self.triton_client = TritonClient()
        self.preprocessor = YOLOPreprocessor()
        self.postprocessor = YOLOPostprocessor()
    
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
            Detection results
        """
        # Update postprocessor thresholds
        self.postprocessor.conf_threshold = conf_threshold
        self.postprocessor.iou_threshold = iou_threshold
        
        # Preprocess
        img_array, original_size, scale = self.preprocessor.preprocess(image_bytes)
        
        # Prepare input
        inputs = [
            grpcclient.InferInput("images", [1, 3, 640, 640], "FP32")
        ]
        inputs[0].set_data_from_numpy(img_array[np.newaxis, ...])
        
        # Prepare output
        outputs = [
            grpcclient.InferRequestedOutput("output0")
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
        output = response.as_numpy("output0")
        
        # Postprocess
        results = self.postprocessor.postprocess(
            output, original_size, scale, class_names
        )
        
        return results


# Singleton instance
yolo_inference_service = YOLOInferenceService()
