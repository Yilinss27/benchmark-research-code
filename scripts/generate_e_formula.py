#!/usr/bin/env python3
"""Generate E formula tasks from template config."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.assign_time_bands import update_row as update_temporal_band

DEFAULT_TRAINING_CUTOFF = "2024-06-30"
DEFAULT_CURRENT_DATE = "2026-08-17"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--templates", default="configs/e_formula_templates_v1.json")
    parser.add_argument("--output", default="seeds/e_formula.jsonl")
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--training-cutoff", default=DEFAULT_TRAINING_CUTOFF)
    parser.add_argument("--current-date", default=DEFAULT_CURRENT_DATE)
    return parser.parse_args()


def _prompt_template() -> str:
    return (ROOT / "prompts" / "e_formula.txt").read_text(encoding="utf-8")


def _render_prompt(template: str, problem_text: str) -> str:
    return template.replace("{problem_text}", problem_text)


def _round(value: float, digits: int = 2) -> float:
    return float(f"{value:.{digits}f}")


def _materialize(formula_id: str, idx: int) -> tuple[str, float, str]:
    n = idx + 1
    if formula_id == "gordon_growth":
        fcf = 80 + 4 * n
        wacc = 8 + (n % 6)
        g = 2 + (n % 3)
        answer = _round(fcf / (wacc / 100 - g / 100), 2)
        text = (
            f"某项目未来一年自由现金流 FCF={fcf}（百万元），贴现率 WACC={wacc}%，"
            f"永续增长率 g={g}%。请根据 Gordon Growth Model 计算企业终值，结果以百万元为单位，保留两位小数。"
        )
        return text, answer, "CNY million"
    if formula_id == "wacc_blend":
        we = 50 + (n % 25)
        wd = 100 - we
        re = 9 + (n % 5)
        rd = 4 + (n % 4)
        tax = 20 + (n % 8)
        answer = _round((we / 100) * (re / 100) + (wd / 100) * (rd / 100) * (1 - tax / 100), 4)
        text = (
            f"某公司资本结构中权益占比 {we}%，债务占比 {wd}%。权益成本为 {re}%，税前债务成本为 {rd}%，"
            f"所得税率 {tax}%。请计算 WACC，结果保留四位小数（小数）。"
        )
        return text, answer, "ratio"
    if formula_id == "sharpe_ratio":
        ret = 8 + (n % 8)
        vol = 6 + (n % 7)
        rf = 2 + (n % 2)
        answer = _round((ret - rf) / vol, 2)
        text = (
            f"某投资组合年化收益率 {ret}%，年化波动率 {vol}%，无风险利率 {rf}%。"
            "请计算 Sharpe Ratio，保留两位小数。"
        )
        return text, answer, "ratio"
    if formula_id == "capm_expected_return":
        beta = _round(0.8 + (n % 8) * 0.15, 2)
        rf = 2 + (n % 3)
        rm = 8 + (n % 4)
        answer = _round(rf + beta * (rm - rf), 2)
        text = (
            f"某股票 beta={beta}，无风险利率 {rf}%，市场组合预期收益率 {rm}%。"
            "请根据 CAPM 计算该股票预期收益率（%），保留两位小数。"
        )
        return text, answer, "%"
    if formula_id == "bond_ytm_simple":
        price = 94 + (n % 8)
        payoff = 102 + (n % 6)
        answer = _round((payoff / price - 1) * 100, 2)
        text = (
            f"某面值 100 的一年期债券，当前价格 {price}，一年后兑付本息 {payoff}。"
            "请计算到期收益率（%），保留两位小数。"
        )
        return text, answer, "%"
    if formula_id == "duration_approx":
        duration = _round(4.0 + (n % 6) * 0.7, 2)
        dy = 20 + (n % 45)
        answer = _round(-duration * (dy / 10000) * 100, 2)
        text = (
            f"某债券修正久期为 {duration}，当前收益率上升 {dy} 个基点。"
            "请用久期近似计算价格变动百分比（%），保留两位小数。"
        )
        return text, answer, "%"
    if formula_id == "black_scholes_call":
        s = 90 + (n % 20)
        k = 85 + (n % 18)
        r = _round(2.0 + (n % 5) * 0.5, 1)
        t = _round(0.5 + (n % 3) * 0.25, 2)
        nd1 = _round(0.58 + (n % 7) * 0.03, 2)
        nd2 = _round(0.50 + (n % 7) * 0.03, 2)
        answer = _round(s * nd1 - k * math.exp(-(r / 100) * t) * nd2, 2)
        text = (
            f"某欧式看涨期权参数：标的价格 S={s}，行权价 K={k}，无风险利率 r={r}%（连续复利），"
            f"到期时间 T={t} 年，N(d1)={nd1}，N(d2)={nd2}。请计算看涨期权价格，保留两位小数。"
        )
        return text, answer, "price"
    if formula_id == "put_call_parity":
        s = 100 + (n % 12)
        k = 95 + (n % 10)
        r = _round(2.0 + (n % 4) * 0.5, 1)
        t = _round(0.5 + (n % 4) * 0.25, 2)
        call = _round(8 + (n % 7) * 0.9, 2)
        answer = _round(call + k * math.exp(-(r / 100) * t) - s, 2)
        text = (
            f"某欧式期权：标的价格 S={s}，行权价 K={k}，无风险利率 r={r}%（连续复利），"
            f"到期时间 T={t} 年，看涨期权价格 C={call}。请根据 Put-Call Parity 计算看跌期权价格，保留两位小数。"
        )
        return text, answer, "price"
    raise ValueError(f"Unsupported formula_id: {formula_id}")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> int:
    args = parse_args()
    payload = json.loads((ROOT / args.templates).read_text(encoding="utf-8"))
    templates = payload["templates"]
    prompt_template = _prompt_template()

    # Target distribution: easy=10, medium=15, hard=5.
    ordered = (
        [t for t in templates if t["difficulty"] == "easy"] * 5
        + [t for t in templates if t["difficulty"] == "medium"] * 5
        + [t for t in templates if t["difficulty"] == "hard"] * 3
    )
    rows: list[dict[str, Any]] = []
    for idx in range(args.count):
        t = ordered[idx % len(ordered)]
        problem_text, answer, unit = _materialize(t["formula_id"], idx)
        row = {
            "task_id": f"E-{idx + 1:05d}",
            "category": "E",
            "variant": None,
            "time_band": "T1",
            "status": "ready",
            "seed": {
                "problem_text": problem_text,
                "topic_category": t["topic_category"],
                "difficulty": t["difficulty"],
                "cutoff_date": "2024-06-01",
            },
            "prompt": _render_prompt(prompt_template, problem_text),
            "expected_output": {"formula_used": "str", "answer": "float", "unit": "str"},
            "ground_truth": {
                "correct_answer": answer,
                "correct_formula": t["formula_id"],
                "answer_unit": unit,
            },
            "metadata": {
                "is_template": False,
                "prompt_template": "prompts/e_formula.txt",
                "temporal_applicability": "atemporal_formula",
                "generation_source": "configs/e_formula_templates_v1.json",
            },
        }
        rows.append(update_temporal_band(row, args.training_cutoff, args.current_date))

    _write_jsonl(ROOT / args.output, rows)
    print(json.dumps({"output": args.output, "records": len(rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
