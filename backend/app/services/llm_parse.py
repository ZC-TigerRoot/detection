from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.services.detect import detect_project_type

SYSTEM_PROMPT = """你是环境监测方案结构化助手。根据用户提供的客户方案原文，抽取统一 JSON。
只输出 JSON，不要 Markdown 代码块，不要解释。

JSON Schema:
{
  "name": "项目名称",
  "client_name": "委托/建设单位",
  "address": "地址",
  "contact": "联系人",
  "phone": "电话",
  "project_type": "basic 或 annual",
  "year": "年份或周期，如 2026",
  "longitude": "",
  "latitude": "",
  "overview": "项目概况摘要",
  "remark": "备注",
  "items": [
    {
      "category": "检测类别，如有组织废气/无组织废气/废水/噪声/土壤/地下水/污泥/在线比对等",
      "outlet_code": "排放口/点位编号，如 DA001、DW001",
      "outlet_name": "排放口或点位名称",
      "point_location": "测点位置描述",
      "factors": "监测因子，多个用顿号或逗号分隔",
      "sample_freq": "采样频次描述，如 3次/天，监测1天",
      "period_freq": "周期频次，如 1次/月、1次/季、1次/年",
      "monitor_days": "监测天数",
      "samples_per_day": "每天次数或样数",
      "annual_times": "年检测次数（年度方案）",
      "months_plan": "计划执行月份，可写文本",
      "standard_text": "执行标准",
      "remark": "备注"
    }
  ]
}

规则:
1. project_type: 含年度/月度/季度/排污许可自行监测计划等用 annual；单次环评/验收/临时委托用 basic。
2. 同一点位不同因子/频次拆成多行 items。
3. 合并单元格导致空的类别/编号，沿用上一行非空值。
4. 无法确定的字段用空字符串，不要编造。
5. factors 保持原文因子名称，不要擅自改成别的标准名。
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    text = _strip_code_fence(text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("模型未返回有效 JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("JSON 根节点必须是对象")
    return data


async def parse_with_llm(settings: Settings, document_text: str) -> dict[str, Any]:
    if not settings.llm_api_key:
        return _heuristic_parse(document_text)

    base = settings.llm_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"请从以下环境监测/检测方案中抽取结构化数据：\n\n{document_text}",
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        body = resp.json()

    content = body["choices"][0]["message"]["content"]
    data = _extract_json_object(content)
    data["_raw_llm"] = content
    return data


async def stream_parse_with_llm(
    settings: Settings, document_text: str
) -> AsyncIterator[dict[str, Any]]:
    """
    流式 SSE 解析。依次 yield 事件字典：
      {"type": "stage", "stage": str, "message": str}
      {"type": "delta", "content": str}           # LLM 文本 token
      {"type": "thought", "content": str}         # reasoning_content (若模型支持)
      {"type": "done", "item_count": int, "data": dict}
      {"type": "error", "message": str}
    """
    yield {"type": "stage", "stage": "prepare", "message": "正在准备文档内容…"}

    if not settings.llm_api_key:
        yield {"type": "stage", "stage": "heuristic", "message": "未配置 LLM，使用本地启发式解析…"}
        result = _heuristic_parse(document_text)
        norm = normalize_parsed(result)
        yield {
            "type": "done",
            "item_count": len(norm["items"]),
            "data": norm,
        }
        return

    yield {"type": "stage", "stage": "llm_call", "message": "正在调用 AI 模型进行解析…"}

    base = settings.llm_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "temperature": 0.1,
        "stream": True,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"请从以下环境监测/检测方案中抽取结构化数据：\n\n{document_text}",
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    full_content = ""
    full_reasoning = ""

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}

                    # reasoning_content (DeepSeek-R1 等支持)
                    rc = delta.get("reasoning_content") or ""
                    if rc:
                        full_reasoning += rc
                        yield {"type": "thought", "content": rc}

                    # 普通文本
                    c = delta.get("content") or ""
                    if c:
                        full_content += c
                        yield {"type": "delta", "content": c}
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"LLM 调用失败: {exc}"}
        return

    yield {"type": "stage", "stage": "parse_json", "message": "正在解析 JSON 结构…"}

    try:
        raw_data = _extract_json_object(full_content)
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": f"JSON 解析失败: {exc}"}
        return

    raw_data["_raw_llm"] = full_content
    norm = normalize_parsed(raw_data)

    yield {"type": "stage", "stage": "save", "message": f"解析完成，共 {len(norm['items'])} 条监测条目"}
    yield {"type": "done", "item_count": len(norm["items"]), "data": norm}


def _heuristic_parse(document_text: str) -> dict[str, Any]:
    """无 API Key 时的简单回退：尽量从 markdown 表抽行，便于联调。"""
    lines = [ln.strip() for ln in document_text.splitlines() if ln.strip()]
    name = ""
    for ln in lines[:40]:
        if ln.startswith("=====") or ln.startswith("|") or ln.startswith("#"):
            continue
        if any(k in ln for k in ("公司", "医院", "项目名称", "有限公司")):
            name = re.sub(r"^(项目名称|委托单位)[：:\s]*", "", ln)
            name = re.sub(r"^#+\s*", "", name)[:200].strip()
            if name:
                break
    if not name:
        for ln in lines[:40]:
            if "方案" in ln and not ln.startswith("|") and not ln.startswith("====="):
                name = re.sub(r"^#+\s*", "", ln)[:200].strip()
                break

    items: list[dict[str, str]] = []

    def _row_to_item(cells: list[str]) -> dict[str, str] | None:
        if len(cells) < 3:
            return None
        headerish = "".join(cells)
        if any(
            k in headerish
            for k in (
                "检测类别",
                "监测类别",
                "排放口编号",
                "监测因子",
                "检测指标",
                "监测项目",
                "监测频次",
                "测试项目",
                "采样点名称",
                "月份",
            )
        ):
            return None
        nonempty = [c for c in cells if c]
        if len(nonempty) == 1 and ("方案" in nonempty[0] or "一览" in nonempty[0]):
            return None
        # xlsx 月度表: 月份,检测类型,排口编号,采样点名称,测试项目,采样点数量,备注
        month_like = bool(re.search(r"\d{1,2}\s*月", cells[0] or "")) or (cells[0] == "")
        looks_monthly = len(cells) >= 6 and month_like and (
            any(k in (cells[1] or "") for k in ("废水", "废气", "噪声", "污泥", "在线", "无组织", "环境"))
            or bool(re.search(r"(DA|DW|YS)\d+", cells[2] or "", re.I))
            or bool(cells[4])
        )
        if looks_monthly:
            item = {
                "category": cells[1] or "",
                "outlet_code": cells[2] or "",
                "outlet_name": cells[3] or "",
                "factors": cells[4] or "",
                "sample_freq": cells[5] or "",
                "period_freq": "",
                "annual_times": "",
                "remark": cells[6] if len(cells) > 6 else "",
                "point_location": "",
                "monitor_days": "",
                "samples_per_day": "",
                "months_plan": cells[0] or "",
                "standard_text": "",
            }
            if item["factors"] or item["outlet_code"] or item["outlet_name"]:
                return item

        item = {
            "category": cells[0] if len(cells) > 0 else "",
            "outlet_code": cells[1] if len(cells) > 1 else "",
            "outlet_name": cells[2] if len(cells) > 2 else "",
            "factors": cells[3] if len(cells) > 3 else "",
            "sample_freq": cells[4] if len(cells) > 4 else "",
            "period_freq": cells[4] if len(cells) > 4 else "",
            "annual_times": cells[5] if len(cells) > 5 else "",
            "remark": cells[6] if len(cells) > 6 else "",
            "point_location": "",
            "monitor_days": "",
            "samples_per_day": "",
            "months_plan": "",
            "standard_text": "",
        }
        if item["factors"] or item["sample_freq"] or item["outlet_code"]:
            return item
        return None

    for ln in lines:
        if re.match(r"^\|\s*---", ln):
            continue
        cells: list[str]
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
        elif " | " in ln:
            cells = [c.strip() for c in ln.split("|")]
        else:
            continue
        item = _row_to_item(cells)
        if item:
            items.append(item)

    # forward-fill category/code
    last_cat, last_code, last_name = "", "", ""
    for it in items:
        if it["category"]:
            last_cat = it["category"]
        else:
            it["category"] = last_cat
        if it["outlet_code"]:
            last_code = it["outlet_code"]
        else:
            it["outlet_code"] = last_code
        if it["outlet_name"]:
            last_name = it["outlet_name"]
        else:
            it["outlet_name"] = last_name

    project_type = detect_project_type(document_text[:4000])["project_type"]

    return {
        "name": name or "未命名项目",
        "client_name": "",
        "address": "",
        "contact": "",
        "phone": "",
        "project_type": project_type,
        "year": "",
        "longitude": "",
        "latitude": "",
        "overview": "",
        "remark": "（本地启发式解析，未配置 LLM_API_KEY）",
        "items": items[:200],
        "_raw_llm": "",
    }


def normalize_parsed(data: dict[str, Any]) -> dict[str, Any]:
    items_in = data.get("items") or []
    items: list[dict[str, Any]] = []
    for i, raw in enumerate(items_in):
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "category": str(raw.get("category") or "").strip(),
                "outlet_code": str(raw.get("outlet_code") or "").strip(),
                "outlet_name": str(raw.get("outlet_name") or "").strip(),
                "point_location": str(raw.get("point_location") or "").strip(),
                "factors": str(raw.get("factors") or "").strip(),
                "sample_freq": str(raw.get("sample_freq") or "").strip(),
                "period_freq": str(raw.get("period_freq") or "").strip(),
                "monitor_days": str(raw.get("monitor_days") or "").strip(),
                "samples_per_day": str(raw.get("samples_per_day") or "").strip(),
                "annual_times": str(raw.get("annual_times") or "").strip(),
                "months_plan": str(raw.get("months_plan") or "").strip(),
                "standard_text": str(raw.get("standard_text") or "").strip(),
                "remark": str(raw.get("remark") or "").strip(),
                "sort_order": i,
            }
        )

    ptype = str(data.get("project_type") or "annual").lower()
    if ptype not in {"basic", "annual"}:
        ptype = "annual"

    return {
        "name": str(data.get("name") or "").strip(),
        "client_name": str(data.get("client_name") or "").strip(),
        "address": str(data.get("address") or "").strip(),
        "contact": str(data.get("contact") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "project_type": ptype,
        "year": str(data.get("year") or "").strip() or None,
        "longitude": str(data.get("longitude") or "").strip(),
        "latitude": str(data.get("latitude") or "").strip(),
        "overview": str(data.get("overview") or "").strip(),
        "remark": str(data.get("remark") or "").strip(),
        "items": items,
        "raw": str(data.get("_raw_llm") or ""),
    }
