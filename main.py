# ======================================================
# Audio visualizer with arduino integration
# Mustafa Bakir,
# April 7th, 2025
# New York University Abu Dhabi
# ======================================================
#
# this script captures audio from your computers input, analyzes freq bands,
# and sends data to an arduino to drive led visualization.
#
# key features:
# - system vol control via arduino potentiometer
# - multi-mode operation (audio ctrl, animation, visualizer)
# - real-time freq analysis w/ fft
# - beat detection & tempo sync for musical visualization
# - customizable freq bands for different musical elements
#
# hw requirements:
# - arduino connected via serial port
# - leds connected to arduino pins 3, 5, 6, 9, 10
# - potentiometer for vol control
# - push button for mode switching
#
# dependencies:
# - numpy, pyaudio, scipy, serial, pycaw (on windows)
#
#
# !!!! MAKE SURE YOU UPLOAD YOUR ARDUINO CODE BEFORE RUNNING YOUR PYTHON CODE,
# !!!! BOTH IDE'S CAN NOT USE COM5 PORT AT THE SAME TIME
# ======================================================

import numpy as np
import pyaudio
import time
import serial
import sys
import traceback
from scipy.fft import fft
import threading

# for windows vol ctrl
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    WINDOWS = True
except ImportError:
    WINDOWS = False
    print("windows vol ctrl lib (pycaw) not found.")
    print("install with: pip install pycaw")
    print("vol ctrl will be simulated.")

# serial port config - adjust for your system if ur using this code for smtn other than windows,
# btw usually the port is com5 but some devices are weird, got COM3 on my friend's laptop so do check pls
COM_PORT = 'COM5'
BAUD_RATE = 9600

# audio settings
CHUNK = 2048  # larger chunk size for better freq resolution
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

# viz settings
SENSITIVITY = 1.2  # adjusted for comp audio
SMOOTHING = 0.3  # higher = smoother led transitions
UPDATE_RATE = 30  # send updates to arduino at this rate (ms)

# freq bands for viz - each mapped to diff arduino pin
FREQ_BANDS = {
    'vocals': (300, 3000),  # vocal freq range (pin 3)
    'chord': (200, 2000),  # musical chord freqs (pin 9)
    'snares': (150, 250),  # snare drum freqs (pin 5)
    'claps': (2000, 5000),  # clap/high transient freqs (pin 6)
    'bass': (50, 120)  # focus on kick drum freqs (pin 10)
}

# program states
AUDIO_CONTROL_MODE = "AUDIO_CONTROL"
ANIMATION_MODE = "ANIMATION"
VISUALIZER_MODE = "VISUALIZER"
current_mode = AUDIO_CONTROL_MODE

# smoothed band lvls - init all to 0
smoothed_levels = {band: 0 for band in FREQ_BANDS}

# debug settings
DEBUG = False  # set true for more detailed output


