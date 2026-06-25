import pandas as pd
import re
from jiwer import wer, cer

def clean_text(text, is_hindi=False):
    """
    Cleans text by removing casing, punctuation, and extra whitespace.
    Maintains Devanagari character sets intact while stripping Western marks.
    """
    if pd.isna(text):
        return ""
    
    text = str(text)
    
    # 1. Handle Casing (English characters)
    text = text.lower()
    
    # 2. Strip Punctuation and special tokens
    # This keeps characters, numbers, and basic spaces across both English and Devanagari
    text = re.sub(re.compile(r'[^\w\s\d]', re.UNICODE), ' ', text)
    
    # 3. Clean up formatting whitespace anomalies
    text = " ".join(text.split())
    return text

def run_evaluation():
    log_file = "nemotron_evaluation_logs.csv"
    
    if not pd.os.path.path.exists(log_file):
        print(f"Error: Could not locate log file '{log_file}'. Make sure it's in this folder.")
        return

    # Load logs
    df = pd.read_csv(log_file)
    
    # Validation Check
    if 'User_Input_ASR' not in df.columns or 'Script' not in df.columns:
        print("Error: Columns 'User_Input_ASR' and 'Script' must exist in your CSV file.")
        return

    print(f"Analyzing {len(df)} turns from {log_file}...")

    turn_wers = []
    turn_cers = []

    for idx, row in df.iterrows():
        # Clean both the target ground-truth script entry and the machine ASR transcript
        ground_truth = clean_text(row['Script'])
        asr_transcript = clean_text(row['User_Input_ASR'])
        
        # Guard against blank entries to avoid division-by-zero crashes
        if not ground_truth:
            turn_wers.append(0.0)
            turn_cers.append(0.0)
            continue
            
        # Calculate instantaneous row-level alignments
        w_score = wer(ground_truth, asr_transcript)
        c_score = cer(ground_truth, asr_transcript)
        
        turn_wers.append(w_score)
        turn_cers.append(c_score)

    # Ingest calculations cleanly back into new standalone matrix columns
    df['Turn_WER'] = turn_wers
    df['Turn_CER'] = turn_cers

    # Overwrite/save the updated dataframe
    df.to_csv(log_file, index=False)
    
    # Compute system global evaluation macro-averages
    print("\n=============================================")
    print("      WHISPER PIPELINE ACCURACY RESULTS       ")
    print("=============================================")
    print(f"Global Baseline Average WER: {df['Turn_WER'].mean() * 100:.2f}%")
    print(f"Global Baseline Average CER: {df['Turn_CER'].mean() * 100:.2f}%")
    print("=============================================")
    print(f"Successfully updated '{log_file}' with 'Turn_WER' and 'Turn_CER' columns!")

if __name__ == "__main__":
    run_evaluation()
