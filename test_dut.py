import time
import pytest
import pyvisa
import serial
import csv
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(__file__).parent / "fvt_production_log.csv"
SIM_YAML = Path(__file__).parent / "instruments_sim.yaml"
SERIAL_PORT = "/dev/cu.usbserial-0001"
BAUD = 115200

def log_measurement(serial_num: str, test_name: str, measured: float, low: float, high: float, unit: str):
    """Log measurement to production CSV and enforce min/max tolerance limits."""
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
    assert passed, f"{test_name} FAILED: {measured}{unit} outside [{low}, {high}]"


class SCPIInstrument:
    """Base PyVISA wrapper with SCPI error queue verification."""

    def __init__(self, rm: pyvisa.ResourceManager, resource_name: str):
        self.inst = rm.open_resource(
            resource_name,
            read_termination="\n",
            write_termination="\n",
        )
        self.inst.timeout = 3000
    
    def check_error_queue(self):
        err = self.inst.query("SYST:ERR?").strip()
        if not err.startswith("0,"):
            raise RuntimeError(f"Instrument SCPI Error: {err}")
    
    def write_checked(self, cmd: str):
        self.inst.write(cmd)
        self.check_error_queue()
    
    def close(self):
        self.inst.close()


class PowerSupplyDriver(SCPIInstrument):
    """Driver for Programmable DC Power Supply (Keysight E36312A)."""

    def configure_and_enable(self, volts: float = 5.0, current_limit: float = 0.5):
        self.write_checked("*RST")
        self.write_checked("*CLS")
        self.write_checked(f"VOLT {volts}")
        self.write_checked(f"CURR {current_limit}")
        self.write_checked("OUTP ON")
    
    def measure_current(self):
        return float(self.inst.query("MEAS:CURR?").strip())
    
    def output_off(self):
        try:
            self.inst.write("OUTP OFF")
        except Exception:
            pass


class BenchDMMDriver(SCPIInstrument):
    """Driver for Bench Digital Multimeter (Keysight 34461A)."""

    def measure_dc_voltage(self) -> float:
        self.write_checked("CONF:VOLT:DC 10,0.0001")
        return float(self.inst.query("READ?").strip())


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
def test_station():
    """Initialize ATE instruments (PyVISA) and real ESP32 DUT (PySerial) with safe teardown."""
    rm = pyvisa.ResourceManager(f"{SIM_YAML}@sim")
    psu = PowerSupplyDriver(rm, "USB0::0x2A8D::0x1102::MY59001234::INSTR")
    dmm = BenchDMMDriver(rm, "USB0::0x2A8D::0x1301::MY57200001::INSTR")
    dut = DUTDriver(SERIAL_PORT, BAUD)

    yield {"psu": psu, "dmm": dmm, "dut": dut}

    # Safe Teardown: always disable power and close connections
    dut.close()
    psu.output_off()
    psu.close()
    dmm.close()
    rm.close()


# @pytest.fixture(scope="module")
# def dut():
#     device = DUTDriver(PORT, BAUD)
#     yield device
#     device.close()


@pytest.fixture(scope="module")
def serial_number(test_station):
    """Extract DUT serial number from *IDN? once per test run."""
    idn = test_station["dut"].query("*IDN?")
    return idn.split(",")[2]


def test_01_power_up_and_quiescent_current_(test_station, serial_number):
    """Apply 5.0V rail via PSU and verify board current draw is within spec (40mA - 150mA)."""
    psu = test_station["psu"]
    psu.configure_and_enable(volts=5.0, current_limit=0.5)
    current_a = psu.measure_current()
    log_measurement(serial_number, "PSU_5V_Current", current_a, low=0.040,  high=0.150, unit="A")


def test_02_bench_dmm_3v3_rail(test_station, serial_number):
    """Verify onboard 3.3V regulator output via Bench DMM (3.20V - 3.40V)."""
    dmm = test_station["dmm"]
    rail_v = dmm.measure_dc_voltage()
    log_measurement(serial_number, "DMM_3V3_Rail", rail_v, low=3.20, high=3.40, unit="V")


def test_03_dut_identification(test_station):
    """Verify ESP32 firware responds with valid manufacturer, model, and firmware version."""
    idn = test_station["dut"].query("*IDN?")
    parts = idn.split(",")
    assert len(parts) == 4, f"Malformed IDN string: {idn}"
    assert parts[0] == "ACME-HW"
    assert parts[1] == "ESP32-DUT-REV1"
    assert parts[3] == "FW1.1.0"


def test_04_led_gpio_control(test_station):
    """Verify GPIO 2 output toggles properly on real ESP32 hardware."""
    dut = test_station["dut"]
    assert dut.query("LED ON") == "OK:LED=1"
    assert dut.query("LED?") == "LED=1"
    time.sleep(0.5) # Pause briefly to see the blue LED light up
    assert dut.query("LED OFF") == "OK:LED=0"
    assert dut.query("LED?") == "LED=0"


def test_05_calibrated_adc_voltage_divider(test_station, serial_number):
    """Verify calibrated ESP32 ADC reads ~1.65V resistor divider within +/-6% tolerance."""
    voltage = float(test_station["dut"].query("READ:ADC?"))
    # assert 0.0 <= voltage <= 3.3, f"ADC voltage out of bounds: {voltage} V"
    log_measurement(serial_number, "DUT_ADC_Divider", voltage, low=1.55, high=1.75, unit="V")


def test_06_internal_mcu_temperature(test_station, serial_number):
    """Verify ESP32 internal temperature is within safe operating limits (15C - 65C)."""
    temp_c = float(test_station["dut"].query("READ:TEMP?"))
    # assert 15.0 <= temp_c <= 65.0, f"MCU temperature out of spec: {temp_c} C"
    log_measurement(serial_number, "DUT_MCU_Temp", temp_c, low=15.0, high=65.0, unit="C")


# def test_invalid_command_error_handling(dut):
#     """Verify DUT gracefully rejects unknown commands without crashing."""
#     resp = dut.query("INVALID:CMD?")
#     assert resp.startswith("ERR:UNKNOWN_CMD")

