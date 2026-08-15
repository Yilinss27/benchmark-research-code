"""Minimum viable universes for paired T1/T2 generation."""

from __future__ import annotations

from typing import TypedDict

MARKET_CURRENCY = {
    "CN_A": "CNY",
    "US": "USD",
    "HK": "HKD",
}

CURRENCY_UNIT = {
    "CNY": "元",
    "USD": "USD",
    "HKD": "HKD",
}


class UniverseName(TypedDict):
    """One listed name in a market universe."""

    stock_code: str
    stock_name: str


class CohortSpec(TypedDict):
    """A2 ranking cohort definition."""

    cohort_key: str
    industry_name: str
    stocks: list[UniverseName]


A1_UNIVERSE: dict[str, list[UniverseName]] = {
    "CN_A": [
        {"stock_code": "600519", "stock_name": "贵州茅台"},
        {"stock_code": "000858", "stock_name": "五粮液"},
        {"stock_code": "601318", "stock_name": "中国平安"},
        {"stock_code": "600036", "stock_name": "招商银行"},
        {"stock_code": "601398", "stock_name": "工商银行"},
        {"stock_code": "600030", "stock_name": "中信证券"},
        {"stock_code": "300750", "stock_name": "宁德时代"},
        {"stock_code": "601012", "stock_name": "隆基绿能"},
        {"stock_code": "002594", "stock_name": "比亚迪"},
        {"stock_code": "300760", "stock_name": "迈瑞医疗"},
        {"stock_code": "600276", "stock_name": "恒瑞医药"},
        {"stock_code": "603259", "stock_name": "药明康德"},
        {"stock_code": "000333", "stock_name": "美的集团"},
        {"stock_code": "000651", "stock_name": "格力电器"},
        {"stock_code": "603288", "stock_name": "海天味业"},
        {"stock_code": "601888", "stock_name": "中国中免"},
        {"stock_code": "300059", "stock_name": "东方财富"},
        {"stock_code": "688981", "stock_name": "中芯国际"},
        {"stock_code": "000002", "stock_name": "万科A"},
        {"stock_code": "601668", "stock_name": "中国建筑"},
    ],
    "US": [
        {"stock_code": "AAPL", "stock_name": "Apple"},
        {"stock_code": "MSFT", "stock_name": "Microsoft"},
        {"stock_code": "JPM", "stock_name": "JPMorgan"},
    ],
    "HK": [
        {"stock_code": "0700", "stock_name": "腾讯控股"},
        {"stock_code": "0005", "stock_name": "汇丰控股"},
        {"stock_code": "9988", "stock_name": "阿里巴巴"},
    ],
}

B_UNIVERSE: dict[str, list[UniverseName]] = {
    "CN_A": [
        {"stock_code": "600519", "stock_name": "贵州茅台"},
        {"stock_code": "000858", "stock_name": "五粮液"},
        {"stock_code": "601318", "stock_name": "中国平安"},
        {"stock_code": "600036", "stock_name": "招商银行"},
        {"stock_code": "300750", "stock_name": "宁德时代"},
        {"stock_code": "002594", "stock_name": "比亚迪"},
    ],
    "US": [
        {"stock_code": "AAPL", "stock_name": "Apple"},
        {"stock_code": "MSFT", "stock_name": "Microsoft"},
        {"stock_code": "JPM", "stock_name": "JPMorgan"},
    ],
    "HK": [
        {"stock_code": "0700", "stock_name": "腾讯控股"},
        {"stock_code": "0005", "stock_name": "汇丰控股"},
        {"stock_code": "9988", "stock_name": "阿里巴巴"},
    ],
}

C_METRICS = ("operating_revenue", "net_profit")

B_EVENT_WINDOWS = {
    "2023-12-29": ("2023-07-01", "2024-06-01"),
    "2026-01-30": ("2025-07-01", "2026-07-31"),
}

A2_T_COHORTS: dict[str, list[CohortSpec]] = {
    "CN_A": [
        {
            "cohort_key": "financial",
            "industry_name": "大金融",
            "stocks": [
                {"stock_code": "000001", "stock_name": "平安银行"},
                {"stock_code": "600036", "stock_name": "招商银行"},
                {"stock_code": "601398", "stock_name": "工商银行"},
                {"stock_code": "601318", "stock_name": "中国平安"},
                {"stock_code": "600030", "stock_name": "中信证券"},
                {"stock_code": "300059", "stock_name": "东方财富"},
            ],
        },
        {
            "cohort_key": "consumer",
            "industry_name": "消费龙头",
            "stocks": [
                {"stock_code": "600519", "stock_name": "贵州茅台"},
                {"stock_code": "000858", "stock_name": "五粮液"},
                {"stock_code": "000333", "stock_name": "美的集团"},
                {"stock_code": "000651", "stock_name": "格力电器"},
                {"stock_code": "603288", "stock_name": "海天味业"},
                {"stock_code": "601888", "stock_name": "中国中免"},
            ],
        },
    ],
    "US": [
        {
            "cohort_key": "us_mega",
            "industry_name": "US mega-cap",
            "stocks": [
                {"stock_code": "AAPL", "stock_name": "Apple"},
                {"stock_code": "MSFT", "stock_name": "Microsoft"},
                {"stock_code": "GOOGL", "stock_name": "Alphabet"},
                {"stock_code": "AMZN", "stock_name": "Amazon"},
                {"stock_code": "JPM", "stock_name": "JPMorgan"},
                {"stock_code": "JNJ", "stock_name": "Johnson & Johnson"},
            ],
        }
    ],
    "HK": [
        {
            "cohort_key": "hk_bluechip",
            "industry_name": "港股蓝筹",
            "stocks": [
                {"stock_code": "0700", "stock_name": "腾讯控股"},
                {"stock_code": "0005", "stock_name": "汇丰控股"},
                {"stock_code": "9988", "stock_name": "阿里巴巴"},
                {"stock_code": "0941", "stock_name": "中国移动"},
                {"stock_code": "1299", "stock_name": "友邦保险"},
                {"stock_code": "0388", "stock_name": "香港交易所"},
            ],
        }
    ],
}


def currency_for_market(market: str) -> str:
    """Return ISO currency code for a market."""
    if market not in MARKET_CURRENCY:
        raise ValueError(f"Unsupported market: {market}")
    return MARKET_CURRENCY[market]


def currency_unit(currency: str) -> str:
    """Return display unit used in A1 prompts."""
    return CURRENCY_UNIT.get(currency, currency)
