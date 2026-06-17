# arch.xor.tensor
## @lineage: hub.xor.tensor
## @lineage: xe.xor.tensor
## @lineage: arch.xphi.xor.tensor
## @lineage: arch.proto.xor.tensor
## @lineage: meta.xor.vm
## @lineage: phase.xor.vm
## @lineage: xphi.xor.vm
import asyncio
import logging
import torch
from watcher.plane.emitter import get_emitter

log = get_emitter("xor.tensor")

class XorTensor:
    @torch.compile(fullgraph=True, backend="inductor")
    def add(self, a: torch.Tensor, b: torch.Tensor, bit_width: int = 32) -> torch.Tensor:
        for _ in range(bit_width):
            carry = torch.bitwise_left_shift(torch.bitwise_and(a, b), 1)
            a = torch.bitwise_xor(a, b)
            b = carry
        return a

    @torch.compile(fullgraph=True, backend="inductor")
    def sub(self, a: torch.Tensor, b: torch.Tensor, bit_width: int = 32) -> torch.Tensor:
        mask = (1 << bit_width) - 1
        neg_b = self.add(torch.bitwise_and(torch.bitwise_not(b), mask), 
                         torch.tensor(1, dtype=a.dtype, device=a.device), bit_width)
        return self.add(a, neg_b, bit_width)

    @torch.compile(fullgraph=True, backend="inductor")
    def xor(self, a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        return torch.bitwise_xor(a, b)

class XorVM:
    """튜링 머신의 동적 테이프를 텐서 메모리로, 제어 흐름을 Branchless 병렬 텐서 마스킹(torch.where)으로 전환"""
    def __init__(self, alu: XorTensor, mem_size: int = 256):
        self.alu = alu
        self.mem_size = mem_size

    @torch.compile(fullgraph=True, backend="inductor")
    def run_cycles(self, memory: torch.Tensor, registers: torch.Tensor, cycles: int = 10) -> torch.Tensor:
        """
        - memory: 명령어(Opcode)와 데이터가 담긴 1D 텐서 배열
        - registers: [0] = PC (Program Counter), [1] = Accumulator (ACC)
        - cycles: Dynamo 컴파일을 위한 정적 언롤링(Static Unroll) 횟수
        """
        for _ in range(cycles):
            pc = registers[0]
            acc = registers[1]

            ## FETCH - 안전한 메모리 접근을 위해 modulo 연산 사용
            safe_pc = torch.remainder(pc, self.mem_size)
            opcode = memory[safe_pc]

            safe_operand_addr = torch.remainder(pc + 1, self.mem_size)
            operand = memory[safe_operand_addr]

            ## EXECUTE (Branchless Execution)
            ## 모든 연산을 미리 계산하고, opcode에 따라 torch.where로 결과를 취사
            res_add = self.alu.add(acc, operand)  # Opcode 1
            res_sub = self.alu.sub(acc, operand)  # Opcode 2
            res_xor = self.alu.xor(acc, operand)  # Opcode 3

            ## 상태 전이 (Multiplexing)
            next_acc = acc
            next_acc = torch.where(opcode == 1, res_add, next_acc)
            next_acc = torch.where(opcode == 2, res_sub, next_acc)
            next_acc = torch.where(opcode == 3, res_xor, next_acc)

            ## UPDATE STATE - Opcode가 0(Halt/NOP)이 아닐 경우에만 PC를 2칸 전진
            registers[1] = next_acc
            registers[0] = torch.where(opcode != 0, pc + 2, pc)

        return registers

async def main():
    log.info(">>> Initializing Tensor Von Neumann Machine <<<")
    
    alu = XorTensor()
    vm = XorVM(alu, mem_size=16)

    ## 메모리 버퍼 초기화 (0으로 채움)
    memory = torch.zeros(16, dtype=torch.int32)
    
    ## 레지스터 초기화: [PC=0, ACC=10]
    registers = torch.tensor([0, 10], dtype=torch.int32)

    ## 프로그램 적재 (Instruction Set)
    ## [Opcode, Operand, Opcode, Operand, ...]
    ## 1: ADD, 2: SUB, 3: XOR, 0: HALT
    memory[0] = 1; memory[1] = 5   # ADD 5  (ACC 10 + 5 = 15)
    memory[2] = 2; memory[3] = 3   # SUB 3  (ACC 15 - 3 = 12)
    memory[4] = 3; memory[5] = 15  # XOR 15 (ACC 12 ^ 15 = 3)
    memory[6] = 0; memory[7] = 0   # HALT

    log.info(f"Initial Memory: {memory.tolist()}")
    log.info(f"Initial Registers [PC, ACC]: {registers.tolist()}")

    ## 컴파일 및 실행 (지정된 사이클만큼 실행)
    final_registers = vm.run_cycles(memory, registers, cycles=4)
    log.info(f"Final Registers [PC, ACC]: {final_registers.tolist()}")
    log.info(">>> VM Execution Complete. Topological Closure. <<<")

if __name__ == "__main__":
    asyncio.run(main())