import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

class LlamaEngine:
    def __init__(self, model_path):
        print(f"[LLM] Loading Llama-Instruct from {model_path}...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        
        # Blackwell sm_120 strongly prefers bfloat16
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            local_files_only=True
        )
        
        # Ensure the pad token is set correctly for Llama
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
            
        self.max_history = 10 
        self.reset_conversation()
        
    def reset_conversation(self):
        """Call this to clear memory when a new patient starts a session."""
        self.chat_history = [
            {"role": "system", "content": "You are a healthcare assistant."}
        ]

    def generate_response(self, user_text, detected_language="en"):
        print(f"[LLM] Generating response (ASR tagged: {detected_language})...")

        # 1. Robust language matching (carried over from our Nemotron fix)
        detected_lower = detected_language.lower()
        if detected_lower in ["hi", "hindi", "ur", "urdu", "pa", "punjabi", "ne", "nepali"]:
            lang_code = "hi"
        else:
            lang_code = "en"

        # 2. Base Clinical Persona
        base_persona = (
            "You are Dr. Kavita, an expert, deeply empathetic cardiologist in India. "
            "You are speaking with a patient. "
            "CRITICAL RULE: If the patient mentions severe symptoms like 'chest pain', 'shortness of breath', "
            "or 'dizziness', immediately adopt a highly serious, focused, and authoritative medical tone. "
            "Prioritize their safety, remain calm, and do not act casual. "
            "Keep your responses short, warm, and highly reassuring. "
        )

        # 3. Assign active prompt based on the robust lang_code
        if lang_code == "hi":
            print("[LLM] Dynamic prompt set to Hindi")
            active_prompt = base_persona + "The patient is speaking Hindi/Hinglish. You MUST respond fully in natural Hindi using ONLY the Devanagari script like 'नमस्ते', and using a comforting, respectful tone (using 'आप'). DO NOT USE ANY ENGLISH WORDS."
        else:
            print("[LLM] Dynamic prompt set to English")
            active_prompt = base_persona + "The patient is speaking English. You MUST respond strictly in English using the Latin script only."

        # Update the system role dynamically
        if len(self.chat_history) > 0:
            self.chat_history[0]["content"] = active_prompt

        # Add the patient's ACTUAL text to memory
        self.chat_history.append({"role": "user", "content": user_text})

        # Prune history if it gets too long
        if len(self.chat_history) > self.max_history + 1:
            self.chat_history = [self.chat_history[0]] + self.chat_history[-self.max_history:]

        # Format with Llama 3's native Chat Template
        text_prompt = self.tokenizer.apply_chat_template(
            self.chat_history,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = self.tokenizer([text_prompt], return_tensors="pt").to(self.model.device)

        # Generate the response
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=150,
            temperature=0.6,
            do_sample=True, 
            pad_token_id=self.tokenizer.pad_token_id
        )

        # Extract just the newly generated tokens
        input_length = inputs.input_ids.shape[1]
        response_text = self.tokenizer.decode(outputs[0][input_length:], skip_special_tokens=True).strip()

        # Save the AI's response to memory so it remembers it next time
        self.chat_history.append({"role": "assistant", "content": response_text})

        return response_text
