// ======================================================
// audio visualizer w/ multi-mode operation - arduino code
// Mustafa Bakir
// April 7th, 2025
// New York University Abu Dhabi
// ======================================================
// this sketch implements a sophisticated audio visualizer system 
// that connects to a computer running the python fft analyzer.
// 
// three op modes:
// 1. audio ctrl mode: pot adjusts sys vol on connected comp
// 2. animation mode: auto-cycling led patterns for ambient lighting
// 3. visualizer mode: leds respond to audio freqs received via serial
// 
// hw config:
// - 5 leds connected to pwm pins (3,9,5,6,10) cus those are PMW pins
// - pushbutton on a0  for mode switching
// - indicator led on pin 2 for status
// - potentiometer on a1 for vol ctrl
// 
// serial protocol:
// - receives led vals as "L:val1,val2,val3,val4,val5"
// - sends mode changes as "MODE:XXXX"
// - sends vol lvl as "VOL:xx"
// 
//
// ======================================================

// pin cfg - all pwm capable for brightness ctrl
const int num_leds = 5;  
const int led_pins[num_leds] = {3, 9, 5, 6, 10};  // pwm pins for freq bands
const int btn_pin = A0;          // mode toggle btn 
const int ind_led_pin = 2;       // status indicator led
const int pot_pin = A1;          // vol ctrl pot

// prog states
enum prog_mode {
  audio_ctrl,      // vol ctrl via pot
  anim_mode,       // pretty light patterns
  viz_mode         // real audio viz
};

prog_mode curr_mode = audio_ctrl;  // start in vol ctrl mode

// btn debounce vars - prevents false triggers from noisy switches
int last_btn_state = HIGH;     // HIGH = not pressed
int btn_state = HIGH;          // curr stable btn state
unsigned long last_debounce_time = 0;  // timestamp of last state change
const int debounce_delay = 50;   // ms to wait for stable reading

// viz settings - stores brightness vals for each led
int viz_brightness[num_leds] = {0, 0, 0, 0, 0};  // init all off

// custom decay rates for each freq band - gives more musical feel
// lower val = faster decay (more responsive to transients)
const float decay_rates[num_leds] = {
  0.6,  // pin 3 - vocals (med decay)
  0.5,  // pin 9 - chords (med decay)
  0.1,  // pin 5 - snares (fast decay for transients)
  0.1,  // pin 6 - claps/hi-hats (fast decay for transients)
  0.3   // pin 10 - bass/kicks (med-fast decay)
};

// anim vars - used to track state of animations
static unsigned long last_anim_update = 0;  // timestamp for anim timing
static int anim_step = 0;  // curr step in animation sequence
const int anim_delay = 30; // ms between anim frames (33fps approx)

// other timing vars
unsigned long last_pot_update = 0;  // prevent flooding serial w/ pot readings
const int pot_update_interval = 100;  // only send pot updates every 100ms

void setup() {
  // init led pins as outputs and turn off
  for (int i = 0; i < num_leds; i++) {
    pinMode(led_pins[i], OUTPUT);
    analogWrite(led_pins[i], 0);  // start w/ leds off (0 brightness)
  }
  
  // setup indicator led for status feedback
  pinMode(ind_led_pin, OUTPUT);
  digitalWrite(ind_led_pin, LOW);  // off by default
  
  // btn setup w/ internal pullup - saves external resistor
  pinMode(btn_pin, INPUT_PULLUP);  // HIGH when not pressed
  
  // init serial comm for talking to python script
  // keep baud rate matching python side
  Serial.begin(9600);
  Serial.println("Audio Visualizer Ready");
  Serial.println("MODE:AUDIO_CONTROL");  // notify host of initial mode
}

void loop() {
  // always check for btn press first - allows mode switching
  check_btn();
  
  // handle curr mode's functionality - cleaner than big if/else blocks
  switch (curr_mode) {
    case audio_ctrl:
      handle_audio_ctrl();  // handle vol ctrl mode
      break;
    case anim_mode:
      handle_animation();   // run led animations
      break;
    case viz_mode:
      handle_visualizer();  // process audio viz data
      break;
  }
}

