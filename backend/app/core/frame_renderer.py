"""Unified frame rendering for video inference pipelines.

Extracts the detection-drawing logic that was previously duplicated in
``VideoInferenceService.draw_detections_on_frame`` (file-based) and
``VideoInferenceService._draw_detections_on_array`` (array-based) into a
single reusable ``FrameRenderer`` class.

Supports multiple render modes:
- ``"boxes"``        — bounding boxes with labels (YOLO, OWL, DETR)
- ``"masks"``        — semi-transparent segmentation masks (SAM)
- ``"boxes+masks"``  — both overlays combined
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Font search paths — tried in order, first hit wins
_FONT_PATHS = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


class FrameRenderer:
    """Draw detection results (boxes, labels, masks) onto frames.

    Instantiate once and reuse across frames — the font is loaded only
    during ``__init__``.
    """

    def __init__(self, font_size: int = 14, line_width: int = 2):
        self.font_size = font_size
        self.line_width = line_width
        self.font: ImageFont.FreeTypeFont = self._load_font(font_size)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def render(
        self,
        image: Union[Image.Image, np.ndarray],
        detection_result: Dict[str, Any],
        class_colors: Optional[Dict[str, str]] = None,
        render_mode: str = "boxes",
    ) -> Union[Image.Image, np.ndarray]:
        """Draw detections onto *image* and return the same type.

        Parameters
        ----------
        image:
            RGB PIL Image **or** ``(H, W, 3)`` uint8 numpy array.
        detection_result:
            Standard result dict with keys ``boxes``, ``scores``,
            ``class_names``, and optionally ``masks``.
        class_colors:
            ``{class_name: "#RRGGBB"}`` colour map.
        render_mode:
            One of ``"boxes"``, ``"masks"``, ``"boxes+masks"``.
        """
        is_array = isinstance(image, np.ndarray)
        if is_array:
            pil_image = Image.fromarray(image, "RGB")
        else:
            pil_image = image
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

        if render_mode in ("masks", "boxes+masks"):
            self._draw_masks(pil_image, detection_result, class_colors)

        if render_mode in ("boxes", "boxes+masks"):
            draw = ImageDraw.Draw(pil_image)
            self._draw_boxes(draw, detection_result, class_colors)

        return np.array(pil_image) if is_array else pil_image

    def render_to_file(
        self,
        frame_path: str,
        output_path: str,
        detection_result: Dict[str, Any],
        class_colors: Optional[Dict[str, str]] = None,
        render_mode: str = "boxes",
    ) -> None:
        """Load a frame from *frame_path*, draw detections, save to *output_path*."""
        image = Image.open(frame_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        self.render(image, detection_result, class_colors, render_mode)
        image.save(output_path, "JPEG", quality=95)
        image.close()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load_font(font_size: int) -> ImageFont.FreeTypeFont:
        for path in _FONT_PATHS:
            try:
                return ImageFont.truetype(path, font_size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def _draw_boxes(
        self,
        draw: ImageDraw.ImageDraw,
        detection_result: Dict[str, Any],
        class_colors: Optional[Dict[str, str]],
    ) -> None:
        """Draw bounding boxes with class labels and confidence scores."""
        boxes: List = detection_result.get("boxes", [])
        scores: List = detection_result.get("scores", [])
        class_names_list: List = detection_result.get("class_names", [])

        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box
            class_name = (
                class_names_list[i] if i < len(class_names_list) else f"class_{i}"
            )
            score = scores[i] if i < len(scores) else 0.0

            color_hex = "#FF0000"
            if class_colors and class_name in class_colors:
                color_hex = class_colors[class_name]
            color = self._hex_to_rgb(color_hex)

            # Box
            draw.rectangle([x1, y1, x2, y2], outline=color, width=self.line_width)

            # Label background + text
            label = f"{class_name}: {score * 100:.1f}%"
            bbox = draw.textbbox((0, 0), label, font=self.font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            padding = 4

            label_bg = [
                x1,
                y1 - text_height - padding * 2,
                x1 + text_width + padding * 2,
                y1,
            ]
            if label_bg[1] < 0:
                label_bg = [
                    x1,
                    y2,
                    x1 + text_width + padding * 2,
                    y2 + text_height + padding * 2,
                ]

            draw.rectangle(label_bg, fill=color)
            draw.text(
                (label_bg[0] + padding, label_bg[1] + padding),
                label,
                fill=(255, 255, 255),
                font=self.font,
            )

    def _draw_masks(
        self,
        image: Image.Image,
        detection_result: Dict[str, Any],
        class_colors: Optional[Dict[str, str]],
        alpha: float = 0.4,
    ) -> None:
        """Overlay semi-transparent segmentation masks onto *image* (in-place).

        ``detection_result["masks"]`` is expected to be a list of 2-D
        boolean / uint8 numpy arrays with the same (H, W) as *image*.
        This method is a no-op when no masks are present — it exists to
        provide a ready extension point for SAM and similar models.
        """
        masks: Optional[List] = detection_result.get("masks")
        if not masks:
            return

        class_names_list: List = detection_result.get("class_names", [])
        img_array = np.array(image)

        for i, mask in enumerate(masks):
            if not isinstance(mask, np.ndarray):
                continue
            class_name = (
                class_names_list[i] if i < len(class_names_list) else f"class_{i}"
            )
            color_hex = "#FF0000"
            if class_colors and class_name in class_colors:
                color_hex = class_colors[class_name]
            color = self._hex_to_rgb(color_hex)

            # Create colour overlay where mask is True
            bool_mask = mask.astype(bool)
            overlay = np.array(color, dtype=np.uint8)
            img_array[bool_mask] = (
                (1 - alpha) * img_array[bool_mask] + alpha * overlay
            ).astype(np.uint8)

        # Write back into the PIL image in-place
        image.paste(Image.fromarray(img_array, "RGB"))
