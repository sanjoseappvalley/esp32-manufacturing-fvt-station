import time
import pytest
import serial
import csv
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "fvt_production_log.csv"

PORT = "/dev/cu.usbserial-0001"
BAUD = 115200

def log_measurement(serial_num: str, test_name: str, measured: float, low: float, high: float, unit: str):
    """Helper function: logs measurement to CSV and asserts min/max limits."""
    passed = low <= measured <= high
    file_exists = LOG_FILE.exists()
    with open (LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "SerialNumber", "TestName", "Measured", "LowLimit", "HighLimit", "Unit", "Result"])
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            serial_num,
            test_name,
            f"{measured:.4f}",
            f"{low:.4f}",
            f"{high:.4f}",
            unit,
            "PASS" if passed else "FAIL",
        ])
    assert passed, f"{test_name} FAILED: {measured}{unit} outside [{flow}, {high}]"

class DUTDriver:
    """Hardware Abstraction Layer (HAL) for communicating with the ESP32 dut."""
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        time.sleep(2.0)
        self.ser.reset_input_buffer()
    
    def query(self, command: str) -> str:
        self.ser.write(f"{command}\n".encode("utf-8"))
        response = self.ser.readline().decode("utf-8").strip()
        if not response:
            raise TimeoutError(f"No response from DUT for command: {command}")
        return response
    
    def close(self):
        try:
            self.query("LED OFF")
        except Exception:
            pass
        if self.ser.is_open:
            self.ser.close()


@pytest.fixture(scope="module")
def dut():
    device = DUTDriver(PORT, BAUD)
    yield device
    device.close()


@pytest.fixture(scope="module")
def serial_number(dut):
    """Extract DUT serial number (index 2) from *IDN? once per test run."""
    idn = dut.query("*IDN?")
    return idn.split(",")[2]


def test_dut_identification(dut):
    """Verify DUT responds with expected manufacturer, model, and firmware version."""
    idn = dut.query("*IDN?")
    parts = idn.split(",")
    assert len(parts) == 4, f"Malformed IDN string: {idn}"
    assert parts[0] == "ACME-HW"
    assert parts[1] == "ESP32-DUT-REV1"
    assert parts[3] == "FW1.1.0"


def test_led_gpio_control(dut):
    """Verify GPIO 2 output toggles properly and reports accurate state."""
    assert dut.query("LED ON") == "OK:LED=1"
    assert dut.query("LED?") == "LED=1"
    time.sleep(0.5) # Pause briefly so we can physically see the blue LED light up

    assert dut.query("LED OFF") == "OK:LED=0"
    assert dut.query("LED?" == "LED=0")


def test_internal_mcu_temperature(dut, serial_number):
    """Verify internal chip temperature is within safe operating limits (15C - 65C)."""
    temp_c = float(dut.query("READ:TEMP?"))
    # assert 15.0 <= temp_c <= 65.0, f"MCU temperature out of spec: {temp_c} C"
    log_measurement(serial_number, "MCU_Temp", temp_c, low=15.0, high=65.0, unit="C")


def test_adc_voltage_rail_bounds(dut, serial_number):
    """Verify GPIO 34 ADC reads ~1.65V divider (accounting for ~0.16V ESP32 ADC offset)."""
    voltage = float(dut.query("READ:ADC?"))
    # assert 0.0 <= voltage <= 3.3, f"ADC voltage out of bounds: {voltage} V"
    log_measurement(serial_number, "ADC_GPI034_Divider", voltage, low=1.55, high=1.75, unit="V")


def test_invalid_command_error_handling(dut):
    """Verify DUT gracefully rejects unknown commands without crashing."""
    resp = dut.query("INVALID:CMD?")
    assert resp.startswith("ERR:UNKNOWN_CMD")

