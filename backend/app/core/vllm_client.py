"""vLLM OpenAI-Compatible Client for Vision-Language Model inference

This module handles communication with vLLM server for multimodal (image + text) inference,
specifically for grounding/detection tasks using Qwen-VL models.
"""

import base64
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

import httpx
from PIL import Image
import io

from app.core.config import settings


@dataclass
class BoundingBox:
    """Bounding box with label"""
    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    confidence: Optional[float] = None


@dataclass
class GroundingResult:
    """Grounding/detection result from VLM"""
    boxes: List[BoundingBox]
    raw_response: str
    image_width: int
    image_height: int


class VLLMClient:
    """Client for vLLM OpenAI-compatible API"""
    
    def __init__(self, base_url: str = None, model_name: str = None, timeout: int = None):
        self.base_url = base_url or settings.VLLM_URL
        self.model_name = model_name or settings.VLLM_MODEL_NAME
        self.timeout = timeout or settings.VLLM_TIMEOUT
        self._client = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0)
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    async def health_check(self) -> bool:
        """Check if vLLM server is healthy"""
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except Exception:
            return False
    
    async def get_models(self) -> List[str]:
        """Get available models from vLLM server"""
        try:
            response = await self.client.get("/v1/models")
            if response.status_code == 200:
                data = response.json()
                return [m["id"] for m in data.get("data", [])]
            return []
        except Exception:
            return []
    
    def _encode_image_to_base64(self, image_bytes: bytes) -> str:
        """Encode image bytes to base64 string"""
        return base64.b64encode(image_bytes).decode("utf-8")
    
    def _get_image_size(self, image_bytes: bytes) -> Tuple[int, int]:
        """Get image dimensions from bytes"""
        img = Image.open(io.BytesIO(image_bytes))
        return img.width, img.height
    
    def _parse_grounding_response(
        self, 
        response_text: str, 
        image_width: int, 
        image_height: int,
        normalize_coords: bool = True
    ) -> List[BoundingBox]:
        """
        Parse bounding boxes from VLM response.
        
        Qwen-VL outputs coordinates in 0-1000 normalized format.
        We convert them to pixel coordinates based on image dimensions.
        
        Expected formats:
        - JSON array: [{"bbox_2d": [x1, y1, x2, y2], "label": "cat"}, ...]
        - Inline format: <ref>cat</ref><box>(x1, y1), (x2, y2)</box>
        - Simple list: [[x1, y1, x2, y2, "label"], ...]
        """
        boxes = []
        
        # Try JSON format first
        try:
            # Find JSON array in response
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
                
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            # Format: {"bbox_2d": [x1, y1, x2, y2], "label": "..."}
                            bbox = item.get("bbox_2d") or item.get("bbox") or item.get("box")
                            label = item.get("label") or item.get("name") or "object"
                            confidence = item.get("confidence") or item.get("score")
                            
                            if bbox and len(bbox) >= 4:
                                x1, y1, x2, y2 = bbox[:4]
                                # Convert from 0-1000 to pixel coordinates
                                if normalize_coords:
                                    x1 = x1 * image_width / 1000
                                    y1 = y1 * image_height / 1000
                                    x2 = x2 * image_width / 1000
                                    y2 = y2 * image_height / 1000
                                
                                boxes.append(BoundingBox(
                                    x1=x1, y1=y1, x2=x2, y2=y2,
                                    label=label, confidence=confidence
                                ))
                        
                        elif isinstance(item, list) and len(item) >= 4:
                            # Format: [x1, y1, x2, y2, "label"]
                            x1, y1, x2, y2 = item[:4]
                            label = item[4] if len(item) > 4 else "object"
                            
                            if normalize_coords:
                                x1 = x1 * image_width / 1000
                                y1 = y1 * image_height / 1000
                                x2 = x2 * image_width / 1000
                                y2 = y2 * image_height / 1000
                            
                            boxes.append(BoundingBox(
                                x1=x1, y1=y1, x2=x2, y2=y2,
                                label=str(label)
                            ))
                
                if boxes:
                    return boxes
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Try Qwen-VL inline format: <ref>label</ref><box>(x1, y1), (x2, y2)</box>
        ref_box_pattern = r'<ref>([^<]+)</ref>\s*<box>\((\d+),\s*(\d+)\),\s*\((\d+),\s*(\d+)\)</box>'
        matches = re.findall(ref_box_pattern, response_text)
        for match in matches:
            label, x1, y1, x2, y2 = match
            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
            
            if normalize_coords:
                x1 = x1 * image_width / 1000
                y1 = y1 * image_height / 1000
                x2 = x2 * image_width / 1000
                y2 = y2 * image_height / 1000
            
            boxes.append(BoundingBox(
                x1=x1, y1=y1, x2=x2, y2=y2,
                label=label.strip()
            ))
        
        return boxes
    
    async def grounding_detection(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> GroundingResult:
        """
        Perform grounding detection on an image.
        
        Args:
            image_bytes: Image data as bytes
            prompt: Description of objects to detect (e.g., "person, car, dog")
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (lower = more deterministic)
        
        Returns:
            GroundingResult with detected bounding boxes
        """
        # Get image dimensions
        image_width, image_height = self._get_image_size(image_bytes)
        
        # Encode image to base64
        image_base64 = self._encode_image_to_base64(image_bytes)
        
        # Detect image format
        img = Image.open(io.BytesIO(image_bytes))
        img_format = img.format.lower() if img.format else "jpeg"
        media_type = f"image/{img_format}"
        
        # Build the grounding prompt
        system_prompt = """You are an expert object detection assistant. 
When asked to detect objects, output ONLY a JSON array of detected objects with their bounding boxes.
Each object should be in format: {"bbox_2d": [x1, y1, x2, y2], "label": "object_name"}
Coordinates should be in 0-1000 normalized format where (0,0) is top-left and (1000,1000) is bottom-right.
Do not include any explanation, just the JSON array."""

        user_prompt = f"""Detect all instances of the following objects in this image: {prompt}

Output the results as a JSON array. If no objects are found, output an empty array [].
Remember: coordinates must be in 0-1000 normalized format."""

        # Build OpenAI-compatible request
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": user_prompt
                    }
                ]
            }
        ]
        
        # Make API request
        response = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"vLLM API error: {response.status_code} - {response.text}")
        
        result = response.json()
        response_text = result["choices"][0]["message"]["content"]
        
        # Parse bounding boxes from response
        boxes = self._parse_grounding_response(response_text, image_width, image_height)
        
        return GroundingResult(
            boxes=boxes,
            raw_response=response_text,
            image_width=image_width,
            image_height=image_height
        )
    
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        image_bytes: Optional[bytes] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        General chat completion with optional image input.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            image_bytes: Optional image data for vision tasks
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            stream: Whether to stream the response
        
        Returns:
            Chat completion response dict
        """
        # If image is provided, inject it into the last user message
        if image_bytes and messages:
            image_base64 = self._encode_image_to_base64(image_bytes)
            img = Image.open(io.BytesIO(image_bytes))
            img_format = img.format.lower() if img.format else "jpeg"
            media_type = f"image/{img_format}"
            
            # Find the last user message and add image
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]["role"] == "user":
                    content = messages[i]["content"]
                    if isinstance(content, str):
                        messages[i]["content"] = [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{image_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": content
                            }
                        ]
                    break
        
        response = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": stream,
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"vLLM API error: {response.status_code} - {response.text}")
        
        return response.json()


# Global vLLM client instance
vllm_client = VLLMClient()
