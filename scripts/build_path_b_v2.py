#!/usr/bin/env python3
"""Build the frozen Path B / v2 review ledger and HF delivery package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.providers.yahoo import YahooPriceProvider
from src.temporal.evidence_provenance import DEFAULT_CACHE_DIR, fetch_url_bytes, hash_price_bar

BASELINE_COMMIT = "736273f4d211c0c31fab43da1fbfd49509598e85"
BASELINE_TREE = "2ce364a577336f8bd88a960397ed7a692fb1a7b2"
DEFAULT_BASELINE = ROOT / "artifacts/hf_736273f"
DEFAULT_OUTPUT = ROOT / "hf_dataset_path_b_v2"
LEDGER_PATH = ROOT / "calibration/review_ledger_v2.csv"
PACKAGES_PATH = ROOT / "calibration/evidence_packages_v2.jsonl"
MANIFEST_PATH = ROOT / "calibration/path_b_v2_manifest.json"
EXCLUSIONS_PATH = ROOT / "calibration/path_b_v2_exclusions.csv"
ATTESTATIONS_PATH = ROOT / "calibration/review_attestations_v2.csv"
REVIEW_CONTRACT_PATH = ROOT / "configs/path_b_v2_review_contract.json"
TEMPORAL_INDEX_PATH = ROOT / "data/task_temporal_index.jsonl"
TABLE1_PATH = ROOT / "calibration/temporal_provenance_table.csv"
TABLE2_PATH = ROOT / "calibration/b_event_evidence_table.csv"

COLLECTOR_ID = "deepfineval_evidence_collector_v2"
ATTESTATION_FIELDS = (
    "task_id",
    "decision",
    "reviewer_id",
    "review_method",
    "reviewed_at",
    "evidence_package_sha256",
    "review_notes",
    "attestation_sha256",
)
BLOCKING_FLAGS = {
    "fundamentals_after_origin",
    "heuristic_outcome_availability",
    "missing_event_evidence",
    "missing_outcome_evidence",
    "modeled_outcome_availability",
    "non_pit_fundamentals",
    "official_disclosure_lookup_failed",
}
EXCLUDED_FILE_HASHES = {
    "data/a2_f/train.jsonl": "2258a0c7ef13c93da1d995b7d8739178b4dff141c0082603f0d6a2ba7f43f4d0",
    "data/a2_h/train.jsonl": "c7fe4a2f2c38a729c4cdd46b99ce59c7eb496ba37f7409d561ac5f8687ed257d",
    "data/c/train.jsonl": "2698e0fda7c3b35312a183f1a117bd68398cbe372fcdf69b56b9fa28abc9ee02",
    "data/d/train.jsonl": "a0c339d0ada9e05472173ceaa7580a490f1f845651321bd496d8f4efb57f1527",
    "data/e/train.jsonl": "bc4ee2f25b2e68f1e15603f52621320c4def26f7890abeae4d3b8205ac0b77a1",
}
MACRO_ARCHIVE_OVERRIDES = {
    "B-MACRO-CN_A-20250109-CPI-600519": {
        "url": "https://www.stats.gov.cn/xxgk/sjfb/zxfb2020/202501/t20250109_1958170.html",
        "published_at": "2025-01-09T01:30:00Z",
    },
    "B-MACRO-CN_A-20250127-PMI-601318": {
        "url": "https://www.stats.gov.cn/xxgk/sjfb/zxfb2020/202501/t20250127_1958493.html",
        "published_at": "2025-01-27T01:30:00Z",
    },
}

LEDGER_FIELDS = (
    "task_id",
    "scope_role",
    "category",
    "variant",
    "paper_band",
    "review_status",
    "official_temporal_eligible",
    "collector_id",
    "reviewer_id",
    "review_method",
    "reviewed_at",
    "event_evidence_status",
    "price_evidence_status",
    "exclusion_reason_code",
    "review_notes",
    "evidence_package_sha256",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fetch-content", action="store_true")
    parser.add_argument("--attestations", type=Path, default=ATTESTATIONS_PATH)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_csv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["task_id"]: row for row in csv.DictReader(handle)}


def load_review_methods() -> set[str]:
    contract = json.loads(REVIEW_CONTRACT_PATH.read_text(encoding="utf-8"))
    return {str(value) for value in contract.get("review_method_enum", [])}


def normalize_flags(*values: Any) -> set[str]:
    flags: set[str] = set()
    for value in values:
        if isinstance(value, str):
            flags.update(part.strip() for part in value.split(",") if part.strip())
        elif isinstance(value, list):
            flags.update(str(part).strip() for part in value if str(part).strip())
    return flags


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_sha(payload: Any) -> str:
    content = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(content)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def snapshot_item(cache_key: str, kind: str) -> dict[str, Any] | None:
    root = Path(DEFAULT_CACHE_DIR)
    safe_key = cache_key.replace("/", "_").replace(":", "_")
    metadata_path = root / f"{safe_key}.provenance.json"
    if not metadata_path.exists():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    binary_path = root / f"{safe_key}.bin"
    source_path = root / f"{safe_key}.source"
    snapshot_path = binary_path if binary_path.exists() else source_path
    if not snapshot_path.exists():
        return None
    actual_sha = sha256_file(snapshot_path)
    if actual_sha != metadata.get("content_sha256"):
        return None
    return {
        "kind": kind,
        "cache_key": safe_key,
        "source_url": metadata.get("source_url"),
        "published_at": metadata.get("published_at"),
        "fetched_at": metadata.get("fetched_at"),
        "snapshot_sha256": actual_sha,
        "snapshot_path": f"evidence/snapshots/{actual_sha[:2]}/{actual_sha}",
        "parser_version": metadata.get("parser_version"),
    }


def price_item(
    *,
    provider: YahooPriceProvider,
    symbol: str,
    market: str,
    trading_day: str,
    role: str,
    fetch_content: bool,
) -> dict[str, Any] | None:
    cache_key = f"price_raw_{market}_{symbol}_{trading_day}_{role}"
    existing = snapshot_item(cache_key, "price_snapshot")
    if existing is not None:
        return existing
    if not fetch_content:
        return None
    bar = provider.get_close_on_or_before(symbol, market, trading_day)
    if bar is None or bar.trading_day != trading_day:
        return None
    artifact = hash_price_bar(
        symbol=symbol,
        market=market,
        bar=bar,
        role=role,
    )
    if not artifact.manual_review_eligible:
        return None
    return snapshot_item(cache_key, "price_snapshot")


def event_item(
    task_id: str,
    table_row: dict[str, str],
    *,
    fetch_content: bool,
) -> dict[str, Any] | None:
    cache_key = f"b_{task_id}"
    existing = snapshot_item(cache_key, "event_snapshot")
    if (
        existing is not None
        and existing.get("source_url") == table_row.get("evidence_url")
    ):
        return existing
    override = MACRO_ARCHIVE_OVERRIDES.get(task_id)
    if not fetch_content or not override:
        return None
    try:
        fetch_url_bytes(
            override["url"],
            cache_key=cache_key,
            published_at=override["published_at"],
            parser_version="path_b_v2_official_archive",
            timeout_seconds=45,
            user_agent="Mozilla/5.0 (compatible; DeepFinEval evidence review)",
        )
    except Exception:
        return None
    return snapshot_item(cache_key, "event_snapshot")


def baseline_item(record: dict[str, Any], hf_config: str) -> dict[str, Any]:
    return {
        "kind": "baseline_task_identity",
        "cache_key": f"hf_{BASELINE_COMMIT}_{record['task_id']}",
        "source_url": (
            f"https://huggingface.co/datasets/sselaine27/benchmark-research/"
            f"blob/{BASELINE_COMMIT}/data/{hf_config}/train.jsonl"
        ),
        "published_at": None,
        "fetched_at": None,
        "snapshot_sha256": canonical_sha(record),
        "snapshot_path": None,
        "parser_version": "path_b_v2_baseline_identity",
    }


def package_row(task_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(items, key=lambda item: (str(item["kind"]), str(item["cache_key"])))
    return {
        "task_id": task_id,
        "items": ordered,
        "evidence_package_sha256": canonical_sha(ordered),
    }


def attestation_payload(row: dict[str, str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in ATTESTATION_FIELDS if field != "attestation_sha256"}


def validate_attestation(
    row: dict[str, str],
    *,
    task_id: str,
    package: dict[str, Any],
    review_methods: set[str],
) -> str | None:
    if row.get("task_id") != task_id:
        return "task_id mismatch"
    if row.get("decision") != "reviewed":
        return "decision must be reviewed"
    if not row.get("reviewer_id"):
        return "reviewer_id is required"
    if row.get("review_method") not in review_methods:
        return "review_method is not in the formal contract"
    if row.get("evidence_package_sha256") != package["evidence_package_sha256"]:
        return "evidence package hash mismatch"
    if canonical_sha(attestation_payload(row)) != row.get("attestation_sha256"):
        return "attestation hash mismatch"
    try:
        reviewed_at = datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return "reviewed_at must be timezone-aware RFC3339"
    if reviewed_at.tzinfo is None:
        return "reviewed_at must include a timezone"
    for item in package["items"]:
        if item.get("fetched_at"):
            fetched_at = datetime.fromisoformat(str(item["fetched_at"]).replace("Z", "+00:00"))
            if reviewed_at <= fetched_at:
                return "reviewed_at must be later than every fetched_at"
    if not row.get("review_notes") or row["review_notes"].strip().lower() == "ok":
        return "review_notes must describe the manual check"
    return None


def materialize_snapshots(packages: list[dict[str, Any]], output: Path) -> int:
    cache_root = Path(DEFAULT_CACHE_DIR)
    copied: set[str] = set()
    for package in packages:
        for item in package["items"]:
            destination_rel = item.get("snapshot_path")
            if not destination_rel:
                continue
            expected_sha = str(item["snapshot_sha256"])
            if expected_sha in copied:
                continue
            cache_key = str(item["cache_key"])
            binary_path = cache_root / f"{cache_key}.bin"
            source_path = cache_root / f"{cache_key}.source"
            source = binary_path if binary_path.exists() else source_path
            if not source.exists() or sha256_file(source) != expected_sha:
                raise SystemExit(f"Missing or corrupt source snapshot: {cache_key}")
            destination = output / str(destination_rel)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.add(expected_sha)
    return len(copied)


def attach_review(record: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    row = dict(record)
    for field in LEDGER_FIELDS:
        if field != "task_id":
            row[field] = ledger[field]
    return row


def build_readme(counts: dict[str, int]) -> str:
    return f"""---
