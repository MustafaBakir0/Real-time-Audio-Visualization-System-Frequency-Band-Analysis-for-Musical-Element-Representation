# Mustafa Bakir  
**Date:** 4/7/2025  
**Institution:** New York University Abu Dhabi  
**Email:** MB9457@nyu.edu  

## Real-time Audio Visualization System: Frequency Band Analysis for Musical Element Representation

This study presents the design, implementation, and evaluation of a real-time audio visualization system that maps frequency bands to corresponding LED indicators representing distinct musical elements. The system consists of an Arduino-based hardware controller integrated with Python-based audio processing software, utilizing Fast Fourier Transform (FFT) for frequency analysis.

By isolating energy from specific frequency ranges related to vocals, chords, percussion, and bass, the system creates an intuitive visual representation of music's core components. The implementation features multiple operational modes, tempo synchronization capabilities, and adaptive smoothing algorithms to create responsive yet stable visualizations. Testing confirms the system achieves low-latency performance with approximately 30ms end-to-end delay while effectively representing musical structure through synchronized LED patterns.

---

## System Architecture

The audio visualization system integrates hardware and software components to transform audio signals into visual LED patterns. The architecture follows a clear signal path from audio capture through processing to visual output, with multiple modes of operation.

### Hardware-Software Integration

The system consists of two primary components: an Arduino microcontroller handling LED control and user inputs, and a Python application performing audio capture and advanced signal processing. These components communicate bidirectionally via serial connection.

**The hardware layer includes:**
- 5 LEDs connected to Arduino pins 3, 4, 5, 6, and 7, representing different musical elements  
- A button on analog pin A0 for mode selection  
- A potentiometer on analog pin A1 for volume control in audio control mode  
- Serial connection to the host computer for data transfer  

**The software layer includes:**
- Audio capture and buffer management via PyAudio  
- Frequency analysis using Fast Fourier Transform (FFT)  
- Frequency band isolation and energy calculation  
- Beat detection and tempo synchronization  
- Volume control integration with the operating system  
- Serial communication with the Arduino controller  

---

## Signal Flow and Processing

The system's signal path follows a clear sequence:
1. Audio is captured from the computer's microphone or line input at 44.1kHz with 16-bit resolution  
2. The audio is processed in chunks of 2048 samples to balance frequency resolution and latency  
3. Each chunk undergoes windowing with a Hann function to minimize spectral leakage  
4. FFT converts the time-domain signal to frequency domain representation  
5. Energy in specific frequency bands is calculated using both peak and average values  
6. The energy values are logarithmically scaled and normalized to match human perception  
7. Smoothing algorithms are applied to prevent LED flickering while maintaining responsiveness  
8. The processed values are sent to Arduino via serial communication as LED brightness levels  
9. Arduino updates LED states based on received data and current operational mode  

---

## Operational Modes

The system implements three distinct operational modes:

- **POT_MODE (Audio Control Mode):** The potentiometer controls system volume, with LED brightness indicating the volume level. The Python application reads potentiometer values from Arduino and adjusts system volume accordingly.

- **ANIMATION_MODE:** The system runs a predefined sequential animation pattern independent of audio input. LEDs turn on and off in sequence with configurable timing, creating a light show effect.

- **VISUALIZER_MODE:** The core functionality where LEDs respond to musical elements in real-time. The Python application processes audio, extracts frequency information, and sends LED brightness values to Arduino.

Mode switching occurs via the button connected to analog pin A0. The Arduino implements debouncing with a 50ms delay to prevent false triggers during button presses.

---

## Audio Acquisition and Processing

The audio processing pipeline forms the foundation of the visualization system, transforming raw audio signals into meaningful musical element representations through several sophisticated processing stages.

### Audio Capture and Preprocessing

Audio acquisition begins with PyAudio capturing data from the selected input device. The system implements a robust device selection mechanism that:
- Lists all available audio input devices  
- Allows manual device selection  
- Attempts systematic testing of devices when selection is ambiguous  
- Tries multiple parameter combinations for maximum compatibility  

Once captured, the audio undergoes preprocessing:
- Conversion to NumPy array for efficient processing  
- Normalization to the range [-1, 1]  
- Application of Hanning window to minimize spectral leakage during FFT  

The system uses a chunk size of 2048 samples at 44.1kHz, striking a balance between frequency resolution (approximately 21.5Hz per FFT bin) and processing latency.
