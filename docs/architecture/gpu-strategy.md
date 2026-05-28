# Eidolon, GPU strategy

Status: Draft
Last updated: 2026-04-18

## Today (v0.1 host)

| GPU | Role | Reasoning |
|-----|------|-----------|
| RX 7600 XT (16 GB VRAM) | Cracker VM, hashcat | Known good hashcat OpenCL target. Not on the ROCm matrix, but hashcat's OpenCL backend works on gfx1102. |
| Arc A380 (6 GB VRAM) | Host display, LLM Analyst fallback via Vulkan | Low power. Runs a 7B model at low tokens per second if you need it before the GPU upgrade. |

### What this means in practice

RX 7600 XT is PCIe passthroughed to the cracker VM. Cracker owns it.

LLM Analyst VM runs on CPU or on the Arc A380 via Vulkan. Acceptable for Foundation Sec 8B and WhiteRabbitNeo 7B at Q4. About 5 to 15 t/s on CPU, faster on A380 Vulkan.

No hot swap. Trying to share the 7600 XT between cracker and LLM Analyst is a scheduler problem and not attempted in v0.1.

### Why not ROCm on the 7600 XT?

gfx1102 is not officially in AMD's ROCm support matrix.

Third party ROCm builds (lemonade sdk, TheRock) exist and usually work, but they break every ROCm release.

hashcat needs OpenCL. OpenCL works via the AMDGPU OpenCL userspace without full ROCm. Good enough.

llama.cpp ROCm/HIP on unsupported arches is doable but you babysit builds.

v0.1 picks stability. No ROCm hacks.

## Upgrade path

### Near term: nothing

Do not buy more GPU hardware for v0.1. The 7600 XT plus Arc A380 combo is good enough to ship the framework and prove the architecture.

### Mid term: RTX PRO 6000 Blackwell (96 GB VRAM)

Once the framework works, add a single RTX PRO 6000.

| GPU | Role |
|-----|------|
| RTX PRO 6000 | LLM Analyst. Llama 3.3 70B or 72B fine tunes, Q4 to Q6. |
| RX 7600 XT | Cracker, unchanged. |
| Arc A380 | Host display. |

About $8,500 at current pricing.

96 GB VRAM fits 70B at Q8 comfortably, or 2x 34B in parallel.

CUDA on Blackwell is a known good llama.cpp target. No ROCm babysitting.

### Long term: multi cracker or multi analyst

Second RX 7600 XT, or step up to a 7900 class card, for a second cracker VM when workload justifies it.

Do not pool GPUs across VMs. Proxmox passthrough is per device. Live migration of pinned GPU VMs is not supported in v0.1.

## What if you already have an NVIDIA GPU today?

If the operator already owns a 3090, 4090, 4080, or 5090:

Use it for LLM Analyst. Keep the 7600 XT on cracker.

Arc A380 still helps as the host display GPU. Frees the main GPU from console weirdness.

llama.cpp with CUDA is strictly easier than ROCm. No GPU strategy changes. Slot it in.

## What if you only have one GPU?

Put it on the cracker. Cracking gains more from GPU than LLM Analyst does. Hashcat is embarrassingly parallel. A 7B model runs acceptably on CPU.

LLM Analyst then runs on CPU only. Q4 Foundation Sec 8B on a modern CPU gets about 5 to 8 t/s. Workable for QA and analyst roles. Too slow for interactive chat. That's fine. Claude Code on the operator's laptop is the interactive surface. LLM Analyst is batch.

## Operator workstation GPU

No GPU requirement on the operator laptop beyond what Claude Code uses locally (nothing).

Eidolon pushes all heavy work server side. That's intentional.

## Related

- [`vm-roles.md`](./vm-roles.md). Cracker and LLM Analyst VM specs.
- [`provider-router.md`](./provider-router.md). Which models run where.
