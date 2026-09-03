"""
Processing subpackage for Acoustic Eye.

Module map
----------
video_reader        -- open / validate / iterate video frames (robust frame counting)
visual_microphone   -- phase-based Visual Microphone core (adapted from visual-mic-master)
signal_processing   -- scaling, high-pass filtering, spectral subtraction
audio_writer        -- WAV writing + waveform / spectrogram PNG rendering
text_report         -- signal-to-text description + optional speech-to-text
pipeline            -- glue that runs the full Upload -> WAV -> visualisation flow
"""