void check_btn() {
  // read btn state - LOW when pressed (due to pullup)
  int reading = digitalRead(btn_pin);
  
  // reset debounce timer on state change
  if (reading != last_btn_state) {
    last_debounce_time = millis();
  }
  
  // if state stable for debounce period, process it
  if ((millis() - last_debounce_time) > debounce_delay) {
    // only act on actual state changes
    if (reading != btn_state) {
      btn_state = reading;  // update stable state
      
      // if btn was just pressed (LOW)
      if (btn_state == LOW) {
        toggle_mode();  // change operating mode
      }
    }
  }
  
  // save reading for next comparison
  last_btn_state = reading;
}

void toggle_mode() {
  // clean slate - turn off all leds when changing modes
  for (int i = 0; i < num_leds; i++) {
    analogWrite(led_pins[i], 0);
    viz_brightness[i] = 0;  // reset viz state too
  }
  
  // reset animation counters
  anim_step = 0;
  
  // cycle thru modes in sequence - audio->anim->viz->audio...
  switch (curr_mode) {
    case audio_ctrl:
      curr_mode = anim_mode;
      Serial.println("MODE:ANIMATION");  // notify host of mode change
      break;
      
    case anim_mode:
      curr_mode = viz_mode;
      Serial.println("MODE:VISUALIZER");  // notify host
      break;
      
    case viz_mode:
      curr_mode = audio_ctrl;
      Serial.println("MODE:AUDIO_CONTROL");  // notify host
      break;
  }
  
  // visual feedback for mode change
  flash_indicator();
}

void flash_indicator() {
  // quick flash of indicator led to confirm btn press
  digitalWrite(ind_led_pin, HIGH);
  delay(50);  // brief flash - still noticeable
  digitalWrite(ind_led_pin, LOW);
}

void handle_audio_ctrl() {
  // read pot val (0-1023)
  int pot_val = analogRead(pot_pin);
  
  // throttle updates to prevent serial flooding
  // only send updates periodically or on significant changes
  if (millis() - last_pot_update > pot_update_interval) {
    last_pot_update = millis();
    
    // map pot range (0-1023) to vol pct (0-100)
    int vol_pct = map(pot_val, 0, 1023, 0, 100);
    
    // send to host pc
    Serial.print("VOL:");
    Serial.println(vol_pct);
  }
  
  // provide visual feedback of current vol level
  display_vol_level(pot_val);
}

void display_vol_level(int pot_val) {
  // convert pot val (0-1023) to led display w/ fractional brightness
  // gives smooth transition between leds as pot turns
  float led_level = (float)pot_val / 1023.0 * num_leds;
  
  // update each led based on calculated level
  for (int i = 0; i < num_leds; i++) {
    if (i < floor(led_level)) {
      // fully on - below current level
      analogWrite(led_pins[i], 255);
    } else if (i == floor(led_level)) {
      // partially on - fractional part determines brightness
      // creates smooth transition as you turn pot
      float fraction = led_level - floor(led_level);
      int brightness = fraction * 255;
      analogWrite(led_pins[i], brightness);
    } else {
      // fully off - above current level
      analogWrite(led_pins[i], 0);
    }
  }
}

