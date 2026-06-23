import time
import csv
import os
from src.config import Config
from src.audio.mic_stream import MicStream
from src.asr.streaming_whisper import StreamingWhisper
from src.llm.nemotron_engine import NemotronEngine
# from src.llm.llama_engine import LlamaEngine
from src.tts.xtts_engine import MultilingualTTSEngine

class PipelineOrchestrator:
    def __init__(self):
        Config.setup_dirs()
        self.mic = MicStream(Config.SAMPLE_RATE, Config.CHUNK_SIZE, Config.INPUT_DEVICE_INDEX)
        self.asr = StreamingWhisper(Config.WHISPER_MODEL, Config.DEVICE, Config.COMPUTE_TYPE)
        self.llm = NemotronEngine(Config.Nemotron_MODEL)
        # self.llm = LlamaEngine(Config.Llama_MODEL_3b)
        self.tts = MultilingualTTSEngine(Config.TTS_MODEL_PATH, Config.TTS_OUTPUT_DIR)
        
        # --- EVALUATION SETUP ---
        self.eval_file = "evaluation_logs.csv"
        self._initialize_eval_logger()

    def _initialize_eval_logger(self):
        """Creates the evaluation table if it doesn't exist with comprehensive metrics."""
        file_exists = os.path.isfile(self.eval_file)
        with open(self.eval_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow([
                    "Timestamp", 
                    "Detected_Lang", 
                    "User_Input_ASR", 
                    "LLM_Response", 
                    "ASR_Latency_sec",
                    "LLM_Latency_sec", 
                    "TTS_Total_Time_sec", 
                    "TTFA_sec",
                    "E2E_Latency_sec", 
                    "Input_Audio_Tokens",
                    "Transcribed_Text_Tokens",
                    "Response_Text_Tokens",
                    "Output_Audio_Tokens",
                    "ASR_Audio_Token_Rate_per_sec",
                    "LLM_TPS",
                    "TTS_CPS",
                    "RTF",
                    "Notes_Subjective_Eval"
                ])

    def log_evaluation(self, lang, user_text, llm_text, asr_lat, llm_lat, tts_lat, ttfa, e2e_lat,
                       in_aud_tok, tx_in_tok, tx_out_tok, out_aud_tok, asr_aud_rate, llm_tps, tts_cps, rtf):
        """Saves detailed turn metrics to the CSV table."""
        with open(self.eval_file, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                lang,
                user_text,
                llm_text,
                f"{asr_lat:.3f}",
                f"{llm_lat:.3f}",
                f"{tts_lat:.3f}",
                f"{ttfa:.3f}",
                f"{e2e_lat:.3f}",
                int(in_aud_tok),
                int(tx_in_tok),
                int(tx_out_tok),
                int(out_aud_tok),
                f"{asr_aud_rate:.2f}",
                f"{llm_tps:.2f}",
                f"{tts_cps:.2f}",
                f"{rtf:.3f}",
                ""  # Blank space for manual subjective MOS scores
            ])

    def run(self):
        self.mic.start()
        print("\n=== Pipeline Active. Start speaking. Press Ctrl+C to stop. ===")
        
        try:
            while True:
                time.sleep(0.01)
                chunk = self.mic.get_audio_chunk()
                
                # Capture onset time right before chunk processing to isolate ASR latency bounds
                t_asr_start = time.perf_counter()
                final_text, partial_text, detected_lang = self.asr.process_chunk(chunk)
                
                if partial_text:
                    print(f"\r[ASR Partial]: {partial_text[:88].ljust(80)}", end="", flush=True)
                
                if final_text:
                    t_endpoint = time.perf_counter()
                    asr_latency = t_endpoint - t_asr_start

                    # Fallback language routing normalization
                    if detected_lang and "hindi" in detected_lang.lower():
                        detected_lang = "hi"
                    elif detected_lang and "urdu" in detected_lang.lower():
                        detected_lang = "hi"
                    elif detected_lang and "english" in detected_lang.lower():
                        detected_lang = "en"
                    
                    if not detected_lang:
                        detected_lang = "en"
                        
                    print(f"\n[ASR Final ({detected_lang})]: {final_text}")
                    
                    # 1. Pause microphone input stream loop
                    self.mic.pause_listening()
                    
                    # 2. AI generation pipeline block
                    print("[LLM] Generating response...")
                    t_llm_start = time.perf_counter()
                    llm_response = self.llm.generate_response(final_text, detected_language=detected_lang)
                    t_llm_end = time.perf_counter()
                    llm_latency = t_llm_end - t_llm_start
                    
                    # Compute intermediate TTFA (Time to First Audio generation milestone)
                    ttfa = t_llm_end - t_endpoint
                    print(f"[LLM Output]: {llm_response}")
                    
                    # 3. Synchronized audio generation and system call output routing
                    t_tts_start = time.perf_counter()
                    self.tts.synthesize_and_play(llm_response, language=detected_lang)
                    t_tts_end = time.perf_counter()
                    tts_latency = t_tts_end - t_tts_start
                    
                    # End-to-End turn cycle calculation
                    e2e_latency = t_tts_end - t_endpoint
                    
                    # --- METRICS TOKENIZATION AND DERIVATION MATH ---
                    # Compute input audio parameters (Using 25ms window baseline tokens: 400 samples/frame at 16kHz)
                    # Safe fall-back uses Silero minimum baseline capture array dimensions if frame calculations vary
                    input_samples = len(chunk) if chunk else Config.SAMPLE_RATE * 1.5 
                    input_audio_tokens = input_samples / 400.0 if input_samples > 0 else 0
                    input_audio_duration = input_samples / float(Config.SAMPLE_RATE)
                    
                    # Estimate processed Text Token distributions
                    multilingual_factor = 1.5 if detected_lang == "hi" else 1.33
                    transcribed_text_tokens = len(final_text.split()) * multilingual_factor
                    response_text_tokens = len(llm_response.split()) * multilingual_factor
                    
                    # Output audio estimation (approximate human pacing scale of 13 characters/sec)
                    estimated_output_duration = len(llm_response) / 13.0
                    output_audio_tokens = estimated_output_duration * 50.0 # 50 frames per second standard audio codec frame rate
                    
                    # Normalize Rate Throughputs
                    asr_audio_token_rate = input_audio_tokens / asr_latency if asr_latency > 0 else 0
                    llm_tps = response_text_tokens / llm_latency if llm_latency > 0 else 0
                    tts_cps = len(llm_response) / tts_latency if tts_latency > 0 else 0
                    rtf = tts_latency / estimated_output_duration if estimated_output_duration > 0 else 0
                    
                    print(f"\n--- Turn Statistics Matrix ---")
                    print(f"ASR Latency: {asr_latency:.2f}s | ASR Audio Token Rate: {asr_audio_token_rate:.1f}/s")
                    print(f"LLM Latency: {llm_latency:.2f}s | LLM TPS: {llm_tps:.1f} tok/s")
                    print(f"TTS Duration: {tts_latency:.2f}s | TTS CPS: {tts_cps:.1f} char/s | RTF: {rtf:.3f}")
                    print(f"TTFA: {ttfa:.2f}s | E2E Turnaround: {e2e_latency:.2f}s")
                    print(f"Tokens Tracking -> Input Audio: {int(input_audio_tokens)} | Text In: {int(transcribed_text_tokens)} | Text Out: {int(response_text_tokens)} | Output Audio: {int(output_audio_tokens)}")
                    
                    # Save metrics directly to CSV table
                    self.log_evaluation(
                        detected_lang, final_text, llm_response, asr_latency, llm_latency, tts_latency, ttfa, e2e_latency,
                        input_audio_tokens, transcribed_text_tokens, response_text_tokens, output_audio_tokens,
                        asr_audio_token_rate, llm_tps, tts_cps, rtf
                    )

                    # 4. Resume stream listening context
                    self.mic.resume_listening()
                    print("\n=== Ready for your next sentence. ===")
                    
        except KeyboardInterrupt:
            print("\nShutting down pipeline...")
            self.mic.stop()
