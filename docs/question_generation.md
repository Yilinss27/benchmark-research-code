# 可复现题目生成

统一入口 `python -m src.question_generator` 将用户提供的 CSV 数据转换成现有
benchmark record。生成器复用各题型 builder，不读取模型输出，也不会生成或
猜测日期、URL、SHA、审核人或人工审核结论。

## 快速使用

复制并修改 `configs/question_generation.example.json`，然后运行：

```bash
python -m src.question_generator \
  --spec configs/question_generation.example.json \
  --clean
```

配置中的相对路径均以 spec 文件所在目录为基准。输出包含：

- 每个 job 指定的 JSONL 题目文件；
- `generation_manifest.json`，记录输入与输出 SHA-256；
- `calibration/evidence_packages.jsonl`；
- 若提供原始证据，则包含
  `evidence/snapshots/<SHA 前两位>/<完整 SHA-256>`。

所有自动生成记录固定为 `review_status=draft` 和
`official_temporal_eligible=false`。人工审核必须走独立 attestation 流程。

## 支持的输入

- A1：`input_csv`，沿用 `a1_from_csv_builder` 的字段。
- A2-T：`price_series_csv`。
- A2-F：`fundamentals_csv`、`cohorts_csv`、`returns_csv`。
- A2-H：`fundamentals_csv`、`price_series_csv`。
- B：`input_csv`，沿用 B event CSV 字段。
- C：`input_csv`，沿用 C financial snapshot CSV 字段。

A1、B、C 必须分别提供 `task_id`、`event_id`、`task_id`。所有 A2 输入必须为
同一 cohort 的每一行提供一致且非空的 `task_id`。生成器逐项比较输入和输出
ID；缺失、替换、重复或自动新造 ID 会直接失败。

## 证据输入

在 spec 顶层设置 `evidence_jsonl`。每行格式：

```json
{"task_id":"A1-00001","items":[{"kind":"price_snapshot","source_url":"https://example.org/source","published_at":"2025-07-04T07:00:00Z","snapshot_file":"snapshots/a1-00001.json","content_sha256":"<64 位 SHA-256>"}]}
```

生成器会检查：

- URL 必须为 HTTP(S)；
- `published_at` 必须是带时区 RFC3339；
- snapshot 文件必须存在；
- 文件实际 SHA-256 必须等于声明值；
- evidence task_id 必须与本次生成题目完全对应。

设置 `"require_evidence": true` 后，任何题缺少 evidence package 都会导致构建
失败。证据齐全也只代表“可供审核”，不会自动变成 `reviewed`。

## 安全边界

- `--clean` 仅清理 spec 指定的 `output_dir`。
- `output_jsonl` 不允许绝对路径或 `..`，不能逃出输出目录。
- A2/C 数据不足会产生非 `ready` 记录；统一生成器默认拒绝。仅用于本地检查时
  可在对应 job 设置 `"allow_incomplete": true`。
- D/E 是合成或反事实题，不属于“传入带真实时间证据的数据生成事实题”的入口，
  继续使用原有 `generate_d_counterfactual.py` 和 `generate_e_formula.py`。
