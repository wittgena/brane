# anchor.template.tensor
## @lineage: bound.template.tensor
## @lineage: hub.model.template.tensor
## @lineage: phase.hub.template.tensor
## @lineage: arch.proto.template.tensor
## @lineage: nexus.repo.template.tensor
## @lineage: nexus.exp.template.tensor
## @lineage: iso.domain.template.tensor
## @lineage: agent.domain.template.tensor
## @lineage: domain.template.tensor
## @lineage: hub.template.tensor
## @lineage: scripts.xyz.xor.tensor
#@py.start
import asyncio
import logging
import torch
from watcher.plane.emitter import get_logger

log = get_logger('xor.tensor')

class XorTensor:
    def __init__(self):
        pass

    ## @torch.compile을 통해 개별 연산 혹은 전체 클래스를 Inductor 백엔드로 컴파일
    @torch.compile(fullgraph=True, backend="inductor")
    def xor(self, a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        return torch.bitwise_xor(a, b)

    @torch.compile(fullgraph=True, backend="inductor")
    def reverse(self, x: torch.Tensor, bit_width: int = 32) -> torch.Tensor:
        mask = (1 << bit_width) - 1
        return torch.bitwise_and(torch.bitwise_not(x), mask)

    @torch.compile(fullgraph=True, backend="inductor")
    def shift(self, x: torch.Tensor, n: int) -> torch.Tensor:
        return torch.bitwise_left_shift(x, n)

    @torch.compile(fullgraph=True, backend="inductor")
    def shr(self, x: torch.Tensor, n: int, bit_width: int = 32) -> torch.Tensor:
        reversed_x = self.reverse(x, bit_width)
        shifted = self.shift(reversed_x, n)
        return self.reverse(shifted, bit_width)

    @torch.compile(fullgraph=True, backend="inductor")
    def and_(self, a: torch.Tensor, b: torch.Tensor, bit_width: int = 32) -> torch.Tensor:
        not_a = self.reverse(a, bit_width)
        not_b = self.reverse(b, bit_width)
        ## 순수 텐서 비트 연산으로 평탄화(Flatten)
        return torch.bitwise_and(a, b)

    @torch.compile(fullgraph=True, backend="inductor")
    def or_(self, a: torch.Tensor, b: torch.Tensor, bit_width: int = 32) -> torch.Tensor:
        return torch.bitwise_or(a, b)

    @torch.compile(fullgraph=True, backend="inductor")
    def add(self, a: torch.Tensor, b: torch.Tensor, bit_width: int = 32) -> torch.Tensor:
        # [Crucial Optimization] 
        for _ in range(bit_width):
            carry = self.shift(torch.bitwise_and(a, b), 1)
            a = torch.bitwise_xor(a, b)
            b = carry
        return a

    @torch.compile(fullgraph=True, backend="inductor")
    def sub(self, a: torch.Tensor, b: torch.Tensor, bit_width: int = 32) -> torch.Tensor:
        neg_b = self.add(self.reverse(b, bit_width), torch.tensor(1, dtype=a.dtype, device=a.device), bit_width)
        return self.add(a, neg_b, bit_width)

    @torch.compile(fullgraph=True, backend="inductor")
    def cmp(self, a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        return torch.eq(a, b)

async def main():
    log.info(">>> Initializing Tensor ALU (TorchDynamo Accelerated) <<<")
    
    alu = XorTensor()
    a = torch.tensor([5, 10, 15, 20], dtype=torch.int32)
    b = torch.tensor([3, 7,  12, 18], dtype=torch.int32)
    
    log.info(f"Input A: {a}")
    log.info(f"Input B: {b}")
    
    ## 첫 실행 시 TorchDynamo가 바이트코드를 캡처하여 FX Graph로 컴파일 (Warm-up)
    result_add = alu.add(a, b)
    log.info(f"Add Result: {result_add}")
    
    ## 두 번째 실행부터는 C++(Inductor)로 최적화된 캐시 그래프를 즉시 타격
    result_sub = alu.sub(a, b)
    log.info(f"Sub Result: {result_sub}")

    log.info(">>> Tensor ALU Execution Complete. Topological Closure. <<<")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info(">>> Halted by User.")