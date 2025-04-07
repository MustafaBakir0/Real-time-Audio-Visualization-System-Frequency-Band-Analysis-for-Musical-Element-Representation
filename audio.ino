const int numLEDs = 5;
const int ledPins[numLEDs] = {3, 4, 5, 6, 7}; 
const int buttonPin = A0; 
const int potPin = A1;
const int animationDelay = 200;

// Program states
enum ProgramMode {
  POT_MODE,        // Control via potentiometer
  ANIMATION_MODE,  // Sequential animation
  VISUALIZER_MODE  // Audio visualizer
};

ProgramMode currentMode = POT_MODE;

int lastButtonState = LOW;  // For button without pull-up
int currentButtonState = LOW;
unsigned long lastDebounceTime = 0;
const int debounceDelay = 50;

// Visualizer settings
int visualizerBrightness[numLEDs] = {0, 0, 0, 0, 0};
const float decayRate = 0.8; // How quickly the visualization falls

void setup() {
  // Initialize LED pins as outputs
  for (int i = 0; i < numLEDs; i++) {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }
  
  // Button without pull-up
  pinMode(buttonPin, INPUT);
  
  // Initialize serial for computer communication
  Serial.begin(9600);
  Serial.println("Music Visualizer Ready");
}

void loop() {
  // Process button
  handleButton();
  
  // Handle serial input for visualizer mode
  if (currentMode == VISUALIZER_MODE) {
    processSerialData();
  }
  
  // Handle LED control based on current mode
  switch(currentMode) {
    case POT_MODE:
      controlLEDsWithPot();
      break;
    case ANIMATION_MODE:
      runAnimation();
      break;
    case VISUALIZER_MODE:
      // LED updates are handled in processSerialData()
      // Apply decay effect when no data is coming
      applyDecayEffect();
      break;
  }
}

void handleButton() {
  // Read button and handle debounce
  int reading = digitalRead(buttonPin);
  
  // If button reading changed, reset debounce timer
  if (reading != lastButtonState) {
    lastDebounceTime = millis();
  }
  
  // Check if button state has been stable long enough
  if ((millis() - lastDebounceTime) > debounceDelay) {
    // If button state has changed
    if (reading != currentButtonState) {
      currentButtonState = reading;
      
      // If button is pressed (HIGH when pressed, no pull-up)
      if (currentButtonState == HIGH && lastButtonState == LOW) {
        // Cycle through modes
        switch(currentMode) {
          case POT_MODE:
            currentMode = ANIMATION_MODE;
            break;
          case ANIMATION_MODE:
            currentMode = VISUALIZER_MODE;
            Serial.println("VISUALIZER");  // Signal to computer
            break;
          case VISUALIZER_MODE:
            currentMode = POT_MODE;
            break;
        }
        
        // Turn off all LEDs when toggling mode
        for (int i = 0; i < numLEDs; i++) {
          digitalWrite(ledPins[i], LOW);
        }
      }
    }
  }
  
  lastButtonState = reading;
}

void processSerialData() {
  if (Serial.available() > 0) {
    String data = Serial.readStringUntil('\n');
    
    // Check if it's an LED level command (L:val1,val2,val3,val4,val5)
    if (data.startsWith("L:")) {
      // Remove the "L:" prefix
      data = data.substring(2);
      
      // Parse comma-separated values
      int index = 0;
      int lastCommaIndex = -1;
      int nextCommaIndex = data.indexOf(',');
      
      while (index < numLEDs && nextCommaIndex != -1) {
        String valueStr = data.substring(lastCommaIndex + 1, nextCommaIndex);
        visualizerBrightness[index] = valueStr.toInt();
        
        lastCommaIndex = nextCommaIndex;
        nextCommaIndex = data.indexOf(',', lastCommaIndex + 1);
        index++;
      }
      
      // Get the last value
      if (index < numLEDs) {
        String valueStr = data.substring(lastCommaIndex + 1);
        visualizerBrightness[index] = valueStr.toInt();
      }
      
      // Update LEDs with new brightness values
      updateLEDs();
    }
  }
}

void updateLEDs() {
  // Update all LEDs with current brightness
  for (int i = 0; i < numLEDs; i++) {
    // Handle PWM vs non-PWM pins
    if (ledPins[i] == 3 || ledPins[i] == 5 || ledPins[i] == 6) {
      analogWrite(ledPins[i], visualizerBrightness[i]);
    } else {
      // For non-PWM pins, use threshold
      digitalWrite(ledPins[i], (visualizerBrightness[i] > 127) ? HIGH : LOW);
    }
  }
}

void applyDecayEffect() {
  static unsigned long lastDecayTime = 0;
  
  if (millis() - lastDecayTime > 50) {  // Apply decay every 50ms
    lastDecayTime = millis();
    
    for (int i = 0; i < numLEDs; i++) {
      visualizerBrightness[i] *= decayRate;
    }
    
    updateLEDs();
  }
}

void controlLEDsWithPot() {
  // Read potentiometer value (0-1023)
  int potValue = analogRead(potPin);
  
  // Calculate how many LEDs should be fully on (0 to numLEDs)
  float ledLevel = (float)potValue / 1023.0 * numLEDs;
  
  // Control each LED - with special handling for non-PWM pins
  for (int i = 0; i < numLEDs; i++) {
    if (i < floor(ledLevel)) {
      // Fully on
      digitalWrite(ledPins[i], HIGH);
    } else if (i == floor(ledLevel)) {
      // Partially on (the fractional part determines brightness)
      float fraction = ledLevel - floor(ledLevel);
      
      // For PWM pins (3, 5, 6), use analogWrite
      if (ledPins[i] == 3 || ledPins[i] == 5 || ledPins[i] == 6) {
        int brightness = fraction * 255;
        analogWrite(ledPins[i], brightness);
      } 
      // For non-PWM pins (4, 7), use a threshold to turn on/off
      else {
        digitalWrite(ledPins[i], (fraction > 0.5) ? HIGH : LOW);
      }
    } else {
      // Off
      digitalWrite(ledPins[i], LOW);
    }
  }
}

void runAnimation() {
  static unsigned long lastAnimationStep = 0;
  static int animationState = 0;
  
  // Only update animation at specified intervals
  if (millis() - lastAnimationStep >= animationDelay) {
    lastAnimationStep = millis();
    
    // State 0-4: Turn LEDs on sequentially
    // State 5-9: Turn LEDs off sequentially
    if (animationState < numLEDs) {
      digitalWrite(ledPins[animationState], HIGH);
    } else if (animationState < 2 * numLEDs) {
      digitalWrite(ledPins[animationState - numLEDs], LOW);
    }
    
    // Increment state and reset if needed
    animationState = (animationState + 1) % (2 * numLEDs);
  }
}