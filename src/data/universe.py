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
        {"stock_code": "600276", "stock_name": "恒瑞医药"},
        {"stock_code": "601398", "stock_name": "工商银行"},
        {"stock_code": "000333", "stock_name": "美的集团"},
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
                {"stock_code": "601939", "stock_name": "建设银行"},
                {"stock_code": "601288", "stock_name": "农业银行"},
                {"stock_code": "601166", "stock_name": "兴业银行"},
                {"stock_code": "600000", "stock_name": "浦发银行"},
                {"stock_code": "601988", "stock_name": "中国银行"},
                {"stock_code": "601628", "stock_name": "中国人寿"},
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
                {"stock_code": "002304", "stock_name": "洋河股份"},
                {"stock_code": "600887", "stock_name": "伊利股份"},
                {"stock_code": "000568", "stock_name": "泸州老窖"},
                {"stock_code": "002714", "stock_name": "牧原股份"},
                {"stock_code": "300896", "stock_name": "爱美客"},
                {"stock_code": "603369", "stock_name": "今世缘"},
            ],
        },
        {
            "cohort_key": "tech",
            "industry_name": "科技成长",
            "stocks": [
                {"stock_code": "300750", "stock_name": "宁德时代"},
                {"stock_code": "002594", "stock_name": "比亚迪"},
                {"stock_code": "688981", "stock_name": "中芯国际"},
                {"stock_code": "603501", "stock_name": "韦尔股份"},
                {"stock_code": "002415", "stock_name": "海康威视"},
                {"stock_code": "000725", "stock_name": "京东方A"},
                {"stock_code": "002230", "stock_name": "科大讯飞"},
                {"stock_code": "300014", "stock_name": "亿纬锂能"},
                {"stock_code": "688012", "stock_name": "中微公司"},
                {"stock_code": "002371", "stock_name": "北方华创"},
                {"stock_code": "603986", "stock_name": "兆易创新"},
                {"stock_code": "601012", "stock_name": "隆基绿能"},
            ],
        },
        {
            "cohort_key": "pharma",
            "industry_name": "医药健康",
            "stocks": [
                {"stock_code": "600276", "stock_name": "恒瑞医药"},
                {"stock_code": "300760", "stock_name": "迈瑞医疗"},
                {"stock_code": "603259", "stock_name": "药明康德"},
                {"stock_code": "300122", "stock_name": "智飞生物"},
                {"stock_code": "300015", "stock_name": "爱尔眼科"},
                {"stock_code": "000661", "stock_name": "长春高新"},
                {"stock_code": "600436", "stock_name": "片仔癀"},
                {"stock_code": "688235", "stock_name": "百济神州"},
                {"stock_code": "300347", "stock_name": "泰格医药"},
                {"stock_code": "002821", "stock_name": "凯莱英"},
                {"stock_code": "600196", "stock_name": "复星医药"},
                {"stock_code": "002007", "stock_name": "华兰生物"},
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
                {"stock_code": "META", "stock_name": "Meta"},
                {"stock_code": "NVDA", "stock_name": "NVIDIA"},
                {"stock_code": "V", "stock_name": "Visa"},
                {"stock_code": "MA", "stock_name": "Mastercard"},
                {"stock_code": "WMT", "stock_name": "Walmart"},
                {"stock_code": "PG", "stock_name": "Procter & Gamble"},
            ],
        },
        {
            "cohort_key": "us_tech",
            "industry_name": "US tech leaders",
            "stocks": [
                {"stock_code": "NVDA", "stock_name": "NVIDIA"},
                {"stock_code": "AMD", "stock_name": "Advanced Micro Devices"},
                {"stock_code": "AVGO", "stock_name": "Broadcom"},
                {"stock_code": "CRM", "stock_name": "Salesforce"},
                {"stock_code": "ORCL", "stock_name": "Oracle"},
                {"stock_code": "ADBE", "stock_name": "Adobe"},
                {"stock_code": "INTC", "stock_name": "Intel"},
                {"stock_code": "QCOM", "stock_name": "Qualcomm"},
                {"stock_code": "NFLX", "stock_name": "Netflix"},
                {"stock_code": "CSCO", "stock_name": "Cisco"},
                {"stock_code": "IBM", "stock_name": "IBM"},
                {"stock_code": "TXN", "stock_name": "Texas Instruments"},
            ],
        },
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
                {"stock_code": "0939", "stock_name": "建设银行"},
                {"stock_code": "1398", "stock_name": "工商银行"},
                {"stock_code": "2318", "stock_name": "中国平安"},
                {"stock_code": "3690", "stock_name": "美团"},
                {"stock_code": "1810", "stock_name": "小米集团"},
                {"stock_code": "0883", "stock_name": "中国海洋石油"},
            ],
        },
        {
            "cohort_key": "hk_tech",
            "industry_name": "港股科技",
            "stocks": [
                {"stock_code": "0700", "stock_name": "腾讯控股"},
                {"stock_code": "9988", "stock_name": "阿里巴巴"},
                {"stock_code": "3690", "stock_name": "美团"},
                {"stock_code": "1810", "stock_name": "小米集团"},
                {"stock_code": "9888", "stock_name": "百度集团"},
                {"stock_code": "9618", "stock_name": "京东集团"},
                {"stock_code": "9999", "stock_name": "网易"},
                {"stock_code": "1024", "stock_name": "快手"},
                {"stock_code": "2015", "stock_name": "理想汽车"},
                {"stock_code": "9866", "stock_name": "蔚来"},
                {"stock_code": "2382", "stock_name": "舜宇光学"},
                {"stock_code": "0285", "stock_name": "比亚迪电子"},
            ],
        },
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
