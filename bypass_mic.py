import subprocess
import numpy as np

def stream_audio_from_kernel():
    # The exact device name from your arecord -l output
    # 'plughw:CARD=Audio,DEV=0' automatically handles 16kHz conversion
    device_name = "plughw:CARD=Audio,DEV=0"
    
    # The arecord command strictly formatted for your Phase 1 pipeline
    # -f S16_LE: 16-bit audio
    # -c 1: Mono channel
    # -r 16000: 16kHz sample rate
    # -t raw: Raw PCM bytes (no WAV header)
    command = [
        'arecord', 
        '-D', device_name, 
        '-f', 'S16_LE', 
        '-c', '1', 
        '-r', '16000', 
        '-t', 'raw'
    ]

    print(f"--- Bypassing PyAudio ---")
    print(f"Connecting directly to Linux Kernel via: {device_name}")
    print("Speak into your USB headset for 3 seconds...\n")

    try:
        # Open the hidden terminal and start streaming
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        frames = []
        bytes_per_chunk = 1024 * 2 # 1024 frames * 2 bytes (16-bit audio)
        
        # Capture exactly 3 seconds of audio (~46 chunks of 1024 frames at 16kHz)
        for _ in range(46): 
            # Read directly from the terminal's live output!
            raw_bytes = process.stdout.read(bytes_per_chunk)
            
            if not raw_bytes:
                break
                
            # Convert the raw bytes into a numpy array (exactly what Whisper/Silero needs)
            audio_chunk = np.frombuffer(raw_bytes, dtype=np.int16)
            frames.append(audio_chunk)

        # Stop the recording process
        process.terminate()
        
        # Analyze the results
        full_audio = np.concatenate(frames)
        max_volume = np.max(np.abs(full_audio))
        
        if max_volume > 0:
            print("✅ SUCCESS! The kernel bypass worked perfectly.")
            print(f"Captured {len(full_audio)} frames. Max volume spike: {max_volume}")
            print("You can drop this exact subprocess logic into your pipeline instead of PyAudio!")
        else:
            print("⚠️ Warning: Streamed successfully, but recorded dead silence.")

    except Exception as e:
        print(f"❌ Error during bypass: {e}")

if __name__ == "__main__":
    stream_audio_from_kernel()
