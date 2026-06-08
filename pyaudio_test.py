import pyaudio
import numpy as np

def test_pyaudio_usb_mic():
    p = pyaudio.PyAudio()
    usb_mic_index = None

    print("--- PyAudio Device List ---")
    # 1. Scan all devices
    for i in range(p.get_device_count()):
        dev_info = p.get_device_info_by_index(i)
        name = dev_info['name']
        inputs = dev_info['maxInputChannels']
        
        # Print devices that actually have microphones (inputs > 0)
        if inputs > 0:
            print(f"[{i}] {name} (Inputs: {inputs})")
            
            # Automatically find the plughw or sysdefault for your USB mic
            # We look for 'sysdefault' and your headset name 'AB13X' or 'USB Audio'
            if ('USB Audio' in name or 'AB13X' in name) and ('sysdefault' in name or 'plughw' in name):
                usb_mic_index = i

    if usb_mic_index is None:
        print("\n❌ Could not automatically find the AB13X USB headset in PyAudio.")
        print("Look at the list above and manually set usb_mic_index to the correct number.")
        p.terminate()
        return

    print(f"\n✅ Auto-selected PyAudio Device Index: {usb_mic_index}")
    print("\n--- Testing Recording ---")
    print("Speak into your headset for 3 seconds...")

    try:
        # 2. Open the PyAudio stream using your Phase 1 settings
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        input_device_index=usb_mic_index,
                        frames_per_buffer=1024)

        frames = []
        # Record for ~3 seconds (16000 rate / 1024 frames = ~15 chunks per second)
        for _ in range(0, int(16000 / 1024 * 3)):
            # exception_on_overflow=False prevents crashes if Linux audio buffers slightly out of sync
            data = stream.read(1024, exception_on_overflow=False) 
            frames.append(np.frombuffer(data, dtype=np.int16))

        # Stop and close the stream properly
        stream.stop_stream()
        stream.close()
        p.terminate()

        # 3. Check for actual sound waves
        audio_data = np.hstack(frames)
        if np.max(np.abs(audio_data)) > 0:
            print("✅ SUCCESS! PyAudio perfectly captured your voice.")
            print("You can safely plug this device index into your Phase 1 pipeline!")
        else:
            print("⚠️ Warning: PyAudio connected, but recorded dead silence.")

    except Exception as e:
        print(f"❌ PyAudio Error: {e}")
        p.terminate()

if __name__ == "__main__":
    test_pyaudio_usb_mic()
