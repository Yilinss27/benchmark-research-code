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
        {"stock_code": "JNJ", "stock_name": "Johnson & Johnson"},
    ],
    "HK": [
        {"stock_code": "0700", "stock_name": "腾讯控股"},
        {"stock_code": "0005", "stock_name": "汇丰控股"},
        {"stock_code": "9988", "stock_name": "阿里巴巴"},
        {"stock_code": "0941", "stock_name": "中国移动"},
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
        {
            "cohort_key": "energy",
            "industry_name": "能源资源",
            "stocks": [
                {"stock_code": "601857", "stock_name": "中国石油"},
                {"stock_code": "600028", "stock_name": "中国石化"},
                {"stock_code": "601088", "stock_name": "中国神华"},
                {"stock_code": "600938", "stock_name": "中国海油"},
                {"stock_code": "601898", "stock_name": "中煤能源"},
                {"stock_code": "601225", "stock_name": "陕西煤业"},
                {"stock_code": "600188", "stock_name": "兖矿能源"},
                {"stock_code": "600256", "stock_name": "广汇能源"},
                {"stock_code": "601808", "stock_name": "中海油服"},
                {"stock_code": "600583", "stock_name": "海油工程"},
            ],
        },
        {
            "cohort_key": "industrial",
            "industry_name": "高端制造与基建",
            "stocks": [
                {"stock_code": "601668", "stock_name": "中国建筑"},
                {"stock_code": "601390", "stock_name": "中国中铁"},
                {"stock_code": "601186", "stock_name": "中国铁建"},
                {"stock_code": "601800", "stock_name": "中国交建"},
                {"stock_code": "600031", "stock_name": "三一重工"},
                {"stock_code": "000157", "stock_name": "中联重科"},
                {"stock_code": "601766", "stock_name": "中国中车"},
                {"stock_code": "600089", "stock_name": "特变电工"},
                {"stock_code": "600406", "stock_name": "国电南瑞"},
                {"stock_code": "002202", "stock_name": "金风科技"},
            ],
        },
        {
            "cohort_key": "communications",
            "industry_name": "通信设备与运营",
            "stocks": [
                {"stock_code": "600050", "stock_name": "中国联通"},
                {"stock_code": "601728", "stock_name": "中国电信"},
                {"stock_code": "600941", "stock_name": "中国移动"},
                {"stock_code": "000063", "stock_name": "中兴通讯"},
                {"stock_code": "002281", "stock_name": "光迅科技"},
                {"stock_code": "600522", "stock_name": "中天科技"},
                {"stock_code": "600498", "stock_name": "烽火通信"},
                {"stock_code": "300308", "stock_name": "中际旭创"},
                {"stock_code": "002396", "stock_name": "星网锐捷"},
                {"stock_code": "603236", "stock_name": "移远通信"},
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
        {
            "cohort_key": "us_financial",
            "industry_name": "US financial leaders",
            "stocks": [
                {"stock_code": "JPM", "stock_name": "JPMorgan"},
                {"stock_code": "BAC", "stock_name": "Bank of America"},
                {"stock_code": "WFC", "stock_name": "Wells Fargo"},
                {"stock_code": "C", "stock_name": "Citigroup"},
                {"stock_code": "GS", "stock_name": "Goldman Sachs"},
                {"stock_code": "MS", "stock_name": "Morgan Stanley"},
                {"stock_code": "BLK", "stock_name": "BlackRock"},
                {"stock_code": "SCHW", "stock_name": "Charles Schwab"},
                {"stock_code": "AXP", "stock_name": "American Express"},
                {"stock_code": "USB", "stock_name": "U.S. Bancorp"},
                {"stock_code": "PNC", "stock_name": "PNC Financial"},
                {"stock_code": "BK", "stock_name": "Bank of New York Mellon"},
            ],
        },
        {
            "cohort_key": "us_healthcare",
            "industry_name": "US healthcare leaders",
            "stocks": [
                {"stock_code": "JNJ", "stock_name": "Johnson & Johnson"},
                {"stock_code": "LLY", "stock_name": "Eli Lilly"},
                {"stock_code": "UNH", "stock_name": "UnitedHealth"},
                {"stock_code": "PFE", "stock_name": "Pfizer"},
                {"stock_code": "MRK", "stock_name": "Merck"},
                {"stock_code": "ABBV", "stock_name": "AbbVie"},
                {"stock_code": "TMO", "stock_name": "Thermo Fisher"},
                {"stock_code": "ABT", "stock_name": "Abbott"},
                {"stock_code": "DHR", "stock_name": "Danaher"},
                {"stock_code": "BMY", "stock_name": "Bristol Myers Squibb"},
                {"stock_code": "AMGN", "stock_name": "Amgen"},
                {"stock_code": "GILD", "stock_name": "Gilead Sciences"},
            ],
        },
        {
            "cohort_key": "us_consumer",
            "industry_name": "US consumer leaders",
            "stocks": [
                {"stock_code": "WMT", "stock_name": "Walmart"},
                {"stock_code": "PG", "stock_name": "Procter & Gamble"},
                {"stock_code": "COST", "stock_name": "Costco"},
                {"stock_code": "KO", "stock_name": "Coca-Cola"},
                {"stock_code": "PEP", "stock_name": "PepsiCo"},
                {"stock_code": "MCD", "stock_name": "McDonald's"},
                {"stock_code": "NKE", "stock_name": "Nike"},
                {"stock_code": "SBUX", "stock_name": "Starbucks"},
                {"stock_code": "HD", "stock_name": "Home Depot"},
                {"stock_code": "LOW", "stock_name": "Lowe's"},
            ],
        },
        {
            "cohort_key": "us_industrial",
            "industry_name": "US industrial leaders",
            "stocks": [
                {"stock_code": "CAT", "stock_name": "Caterpillar"},
                {"stock_code": "GE", "stock_name": "GE Aerospace"},
                {"stock_code": "HON", "stock_name": "Honeywell"},
                {"stock_code": "UPS", "stock_name": "UPS"},
                {"stock_code": "UNP", "stock_name": "Union Pacific"},
                {"stock_code": "RTX", "stock_name": "RTX"},
                {"stock_code": "BA", "stock_name": "Boeing"},
                {"stock_code": "DE", "stock_name": "Deere"},
                {"stock_code": "ETN", "stock_name": "Eaton"},
                {"stock_code": "MMM", "stock_name": "3M"},
            ],
        },
        {
            "cohort_key": "us_energy",
            "industry_name": "US energy leaders",
            "stocks": [
                {"stock_code": "XOM", "stock_name": "Exxon Mobil"},
                {"stock_code": "CVX", "stock_name": "Chevron"},
                {"stock_code": "COP", "stock_name": "ConocoPhillips"},
                {"stock_code": "SLB", "stock_name": "SLB"},
                {"stock_code": "EOG", "stock_name": "EOG Resources"},
                {"stock_code": "MPC", "stock_name": "Marathon Petroleum"},
                {"stock_code": "PSX", "stock_name": "Phillips 66"},
                {"stock_code": "OXY", "stock_name": "Occidental Petroleum"},
                {"stock_code": "KMI", "stock_name": "Kinder Morgan"},
                {"stock_code": "WMB", "stock_name": "Williams"},
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
        {
            "cohort_key": "hk_financial",
            "industry_name": "港股金融",
            "stocks": [
                {"stock_code": "0005", "stock_name": "汇丰控股"},
                {"stock_code": "1299", "stock_name": "友邦保险"},
                {"stock_code": "0388", "stock_name": "香港交易所"},
                {"stock_code": "0939", "stock_name": "建设银行"},
                {"stock_code": "1398", "stock_name": "工商银行"},
                {"stock_code": "2318", "stock_name": "中国平安"},
                {"stock_code": "3988", "stock_name": "中国银行"},
                {"stock_code": "2628", "stock_name": "中国人寿"},
                {"stock_code": "3968", "stock_name": "招商银行"},
                {"stock_code": "3328", "stock_name": "交通银行"},
                {"stock_code": "1288", "stock_name": "农业银行"},
                {"stock_code": "1658", "stock_name": "邮储银行"},
            ],
        },
        {
            "cohort_key": "hk_consumer",
            "industry_name": "港股消费",
            "stocks": [
                {"stock_code": "2020", "stock_name": "安踏体育"},
                {"stock_code": "2331", "stock_name": "李宁"},
                {"stock_code": "2319", "stock_name": "蒙牛乳业"},
                {"stock_code": "0291", "stock_name": "华润啤酒"},
                {"stock_code": "9633", "stock_name": "农夫山泉"},
                {"stock_code": "1928", "stock_name": "金沙中国"},
                {"stock_code": "1929", "stock_name": "周大福"},
                {"stock_code": "6862", "stock_name": "海底捞"},
                {"stock_code": "6690", "stock_name": "海尔智家"},
                {"stock_code": "0880", "stock_name": "澳博控股"},
                {"stock_code": "0175", "stock_name": "吉利汽车"},
                {"stock_code": "1211", "stock_name": "比亚迪股份"},
            ],
        },
        {
            "cohort_key": "hk_state_owned",
            "industry_name": "港股央企龙头",
            "stocks": [
                {"stock_code": "0941", "stock_name": "中国移动"},
                {"stock_code": "0883", "stock_name": "中国海洋石油"},
                {"stock_code": "0857", "stock_name": "中国石油股份"},
                {"stock_code": "0386", "stock_name": "中国石油化工股份"},
                {"stock_code": "1088", "stock_name": "中国神华"},
                {"stock_code": "2628", "stock_name": "中国人寿"},
                {"stock_code": "3988", "stock_name": "中国银行"},
                {"stock_code": "1288", "stock_name": "农业银行"},
                {"stock_code": "3328", "stock_name": "交通银行"},
                {"stock_code": "0762", "stock_name": "中国联通"},
            ],
        },
        {
            "cohort_key": "hk_healthcare",
            "industry_name": "港股医药健康",
            "stocks": [
                {"stock_code": "1093", "stock_name": "石药集团"},
                {"stock_code": "1177", "stock_name": "中国生物制药"},
                {"stock_code": "2269", "stock_name": "药明生物"},
                {"stock_code": "6160", "stock_name": "百济神州"},
                {"stock_code": "3692", "stock_name": "翰森制药"},
                {"stock_code": "1877", "stock_name": "君实生物"},
                {"stock_code": "0867", "stock_name": "康哲药业"},
                {"stock_code": "2359", "stock_name": "药明康德"},
                {"stock_code": "2186", "stock_name": "绿叶制药"},
                {"stock_code": "9995", "stock_name": "荣昌生物"},
            ],
        },
        {
            "cohort_key": "hk_utilities",
            "industry_name": "港股公用事业与通信",
            "stocks": [
                {"stock_code": "0941", "stock_name": "中国移动"},
                {"stock_code": "0762", "stock_name": "中国联通"},
                {"stock_code": "0728", "stock_name": "中国电信"},
                {"stock_code": "0002", "stock_name": "中电控股"},
                {"stock_code": "0003", "stock_name": "香港中华煤气"},
                {"stock_code": "0006", "stock_name": "电能实业"},
                {"stock_code": "1038", "stock_name": "长江基建集团"},
                {"stock_code": "0836", "stock_name": "华润电力"},
                {"stock_code": "0902", "stock_name": "华能国际电力"},
                {"stock_code": "0916", "stock_name": "龙源电力"},
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
