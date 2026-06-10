import time
import numpy as np
import torch
from transformers import pipeline
from src.config import Config

class StreamingWhisper:
    def __init__(self, model_path, device, compute_type):
        print(f"[ASR] Loading Hugging Face Whisper (Turbo) from: {model_path} ...")
        
        # Map string compute_type to torch_dtype for Blackwell FP16 support
        torch_dtype = torch.float16 if compute_type == "float16" else torch.float32
        
        # Initialize pure PyTorch Hugging Face pipeline
        self.pipeline = pipeline(
            "automatic-speech-recognition",
            model=model_path,
            device=device,
            torch_dtype=torch_dtype,
        )
        
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_voice_time = time.time()

    def _run_inference(self, audio_array):
        """Helper function to execute HF pipeline inference with medical biasing."""
        try:
            # HF pipeline requires a dictionary for raw arrays
            result = self.pipeline(
                {"sampling_rate": 16000, "raw": audio_array},
                generate_kwargs={
                    "initial_prompt": Config.MEDICAL_PROMPT,
                    "num_beams": 5,
                    "task": "transcribe"
                },
                return_language=True # Supported in transformers==4.46.3
            )
            
            text = result.get("text", "").strip()
            
            # Safely extract language tag (handles HF dictionary variations)
            language = result.get("language", None)
            if not language and "chunks" in result and len(result["chunks"]) > 0:
                language = result["chunks"][0].get("language", "en")
                
            return text, language or "en"
            
        except Exception as e:
            print(f"[ASR Warning] Inference failure: {e}")
            return "", "en"

    def process_chunk(self, audio_chunk):
        current_time = time.time()

        # SILENCE DETECTED (Endpointing timeout or Orchestrator idle check)
        if audio_chunk is None:
            # If buffer has audio AND 1.5 seconds of silence has passed
            if len(self.audio_buffer) > 0 and (current_time - self.last_voice_time) > 1.5:
                
                # AGGRESSIVE PURGE: If audio is less than 0.5s (8000 samples), drop it
                if len(self.audio_buffer) < 8000:
                    self.audio_buffer = np.array([], dtype=np.float32)
                    return None, None, None
                
                # Otherwise, it's speech. Run final inference.
                final_text, language = self._run_inference(self.audio_buffer)
                
                # CRITICAL: Always empty the bucket after a silence timeout
                self.audio_buffer = np.array([], dtype=np.float32)
                
                if final_text:
                    return final_text, None, language
            return None, None, None

        # VOICE DETECTED
        self.last_voice_time = current_time
        self.audio_buffer = np.concatenate((self.audio_buffer, audio_chunk))

        # Process partials once we have at least 1 second of audio
        if len(self.audio_buffer) >= 16000:
            current_text, language = self._run_inference(self.audio_buffer)
            
            # Safety fallback: Cut off non-stop rambling after 15 seconds
            if len(self.audio_buffer) > 16000 * 15:
                final_text = current_text
                self.audio_buffer = np.array([], dtype=np.float32)
                return final_text, current_text, language
                
            return None, current_text, language
            
        return None, None, None
