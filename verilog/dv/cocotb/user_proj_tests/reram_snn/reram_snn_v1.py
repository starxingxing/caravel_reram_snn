import os
import re
import cocotb
from cocotb.triggers import RisingEdge, ClockCycles, Timer
from cocotb.clock import Clock

PERIOD  = 20
RD_DLY  = 44
WR_DLY  = 200
MODE_PROGRAM = 0xC0000000
MODE_READ    = 0x40000000
N_SAMPLES    = 269

def parse_hex_file(filename):
    out = []
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if line.startswith('//') or not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                out.append((int(parts[0], 16), int(parts[1], 16)))
    return out

def parse_expected_output(filename):
    expected = {}; current = None
    with open(filename) as f:
        for line in f:
            line = line.strip()
            m = re.search(r'SAMPLE_START\s+(\d+)', line)
            if m:
                current = int(m.group(1)); expected[current] = []; continue
            if 'SAMPLE_END' in line:
                current = None; continue
            if current is not None and not line.startswith('//'):
                parts = line.split()
                if len(parts) >= 2:
                    expected[current].append((int(parts[0],16), int(parts[1],16)))
    return expected

def parse_input_stimuli_by_sample(filename):
    stimuli = {}; current = None
    with open(filename) as f:
        for line in f:
            raw = line; line = line.strip()
            if 'Sample' in raw:
                m = re.search(r'Sample\s+(\d+)', raw)
                if m:
                    current = int(m.group(1)); stimuli[current] = []; continue
            if line.startswith('//') or not line:
                continue
            if current is not None:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        addr = int(parts[0], 16)
                        if parts[1].upper() == 'READ': continue
                        stimuli[current].append((addr, int(parts[1], 16)))
                    except ValueError:
                        pass
    return stimuli

# ── Wishbone primitives ────────────────────────────────────────────────────

async def wishbone_write(dut, addr, data):
    dut.wbs_cyc_i.value = 1; dut.wbs_stb_i.value = 1
    dut.wbs_we_i.value  = 1; dut.wbs_sel_i.value = 0xF
    dut.wbs_adr_i.value = addr; dut.wbs_dat_i.value = data
    await RisingEdge(dut.wb_clk_i)
    dut.wbs_cyc_i.value = 0; dut.wbs_stb_i.value = 0
    dut.wbs_we_i.value  = 0; dut.wbs_sel_i.value = 0; dut.wbs_dat_i.value = 0

async def wishbone_read(dut, addr):
    """2-cycle registered read — samples wbs_dat_o at T+2 after asserting."""
    dut.wbs_cyc_i.value = 1; dut.wbs_stb_i.value = 1
    dut.wbs_we_i.value  = 0; dut.wbs_sel_i.value = 0xF
    dut.wbs_adr_i.value = addr; dut.wbs_dat_i.value = 0
    await RisingEdge(dut.wb_clk_i)   # T+1: slave registers request (NBA)
    await RisingEdge(dut.wb_clk_i)   # T+2: wbs_dat_o valid
    data = dut.wbs_dat_o.value.integer
    dut.wbs_cyc_i.value = 0; dut.wbs_stb_i.value = 0; dut.wbs_sel_i.value = 0
    return data

async def nvm_write(dut, addr, data):
    """Program one NVM cell — injects MODE_PROGRAM into bits[31:30]."""
    await wishbone_write(dut, addr, (data & 0x3FFFFFFF) | MODE_PROGRAM)
    await ClockCycles(dut.wb_clk_i, WR_DLY + 5)

async def nvm_inference_read(dut, addr, data):
    """
    One axon inference step — 3-phase handshake:

    Phase 1: wishbone_write with MODE_READ → X1 queues READ into op_fifo.
    Phase 2: wait RD_DLY+2 cycles for X1 engines to fetch bit → op_fifo ready.
    Phase 3: hold cyc/stb for 2 posedges with wbs_dat_i = original data:
      • T+1: X1 pops op_fifo → core_ack=1 (NBA). After T+1:
             slave_ack_o=1, wbs_ack_o=1, enable=1 (combinational).
      • T+2: nvm_neuron_block clocks enable=1:
             group_sel = wbs_dat_i[26:25]  (row%4)
             stimuli   = ±wbs_dat_i[15:0]  (sign from row[3]=wbs_dat_i[28])
             Neuron group accumulates.  Then deassert.
    """
    await wishbone_write(dut, addr, (data & 0x3FFFFFFF) | MODE_READ)
    await ClockCycles(dut.wb_clk_i, RD_DLY + 2)
    dut.wbs_cyc_i.value = 1; dut.wbs_stb_i.value = 1
    dut.wbs_we_i.value  = 0; dut.wbs_sel_i.value = 0xF
    dut.wbs_adr_i.value = addr; dut.wbs_dat_i.value = data
    await RisingEdge(dut.wb_clk_i)
    await RisingEdge(dut.wb_clk_i)
    dut.wbs_cyc_i.value = 0; dut.wbs_stb_i.value = 0
    dut.wbs_we_i.value  = 0; dut.wbs_sel_i.value = 0; dut.wbs_dat_i.value = 0

