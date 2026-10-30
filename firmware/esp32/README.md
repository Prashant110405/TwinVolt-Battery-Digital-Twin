# TwinVolt ESP32 Hardware Integration Guide

This guide describes the physical wiring, calibration procedures, and firmware configuration for integrating an **ESP32-based battery parameter monitoring prototype** with the **TwinVolt Universal Battery Digital Twin Platform**.

---

## 1. Physical Hardware BOM (Bill of Materials)

| Component | Specification / Model | Function |
|---|---|---|
| **Microcontroller** | ESP32-WROOM-32 / NodeMCU ESP32 (30-pin or 38-pin) | Real-time ADC sampling, calculation, Wi-Fi & Serial transport |
| **Voltage Sensor** | Precision Resistor Divider (e.g., $R_1 = 30\,\text{k}\Omega$, $R_2 = 7.5\,\text{k}\Omega$) | Steps down pack voltage ($0 - 16.5\,\text{V}$) to ESP32 ADC ($0 - 3.3\,\text{V}$) |
| **Current Sensor** | Allegro ACS712 Hall-Effect Module (5A, 20A, or 30A model) | Bi-directional current sensing with galvanic isolation |
| **Temperature Sensor** | 10k NTC Thermistor ($B = 3950\,\text{K}$) with $10\,\text{k}\Omega$ pull-down | Battery pack surface temperature monitoring |
| **Safety Relay** | 1-Channel 5V Relay Module with optocoupler isolation | Fail-safe load isolation / safety cutoff |
| **Alarm Buzzer** | Active 5V Buzzer | Audible alert on overvoltage, undervoltage, or thermal runaway risk |
| **DC Fan Load** | 12V / 5V DC brushless fan | Switchable electrical test load & cell cooling |
| **Battery Pack** | 1S, 2S, or 3S Lithium-Ion / LiFePO4 pack | Monitored energy storage system |
| **Power Supply** | 5V 2A USB power supply / buck converter | Powers ESP32, ACS712, relay coil, and buzzer |

---

## 2. Complete Wiring & Pinout Diagram

> [!WARNING]
> **ESP32 ADC Input Voltage Limit:** Never expose ESP32 GPIO pins to voltages exceeding **3.3V**. Always verify divider outputs with a digital multimeter before wiring to the ESP32.

### Pinout Mapping Table

| Component Pin | ESP32 GPIO | Channel / Function | Signal Type | Notes |
|---|---|---|---|---|
| **Voltage Divider V_OUT** | **GPIO 34** | `ADC1_CH6` | Analog Input | High-impedance input-only pin; ideal for analog sensing |
| **Current Sensor V_OUT** | **GPIO 35** | `ADC1_CH7` | Analog Input | High-impedance input-only pin; ACS712 output |
| **NTC Thermistor Junction** | **GPIO 32** | `ADC1_CH4` | Analog Input | Midpoint between NTC and $10\,\text{k}\Omega$ resistor |
| **Relay Signal (IN)** | **GPIO 26** | Digital Output | Active HIGH / LOW | Controlled safety disconnect switch |
| **Buzzer Signal (+)** | **GPIO 27** | Digital Output | Active HIGH | Warning alarm for limit violations |
| **DC Fan Switch Gate** | **GPIO 25** | Digital / PWM | Load / Cooling | Gate of N-channel MOSFET driving DC Fan |

---

## 3. Sensor Circuit Schematics & Formulas

### A. Voltage Divider Circuit
Connect battery positive ($V_{\text{pack}}^+$) to $R_1$, the junction to ESP32 GPIO 34, and $R_2$ to Common Ground:
```text
Battery (+) ----[ R1: 30 kΩ ]----+----> To ESP32 GPIO 34 (ADC)
                                 |
                               [ R2: 7.5 kΩ ]
                                 |
Battery (-) ---------------------+---- Common GND
```
**Voltage Formula:**
$$V_{\text{measured}} = V_{\text{ADC}} \times \frac{R_1 + R_2}{R_2} = V_{\text{ADC}} \times 5.00$$

### B. ACS712 Current Sensor Circuit
- Connect ACS712 $V_{\text{CC}}$ to $5\,\text{V}$ and GND to Common GND.
- Connect terminal block pins in series with the battery load.
- Connect sensor `OUT` to ESP32 GPIO 35.
- **Formula:**
$$I_{\text{pack}} = \frac{V_{\text{ADC}} - V_{\text{zero}}}{\text{Sensitivity}}$$
  - ACS712-05B: $\text{Sensitivity} = 0.185\,\text{V/A}$
  - ACS712-20A: $\text{Sensitivity} = 0.100\,\text{V/A}$
  - ACS712-30A: $\text{Sensitivity} = 0.066\,\text{V/A}$

### C. NTC Thermistor Circuit
```text
3.3V --------- [ NTC: 10 kΩ @ 25°C ] ----+----> To ESP32 GPIO 32 (ADC)
                                         |
                                       [ R_fixed: 10 kΩ ]
                                         |
GND -------------------------------------+
```
Using the Steinhart-Hart B-parameter equation:
$$\frac{1}{T} = \frac{1}{T_0} + \frac{1}{B} \ln\left(\frac{R_{\text{NTC}}}{R_0}\right)$$
where $T_0 = 298.15\,\text{K}$ ($25\,^\circ\text{C}$), $R_0 = 10{,}000\,\Omega$, and $B = 3950\,\text{K}$.

### D. Power Calculation
Real electrical power is computed strictly when both voltage and current are valid:
$$P = V_{\text{pack}} \times I_{\text{pack}}$$

---

## 4. Calibration Checklist

