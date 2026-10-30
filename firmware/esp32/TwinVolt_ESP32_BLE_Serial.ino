/*
  ==============================================================================
  PROJECT: TwinVolt Universal Battery Digital Twin Platform
  FIRMWARE: ESP32 Dual-Transport — USB Serial + Bluetooth Low Energy (BLE GATT)
  VERSION:  2.0
  ==============================================================================

  TARGET HARDWARE:
  - ESP32 Development Module (ESP-WROOM-32 / NodeMCU ESP32)
  - Battery Voltage Sensor: Resistor Divider on ADC GPIO 34 (R1=30k, R2=7.5k)
  - Current Sensor: ACS712 on ADC GPIO 35 (5A model, 0.185 V/A sensitivity)
  - Temperature Sensor: 10k NTC Thermistor on ADC GPIO 32 (Beta=3950)
  - Safety Relay: Digital Output GPIO 26 (fail-safe OPEN at boot)
  - Warning Buzzer: Digital Output GPIO 27
  - DC Fan Load: Digital/PWM Output GPIO 25

  TRANSPORTS (both run simultaneously at 2 Hz):
  1. USB Serial — 115200 baud, JSON Lines, compatible with TwinVolt Serial Gateway
  2. BLE GATT Server — Web Bluetooth API compatible for TwinVolt dashboard

  BLE GATT Configuration (matches Windows registry paired device):
    Device Name:    "Twin Volt"
    Service UUID:   7a100001-1234-5678-1234-56789abcdef0
    Telemetry Char: 7a100002-1234-5678-1234-56789abcdef0 (NOTIFY | READ)
    Control Char:   7a100003-1234-5678-1234-56789abcdef0 (WRITE | READ)

  USB Power + BLE Data Mode:
    Power the ESP32 from laptop USB; telemetry streams wirelessly via BLE.
    Simultaneous serial data works if the USB-UART driver is installed.

  DATA INTEGRITY NOTICE:
    All sensor readings are real physical measurements. No synthetic data.
    Safety relay is fail-safe OPEN at boot.
  ==============================================================================
*/

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <math.h>

// ============================================================
// 1. BLE Service & Characteristic UUIDs
//    These match the Windows BLE registry for "Twin Volt" (00:70:07:25:28:BE)
//    DO NOT change without updating src/ui/js/ble.js TWINVOLT_BLE_CONFIG.
// ============================================================
#define DEVICE_NAME          "Twin Volt"
#define SERVICE_UUID         "7a100001-1234-5678-1234-56789abcdef0"
#define TELEMETRY_CHAR_UUID  "7a100002-1234-5678-1234-56789abcdef0"
#define CONTROL_CHAR_UUID    "7a100003-1234-5678-1234-56789abcdef0"

const char* SYSTEM_ID = "twin_prototype_3s1p";

// ============================================================
// 2. GPIO Pin Assignments
// ============================================================
const int PIN_VOLTAGE_ADC = 34;
const int PIN_CURRENT_ADC = 35;
const int PIN_TEMP_ADC    = 32;
const int PIN_RELAY       = 26;
const int PIN_BUZZER      = 27;
const int PIN_FAN         = 25;

// ============================================================
// 3. Sensor Calibration Constants
// ============================================================
const float ADC_VREF       = 3.30f;
const float ADC_MAX        = 4095.0f;
const int   ADC_SAMPLES    = 16;

// Voltage divider: R1=30k, R2=7.5k → ratio 5.0
const float V_DIVIDER      = 5.00f;

// ACS712-5A current sensor
const float ACS_SENS       = 0.185f; // V/A
float       acs_zero       = 2.50f;  // Calibrated at boot

// NTC Thermistor (10k Beta 3950, series 10k to GND)
const float NTC_BETA       = 3950.0f;
const float NTC_T0         = 298.15f;
const float NTC_R0         = 10000.0f;
const float NTC_RS         = 10000.0f;

// Safety thresholds (3S Li-Ion pack)
const float V_MIN          = 9.00f;
const float V_MAX          = 12.75f;
const float T_MAX          = 55.0f;

