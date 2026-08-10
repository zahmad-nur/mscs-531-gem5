import m5

from gem5.resources.resource import obtain_resource
from gem5.simulate.simulator import Simulator

from gem5.components.boards.x86_board import X86Board
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.cpu_types import CPUTypes
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.cachehierarchies.classic.no_cache import NoCache

from gem5.isas import ISA


# Processor
processor = SimpleProcessor(
    cpu_type=CPUTypes.TIMING,
    num_cores=1,
    isa=ISA.X86,
)

# Memory
memory = SingleChannelDDR3_1600(
    size="512MB"
)

# Board
board = X86Board(
    clk_freq="1GHz",
    processor=processor,
    memory=memory,
    cache_hierarchy=NoCache(),
)

# Set SE workload
board.set_se_binary_workload(
    obtain_resource("hello")
)

# Run simulation
simulator = Simulator(board=board)

print("Beginning simulation!")

simulator.run()

print("Simulation complete")