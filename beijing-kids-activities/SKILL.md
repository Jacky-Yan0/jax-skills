---
name: beijing-kids-activities
description: >
  Query parent-child activities at Beijing kindergartens (北京幼儿园亲子活动).
  Calls the 3ren.cn baby-map-center POI API to search for kindergarten activities
  by keyword and start time. Returns structured results with location, categories,
  registration details, and pagination.
version: 1.0.0
author: Generated from user request
---

# Beijing Kids Activities (北京幼儿园亲子活动)

## Description

This skill queries the **3ren.cn baby-map-center** POI service to find
parent-child activities at Beijing kindergartens. It wraps the underlying HTTP
POST request with clean Python CLI arguments.

## Quick start

```bash
python scripts/query_activities.py --keywords "中华女子" --start-time 1783180800000
```

## Core workflow

Read [manifest.yaml](manifest.yaml) and the files listed under `always_load`:

- `static/core/workflow.md` — parameter reference, output structure, error handling.

## Script

The runnable entry point is `scripts/query_activities.py`. It accepts
`--keywords`, `--start-time`, `--page-index`, `--page-size`, and `--debug`.

## Output schema (输出字段定义)

查询结果返回给用户时，每个活动必须包含以下字段，按此顺序输出：

### 活动概览（每个 row 一条）

| 输出位置 | JSON 路径 | 说明 | 示例 |
|---------|----------|------|------|
| **活动名称** ⭐ | `rows[].mapName` | 活动标题，**必须放在最前面** | 开心入园 |
| **机构名称** | `rows[].orgName` | 幼儿园名称 | 中华女子学院附属实验幼儿园 |
| **地址** | `rows[].address` | 详细地址 | 北京市朝阳区小营路育慧西里25号 |
| **距离** | `rows[].distance` | 距查询位置米数，自动取整 | 约 998m |
| **活动类型** | `rows[].categoryList[hdlx]` | 从 categoryList 中取 keyType=hdlx | 亲子互动 |
| **年龄段** | `rows[].categoryList[age]` | 从 categoryList 中取 keyType=age | 2-3岁 |
| **活动状态** | `poiActivityDTO.activityStatusName` | 未开始 / 进行中 / 已结束 | 未开始 |
| **报名状态** | `rows[].categoryList[bmzt]` | 从 categoryList 中取 keyType=bmzt | 进行中 / 已结束 |
| **活动时间** | `poiActivityDTO.startTime` / `endTime` | 毫秒时间戳，展示时转为可读日期 | 2026-07-07 |
| **报名时间** | `poiActivityDTO.registrationStartTime` / `registrationEndTime` | 毫秒时间戳，展示时转为可读日期 | 2026-07-07 前 |
| **已报名** | `poiActivityDTO.registrationUserCount` | 已报名人数 | 10 人 |
| **候补** | `poiActivityDTO.isWaitName` | 是否支持候补 | 候补 / 无名额 |
| **合作关系** | `rows[].categoryList[dataCooperation]` | 数据来源 | 京小宝 |

### 分页信息

| 字段 | JSON 路径 | 说明 |
|------|----------|------|
| 总条数 | `data.total` | 匹配活动总数 |
| 当前页 | `data.pageIndex` | 当前页码 |
| 每页 | `data.pageSize` | 每页条数 |
| 总页数 | `data.totalPage` | 总页码 |

### 时间戳转换规则

API 中所有时间字段均为**毫秒级时间戳**（13 位数字），展示给用户时必须转换为 `YYYY-MM-DD HH:mm` 可读格式。

### 输出格式示例

```
🎉 活动：开心入园
📚 机构：中华女子学院附属实验幼儿园
📍 地址：北京市朝阳区小营路育慧西里25号（约 998m）
🏷️ 类型：亲子互动 | 适合：2-3岁
⏳ 状态：未开始 | 报名：进行中
📅 活动时间：2026-07-07
⏰ 报名截止：2026-07-07 前
👥 已报名：10 人 | 候补：有名额
```

## Trigger phrases

Use this skill when the user says any of:
- "查一下北京幼儿园亲子活动"
- "搜索北京亲子活动"
- "查询幼儿园活动"
- "北京 kindergarten activities"
- "查亲子活动 关键词 XXX 时间 XXX"
- "帮我查一下亲子活动"