async def reset_neurons(dut):
    """Reset all 64 neuron potentials via two picture_done writes."""
    for pd_addr in [0x30002000, 0x30002004]:
        await ClockCycles(dut.wb_clk_i, 10)
        await wishbone_write(dut, pd_addr, 0x00000000)
    await ClockCycles(dut.wb_clk_i, 10)

# ── main test ──────────────────────────────────────────────────────────────

@cocotb.test()
async def reram_snn(dut):
    print("\n" + "=" * 70)
    print("SNN HARDWARE TEST — nvm_neuron_core_256x64 (corrected)")
    print("=" * 70 + "\n")

    clock = Clock(dut.wb_clk_i, PERIOD, units="ns")
    cocotb.start_soon(clock.start())

    dut.wb_rst_i.value = 1
    for sig in [dut.wbs_cyc_i, dut.wbs_stb_i, dut.wbs_we_i,
                dut.wbs_sel_i, dut.wbs_adr_i, dut.wbs_dat_i]:
        sig.value = 0
    await RisingEdge(dut.wb_clk_i)
    await Timer(1000, units="ns") #changed to 1000 from 100
    dut.wb_rst_i.value = 0
    await RisingEdge(dut.wb_clk_i)

    # Weight programming — new file has 512 entries, one per NVM cell, no reuse
    print("Programming weights...")
    weights = parse_hex_file("/home/impact/projects/memristor_development/EDABK_SNN_CIM/zayed_version/caravel_reram_snn/verilog/dv/cocotb/user_proj_tests/reram_snn/weights_wishbone.hex")
    for idx, (addr, data) in enumerate(weights):
        await nvm_write(dut, addr, data)
        if (idx + 1) % 100 == 0:
            print(f"  {idx + 1}/{len(weights)} ...")
    print(f"  ✓ {len(weights)} weight entries programmed\n")

    expected = parse_expected_output("/home/impact/projects/memristor_development/EDABK_SNN_CIM/zayed_version/caravel_reram_snn/verilog/dv/cocotb/user_proj_tests/reram_snn/expected_output.hex")
    stimuli  = parse_input_stimuli_by_sample("/home/impact/projects/memristor_development/EDABK_SNN_CIM/zayed_version/caravel_reram_snn/verilog/dv/cocotb/user_proj_tests/reram_snn/input_stimuli.hex")
    sample_ids = sorted(stimuli.keys())[:N_SAMPLES]
    print(f"Running {len(sample_ids)} samples (0 – {sample_ids[-1]})\n")

    total_correct = 0; total_checks = 0; sample_results = []

    for sample in sample_ids:
        if sample not in expected:
            print(f"  [SKIP] sample {sample}")
            continue

        await reset_neurons(dut)

        for addr, data in stimuli[sample]:
            region = (addr >> 12) & 0xF
            if region == 0:
                await nvm_inference_read(dut, addr, data)
            elif region == 2:
                await ClockCycles(dut.wb_clk_i, 50)
                await wishbone_write(dut, addr, data)
            else:
                await wishbone_write(dut, addr, data)

        await ClockCycles(dut.wb_clk_i, 100)

        sc = 0; st = 0
        for addr, exp in expected[sample]:
            act = await wishbone_read(dut, addr)
            if act == exp: sc += 1
            st += 1

        total_correct += sc; total_checks += st
        passed = (sc == st)
        sample_results.append((sample, passed, sc, st))
        print(f"  Sample {sample:3d}: {'PASS' if passed else 'FAIL'} ({sc}/{st})")

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    for sample, passed, sc, st in sample_results:
        print(f"  {'✓' if passed else '✗'} Sample {sample:3d}: {sc}/{st}")
    passed_count = sum(1 for _, p, _, _ in sample_results if p)
    print(f"\n  Samples passed : {passed_count}/{len(sample_results)}")
    if total_checks:
        print(f"  Output accuracy: {total_correct}/{total_checks} "
              f"({100*total_correct/total_checks:.1f}%)")
    print("=" * 70 + "\n")