class AudioProcessor:
    def __init__(self):
        """
        init the audio processor - sets up audio capture, arduino conn,
        vol ctrl, and tempo tracking
        """
        # init pyaudio
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.arduino = None
        self.running = False
        self.update_thread = None

        # setup vol ctrl
        self.setup_volume_control()

        # add tempo tracking
        self.tempo = 120  # default tempo in bpm
        self.beat_position = 0  # 0-3 representing beats 1-4
        self.last_beat_time = time.time()
        self.beat_duration = 60.0 / self.tempo  # duration of one beat in secs
        self.tempo_sync_enabled = True

        # add threshold tracking for onset detection
        self.energy_history = []
        self.energy_window_size = 20  # track energy over this many frames
        self.onset_threshold_multiplier = 1.5  # energy must increase by this factor for onset
        self.prev_bass_data = None  # for transient detection

    def setup_volume_control(self):
        """
        init vol ctrl system - uses pycaw on win, simulated elsewhere
        sets up vol range and interface to system audio
        """
        global WINDOWS

        if WINDOWS:
            try:
                # get audio endpoint device
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self.volume = cast(interface, POINTER(IAudioEndpointVolume))

                # get vol range (typically min_vol to max_vol)
                volume_range = self.volume.GetVolumeRange()
                self.min_volume = volume_range[0]
                self.max_volume = volume_range[1]

                print(f"system vol range: {self.min_volume:.2f} to {self.max_volume:.2f} db")
            except Exception as e:
                print(f"err initializing vol ctrl: {e}")
                WINDOWS = False
                self.volume = None
        else:
            self.volume = None

    def set_system_volume(self, level_percent):
        """
        set system vol level (0-100%)

        args:
            level_percent: vol level as percentage

        returns:
            bool: success or failure
        """
        if not WINDOWS or self.volume is None:
            print(f"[simulation] setting system vol to {level_percent}%")
            return True

        try:
            # convert percentage to vol scalar
            # map 0-100 to vol range
            volume_scalar = self.min_volume + (self.max_volume - self.min_volume) * (level_percent / 100.0)

            # ensure within valid range
            volume_scalar = max(self.min_volume, min(self.max_volume, volume_scalar))

            # set vol
            self.volume.SetMasterVolumeLevel(volume_scalar, None)
            return True

        except Exception as e:
            print(f"err setting vol: {e}")
            return False

    def get_system_volume(self):
        """
        get current system vol as percentage

        returns:
            float: current vol as percentage (0-100)
        """
        if not WINDOWS or self.volume is None:
            return 50  # default simulated vol

        try:
            # get current vol level
            volume_scalar = self.volume.GetMasterVolumeLevel()

            # convert to percentage
            volume_percent = (volume_scalar - self.min_volume) / (self.max_volume - self.min_volume) * 100
            return max(0, min(100, volume_percent))

        except Exception as e:
            print(f"err getting vol: {e}")
            return 50

    def connect_arduino(self):
        """
        connect to arduino via serial port

        returns:
            bool: true if conn successful, false otherwise
        """
        try:
            self.arduino = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
            print(f"connected to arduino on {COM_PORT}")

            # send individual decay rates to arduino
            time.sleep(2)  # allow time for conn to establish

            # inform arduino about the individual decay rates
            decay_command = "DECAY:0.6,0.5,0.1,0.1,0.3\n"
            self.arduino.write(decay_command.encode())
            print("sent custom decay rates to arduino")

            return True
        except Exception as e:
            print(f"err connecting to arduino: {e}")
            return False

    def detect_beat(self, audio_data):
        """
        detect beats based on audio energy and timing

        args:
            audio_data: numpy array of audio samples

        returns:
            bool: true if beat detected, false otherwise
        """
        # calc current frame's energy
        energy = np.sum(np.abs(audio_data))
        self.energy_history.append(energy)

        # maintain fixed window size
        if len(self.energy_history) > self.energy_window_size:
            self.energy_history.pop(0)

        # need at least a few frames to detect onsets
        if len(self.energy_history) < 4:
            return False

        # get avg of prev frames (excluding most recent)
        prev_avg = np.mean(self.energy_history[:-1])

        # check for significant energy increase (onset)
        if energy > prev_avg * self.onset_threshold_multiplier and energy > 0.01:
            # make sure we don't detect onsets too close together
            current_time = time.time()
            min_beat_interval = self.beat_duration * 0.5  # min time between beats

            if current_time - self.last_beat_time >= min_beat_interval:
                self.beat_position = (self.beat_position + 1) % 4
                self.last_beat_time = current_time
                self.beat_duration = min(0.8,
                                         max(0.2, current_time - self.last_beat_time))  # update with adaptive tempo
                self.tempo = 60.0 / self.beat_duration

                if DEBUG:
                    print(f"beat {self.beat_position + 1}/4 detected! tempo: {self.tempo:.1f} bpm")
                return True

        return False

    def start_audio_stream(self):
        """
        init and start audio stream with multiple fallback options
        tries to find a working audio input device

        returns:
            bool: true if stream started successfully, false otherwise
        """
        try:
            # list all audio devices
            print("\navailable audio devices:")
            input_devices = []
            for i in range(self.p.get_device_count()):
                dev_info = self.p.get_device_info_by_index(i)
                # only show input devices
                if dev_info.get('maxInputChannels') > 0:
                    input_devices.append(i)
                    print(f"{i}: {dev_info['name']} (input channels: {dev_info['maxInputChannels']})")

            if not input_devices:
                print("no input devices found!")
                return False

            # try approach 1: request specific device
            user_choice = input("\nenter device number to use (or press enter to try all): ")

            if user_choice.strip():
                try:
                    device_index = int(user_choice)
                    dev_info = self.p.get_device_info_by_index(device_index)
                    print(f"trying device: {dev_info['name']}")

                    # try with original settings first
                    try:
                        self.stream = self.p.open(
                            format=FORMAT,
                            channels=CHANNELS,  # original channels setting
                            rate=RATE,  # original sample rate
                            input=True,
                            input_device_index=device_index,
                            frames_per_buffer=CHUNK  # original chunk size
                        )
                        print(f"success! audio stream started with device {device_index}")
                        return True
                    except Exception as e1:
                        print(f"first attempt failed: {e1}")

                        # try again with more compatible settings
                        try:
                            self.stream = self.p.open(
                                format=FORMAT,
                                channels=1,
                                rate=44100,
                                input=True,
                                input_device_index=device_index,
                                frames_per_buffer=CHUNK
                            )
                            print(f"success on second attempt! audio stream started with device {device_index}")
                            return True
                        except Exception as e2:
                            print(f"second attempt failed: {e2}")
                except (ValueError, IndexError) as e:
                    print(f"invalid selection: {e}")

            # try each input device systematically
            print("\ntrying each input device systematically...")
            for idx in input_devices:
                dev_info = self.p.get_device_info_by_index(idx)
                print(f"trying device {idx}: {dev_info['name']}...")

                try:
                    # try with original settings when possible
                    self.stream = self.p.open(
                        format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        input_device_index=idx,
                        frames_per_buffer=CHUNK
                    )
                    print(f"success! audio stream started with device {idx}")
                    return True
                except Exception as e:
                    print(f"failed with device {idx}: {e}")
                    continue

            print("all approaches failed to open an audio stream.")
            return False

        except Exception as e:
            print(f"err in audio stream initialization: {e}")
            traceback.print_exc()
            return False

    def analyze_frequencies(self, data):
        """
        analyze audio data and extract freq bands
        performs fft and extracts energy in diff freq ranges

        args:
            data: raw audio data buffer

        returns:
            tuple: (dict of band levels, bool indicating beat detection)
        """
        # convert audio data to numpy array
        audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)

        # normalize audio data to be between -1 and 1
        audio_data = audio_data / 32768.0

        # detect beat before applying window function
        beat_detected = self.detect_beat(audio_data)

        # apply window function to reduce spectral leakage
        window = np.hanning(len(audio_data))
        audio_data = audio_data * window

        # perform fft
        fft_data = fft(audio_data)
        fft_data = np.abs(fft_data[:CHUNK // 2]) / CHUNK  # take magnitude of first half

        # get freq resolution
        freq_resolution = RATE / CHUNK  # hz per bin

        # extract levels for each freq band
        band_levels = {}
        for band_name, (low_freq, high_freq) in FREQ_BANDS.items():
            # convert freqs to fft bin indices
            low_bin = max(1, int(low_freq / freq_resolution))
            high_bin = min(CHUNK // 2 - 1, int(high_freq / freq_resolution))

            # calc band magnitude based on musical element
            if high_bin > low_bin:
                if band_name in ['claps', 'snares']:
                    # for transient sounds, emphasis on peaks
                    peak = np.max(fft_data[low_bin:high_bin + 1])
                    avg = np.mean(fft_data[low_bin:high_bin + 1])
                    band_mag = 0.9 * peak + 0.1 * avg  # heavy peak emphasis
                elif band_name == 'bass':
                    # bass needs more peak emphasis
                    peak = np.max(fft_data[low_bin:high_bin + 1])
                    avg = np.mean(fft_data[low_bin:high_bin + 1])

                    # for bass/drum detection, add transient detection
                    if hasattr(self, 'prev_bass_data') and self.prev_bass_data is not None:
                        # compare current with prev frame to find transients
                        transient_energy = np.sum(np.abs(fft_data[low_bin:high_bin + 1] - self.prev_bass_data))
                        # weight the transient detection heavily
                        band_mag = 0.5 * peak + 0.2 * avg + 0.3 * transient_energy
                    else:
                        band_mag = 0.7 * peak + 0.3 * avg

                    # store current bass data for next frame comparison
                    self.prev_bass_data = fft_data[low_bin:high_bin + 1].copy()
                else:  # vocals and chord
                    # more balanced
                    peak = np.max(fft_data[low_bin:high_bin + 1])
                    avg = np.mean(fft_data[low_bin:high_bin + 1])
                    band_mag = 0.5 * peak + 0.5 * avg

                # apply logarithmic scaling (better matches human perception)
                band_level = 20 * np.log10(band_mag + 1e-10)

                # normalize to 0-100 scale
                band_level = (band_level + 50) / 50 * 100
                band_level = max(0, min(100, band_level))

                # apply sensitivity
                band_level = min(100, band_level * SENSITIVITY)

                # apply noise floor threshold
                noise_floor = 15
                if band_level < noise_floor:
                    band_level = 0
            else:
                band_level = 0

            band_levels[band_name] = band_level

        return band_levels, beat_detected

    def smooth_levels(self, band_levels):
        """
        apply smoothing to band levels with diff factors for each band
        prevents flickering and makes viz more musical

        args:
            band_levels: dict of raw band levels

        returns:
            dict: smoothed band levels
        """
        global smoothed_levels

        # define smoothing factors that match decay rate prefs
        smoothing_factors = {
            'vocals': 0.4,  # less smoothing for vocals (matches 0.6 decay)
            'chord': 0.5,  # medium smoothing for chord (matches 0.5 decay)
            'snares': 0.9,  # high attack for snares (matches 0.1 decay)
            'claps': 0.9,  # high attack for claps (matches 0.1 decay)
            'bass': 0.7  # medium-high attack for bass drums (matches 0.3 decay)
        }

        for band, level in band_levels.items():
            # apply band-specific smoothing factor
            smooth_factor = smoothing_factors.get(band, SMOOTHING)

            # if the new level is significantly higher, respond more quickly
            if level > smoothed_levels[band] * 1.5:
                # faster attack for sudden increases in vol
                smooth_factor = min(0.9, smooth_factor * 1.5)

            smoothed_levels[band] = smoothed_levels[band] * (1 - smooth_factor) + level * smooth_factor

        return smoothed_levels

    def map_levels_to_leds(self, smoothed_band_levels):
        """
        map freq band levels to led brightness values with tempo sync

        args:
            smoothed_band_levels: dict of smoothed band levels

        returns:
            list: led brightness values (0-255)
        """
        # init all led values
        led_values = [0, 0, 0, 0, 0]

        # always respond to vocals/chord regardless of beat position
        led_values[0] = int(smoothed_band_levels['vocals'] * 2.55)  # led 1 (pin 3) - vocals
        led_values[1] = int(smoothed_band_levels['chord'] * 2.55)  # led 2 (pin 9) - musical chord

        # claps/high freq response (also not beat-restricted)
        led_values[3] = int(smoothed_band_levels['claps'] * 2.55)  # led 4 (pin 6) - claps

        if self.tempo_sync_enabled:
            # apply 4/4 backbeat pattern

            # bass drum on beats 1 and 3
            if self.beat_position == 0 or self.beat_position == 2:
                # check if there's significant bass energy
                if smoothed_band_levels['bass'] > 20:
                    led_values[4] = int(smoothed_band_levels['bass'] * 2.55)  # pin 10 - bass

            # snare on beats 2 and 4
            if self.beat_position == 1 or self.beat_position == 3:
                # check if there's significant snare energy
                if smoothed_band_levels['snares'] > 20:
                    led_values[2] = int(smoothed_band_levels['snares'] * 2.55)  # pin 5 - snares
        else:
            # regular freq-responsive mode without tempo sync
            led_values[2] = int(smoothed_band_levels['snares'] * 2.55)
            led_values[4] = int(smoothed_band_levels['bass'] * 2.55)

        # ensure values are in valid range (0-255)
        led_values = [max(0, min(255, val)) for val in led_values]

        return led_values

    def visualizer_update_thread(self):
        """
        thread function for sending visualizer updates to arduino
        runs continuously while in visualizer mode
        processes audio, detects beats, and sends led vals to arduino
        """
        print("visualizer thread started with tempo synchronization")
        last_debug_time = time.time()

        # use fixed tempo as fallback if beat detection isn't working well
        use_fixed_tempo = True
        fixed_tempo_time = time.time()

        while self.running and current_mode == VISUALIZER_MODE:
            try:
                # use fixed tempo as fallback when beat detection isn't reliable
                current_time = time.time()
                if use_fixed_tempo and (current_time - fixed_tempo_time) >= 60.0 / self.tempo:
                    self.beat_position = (self.beat_position + 1) % 4
                    fixed_tempo_time = current_time
                    if DEBUG:
                        print(f"fixed tempo beat: {self.beat_position + 1}/4")

                # read audio data
                data = self.stream.read(CHUNK, exception_on_overflow=False)

                # process audio - now also returns beat detection status
                band_levels, beat_detected = self.analyze_frequencies(data)

                # if we detected a beat, don't use fixed tempo for the next few cycles
                if beat_detected:
                    fixed_tempo_time = current_time
                    use_fixed_tempo = False
                else:
                    # if we haven't detected a beat in a while, go back to fixed tempo
                    if current_time - self.last_beat_time > 2.0:
                        use_fixed_tempo = True

                # apply smoothing
                smoothed_band_levels = self.smooth_levels(band_levels)

                # map to led values with tempo sync
                led_values = self.map_levels_to_leds(smoothed_band_levels)

                # format data for arduino
                arduino_data = f"L:{','.join(map(str, led_values))}\n"

                # send to arduino
                if self.arduino and self.arduino.is_open:
                    self.arduino.write(arduino_data.encode())
                    if DEBUG and time.time() - last_debug_time > 1.0:
                        print(f"values: {led_values}, beat: {self.beat_position + 1}/4")
                        last_debug_time = time.time()

            except Exception as e:
                print(f"err in visualizer update: {e}")
                traceback.print_exc()

            # control update rate
            time.sleep(UPDATE_RATE / 1000)

    def run(self):
        """
        main function to run the audio ctrl and visualizer
        handles user input, mode switching, and command processing
        this is the main entry point after creating AudioProcessor
        """
        global current_mode

        print("starting audio control system...")

        # connect to arduino
        if not self.connect_arduino():
            print("failed to connect to arduino. exiting.")
            return

        # start audio stream
        if not self.start_audio_stream():
            print("failed to start audio stream. exiting.")
            if self.arduino:
                self.arduino.close()
            return

        # set initial state
        current_volume = self.get_system_volume()
        print(f"current system vol: {current_volume:.1f}%")

        # display instructions
        print("\naudio control system ready!")
        print("==========================")
        print("press the button on arduino to toggle between modes:")
        print("- audio control: potentiometer adjusts system vol")
        print("- animation mode: animation patterns")
        print("- visualizer: leds show audio freqs")
        print("\nspecial commands:")
        print("- tempo_on: enable 4/4 backbeat pattern (bass on 1&3, snare on 2&4)")
        print("- tempo_off: disable pattern (respond directly to freqs)")
        print("- tempo_set:[bpm]: set specific tempo (e.g., tempo_set:120)")
        print("\npress ctrl+c to exit")

        # main loop
        self.running = True
        try:
            while self.running:
                # check for data from arduino
                if self.arduino and self.arduino.in_waiting > 0:
                    data = self.arduino.readline().decode('utf-8', errors='ignore').strip()

                    if len(data) > 0:
                        print(f"arduino >> {data}")

                        # handle mode changes
                        if data == "MODE:VISUALIZER":
                            if current_mode != VISUALIZER_MODE:
                                current_mode = VISUALIZER_MODE
                                print("\nswitched to visualizer mode")

                                # start visualizer thread
                                self.update_thread = threading.Thread(target=self.visualizer_update_thread)
                                self.update_thread.daemon = True
                                self.update_thread.start()

                        elif data == "MODE:ANIMATION":
                            if current_mode == VISUALIZER_MODE:
                                current_mode = ANIMATION_MODE
                                print("\nswitched to animation mode")

                        elif data == "MODE:AUDIO_CONTROL":
                            if current_mode != AUDIO_CONTROL_MODE:
                                current_mode = AUDIO_CONTROL_MODE
                                print("\nswitched to audio control mode")

                        # handle vol control
                        elif data.startswith("VOL:"):
                            try:
                                volume_level = float(data[4:])
                                self.set_system_volume(volume_level)
                                print(f"vol set to {volume_level:.0f}%")
                            except ValueError:
                                pass

                        # add tempo command handling
                        elif data.startswith("CMD:"):
                            command = data[4:]
                            if command == "TEMPO_ON":
                                self.tempo_sync_enabled = True
                                print("tempo sync enabled - 4/4 backbeat pattern active")
                            elif command == "TEMPO_OFF":
                                self.tempo_sync_enabled = False
                                print("tempo sync disabled - leds respond directly to freqs")
                            elif command.startswith("TEMPO_SET:"):
                                try:
                                    new_tempo = float(command[10:])
                                    if 60 <= new_tempo <= 200:
                                        self.tempo = new_tempo
                                        self.beat_duration = 60.0 / self.tempo
                                        print(f"tempo set to {self.tempo} bpm")
                                except ValueError:
                                    pass

                # small delay to prevent excessive cpu usage
                time.sleep(0.01)

        except KeyboardInterrupt:
            print("\nexiting...")
        except Exception as e:
            print(f"\nerr: {e}")
            traceback.print_exc()
        finally:
            self.cleanup()

    def cleanup(self):
        """
        clean up resources before exiting
        closes threads, streams, and connections
        called when program exits
        """
        print("cleaning up...")
        self.running = False

        # stop thread if running
        if self.update_thread and self.update_thread.is_alive():
            try:
                self.update_thread.join(timeout=1.0)
            except:
                pass

        # close audio stream
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        # close pyaudio
        if self.p:
            self.p.terminate()

        # close arduino connection
        if self.arduino and self.arduino.is_open:
            self.arduino.close()

        print("audio control system terminated.")


if __name__ == "__main__":
    # create processor and run it - this is the entry point
    processor = AudioProcessor()
    processor.run()
