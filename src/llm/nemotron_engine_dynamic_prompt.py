import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

class NemotronEngine:
    def __init__(self, model_path):
        print(f"[LLM] Loading Nemotron-4B-Mini-Hindi from {model_path}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            local_files_only=True
        )
        self.max_history = 10 
        self.reset_conversation()
        
    def reset_conversation(self):
        # We start with a placeholder that gets overwritten instantly
        self.chat_history = [
            {"role": "system", "content": "You are a healthcare assistant."}
        ]

    def generate_response(self, user_text, detected_language="en"):
        # 1. Normalize the language tag to an ISO code just to be safe
        lang_code = "hi" if "hindi" in detected_language.lower() else "en"
        
        # 2. SHAPE-SHIFT PERSONA PROMPT SWITCHER
        base_persona = (
            "You are Dr. Kavita, an expert, deeply empathetic cardiologist in India. "
            "You are speaking with an elderly patient. Keep your responses short, warm, and highly reassuring. "
        )
        
        if lang_code == "hi":
            active_prompt = base_persona + "The patient is speaking Hindi/Hinglish. You MUST respond fully in natural Hindi using ONLY the Devanagari script."
        else:
            active_prompt = base_persona + "The patient is speaking English. You MUST respond strictly and completely in English."
            
        # Overwrite the root system prompt with the strict language rule
        if len(self.chat_history) > 0:
            self.chat_history[0] = {"role": "system", "content": active_prompt}

        print(f"[LLM] Generating response (Forced Language: {lang_code})...")
        
        # 3. Add patient's text
        self.chat_history.append({"role": "user", "content": user_text})
        
        # 4. Prune history
        if len(self.chat_history) > self.max_history + 1:
            self.chat_history = [self.chat_history[0]] + self.chat_history[-self.max_history:]
            
        # 5. Generate
        text_prompt = self.tokenizer.apply_chat_template(
            self.chat_history, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text_prompt], return_tensors="pt").to(self.model.device)
        
        outputs = self.model.generate(
            **inputs, 
            max_new_tokens=150, 
            temperature=0.6,
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id
        )
        
        input_length = inputs.input_ids.shape[1]
        response_text = self.tokenizer.decode(outputs[0][input_length:], skip_special_tokens=True).strip()
        
        # 6. Save response
        self.chat_history.append({"role": "assistant", "content": response_text})
        
        return response_text
