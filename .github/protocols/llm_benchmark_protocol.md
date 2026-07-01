# Protocol — LLM Benchmark (vm_agent / H100 fleet)

Purpose: prove train + infer with hard metrics. Synthetic data. Reproducible. No vibes.

## Communication contract (report style)

Caveman engineer. No prose. No bulletpoints. Metric lines + tables only.
Line shape: `key=val key=val -> result`. Numbers carry units. Fragments fine.
Forbidden: narrative sentences, "we observe that", filler, hedging.
Allowed: tables, `k=v` lines, equations, raw measured numbers.

## Scope

Target: real `deepseek_v4` arch (shrunk to fit 94GB) + dense Llama-style control (clean MFU).
Hardware: `Standard_NC40ads_H100_v5`, 1x H100 NVL 94GB/node, 100GbE, no IB.
Data: synthetic. random token ids. fixed seed. no external corpus.

## Metrics (mandatory, all runs)

Throughput:
- `tok_s` tokens/sec (train: processed; infer-decode: generated).
- `prefill_tok_s` prefill tokens/sec (infer).
- `step_ms` mean step wall time.
- `ttft_ms` time-to-first-token (infer, bs=1).

Compute:
- `tflops` achieved = FLOPs / time. train FLOPs=6*active_params*tokens. infer-fwd FLOPs=2*active_params*tokens.
- `mfu` = tflops / peak_bf16. peak_bf16 declared constant (state value). dense=exact, MoE=active-param est.
- `active_params`, `total_params`.

Resource (nvidia-smi sampled >=5Hz over the measured window, report mean+max):
- `pow_w` power draw W.
- `util_pct` GPU util %.
- `mem_used_gb` device mem used (nvidia-smi).
- `torch_peak_gb` torch max_memory_allocated.
- `sm_mhz` SM clock.
- `temp_c` temperature.

Distributed (scaling runs):
- `global_tok_s` summed across ranks.
- `scaling_eff` = global_tok_s(N) / (N * tok_s(1)).
- `busbw_GBps` gradient all-reduce bus bandwidth.

## Method (per measurement)

1. fixed seed. build model bf16 on cuda.
2. warmup >=3 iters (discard). `torch.cuda.synchronize()` around timed region.
3. timed region >=8 iters. start sampler before, stop after.
4. emit one `RESULT_JSON={...}` line per config.
5. sweep declared BEFORE run. thresholds declared BEFORE run.

## Sweeps (declared)

infer: batch x seqlen grid. decode 64 new tokens. greedy.
train: batch x seqlen grid. fwd+bwd+AdamW.
scale: world in {1,2,4,8,20}. fixed per-rank workload. report global tok_s + eff.

## Falsifying signals (must NOT occur for PASS)

- loss flat/NaN on overfit synthetic batch -> train broken.
- tok_s not monotone-ish with batch (sub-linear ok, regression not) -> investigate.
- params_synced False any rank -> distributed broken.
- mfu absurd (>1.0 or ~0) -> FLOPs/timing bug.

## Report format (output)

File: `build_spec/llm_benchmark_report_<YYYYMMDD>.md`.
Sections (tables only):
1. RIG — hw/sw/model facts.
2. INFER — sweep table.
3. TRAIN — sweep table.
4. SCALE — world-size table + eff.
5. DERIVED — extrapolation to real 1.6T (state assumptions).
6. LANDMINES — k=v lines.
Every number traceable to a `RESULT_JSON` artifact on node.

## Reproduce

artifacts: `/mnt/llmproof/bench_*.jsonl` on node-0; scaling logs `/tmp/scale_*.log` on driver.
scripts: `scripts/llm_proof/bench.py`, `scripts/llm_proof/bench_dist.py`.
