# TODO

v0.4.0 之后仍待补充。

## 数据扩量

### A1 / A2（受源 CSV 限制）

- [ ] 扩充 `data/a1_price_snapshots.csv` 后重跑 A1 builder
- [ ] 新增 A2 cohort + 对应 `a2_price_series` / fundamentals 后重跑 A2-F/T/H
- [ ] 补齐 cutoff 前 fundamentals，去掉 `prototype_fallback_nearest`

### 数据接口接入（A股 / 美股）

当前数据来自手动下载后的本地 CSV。后续需要把 builder 前的数据层抽象出来，支持从标准数据接口拉取并缓存，再生成统一 seed。

- [ ] 设计统一行情接口：`get_price_history(symbol, start_date, end_date, market)`
- [ ] 设计统一财务接口：`get_fundamentals(symbol, as_of_date, market)`
- [ ] 设计统一事件接口：`get_events(symbol_or_index, start_date, end_date, market)`
- [ ] 增加市场字段：`market = CN_A | US`
- [ ] A股数据源候选：Tushare、AkShare、BaoStock、Wind/Choice（如有权限）
- [ ] 美股数据源候选：Polygon、Alpha Vantage、Yahoo Finance、SEC/EDGAR、FMP
- [ ] 为每个接口增加本地缓存层，避免重复请求和保证可复现
- [ ] 为 A1/A2/B/C builder 增加 `--market` 与 `--data-provider` 参数
- [ ] 明确数据许可与再分发边界：接口拉取代码可开源，原始商业数据不直接上传 GitHub
- [ ] 补充 US stocks 的 A1/A2/C 样例，并确认 ticker / exchange / currency 字段规范

### 已完成（v0.3.0 / v0.4.0）

- [x] B：填充 10 条 earnings/macro，生成 ready seeds
- [x] D：6 → 12
- [x] E：5 → 12
- [x] 每条 ready seed 增加 `cutoff_date`、`time_band`、`metadata.temporal_split`

## 仓库解耦

- [x] `scripts/export_hf_dataset.py` 导出 `hf_dataset/`（仅数据）
- [x] HF dataset card 配置 `configs`（`a1`/`a2_f`/…/`e`）
- [x] 将 `hf_dataset/` 上传到 HF，并删除远端代码文件
- [ ] 本代码仓推送到独立 GitHub

## 公开发布

- [ ] 确认是否隐藏 A1 `ground_truth` 中的未来价格
- [ ] HF 仓库是否改为 public

## 完成检查

- [ ] `python scripts/validate.py`
- [ ] `python scripts/export_hf_dataset.py --clean`
- [ ] `manifest.json` 计数与 seeds 行数一致
- [ ] `load_dataset("sselaine27/benchmark-research", "a1")` 可按子集加载