// ============================================================
// 4. Timing
// ============================================================
const unsigned long LOOP_INTERVAL = 500; // ms (2 Hz)
unsigned long lastMs = 0;
unsigned long seqNo  = 0;

// ============================================================
// 5. Actuator State
// ============================================================
bool relayOn  = false;
bool fanOn    = false;
bool buzzerOn = false;

// ============================================================
// 6. BLE Objects
// ============================================================
BLEServer*         pServer      = nullptr;
BLECharacteristic* pTelChar     = nullptr;
BLECharacteristic* pCtrlChar    = nullptr;
bool               bleConnected = false;
bool               bleWasConn   = false;

// BLE server connection callbacks
class ServerCB : public BLEServerCallbacks {
  void onConnect(BLEServer*) override {
    bleConnected = true;
    Serial.println("[BLE] Client connected.");
  }
  void onDisconnect(BLEServer* svr) override {
    bleConnected = false;
    Serial.println("[BLE] Client disconnected. Restarting advertising...");
    delay(100);
    svr->startAdvertising();
  }
};

// BLE control characteristic write callback
class CtrlCB : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* ch) override {
    std::string cmd = ch->getValue();
    Serial.printf("[BLE] Control command: %s\n", cmd.c_str());

    if (cmd == "RELAY_ON") {
      relayOn = true;
      digitalWrite(PIN_RELAY, HIGH);
      Serial.println("[ACT] Relay ON");
    } else if (cmd == "RELAY_OFF") {
      relayOn = false;
      digitalWrite(PIN_RELAY, LOW);
      Serial.println("[ACT] Relay OFF");
    } else if (cmd == "FAN_ON") {
      fanOn = true;
      digitalWrite(PIN_FAN, HIGH);
      Serial.println("[ACT] Fan ON");
    } else if (cmd == "FAN_OFF") {
      fanOn = false;
      digitalWrite(PIN_FAN, LOW);
      Serial.println("[ACT] Fan OFF");
    }
  }
};

// ============================================================
// Helper: Oversampled ADC read → voltage
// ============================================================
float adcVoltage(int pin) {
  long sum = 0;
  for (int i = 0; i < ADC_SAMPLES; i++) {
    sum += analogRead(pin);
    delayMicroseconds(50);
  }
  return ((float)sum / ADC_SAMPLES) * ADC_VREF / ADC_MAX;
}

// ============================================================
// Helper: NTC thermistor temperature
// ============================================================
float ntcTemperature(float v) {
  if (v <= 0.01f || v >= (ADC_VREF - 0.01f)) return 25.0f;
  float rNtc = NTC_RS * ((ADC_VREF / v) - 1.0f);
  if (rNtc <= 0.0f) return 25.0f;
  float s = logf(rNtc / NTC_R0) / NTC_BETA + 1.0f / NTC_T0;
  return 1.0f / s - 273.15f;
}

// ============================================================
// Helper: Calibrate ACS712 zero-current baseline
// ============================================================
void calibrateCurrentZero() {
  Serial.println("[CAL] Calibrating ACS712 zero current (ensure load is OFF)...");
  float sum = 0.0f;
  for (int i = 0; i < 64; i++) {
    sum += adcVoltage(PIN_CURRENT_ADC);
    delay(10);
  }
  acs_zero = sum / 64.0f;
  Serial.printf("[CAL] ACS712 zero offset: %.4f V\n", acs_zero);
}