license: cc-by-4.0
language:
- zh
pretty_name: Benchmark Research Path B v2
configs:
- config_name: a1
  data_files:
  - split: train
    path: data/a1/train.jsonl
- config_name: a2_t
  data_files:
  - split: train
    path: data/a2_t/train.jsonl
- config_name: b_earnings
  data_files:
  - split: train
    path: data/b_earnings/train.jsonl
---

# Benchmark Research — Path B / v2

冻结基线：`{BASELINE_COMMIT}`（tree `{BASELINE_TREE}`）。

本包只含 T1/T2 候选：A1 {counts['a1']}、A2-T {counts['a2_t']}、
B-earnings {counts['b_earnings']}，合计 {sum(counts.values())} 行。

C、A2-F、A2-H、D、E 不进入本轮；13 条 B-macro 只保留在 calibration
审核账本，不进入 T1/T2 比较包。每行的 v2 审核字段来自
`calibration/review_ledger_v2.csv`。

自动构建只采集证据并输出 `draft`。只有
`calibration/review_attestations_v2.csv` 中存在与当前 evidence package hash
完全匹配的独立人工签核时，记录才会晋升为 `reviewed`。原始证据按 SHA-256
存放于 `evidence/snapshots/<前两位>/<完整 SHA-256>`。
"""


def main() -> int:
    args = parse_args()
    baseline_data = args.baseline / "data"
    for rel, expected in EXCLUDED_FILE_HASHES.items():
        actual = sha256_file(args.baseline / rel)
        if actual != expected:
            raise SystemExit(f"Frozen file hash mismatch: {rel}: {actual}")

    a1_rows = load_jsonl(baseline_data / "a1/train.jsonl")
    a2t_rows = load_jsonl(baseline_data / "a2_t/train.jsonl")
    b_rows = load_jsonl(baseline_data / "b/train.jsonl")
    scoped_rows = a1_rows + a2t_rows + b_rows
    if len(scoped_rows) != 543 or len({row["task_id"] for row in scoped_rows}) != 543:
        raise SystemExit("Path B scope must contain exactly 543 unique task_ids")

    temporal = {row["task_id"]: row for row in load_jsonl(TEMPORAL_INDEX_PATH)}
    table1 = load_csv(TABLE1_PATH)
    table2 = load_csv(TABLE2_PATH)
    review_methods = load_review_methods()
    if not args.attestations.exists():
        write_csv(args.attestations, ATTESTATION_FIELDS, [])
    attestations = load_csv(args.attestations)
    provider = YahooPriceProvider()
    ledger_rows: list[dict[str, Any]] = []
    package_rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    reviewed_by_id: dict[str, dict[str, Any]] = {}

    for record in scoped_rows:
        task_id = record["task_id"]
        category = record["category"]
        variant = str(record.get("variant") or "")
        index = temporal.get(task_id) or {}
        paper_band = str(record.get("paper_band") or index.get("paper_band") or "")
        market = str((record.get("seed") or {}).get("market") or "CN_A")
        symbol = str((record.get("seed") or {}).get("stock_code") or "")
        items: list[dict[str, Any]] = []
        event_status = "not_applicable"
        price_status = "missing"
        exclusion = ""
        notes = ""

        hf_config = "a1" if category == "A1" else "a2_t" if category == "A2" else "b"
        items.append(baseline_item(record, hf_config))

        if category == "A1":
            day = str(index.get("outcome_available_at") or "")[:10]
            item = price_item(
                provider=provider,
                symbol=symbol,
                market=market,
                trading_day=day,
                role="primary_forward_close",
                fetch_content=args.fetch_content,
            )
            if item:
                items.append(item)
                price_status = "draft"
                notes = "已采集 forward close 原始响应快照；等待独立人工签核。"
            else:
                exclusion = "price_snapshot_missing"
                notes = "缺少可核验的 forward close 原始响应快照。"
        elif category == "A2" and variant == "T":
            forward_days = index.get("forward_trading_days") or {}
            price_items = []
            for stock in (record.get("seed") or {}).get("stock_list", []):
                code = str(stock.get("code") or "")
                day = str(forward_days.get(code) or index.get("outcome_available_at") or "")[:10]
                item = price_item(
                    provider=provider,
                    symbol=code,
                    market=market,
                    trading_day=day,
                    role="cohort_forward_close",
                    fetch_content=args.fetch_content,
                )
                if item:
                    price_items.append(item)
            expected_count = len((record.get("seed") or {}).get("stock_list", []))
            items.extend(price_items)
            if expected_count and len(price_items) == expected_count:
                price_status = "draft"
                notes = (
                    f"已采集固定基线标的名单及全部 {expected_count} 个标的的 "
                    "forward close 原始响应快照；等待独立人工签核。"
                )
            else:
                exclusion = "cohort_price_snapshot_incomplete"
                notes = f"标的价格快照仅完成 {len(price_items)}/{expected_count}。"
        elif category == "B":
            event_status = "missing"
            event = event_item(task_id, table2.get(task_id, {}), fetch_content=args.fetch_content)
            if event:
                items.append(event)
                event_status = "draft"
            is_earnings = variant == "earnings"
            if is_earnings:
                day = str(index.get("outcome_available_at") or "")[:10]
                price = price_item(
                    provider=provider,
                    symbol=symbol,
                    market=market,
                    trading_day=day,
                    role="event_reaction_close",
                    fetch_content=args.fetch_content,
                )
                if price:
                    items.append(price)
                    price_status = "draft"
                if event_status == "draft" and price_status == "draft":
                    notes = "已采集 earnings 第一方公告及 reaction close 快照；等待独立人工签核。"
                elif event_status != "draft":
                    exclusion = "event_snapshot_missing"
                    notes = "缺少可核验的 earnings 第一方公告快照。"
                else:
                    exclusion = "price_snapshot_missing"
                    notes = "缺少 release-adjusted reaction close 原始响应快照。"
            else:
                price_status = "not_applicable"
                if event_status == "draft":
                    notes = "已采集宏观事件第一方发布快照；等待独立人工签核。"
                else:
                    exclusion = "official_event_snapshot_unfetchable"
                    notes = "官方事件 URL 可定位，但自动抓取失败。"

        package = package_row(task_id, items)
        package_rows.append(package)
        blocking_flags = normalize_flags(
            record.get("quality_flags"),
            index.get("quality_flags"),
        )
        active_blocking_flags = sorted(blocking_flags & BLOCKING_FLAGS)
        evidence_ready = (
            event_status in {"draft", "not_applicable"}
            and price_status in {"draft", "not_applicable"}
            and not exclusion
            and not active_blocking_flags
        )
        attestation = attestations.get(task_id)
        if attestation:
            error = validate_attestation(
                attestation,
                task_id=task_id,
                package=package,
                review_methods=review_methods,
            )
            if error:
                raise SystemExit(f"Invalid attestation for {task_id}: {error}")
            if not evidence_ready:
                raise SystemExit(
                    f"Attestation for {task_id} cannot override missing evidence or blocking flags"
                )
        reviewed = bool(attestation) and evidence_ready
        if reviewed:
            event_status = "reviewed" if event_status == "draft" else event_status
            price_status = "reviewed" if price_status == "draft" else price_status
            exclusion = ""
            notes = str(attestation["review_notes"])
        elif active_blocking_flags:
            exclusion = "blocking_quality_flags"
            notes = f"存在阻断标记：{','.join(active_blocking_flags)}。"
        elif evidence_ready:
            exclusion = "human_attestation_missing"

        ledger = {
            "task_id": task_id,
            "scope_role": (
                "both"
                if category == "B" and variant == "earnings"
                else "b_calibration"
                if category == "B"
                else "temporal_t1_t2"
            ),
            "category": category,
            "variant": variant,
            "paper_band": paper_band,
            "review_status": "reviewed" if reviewed else "draft",
            "official_temporal_eligible": "true" if reviewed else "false",
            "collector_id": COLLECTOR_ID,
            "reviewer_id": attestation["reviewer_id"] if reviewed else "",
            "review_method": attestation["review_method"] if reviewed else "",
            "reviewed_at": attestation["reviewed_at"] if reviewed else "",
            "event_evidence_status": event_status,
            "price_evidence_status": price_status,
            "exclusion_reason_code": exclusion,
            "review_notes": notes,
            "evidence_package_sha256": package["evidence_package_sha256"],
        }
        ledger_rows.append(ledger)
        reviewed_by_id[task_id] = ledger
        if exclusion:
            exclusions.append(
                {
                    "task_id": task_id,
                    "exclusion_reason_code": exclusion,
                    "review_notes": notes,
                }
            )

    ledger_rows.sort(key=lambda row: row["task_id"])
    package_rows.sort(key=lambda row: row["task_id"])
    exclusions.sort(key=lambda row: row["task_id"])
    write_csv(LEDGER_PATH, LEDGER_FIELDS, ledger_rows)
    write_jsonl(PACKAGES_PATH, package_rows)
    write_csv(
        EXCLUSIONS_PATH,
        ("task_id", "exclusion_reason_code", "review_notes"),
        exclusions,
    )

    if args.output.exists():
        shutil.rmtree(args.output)
    snapshot_count = materialize_snapshots(package_rows, args.output)
    candidate_sets = {
        "a1": [attach_review(row, reviewed_by_id[row["task_id"]]) for row in a1_rows],
        "a2_t": [attach_review(row, reviewed_by_id[row["task_id"]]) for row in a2t_rows],
        "b_earnings": [
            attach_review(row, reviewed_by_id[row["task_id"]])
            for row in b_rows
            if row.get("variant") == "earnings"
        ],
    }
    for config, rows in candidate_sets.items():
        write_jsonl(args.output / f"data/{config}/train.jsonl", rows)
    counts = {config: len(rows) for config, rows in candidate_sets.items()}
    (args.output / "README.md").write_text(build_readme(counts), encoding="utf-8")

    manifest = {
        "package": "path_b_v2",
        "baseline": {
            "repo": "sselaine27/benchmark-research",
            "commit": BASELINE_COMMIT,
            "tree": BASELINE_TREE,
        },
        "scope": {
            "ledger_unique_tasks": len(ledger_rows),
            "t1_t2_candidates": sum(counts.values()),
            "a1": counts["a1"],
            "a2_t": counts["a2_t"],
            "b_earnings": counts["b_earnings"],
            "b_calibration_total": len(b_rows),
            "b_macro_calibration_only": sum(
                row.get("variant") == "macro" for row in b_rows
            ),
        },
        "excluded_files_sha256": EXCLUDED_FILE_HASHES,
        "review_methods": sorted(review_methods),
        "reviewed_count": sum(row["review_status"] == "reviewed" for row in ledger_rows),
        "draft_count": sum(row["review_status"] == "draft" for row in ledger_rows),
        "exclusion_count": len(exclusions),
        "snapshot_count": snapshot_count,
        "files": {
            "calibration/review_ledger_v2.csv": sha256_file(LEDGER_PATH),
            "calibration/review_attestations_v2.csv": sha256_file(args.attestations),
            "calibration/evidence_packages_v2.jsonl": sha256_file(PACKAGES_PATH),
            "calibration/path_b_v2_exclusions.csv": sha256_file(EXCLUSIONS_PATH),
            "configs/path_b_v2_review_contract.json": sha256_file(REVIEW_CONTRACT_PATH),
            "calibration/temporal_provenance_table.csv": sha256_file(TABLE1_PATH),
            "calibration/b_event_evidence_table.csv": sha256_file(TABLE2_PATH),
            "data/a1/train.jsonl": sha256_file(args.output / "data/a1/train.jsonl"),
            "data/a2_t/train.jsonl": sha256_file(args.output / "data/a2_t/train.jsonl"),
            "data/b_earnings/train.jsonl": sha256_file(
                args.output / "data/b_earnings/train.jsonl"
            ),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(MANIFEST_PATH, args.output / "path_b_v2_manifest.json")
    calibration_out = args.output / "calibration"
    calibration_out.mkdir(parents=True, exist_ok=True)
    for source in (
        LEDGER_PATH,
        args.attestations,
        PACKAGES_PATH,
        EXCLUSIONS_PATH,
        TABLE1_PATH,
        TABLE2_PATH,
    ):
        shutil.copy2(source, calibration_out / source.name)
    contract_out = args.output / "configs"
    contract_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REVIEW_CONTRACT_PATH, contract_out / REVIEW_CONTRACT_PATH.name)

    print(json.dumps(manifest["scope"] | {
        "reviewed": manifest["reviewed_count"],
        "draft": manifest["draft_count"],
        "excluded": manifest["exclusion_count"],
        "snapshots": manifest["snapshot_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
