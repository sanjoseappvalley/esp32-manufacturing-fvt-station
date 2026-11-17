# ESP32 Manufacturing Functional Verification Test (FVT) Station

An automated Hardware-in-the-Loop (HIL) manufacturing test suite built with **Python**, **PySerial**, **PyVISA**, and **Pytest** to verify an ESP32 Device Under Test (DUT).

## Hardware Setup
- **DUT:** ESP32-WROOM-32 running custom MicroPython SCPI-style diagnostic firmware (`esp32_main.py`)
- **Test Circuit:** Dual-breadboard fixture with a 10kΩ / 10kΩ resistor voltage divider (3.3V -> ~1.65V) connected to GPIO 34 (ADC)
- **Verification Equipment:** AstroAI 20,000-count True RMS Digital Multimeter

## Features
- **SCPI-Style Serial Protocol:** Implements `*IDN?`, `LED ON/OFF`, `READ:ADC?`, and `READ:TEMP?` over UART (115200 baud)
- **Hardware Abstraction Layer (HAL):** Clean `DUTDriver` wrapper with safe `pytest` fixture teardown
- **Production Traceability Logging:** Exports timestamped, serial-numbered test results and min/max tolerance limits to `fvt_production_log.csv`

## How to Run

bash python3 -m venv venv source venv/bin/activate pip install -r requirements.txt pytest -v -s test_dut.py
