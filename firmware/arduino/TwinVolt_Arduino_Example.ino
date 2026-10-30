/*
  TwinVolt — Universal Battery Digital Twin Platform
  Reference Hardware Telemetry Sketch (Arduino / ESP32 / Teensy)

  DISCLAIMER:
  This sketch provides a reference telemetry output structure for streaming
  battery voltage, current, and temperature over USB Serial into TwinVolt.
  Calibrate sensor conversions (voltage dividers, shunts, thermistors)
  according to your specific hardware setup before connecting live battery cells.
*/

// Configuration
const unsigned long BAUD_RATE = 115200;
const unsigned long SAMPLE_INTERVAL_MS = 500; // 2 Hz telemetry rate

// Operational Mode:
// Set to 1 ONLY for offline bench demonstration without physical sensors connected.
// Set to 0 for real physical battery and sensor integration (Default: 0).
#define BENCH_DEMO_MODE 0

// Pin Assignments (Adjust according to your board wiring)
const int PIN_VOLTAGE_ADC = A0;      // Analog input connected to voltage divider
const int PIN_CURRENT_ADC = A1;      // Analog input connected to shunt / ACS712
const int PIN_TEMP_ADC    = A2;      // Analog input connected to NTC thermistor

// Sensor Calibration Constants (Calibrate for your physical circuit)
const float ADC_REF_VOLTAGE = 5.0;       // MCU ADC reference (5.0V for Uno/Nano, 3.3V for ESP32)
const float ADC_RESOLUTION  = 1023.0;    // 10-bit ADC (use 4095.0 for ESP32 12-bit)
const float VOLTAGE_DIVIDER_RATIO = 1.0; // (R1 + R2) / R2 multiplier for voltage divider
const float ACS712_SENSITIVITY_V_PER_A = 0.185; // 0.185 for 5A model, 0.100 for 20A, 0.066 for 30A
const int ACS712_ZERO_OFFSET_RAW = 512;  // Midpoint ADC reading at 0 Amps (e.g., 512 for 10-bit 5V)

unsigned long lastSampleTime = 0;

void setup() {
  // Initialize USB serial communication
  Serial.begin(BAUD_RATE);
  while (!Serial && millis() < 3000) {
    // Wait for USB connection (Leonardo/Micro/Teensy/SAMD)
  }

  // Print startup identification (ignored cleanly by TwinVolt parser)
  Serial.println("TwinVolt Hardware Telemetry Bridge v1.0 Initialized");
#if BENCH_DEMO_MODE
  Serial.println("[NOTICE] Operating in BENCH DEMO MODE (Synthetic Fallbacks Active)");
#endif
}

void loop() {
  unsigned long currentTime = millis();

  if (currentTime - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = currentTime;

    // 1. Read Raw ADC Values
    int rawVoltage = analogRead(PIN_VOLTAGE_ADC);
    int rawCurrent = analogRead(PIN_CURRENT_ADC);
    int rawTemp    = analogRead(PIN_TEMP_ADC);

    // 2. Convert to Physical SI Units (Real Hardware Pipeline)
    float measuredVoltage_V = (rawVoltage * (ADC_REF_VOLTAGE / ADC_RESOLUTION)) * VOLTAGE_DIVIDER_RATIO;
    float measuredCurrent_A = ((rawCurrent - ACS712_ZERO_OFFSET_RAW) * (ADC_REF_VOLTAGE / ADC_RESOLUTION)) / ACS712_SENSITIVITY_V_PER_A;

    // Approximate NTC thermistor reading (10k NTC with 10k pull-down at 25C)
    float measuredTemp_C = 25.0;
    if (rawTemp > 0 && rawTemp < (int)ADC_RESOLUTION) {
      float rThermistor = 10000.0 * ((ADC_RESOLUTION / (float)rawTemp) - 1.0);
      if (rThermistor > 0.0) {
        // Steinhart-Hart B-parameter approximation (B=3950, T0=298.15K)
        float steinhart = rThermistor / 10000.0;
        steinhart = log(steinhart);
        steinhart /= 3950.0;
        steinhart += 1.0 / (25.0 + 273.15);
        steinhart = 1.0 / steinhart;
        measuredTemp_C = steinhart - 273.15;
      }
    }

#if BENCH_DEMO_MODE
    // Bench demonstration overrides ONLY when BENCH_DEMO_MODE is explicitly enabled:
    if (measuredVoltage_V <= 0.1) {
      measuredVoltage_V = 3.70 + (sin(currentTime / 5000.0) * 0.05);
    }
    if (abs(measuredCurrent_A) > 50.0 || rawCurrent < 10) {
      measuredCurrent_A = 1.25 + (cos(currentTime / 4000.0) * 0.15);
    }
#endif

    // 3. Emit Telemetry in JSON Lines Format
    Serial.print("{\"millis\":");
    Serial.print(currentTime);
    Serial.print(",\"voltage_v\":");
    Serial.print(measuredVoltage_V, 3);
    Serial.print(",\"current_a\":");
    Serial.print(measuredCurrent_A, 3);
    Serial.print(",\"temperature_c\":");
    Serial.print(measuredTemp_C, 2);
#if BENCH_DEMO_MODE
    Serial.print(",\"demo\":true");
#endif
    Serial.println("}");
  }
}

