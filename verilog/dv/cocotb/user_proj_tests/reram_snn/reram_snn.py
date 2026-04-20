from caravel_cocotb.caravel_interfaces import test_configure, report_test
import cocotb
from cocotb.triggers import RisingEdge, ClockCycles, Timer
import re
import os

# Constants from original script
RD_DLY  = 44
WR_DLY  = 200
MODE_PROGRAM = 0xC0000000
MODE_READ    = 0x40000000
#N_SAMPLES    = 269
N_SAMPLES    = 1

# --- Helper Functions (Parsing) ---
def parse_hex_file(filename):
    out = []
    with open(filename, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith('//') or not line: continue
            parts = line.split()
            if len(parts) >= 2: out.append((int(parts[0], 16), int(parts[1], 16)))
    return out

def parse_expected_output(filename):
    expected = {}; current = None
    with open(filename, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            m = re.search(r'SAMPLE_START\s+(\d+)', line)
            if m: current = int(m.group(1)); expected[current] = []; continue
            if 'SAMPLE_END' in line: current = None; continue
            if current is not None and not line.startswith('//'):
                parts = line.split()
                if len(parts) >= 2: expected[current].append((int(parts[0],16), int(parts[1],16)))
    return expected

'''def parse_input_stimuli_by_sample(filename):
    stimuli = {}
    current = None
    with open(filename, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Match the "// ── Sample    0" format in input_stimuli.hex
            m = re.search(r'Sample\s+(\d+)', line)
            if m:
                current = int(m.group(1))
                stimuli[current] = []
                continue

            if current is not None and not line.startswith('//') and line:
                parts = line.split()
                if len(parts) >= 2:
                    stimuli[current].append((int(parts[0], 16), int(parts[1], 16)))
    return stimuli'''




def parse_input_stimuli_by_sample(filename):
    stimuli = {}; current = None
    with open(filename, encoding="utf-8") as f:
        for line in f:
            raw = line; line = line.strip()
            if 'Sample' in raw:
                m = re.search(r'Sample\s+(\d+)', raw)
                if m:
                    current = int(m.group(1)); stimuli[current] = []; continue
            if line.startswith('//') or not line:
                continue
            if current is not None and not line.startswith('//') and line:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        addr = int(parts[0], 16)
                        if parts[1].upper() == 'READ': continue
                        stimuli[current].append((addr, int(parts[1], 16)))
                    except ValueError:
                        pass
    return stimuli

# --- Wishbone Handshaking (Using Caravel Hierarchy) ---

async def wishbone_write(mprj, clk, addr, data):
    mprj.wbs_cyc_i.value = 1; mprj.wbs_stb_i.value = 1
    mprj.wbs_we_i.value  = 1; mprj.wbs_sel_i.value = 0xF
    mprj.wbs_adr_i.value = addr; mprj.wbs_dat_i.value = data
    await RisingEdge(clk)
    mprj.wbs_cyc_i.value = 0; mprj.wbs_stb_i.value = 0
    mprj.wbs_we_i.value  = 0; mprj.wbs_sel_i.value = 0; mprj.wbs_dat_i.value = 0

async def wishbone_read(mprj, clk, addr):
    mprj.wbs_cyc_i.value = 1; mprj.wbs_stb_i.value = 1
    mprj.wbs_we_i.value  = 0; mprj.wbs_sel_i.value = 0xF
    mprj.wbs_adr_i.value = addr; mprj.wbs_dat_i.value = 0
    await RisingEdge(clk) # Request phase
    await RisingEdge(clk) # Response phase

    # Check if the value is valid before converting to integer
    resp_val = mprj.wbs_dat_o.value
    if resp_val.is_resolvable:
        data = resp_val.integer
    else:
        # Log a warning and default to 0 so the test doesn't crash
        cocotb.log.warning(f"Read at {hex(addr)} returned unresolvable value: {resp_val.binstr}. Defaulting to 0.")
        data = 0

    mprj.wbs_cyc_i.value = 0; mprj.wbs_stb_i.value = 0; mprj.wbs_sel_i.value = 0
    return data

@cocotb.test(timeout_time=None)
@report_test
async def reram_snn(dut):
    # 1. Initialize Caravel Environment
    # This automatically handles clock generation and power-on reset
    caravelEnv = await test_configure(dut, timeout_cycles=2000000)
    
    # Define shortcuts to mprj signals and clock
    # In Caravel Cocotb, 'dut.uut.mprj' is the standard path to the user wrapper
    mprj = dut.uut.chip_core.mprj
    clk  = mprj.wb_clk_i 

    cocotb.log.info("[TEST] Waiting for Firmware to enable Wishbone...")
    await caravelEnv.wait_mgmt_gpio(1)
    
    cocotb.log.info("[TEST] Starting ReRam SNN weight programming...")
    
    #path = os.path.expandvars("$PROJECT_ROOT")
    #pwd = os.getcwd()
    path = os.path.abspath(os.path.join(os.getcwd(), os.pardir, os.pardir, os.pardir))
    print(path)


    # 2. Weight Programming
    weights = parse_hex_file(f"{path}/user_proj_tests/reram_snn/weights_wishbone.hex")
    for idx, (addr, data) in enumerate(weights):
        # nvm_write logic
        await wishbone_write(mprj, clk, addr, (data & 0x3FFFFFFF) | MODE_PROGRAM)
        await ClockCycles(clk, WR_DLY + 5)
        if (idx + 1) % 100 == 0:
            cocotb.log.info(f"  {idx + 1}/{len(weights)} weights programmed...")

    # 3. Inference Samples
    expected = parse_expected_output(f"{path}/user_proj_tests/reram_snn/expected_output.hex")
    stimuli  = parse_input_stimuli_by_sample(f"{path}/user_proj_tests/reram_snn/input_stimuli.hex")

    sample_ids = sorted(stimuli.keys())[:N_SAMPLES]
    
    total_correct = 0; total_checks = 0

    for sample in sample_ids:
        if sample not in expected: continue

        # Reset neurons via picture_done writes
        for pd_addr in [0x30002000, 0x30002004]:
            await wishbone_write(mprj, clk, pd_addr, 0)
            await ClockCycles(clk, 10)

        # Run Sample Stimuli
        for addr, data in stimuli[sample]:
            region = (addr >> 12) & 0xF
            if region == 0: # nvm_inference_read logic
                await wishbone_write(mprj, clk, addr, (data & 0x3FFFFFFF) | MODE_READ)
                await ClockCycles(clk, RD_DLY + 2)
                # Phase 3 handshake
                mprj.wbs_cyc_i.value = 1; mprj.wbs_stb_i.value = 1
                mprj.wbs_adr_i.value = addr; mprj.wbs_dat_i.value = data
                await ClockCycles(clk, 2)
                mprj.wbs_cyc_i.value = 0; mprj.wbs_stb_i.value = 0

            else:
                await wishbone_write(mprj, clk, addr, data)


            '''elif (region == 1):
                # CRITICAL FIX: These are READ addresses (0x30001000).
                # Do NOT execute wishbone_write on them, or you will erase the SRAM.
                # We can safely ignore them here because the "Check Results" loop reads them.
                continue

            else:
                await wishbone_write(mprj, clk, addr, data)'''

        await ClockCycles(clk, 100)

        # Check Results
        for addr, exp in expected[sample]:
            act = await wishbone_read(mprj, clk, addr)
            if act == exp: total_correct += 1
            total_checks += 1
            cocotb.log.info(f"Expected: {exp}; Actual: {act}")
            
    cocotb.log.info(f"[TEST] Completed. Accuracy: {total_correct}/{total_checks}")
    print ("Done! Simulation Completed Successfully!")
