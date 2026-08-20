# TODO

v0.7.0 之后仍待补充。

## 论文时间几何（paper_band）

- [x] `data/task_temporal_index.jsonl` + `scripts/classify_paper_temporal.py`
- [x] Runner `--temporal-index` / `--paper-band` + `official_score`（任务等权、仅 T2）
- [x] `docs/temporal_changelog.md`
- [x] 扩 A1 论文 T1、A2-T 双带 ≥30、B earnings 扩池
- [ ] A2-F/H 论文 T1 扩至 ≥30（当前约 13，受 cohort/Yahoo 限制）
- [x] T3 前瞻模板 `seeds/t3_forward.jsonl`（84 条 pending）
- [x] 泄漏校准脚手架 `calibration/leakage_probe_v1.json` + SHA manifest

## 数据扩量

### A1 / A2（受源 CSV 限制）

- [x] Yahoo 路径下为现有 A1/A2-T 股票池补 T1/T2 配对（见 `scripts/generate_t1_t2_pairs.py`）
- [ ] 扩充 `data/a1_price_snapshots.csv` 后重跑 A1 builder（CSV 路径仍可用）
- [x] 为 A2-F/H 补 Yahoo T1/T2 配对（含 US/HK 最小集；报告滞后期近似 PIT）
- [ ] 补齐 cutoff 前 vendor PIT fundamentals，去掉旧 CSV 的 `prototype_fallback_nearest`

## Data Interface (Yahoo MVP)

Price-driven A1 / A2-T and lagged Yahoo A2-F / A2-H / B-earnings / C generation go through `src.data_generator` and `src.data.providers.yahoo`. Yahoo cache lives in `data/cache/yahoo/` and is not published.

This round:

- [x] 统一行情接口：`get_price_history` / `get_close_on_or_before` / `get_forward_close`
- [x] Yahoo provider + ticker 映射（`CN_A` / `US` / `HK`）+ 本地 JSON cache
- [x] `python -m src.data_generator --task A1|A2-T|A2-F|A2-H|B|C --market ... --cutoff-date ...`
- [x] seed 增加 `market` / `currency`；A1 prompt 按货币单位渲染
- [x] 为 A1/A2-T 补配对 T1（2023-12-29）与 T2（2026-01-30）；US/HK 最小股票池
- [x] Yahoo 滞后期财务接口（季报 +45 / 年报 +100），用于 A2-F / A2-H / C
- [x] Yahoo earnings dates 用于 B 财报题（非新闻接口）
- [ ] 真正的 vendor PIT fundamentals / events
- [ ] 大规模美股/港股题库
- [ ] B macro 扩量
- [ ] 真实 T3（未来标签未实现）

Yahoo 边界：非官方接口、有限流；A 股财务/事件质量差；365 日窗口若尚未实现则标签为 null。

相关论文（时间泄漏 / cutoff）：

- [Profit Mirage](https://arxiv.org/abs/2510.07920)
- [Time Travel is Cheating: DeepFund](https://arxiv.org/abs/2505.11065)
- [The Memorization Problem](https://arxiv.org/abs/2504.14765)
- [A Test of Lookahead Bias in LLM Forecasts](https://arxiv.org/abs/2512.23847)

### 已完成（v0.3.0 / v0.4.0）

- [x] B：填充 10 条 earnings/macro，生成 ready seeds
- [x] D：6 → 12
- [x] E：5 → 12
- [x] 每条 ready seed 增加 `cutoff_date`、`time_band`、`metadata.temporal_split`

## 仓库解耦

- [x] `scripts/export_hf_dataset.py` 导出 `hf_dataset/`（仅数据）
- [x] HF dataset card 配置 `configs`（`a1`/`a2_f`/…/`e`）
- [x] 将 `hf_dataset/` 上传到 HF，并删除远端代码文件
- [x] 本代码仓推送到独立 GitHub

## 公开发布

- [ ] 确认是否隐藏 A1 `ground_truth` 中的未来价格
- [ ] HF 仓库是否改为 public

## 完成检查

- [x] `python scripts/validate.py`
- [x] `python scripts/export_hf_dataset.py --clean`
- [x] `manifest.json` 计数与 seeds 行数一致
- [x] `load_dataset("sselaine27/benchmark-research", "a1")` 可按子集加载
