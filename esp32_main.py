import sys
import machine
import esp32
import time

# Onboard blue LED is usually GPIO 2 on ESP32 dev boards
led = machine.Pin(2, machine.Pin.OUT)
led.value(0)

# Configure ADC (Analog-to-Digital Converter) on GPIO 34 (input-only pin)
adc = machine.ADC(machine.Pin(34))
adc.atten(machine.ADC.ATTN_11DB) # Full 0V - 3.3V range

DEVICE_ID = "ACME-HW,ESP32-DUT-REV1,SN2026111601,FW1.1.0"

def handle_command(cmd):
    cmd = cmd.strip().upper()
    if not cmd:
        return None
    if cmd == "*IDN?":
        return DEVICE_ID
    elif cmd == "LED ON":
        led.value(1)
        return "OK:LED=1"
    elif cmd == "LED OFF":
        led.value(0)
        return "OK:LED=0"
    elif cmd == "LED?":
        return f"LED={led.value()}"
    if cmd == "READ:ADC?":
        # User factory eFuse calibration in microvolts -> volts
        uv = adc.read_uv()
        volts = uv / 1_000_000.0
        return f"{volts:.4f}"
    elif cmd == "READ:TEMP?":
        # Internal MCU temperature sensor (Fahrenheit to Celsius)
        temp_f = esp32.raw_temperature()
        temp_c = (temp_f - 32.0) * 5.0 / 9.0
        return f"{temp_c:.2f}"
    else:
        return f"ERR:UNKNOWN_CMD:{cmd}"

# Main serial command loop
while True:
    line = sys.stdin.readline()
    if line:
        reply = handle_command(line)
        if reply is not None:
            print(reply)