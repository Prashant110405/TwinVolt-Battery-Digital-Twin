/*
  Twin Volt ESP32 Wi-Fi telemetry bridge
  Sends physical sensor readings to the existing TwinVolt FastAPI backend.
  Existing frontend files and visual design are unchanged.

  Endpoint: http://<COMPUTER_LAN_IP>:8000/api/v1/telemetry/ingest
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <math.h>
#include <string.h>

// ---------- Wi-Fi ----------
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Use the backend computer's LAN IPv4 address, NOT localhost/127.0.0.1.
const char* TWINVOLT_SERVER_HOST = "192.168.1.100";
const uint16_t TWINVOLT_SERVER_PORT = 8000;
const char* TWINVOLT_INGEST_PATH = "/api/v1/telemetry/ingest";

// Must match a twin in the dashboard selector.
const char* TARGET_SYSTEM_ID = "twin_prototype_3s1p";
const char* DEVICE_ID = "TWIN-VOLT-001";

// ---------- Pins from your supplied Twin Volt code ----------
#define BUZZER 4
#define ACS712_PIN 35
#define VOLTAGE_PIN 33
#define LM35_PIN 32

// ---------- Calibration from your supplied code ----------
float sensitivity = 0.185f;
float offset = 1.65f;
float VOLTAGE_MULTIPLIER = 6.2f;
float MAX_VOLTAGE = 12.6f;
float MIN_VOLTAGE = 5.0f;

float voltage = 0.0f;
float current = 0.0f;
float temperature = 0.0f;
float SOC = 0.0f;
float SOH = 100.0f;
bool batteryDisconnected = true;

const unsigned long INTERVAL_MS = 3000;
unsigned long lastReadingTime = 0;

float calculateSOC(float v) {
  float soc = ((v - MIN_VOLTAGE) / (MAX_VOLTAGE - MIN_VOLTAGE)) * 100.0f;
  return constrain(soc, 0.0f, 100.0f);
}

float calculateSOH(float i) {
  float health = 100.0f - (fabsf(i) * 2.0f);
  return constrain(health, 50.0f, 100.0f);
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi connected");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi connection timed out; will retry in loop.");
  }
}

void readSensors() {
  int vRaw = analogRead(VOLTAGE_PIN);
  float vADC = (vRaw / 4095.0f) * 3.3f;
  voltage = vADC * VOLTAGE_MULTIPLIER;

  int cRaw = analogRead(ACS712_PIN);
  float vACS = (cRaw / 4095.0f) * 3.3f;
  current = (vACS - offset) / sensitivity;

  int tRaw = analogRead(LM35_PIN);
  float tVolt = (tRaw / 4095.0f) * 3.3f;
  temperature = (tVolt * 100.0f) + 5.0f;

  SOC = calculateSOC(voltage);
  SOH = calculateSOH(current);
  batteryDisconnected = voltage < 1.0f;
  digitalWrite(BUZZER, batteryDisconnected ? HIGH : LOW);
}

void printReadings() {
  Serial.println("=================================");
  Serial.printf("Device: %s\n", DEVICE_ID);
  Serial.printf("Battery Status: %s\n", batteryDisconnected ? "DISCONNECTED" : "CONNECTED");
  Serial.printf("Voltage: %.2f V\n", voltage);
  Serial.printf("Current: %.3f A\n", current);
  Serial.printf("Temperature: %.2f C\n", temperature);
  Serial.printf("SOC: %.1f %%\n", SOC);
  Serial.printf("SOH estimate: %.1f %%\n", SOH);
  Serial.println("=================================");
}

void sendDataToServer() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi not connected; skipping HTTP POST.");
    return;
  }

  WiFiClient client;
  HTTPClient http;
  char url[160];
  snprintf(url, sizeof(url), "http://%s:%u%s", TWINVOLT_SERVER_HOST,
           TWINVOLT_SERVER_PORT, TWINVOLT_INGEST_PATH);

  // The existing backend expects system_id + raw_data + format_identifier.
  char payload[640];
  snprintf(payload, sizeof(payload),
    "{\"system_id\":\"%s\",\"format_identifier\":\"JSON\",\"raw_data\":{"
    "\"system_id\":\"%s\",\"device_id\":\"%s\","
    "\"pack_voltage_v\":%.3f,\"pack_current_a\":%.3f,\"pack_power_w\":%.3f,"
    "\"ambient_temperature_c\":%.2f,\"soc_fraction\":%.5f,\"soh_fraction\":%.5f,"
    "\"metadata\":{\"source\":\"esp32_hardware\",\"battery_status\":\"%s\"}}}",
    TARGET_SYSTEM_ID, TARGET_SYSTEM_ID, DEVICE_ID,
    voltage, current, voltage * current, temperature,
    SOC / 100.0f, SOH / 100.0f,
    batteryDisconnected ? "DISCONNECTED" : "CONNECTED");

  http.setTimeout(4000);
  if (!http.begin(client, url)) {
    Serial.println("Could not initialize HTTP connection.");
    return;
  }
  http.addHeader("Content-Type", "application/json");
  int responseCode = http.POST((uint8_t*)payload, strlen(payload));
  Serial.printf("HTTP response code: %d\n", responseCode);
  if (responseCode > 0) {
    Serial.print("Backend response: ");
    Serial.println(http.getString());
  } else {
    Serial.print("HTTP POST failed: ");
    Serial.println(http.errorToString(responseCode));
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);
  analogReadResolution(12);
  connectWiFi();
  Serial.println("TWIN VOLT - ESP32 Wi-Fi telemetry started");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastReconnectAttempt = 0;
    if (millis() - lastReconnectAttempt >= 5000) {
      lastReconnectAttempt = millis();
      Serial.println("Attempting Wi-Fi reconnect...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
  }

  if (millis() - lastReadingTime >= INTERVAL_MS) {
    lastReadingTime = millis();
    readSensors();
    printReadings();
    sendDataToServer();
  }
}