1. **Zero-Current Calibration:**
   - Power up the ESP32 while the battery load circuit is open ($I = 0\,\text{A}$).
   - The firmware records and averages 64 baseline samples to calibrate `acs712_zero_voltage`.
2. **Voltage Divider Trimming:**
   - Measure actual battery voltage with a calibrated digital multimeter.
   - Adjust `VOLTAGE_DIVIDER_RATIO` in `TwinVolt_ESP32_WiFi.ino` if resistor tolerances deviate from nominal $1\%$.
3. **ADC Linearity Compensation:**
   - ESP32 ADCs exhibit non-linearity below $0.15\,\text{V}$ and above $3.15\,\text{V}$.
   - Ensure the divider scales normal operational voltages between $1.0\,\text{V}$ and $2.8\,\text{V}$ for maximum accuracy.

---

## 5. Dual Communication Options (v2.0 — BLE + Serial)

The **`TwinVolt_ESP32_BLE_Serial.ino`** firmware streams real sensor telemetry simultaneously on **two independent transport channels** at **2 Hz**:

### Transport A — USB Serial (115200 baud)

- Plug the ESP32 USB cable into your laptop. If the board's USB-UART chip (CP210x or CH340) driver is installed, Windows assigns a COM port (e.g., `COM7`).
- In the TwinVolt UI → **Hardware & Arduino** → select **🔌 USB Serial** tab → pick the COM port → click **Connect USB Serial**.
- Telemetry is ingested by the Python `ArduinoConnectionManager` on the backend.

> [!TIP]
> If Windows only shows `Standard Serial over Bluetooth link` COM ports and no physical COM port appears, you are likely using a **charge-only USB cable** (no data wires) or the CH340/CP210x driver is not installed. In that case, use **Transport B** below.

### Transport B — Bluetooth Low Energy (BLE GATT)

The ESP32 runs a BLE GATT server that is **directly readable by Chrome/Edge** via the Web Bluetooth API without any backend.

#### BLE GATT Service Layout

| GATT Object | UUID | Properties |
|---|---|---|
| **Primary Service** | `7a100001-1234-5678-1234-56789abcdef0` | — |
| **Telemetry Characteristic** | `7a100002-1234-5678-1234-56789abcdef0` | NOTIFY, READ |
| **Control Characteristic** | `7a100003-1234-5678-1234-56789abcdef0` | WRITE, READ |

#### Pairing & Connecting

1. Flash `TwinVolt_ESP32_BLE_Serial.ino` to the ESP32.
2. Power the board (USB cable to laptop is fine — for power only if desired).
3. On Windows: Settings → Bluetooth → Add device → Select **"Twin Volt"** (optional; Web Bluetooth can pair on demand).
4. In the TwinVolt UI → **Hardware & Arduino** → click **📶 Bluetooth Low Energy (BLE)** tab → click **Scan & Connect Bluetooth**.
5. Chrome/Edge will show a native Bluetooth device picker — select **Twin Volt** → click Pair.
6. Telemetry notifications appear in the live stream console immediately after GATT connection.

#### USB Power + BLE Data Workflow

```
Laptop USB port
      │
      │ (5V power only — even a charge cable works)
      ▼
  ESP32 Board
      │
      │ BLE GATT Advertisements (2.4 GHz)
      ▼
Chrome / Edge Browser
      │
      │ Web Bluetooth API (GATT notify)
      ▼
TwinVolt Dashboard — Live Telemetry, Overview, Digital Twin
```

#### Control Commands (written to Control Characteristic)

| Command | Effect |
|---|---|
| `RELAY_ON` | Energize safety relay (connect load) |
| `RELAY_OFF` | De-energize relay (isolate load) |
| `FAN_ON` | Activate DC fan |
| `FAN_OFF` | Deactivate DC fan |

---

## 6. Calibration Checklist

1. **Zero-Current Calibration:**
   - Power up the ESP32 while the battery load circuit is open ($I = 0\\,\\text{A}$).
   - The firmware records and averages 64 baseline samples to calibrate `acs_zero`.
2. **Voltage Divider Trimming:**
   - Measure actual battery voltage with a calibrated digital multimeter.
   - Adjust `V_DIVIDER` in `TwinVolt_ESP32_BLE_Serial.ino` if resistor tolerances deviate from nominal.
3. **ADC Linearity:**
   - ESP32 ADCs show non-linearity below 0.15 V and above 3.15 V.
   - Ensure the divider maps normal operational voltages into 1.0–2.8 V for best accuracy.

---

## 7. Required Arduino IDE Libraries

Install via **Tools → Manage Libraries** or include as ESP32 board package:

| Library | Version | Notes |
|---|---|---|
| `esp32` board package | ≥ 2.0.0 | Provides `BLEDevice`, `BLEServer`, `BLE2902` |
| Built-in `WiFi.h` | bundled | For `TwinVolt_ESP32_WiFi.ino` only |
| Built-in `HTTPClient.h` | bundled | For Wi-Fi variant only |

**Board settings in Arduino IDE:**
- Board: `ESP32 Dev Module`
- Upload Speed: `921600`
- CPU Frequency: `240 MHz`
- Flash Size: `4MB (32Mb)`

---

## 8. Browser Compatibility for BLE

| Browser | Web Bluetooth | Notes |
|---|---|---|
| **Chrome ≥ 56** | ✅ Supported | Requires HTTPS or localhost |
| **Edge (Chromium)** | ✅ Supported | Same as Chrome |
| **Opera** | ✅ Supported | — |
| **Firefox** | ❌ Not supported | Use Chrome instead |
| **Safari (macOS/iOS)** | ❌ Not supported | Use Chrome instead |
