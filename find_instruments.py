import pyvisa
from pathlib import Path

# rm = pyvisa.ResourceManager()
# for resource in rm.list_resources():
#     try:
#         inst = rm.open_resource(resource)
#         inst.timeout = 2000
#         print(f"{resource}\n    {inst.query('*IDN?').strip()}")
#         inst.close()
#     except Exception as exc:
#         print(f"{resource}\n    no response: {exc}")

# inst.write("VOLT 3.3")            # command, no response expected
# value = inst.query("MEAS:VOLT?")  # command + read response
# raw = inst.read()                 # read only, when a response is pending


# Rule: if the SCPI string ends in `?`, use `query`. Otherwise use `write`.


# yaml_path = Path(__file__).parent / "dmm_sim.yaml"
# rm = pyvisa.ResourceManager(f"{yaml_path}@sim")
rm = pyvisa.ResourceManager("dmm_sim.yaml@sim")
dmm = rm.open_resource(
    "USB0::0x2A8D::0x1301::MY57200001::INSTR",
    read_termination="\n",
    write_termination="\n"
    )
dmm.timeout = 2000        # milliseconds

try:
    print(dmm.query("*IDN?").strip())
    # Doing both at the start of every script eliminates an entire category of "it worked yesterday" problems caused by leftover configuration.
    dmm.write("*RST") # *RST puts the instrument in a known state.
    dmm.write("*CLS") # *CLS clears the status and error registers.

    dmm.write("CONF:VOLT:DC 10,0.0001")  # 10 V range, 100 uV resolution
    dmm.write("TRIG:SOUR IMM")

    for _ in range(5):
        val = float(dmm.query("READ?").strip())
        print(f"{val:.6f} V")

finally:
    dmm.close()
    rm.close()


# Always check the error queue
# SCPI instruments do not raise exceptions. The instrument records an error and carries on.
# The output number may look fine but are wrong
def check(inst):
    problems = []
    while True:
        response = inst.query("SYST:ERR?").strip()
        code = int(response.split(",", 1)[0])
        if code == 0:
            break
        problems.append(response)
        if len(problems) > 20:
            break
    if problems:
        raise RuntimeError("instrument errors: " + "; ".join(problems))