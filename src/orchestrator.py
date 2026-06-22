import time
import csv
import os
from src.config import Config
from src.audio.mic_stream import MicStream
from src.asr.streaming_whisper import StreamingWhisper
# from src.llm.nemotron_engine import NemotronEngine
from src.llm.llama_engine import LlamaEngine
from src.tts.xtts_engine import MultilingualTTSEngine

class PipelineOrchestrator:
    def __init__(self):
        Config.setup_dirs()
        self.mic = MicStream(Config.SAMPLE_RATE, Config.CHUNK_SIZE, Config.INPUT_DEVICE_INDEX)
        self.asr = StreamingWhisper(Config.WHISPER_MODEL, Config.DEVICE, Config.COMPUTE_TYPE)
        # self.llm = NemotronEngine(Config.Nemotron_MODEL)
        self.llm = LlamaEngine(Config.Llama_MODEL_3b)
        self.tts = MultilingualTTSEngine(Config.TTS_MODEL_PATH, Config.TTS_OUTPUT_DIR)
        
        # --- EVALUATION SETUP ---
        self.eval_file = "evaluation_logs.csv"
        self._initialize_eval_logger()

    def _initialize_eval_logger(self):
        """Creates the evaluation table if it doesn't exist."""
        file_exists = os.path.isfile(self.eval_file)
        with open(self.eval_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                # Table Headers for our Evaluation matrix
                writer.writerow([
                    "Timestamp", "Detected_Lang", "User_Input_ASR", 
                    "LLM_Response", "LLM_Latency_sec", "TTS_Processing_sec", 
                    "E2E_Latency_sec", "Notes_Subjective_Eval"
                ])

    def log_evaluation(self, lang, user_text, llm_text, llm_lat, tts_lat, e2e_lat):
        """Saves turn metrics to the CSV table."""
        with open(self.eval_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                lang,
                user_text,
                llm_text,
                f"{llm_lat:.3f}",
                f"{tts_lat:.3f}",
                f"{e2e_lat:.3f}",
                "" # Blank space for you to write your subjective MOS scores later
            ])

    def run(self):
        self.mic.start()
        print("\n=== Pipeline Active. Start speaking. Press Ctrl+C to stop. ===")
        
        try:
            while True:
                time.sleep(0.01)
                chunk = self.mic.get_audio_chunk()
                
                # Unpack the new language identifier tracked by Whisper
                final_text, partial_text, detected_lang = self.asr.process_chunk(chunk)
                
                if partial_text:
                    print(f"\r[ASR Partial]: {partial_text[:88].ljust(80)}", end="", flush=True)
                
                if final_text:
                    # --- METRICS: Start End-to-End Timer ---
                    t_endpoint = time.perf_counter()

                    # Fallback default if token validation yields None
                    if detected_lang and "hindi" in detected_lang.lower():
                        detected_lang = "hi"
                    elif detected_lang and "urdu" in detected_lang.lower():
                        detected_lang = "hi"
                    elif detected_lang and "english" in detected_lang.lower():
                        detected_lang = "en"
                    
                    if not detected_lang:
                        detected_lang = "en"
                        
                    print(f"\n[ASR Final ({detected_lang})]: {final_text}")
                    
                    # 1. Pause mic so PyAudio doesn't overflow and it doesn't hear itself speaking
                    self.mic.pause_listening()
                    
                    # 2. AI generation with dynamic language flag ingestion
                    print("[LLM] Generating response...")
                    t_llm_start = time.perf_counter()
                    
                    llm_response = self.llm.generate_response(final_text, detected_language=detected_lang)
                    
                    t_llm_end = time.perf_counter()
                    llm_latency = t_llm_end - t_llm_start
                    
                    print(f"[LLM Output]: {llm_response}")
                    
                    # 3. Synchronized language routing directly to XTTS-V2
                    t_tts_start = time.perf_counter()
                    
                    self.tts.synthesize_and_play(llm_response, language=detected_lang)
                    
                    t_tts_end = time.perf_counter()
                    tts_latency = t_tts_end - t_tts_start
                    
                    # --- METRICS: Calculate End-to-End ---
                    e2e_latency = t_tts_end - t_endpoint
                    
                    print(f"\n--- Metrics ---")
                    print(f"LLM Latency: {llm_latency:.2f}s | TTS Duration: {tts_latency:.2f}s | E2E Turnaround: {e2e_latency:.2f}s")
                    
                    # Save everything to the CSV table
                    self.log_evaluation(detected_lang, final_text, llm_response, llm_latency, tts_latency, e2e_latency)

                    # 4. Wake mic up for next turn
                    self.mic.resume_listening()
                    print("\n=== Ready for your next sentence. ===")
                    
        except KeyboardInterrupt:
            print("\nShutting down pipeline...")
            self.mic.stop()