void handle_animation() {
  // update anim only at specified frame rate
  // controls speed of animations to be consistent
  if (millis() - last_anim_update >= anim_delay) {
    last_anim_update = millis();
    
    // auto-cycle between 3 diff patterns every 5 sec
    // gives variety to the light show
    int anim_pattern = (millis() / 5000) % 3;
    
    // run selected pattern
    switch (anim_pattern) {
      case 0: 
        // breathing effect - smooth fade up/down
        {
          // 512 steps total - 256 up, 256 down
          anim_step = (anim_step + 1) % 512;
          int brightness;
          
          if (anim_step < 256) {
            brightness = anim_step;  // fade up 0->255
          } else {
            brightness = 511 - anim_step;  // fade down 255->0
          }
          
          // apply same brightness to all leds
          for (int i = 0; i < num_leds; i++) {
            analogWrite(led_pins[i], brightness);
          }
        }
        break;
        
      case 1:
        // chase effect - single led moving back and forth
        {
          // clear all leds first
          for (int i = 0; i < num_leds; i++) {
            analogWrite(led_pins[i], 0);
          }
          
          // calc position for led bouncing effect
          // total steps = 2*num_leds-2 (accounts for turnaround)
          anim_step = (anim_step + 1) % (2 * num_leds - 1);
          
          // decide if we're moving forward or backward
          if (anim_step < num_leds) {
            // forward phase - left to right
            analogWrite(led_pins[anim_step], 255);
          } else {
            // reverse phase - right to left
            // math converts position to correct reverse index
            analogWrite(led_pins[2 * num_leds - anim_step - 2], 255);
          }
        }
        break;
        
      case 2:
        // alternating pattern - on/off in groups
        {
          // 16-step pattern for more interesting effect
          anim_step = (anim_step + 1) % 16;
          
          // alternate groups of leds on/off
          for (int i = 0; i < num_leds; i++) {
            // creates wave-like pattern with groups of 2
            if ((anim_step + i) % 4 < 2) {
              analogWrite(led_pins[i], 255);  // on
            } else {
              analogWrite(led_pins[i], 0);    // off
            }
          }
        }
        break;
    }
  }
}

void handle_visualizer() {
  // two main tasks in viz mode:
  
  // 1. check for new data from host
  process_serial_data();
  
  // 2. handle fade-out effects between updates
  apply_decay_effect();
}

void process_serial_data() {
  // check if data available on serial port
  if (Serial.available() > 0) {
    // read full line (terminated by newline)
    String data = Serial.readStringUntil('\n');
    
    // check if it's led data format "L:val1,val2,val3,val4,val5"
    if (data.startsWith("L:")) {  
      // strip the "L:" prefix
      data = data.substring(2);
      
      // parse the csv values
      int index = 0;
      int start_pos = 0;
      int comma_pos;
      
      // extract each val up to comma
      while ((comma_pos = data.indexOf(',', start_pos)) >= 0 && index < num_leds) {
        String val_str = data.substring(start_pos, comma_pos);
        viz_brightness[index] = val_str.toInt();  // convert to int
        start_pos = comma_pos + 1;  // move past comma
        index++;
      }
      
      // handle final value (after last comma)
      if (start_pos < data.length() && index < num_leds) {
        String val_str = data.substring(start_pos);
        viz_brightness[index] = val_str.toInt();
      }
      
      // apply new brightness vals to leds
      update_leds();
    }
    
    // other cmd types could be parsed here
    // e.g. if (data.startsWith("CMD:"))...
  }
}

void update_leds() {
  // apply current brightness vals to physical leds
  for (int i = 0; i < num_leds; i++) {
    analogWrite(led_pins[i], viz_brightness[i]);
  }
}

void apply_decay_effect() {
  // controls how leds fade out when audio stops
  // creates natural trailing effect - more musical
  static unsigned long last_decay_time = 0;
  
  // apply decay every 50ms
  if (millis() - last_decay_time > 50) {
    last_decay_time = millis();
    
    bool updated = false;  // track if any led changed
    
    // process each led
    for (int i = 0; i < num_leds; i++) {
      if (viz_brightness[i] > 1) {
        // apply band-specific decay rate for natural feel
        // multiplying by <1 gradually reduces value
        viz_brightness[i] *= decay_rates[i];
        updated = true;
      } else if (viz_brightness[i] > 0) {
        // floor at 0 to prevent weird behavior
        viz_brightness[i] = 0;
        updated = true;
      }
    }
    
    // only update physical leds if something changed
    // saves unnecessary writes
    if (updated) {
      update_leds();
    }
  }
}
