from __future__ import annotations

import re
from typing import Any

# 年度类（周期监测、自行监测等）
ANNUAL_KEYWORDS: tuple[str, ...] = (
    "年度",
    "排污许可",
    "许可证",
    "自行监测",
    "自行委托监测",
    "监测计划",
    "每月",
    "每季度",
    "每两月",
    "每半年",
    "每周",
    "月度",
    "季度",
    "半年",
    "次/月",
    "次/季",
    "次/年",
    "次/半年",
    "次/周",
    "一个年度",
    "每个年度",
    "合同年",
)

# 单次类（验收、环评、临时委托等）
BASIC_KEYWORDS: tuple[str, ...] = (
    "单次",
    "一次性",
    "竣工验收",
    "环保验收",
    "验收监测",
    "验收检测",
    "环境验收",
    "环评",
    "环境影响评价",
    "现状监测",
    "现状检测",
    "环境质量现状",
    "基础监测",
    "基础检测",
    "临时委托",
    "临时性",
)

FREQ_PATTERN = re.compile(r"(\d+)\s*次/[年季度月]")


def detect_project_type(text: str) -> dict[str, Any]:
    """基于关键词与频次模式直接判断方案应套用 单次(基础) 还是 年度 模板。

    返回 dict:
      project_type: basic / annual
      label: 中文名
      annual_score / basic_score: 得分
      keywords: 命中的关键词列表
      reason: 一句话说明
    """
    annual_hits: list[str] = []
    basic_hits: list[str] = []
    for kw in ANNUAL_KEYWORDS:
        if kw in text:
            annual_hits.append(kw)
    for kw in BASIC_KEYWORDS:
        if kw in text:
            basic_hits.append(kw)

    for m in FREQ_PATTERN.finditer(text):
        annual_hits.append(m.group(0))

    annual_score = len(annual_hits)
    basic_score = len(basic_hits)

    # 未命中任何特征时，按文档惯例默认年度
    if annual_score == 0 and basic_score == 0:
        return {
            "project_type": "annual",
            "label": "年度",
            "annual_score": 0,
            "basic_score": 0,
            "keywords": [],
            "reason": "未发现明显特征关键词，按默认年度处理",
        }

    if basic_score > annual_score:
        return {
            "project_type": "basic",
            "label": "基础/单次",
            "annual_score": annual_score,
            "basic_score": basic_score,
            "keywords": basic_hits,
            "reason": f"命中单次特征：{ '、'.join(basic_hits[:6]) }"
            if basic_hits
            else "单次特征得分更高",
        }

    return {
        "project_type": "annual",
        "label": "年度",
        "annual_score": annual_score,
        "basic_score": basic_score,
        "keywords": annual_hits,
        "reason": f"命中年度特征：{ '、'.join(annual_hits[:6]) }"
        if annual_hits
        else "年度特征得分更高",
    }
