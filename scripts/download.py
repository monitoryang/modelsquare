# Load model directly
from transformers import AutoProcessor, AutoModelForTextToWaveform

processor = AutoProcessor.from_pretrained("Qwen/Qwen3-Omni-30B-A3B-Instruct")
model = AutoModelForTextToWaveform.from_pretrained("Qwen/Qwen3-Omni-30B-A3B-Instruct")