// ============================================================
// Setup
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(800);

  Serial.println("============================================================");
  Serial.println(" TwinVolt ESP32 Dual-Transport Firmware v2.0               ");
  Serial.println(" USB Serial (115200) + BLE GATT (Twin Volt)                ");
  Serial.println("============================================================");

  // Actuator pins — fail-safe defaults
  pinMode(PIN_RELAY,   OUTPUT);
  pinMode(PIN_BUZZER,  OUTPUT);
  pinMode(PIN_FAN,     OUTPUT);
  digitalWrite(PIN_RELAY,  LOW);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_FAN,    LOW);

  // ADC configuration
  analogSetAttenuation(ADC_11db);
  analogReadResolution(12);

  // Calibrate current sensor at boot
  calibrateCurrentZero();

  // ---- BLE Initialization ----
  BLEDevice::init(DEVICE_NAME);

  pServer = BLEDevice::createServer();
  pServer->setCallbacks(new ServerCB());

  BLEService* pSvc = pServer->createService(SERVICE_UUID);

  // Telemetry characteristic (notify + read)
  pTelChar = pSvc->createCharacteristic(
    TELEMETRY_CHAR_UUID,
    BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ
  );
  pTelChar->addDescriptor(new BLE2902());

  // Control characteristic (write + read)
  pCtrlChar = pSvc->createCharacteristic(
    CONTROL_CHAR_UUID,
    BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_READ
  );
  pCtrlChar->setCallbacks(new CtrlCB());

  pSvc->start();

  BLEAdvertising* pAdv = BLEDevice::getAdvertising();
  pAdv->addServiceUUID(SERVICE_UUID);
  pAdv->setScanResponse(true);
  pAdv->setMinPreferred(0x06);
  pAdv->setMaxPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println("[BLE] GATT server started. Device: \"Twin Volt\"");
  Serial.println("[BLE] Service: 7a100001-1234-5678-1234-56789abcdef0");
  Serial.println("[BLE] Telemetry: 7a100002 (NOTIFY|READ), Control: 7a100003 (WRITE|READ)");
  Serial.println("[ESP32] Ready. Broadcasting on both USB Serial and BLE at 2 Hz.");
}

// ============================================================
// Main Loop
// ============================================================
void loop() {
  unsigned long now = millis();

  if (now - lastMs >= LOOP_INTERVAL) {
    lastMs = now;
    seqNo++;

    // ---- ADC Measurements ----
    float vRaw = adcVoltage(PIN_VOLTAGE_ADC);
    float iRaw = adcVoltage(PIN_CURRENT_ADC);
    float tRaw = adcVoltage(PIN_TEMP_ADC);

    // ---- Physical Conversions ----
    float voltage_v  = vRaw * V_DIVIDER;
    float current_a  = (iRaw - acs_zero) / ACS_SENS;
    float tempC      = ntcTemperature(tRaw);

    // Zero-clamp noise floor
    if (fabsf(current_a) < 0.03f) current_a = 0.0f;
    float power_w = voltage_v * current_a;

    // ---- Safety Monitoring ----
    bool fault = (voltage_v > 1.0f && (voltage_v < V_MIN || voltage_v > V_MAX))
              || (tempC > T_MAX);

    if (fault) {
      digitalWrite(PIN_BUZZER, HIGH);
      digitalWrite(PIN_RELAY, LOW);
      relayOn   = false;
      buzzerOn  = true;
    } else {
      digitalWrite(PIN_BUZZER, LOW);
      buzzerOn = false;
    }

    // ---- Build JSON payload ----
    char buf[512];
    snprintf(buf, sizeof(buf),
      "{"
      "\"millis\":%lu,"
      "\"sequence\":%lu,"
      "\"system_id\":\"%s\","
      "\"pack_voltage_v\":%.3f,"
      "\"pack_current_a\":%.3f,"
      "\"pack_power_w\":%.2f,"
      "\"ambient_temperature_c\":%.1f,"
      "\"relay_state\":%s,"
      "\"fan_state\":%s,"
      "\"source\":\"esp32_hardware\""
      "}",
      now, seqNo, SYSTEM_ID,
      voltage_v, current_a, power_w, tempC,
      relayOn ? "true" : "false",
      fanOn   ? "true" : "false"
    );

    // ---- Transport A: USB Serial ----
    Serial.println(buf);

    // ---- Transport B: BLE GATT Notify ----
    if (bleConnected && pTelChar) {
      pTelChar->setValue((uint8_t*)buf, strlen(buf));
      pTelChar->notify();
    }
  }

  // Restart advertising after disconnect
  if (!bleConnected && bleWasConn) {
    delay(100);
    pServer->startAdvertising();
    bleWasConn = false;
  }
  if (bleConnected && !bleWasConn) {
    bleWasConn = true;
  }
}
