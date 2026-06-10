import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

class NemotronEngine:
    def __init__(self, model_path):
        print(f"[LLM] Loading Nemotron-4B-Mini-Hindi from {model_path}...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        
        # Blackwell sm_120 strongly prefers bfloat16, and Nemotron was natively trained on it.
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            local_files_only=True
        )
        
        # Nemotron has a 4096 context window. We cap history to prevent context overflow.
        self.max_history = 10 
        self.reset_conversation()
        
    def reset_conversation(self):
        """Call this to clear memory when a new patient starts a session."""
        
        # UNIFIED PERSONA: Nemotron natively handles code-switching. 
        # We do not need to hot-swap prompts. We just instruct Dr. Kavita to mirror the language.
        unified_system_prompt = (
            "You are Dr. Kavita, an expert, deeply empathetic cardiologist in India. "
            "You are speaking with an elderly patient. Keep your responses short, warm, and highly reassuring. "
            "Never use complex medical jargon without explaining it simply. "
            "If the patient speaks in Hindi or Hinglish, reply seamlessly in the same language "
            "using the Devanagari script for pure Hindi words, and using a comforting, respectful tone (using 'Aap'). "
            "If the patient speaks English, reply in English. Keep all responses under 3 sentences."
        )
        
        self.chat_history = [
            {"role": "system", "content": unified_system_prompt}
        ]

    def generate_response(self, user_text, detected_language="en"):
        # Note: 'detected_language' is kept in the signature to maintain compatibility 
        # with orchestrator.py, but we let Nemotron's native intelligence handle the routing.
        
        print(f"[LLM] Generating response (ASR tagged: {detected_language})...")
        
        # 1. Add patient's new speech to memory
        self.chat_history.append({"role": "user", "content": user_text})
        
        # 2. Prune history if it gets too long (keep system prompt, slice the rest)
        if len(self.chat_history) > self.max_history + 1:
            self.chat_history = [self.chat_history[0]] + self.chat_history[-self.max_history:]
            
        # 3. Format with Nemotron's native Chat Template
        text_prompt = self.tokenizer.apply_chat_template(
            self.chat_history, 
            tokenize=False, 
            add_generation_prompt=True
        )
        
        inputs = self.tokenizer([text_prompt], return_tensors="pt").to(self.model.device)
        
        # 4. Generate the response
        outputs = self.model.generate(
            **inputs, 
            max_new_tokens=150, 
            temperature=0.6,     # Slightly lower temperature for more deterministic clinical responses
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        # 5. Extract just the newly generated tokens
        input_length = inputs.input_ids.shape[1]
        response_text = self.tokenizer.decode(outputs[0][input_length:], skip_special_tokens=True).strip()
        
        # 6. Save the AI's response to memory so it remembers it next time
        self.chat_history.append({"role": "assistant", "content": response_text})
        
        return response_text
