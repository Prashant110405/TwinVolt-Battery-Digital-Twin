# TwinVolt Arduino & Embedded Firmware Workspace

This directory contains reference firmware, protocol templates, and integration guidelines for streaming physical battery telemetry from microcontrollers into the **TwinVolt Universal Battery Digital Twin Platform**.

---

## 1. Safety Notice & Hardware Disclaimer

> [!WARNING]
> **TwinVolt is a monitoring and analytics platform, NOT a physical battery safety controller.**
> The physical Battery Management System (BMS), hardware fuses, contactors, and analog front-end (AFE) ICs remain solely responsible for cell protection, over-voltage/under-voltage cutoffs, short-circuit isolation, and thermal runaway prevention. Never bypass hardware protection mechanisms.

---

## 2. Using Your Own Firmware

If you have pre-existing Arduino firmware:
1. Copy your `.ino` file into this directory (`firmware/arduino/your_sketch.ino`) or upload it via the **Hardware & Arduino** page in the TwinVolt UI.
2. Ensure your firmware outputs telemetry to `Serial` at a configured baud rate (e.g., `115200`).
3. TwinVolt's parser automatically accepts:
   - **JSON Lines** (Recommended for clarity and flexible sensor counts)
   - **CSV / Tabular Lines** (Lightweight, low memory overhead)
   - **Binary BMS Frames** with CRC-16 (High-speed embedded systems)

> [!NOTE]
> Do not change your existing sensor pins, ADC reference voltages, voltage divider ratios, or shunt calibration constants. TwinVolt adapts to your firmware's output format.

---

## 3. Supported Serial Protocol Formats

### Format A: JSON Lines (Recommended)
Each line terminated with newline `\n`:
```json
{"millis": 12500, "voltage_v": 3.72, "current_a": 1.45, "temperature_c": 26.8, "soc": 82.0}
```
Multi-cell example:
```json
{"voltage_v": 11.16, "current_a": 2.1, "temperature_c": 28.0, "cell_v_1": 3.72, "cell_v_2": 3.71, "cell_v_3": 3.73}
```

### Format B: CSV (Comma-Separated Values)
Each line terminated with newline `\n`:
```text
timestamp_ms,voltage_v,current_a,temperature_c
```
Example:
```text
12500,3.72,1.45,26.8
```

---

## 4. Flashing Firmware to Hardware

1. **Option A (Arduino IDE)**:
   - Open `TwinVolt_Arduino_Example.ino` in Arduino IDE.
   - Select your Board and COM Port.
   - Click **Upload**.
2. **Option B (Arduino CLI via TwinVolt UI)**:
   - If `arduino-cli` is installed on your computer, you can verify and upload directly from the TwinVolt **Hardware & Arduino** page.
