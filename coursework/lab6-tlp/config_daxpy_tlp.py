"""
config_daxpy_tlp.py

Classic-style (non-stdlib) gem5 SE-mode config for exploring the
FloatSimdFU opLat/issueLat design space on a multi-core MinorCPU system,
running the multi-threaded daxpy kernel (daxpy_mt.c).

Why classic style and not the gem5 standard library: the stdlib
components (SimpleProcessor / BaseCPUCore) don't expose a clean hook
for overriding individual functional-unit timings inside MinorCPU's FU
pool -- doing it "properly" through stdlib still means subclassing
BaseCPUCore, which drops you into classic-style SimObject code anyway.
Building the System directly, as below, gives direct access to
cpu.executeFuncUnits and keeps the sweep script simple.

The MinorDefaultFUPool / MinorDefaultFloatSimdFU / MinorFU classes
this script overrides are defined in src/cpu/minor/BaseMinorCPU.py
(not a separate MinorFUPool.py -- that filename doesn't exist in all
gem5 versions; check yours with
`grep -rl "MinorDefaultFUPool" src/` if this ever needs re-verifying).

Usage:
  <gem5>/build/X86/gem5.opt --outdir=<outdir> config_daxpy_tlp.py \
      --cmd=./daxpy_mt --options="<num_threads> <n>" \
      --num-cpus=<num_threads> --op-lat=<L> --issue-lat=<L>

Notes:
  - This script uses X86MinorCPU directly rather than the generic
    "MinorCPU" name. gem5's m5.objects.MinorCPU module only rebinds
    the bare "MinorCPU" name to an ISA-specific class for ARM and
    RISCV builds; on an X86-only build, "MinorCPU" resolves to the
    leftover MinorCPU.py submodule itself (not a class), which raises
    "TypeError: 'module' object is not callable" if you try to
    instantiate it. X86MinorCPU is the concrete class gem5 actually
    generates for X86 builds.
  - num-cpus should generally match the thread count you pass to the
    daxpy binary in --options, since gem5 SE mode places each new
    pthread (via clone()) onto the next free CPU context. If you give
    it more CPUs than the program spawns threads, the extras just sit
    idle -- harmless, but wastes wall-clock sim time.
  - opLat + issueLat should sum to 7 per the assignment's fixed budget;
    the script warns (but does not stop) if they don't, so you can
    still use it to sanity-check outside that budget if you want to.
"""

import argparse
import m5
from m5.objects import *

parser = argparse.ArgumentParser()
parser.add_argument("--cmd", required=True, help="path to the workload binary")
parser.add_argument("--options", default="", help="args passed to the workload, e.g. '4 1000000'")
parser.add_argument("--num-cpus", type=int, default=4)
parser.add_argument("--op-lat", type=int, required=True, help="FloatSimdFU opLat (cycles)")
parser.add_argument("--issue-lat", type=int, required=True, help="FloatSimdFU issueLat (cycles)")
parser.add_argument("--sys-clock", default="2GHz")
parser.add_argument("--cpu-clock", default="2GHz")
parser.add_argument("--mem-size", default="2GB")
args = parser.parse_args()

if args.op_lat + args.issue_lat != 7:
    print(
        f"WARNING: opLat ({args.op_lat}) + issueLat ({args.issue_lat}) "
        f"!= 7 -- outside the assignment's fixed 7-cycle budget. "
        f"Continuing anyway."
    )


def make_fu_pool(op_lat, issue_lat):
    """
    Return a MinorDefaultFUPool with the FloatSimd functional unit's
    opLat/issueLat overridden, leaving every other FU (Int, IntMul,
    IntDiv, Mem, Misc, Pred, ...) untouched.

    NOTE: the class-name check below (`"FloatSimd" in type(fu).__name__`)
    matches gem5's conventional naming (MinorDefaultFloatSimdFU). Confirmed
    against src/cpu/minor/BaseMinorCPU.py (in some gem5 versions this
    lives in a separate MinorFUPool.py -- in current checkouts the FU
    pool classes, including MinorDefaultFUPool and
    MinorDefaultFloatSimdFU, are defined directly in BaseMinorCPU.py
    alongside BaseMinorCPU itself). If your checkout names the class
    differently, you can instead check `fu.opClasses` for
    FloatAdd/FloatMult/SimdAdd membership.
    """
    pool = MinorDefaultFUPool()
    matched = False
    for fu in pool.funcUnits:
        if "FloatSimd" in type(fu).__name__:
            fu.opLat = op_lat
            fu.issueLat = issue_lat
            matched = True
    if not matched:
        print(
            "WARNING: no FU matched 'FloatSimd' in its class name -- "
            "the opLat/issueLat override was NOT applied. Inspect "
            "MinorDefaultFUPool().funcUnits in a Python shell to find "
            "the correct class name for your gem5 version."
        )
    return pool


system = System()
system.clk_domain = SrcClockDomain(clock=args.sys_clock, voltage_domain=VoltageDomain())
system.mem_mode = "timing"
system.mem_ranges = [AddrRange(args.mem_size)]

system.cpu = [X86MinorCPU(cpu_id=i, clk_domain=SrcClockDomain(
    clock=args.cpu_clock, voltage_domain=VoltageDomain())) for i in range(args.num_cpus)]

system.membus = SystemXBar()

for cpu in system.cpu:
    cpu.executeFuncUnits = make_fu_pool(args.op_lat, args.issue_lat)
    cpu.createInterruptController()
    # X86's local APIC needs its ports explicitly connected to the
    # membus, or it panics at tick 0 with "Int port not connected to
    # anything!" ARM/RISCV don't need this extra wiring, which is why
    # it's easy to miss if you're working from a generic example.
    cpu.interrupts[0].pio = system.membus.mem_side_ports
    cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
    cpu.interrupts[0].int_responder = system.membus.mem_side_ports
    cpu.icache_port = system.membus.cpu_side_ports
    cpu.dcache_port = system.membus.cpu_side_ports

system.mem_ctrl = MemCtrl()
system.mem_ctrl.dram = DDR3_1600_8x8()
system.mem_ctrl.dram.range = system.mem_ranges[0]
system.mem_ctrl.port = system.membus.mem_side_ports

system.system_port = system.membus.cpu_side_ports

process = Process()
process.cmd = [args.cmd] + args.options.split()

# Recent gem5 versions require an explicit SEWorkload object attached
# to the system before instantiation, or process.cc raises
# "fatal condition !seWorkload occurred: Couldn't find appropriate
# workload object." init_compatible() inspects the binary and builds
# the right SEWorkload (ISA/OS ABI) for it automatically.
system.workload = SEWorkload.init_compatible(args.cmd)

# All CPUs share the same Process object. In SE mode, gem5 routes each
# new thread context created by clone() (i.e. pthread_create) onto the
# next available CPU -- this is what actually gives you one pthread
# per simulated core.
for cpu in system.cpu:
    cpu.workload = process
    cpu.createThreads()

root = Root(full_system=False, system=system)
m5.instantiate()

print(
    f"Beginning simulation: opLat={args.op_lat} issueLat={args.issue_lat} "
    f"numCPUs={args.num_cpus} cmd={args.cmd} options='{args.options}'"
)
exit_event = m5.simulate()
print(f"Exiting @ tick {m5.curTick()} because {exit_event.getCause()}")