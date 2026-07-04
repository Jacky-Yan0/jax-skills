---
name: academic-research
description: "Academic Research Skills (ARS) — a comprehensive research pipeline: deep research, paper writing, peer review, and full pipeline orchestration. Routes between 4 sub-skills based on user intent."
applyTo: "user-request"
metadata:
  version: "3.13.0"
  status: active
  category: academic
---

# Academic Research Skills (ARS)

综合学术研究助手，涵盖研究到发表的全流程。根据用户意图路由到 4 个子 skill。

## 路由表

| 用户意图关键词 | 激活 skill | 说明 |
|--------------|-----------|------|
| research, literature review, systematic review, meta-analysis, evidence synthesis, fact-check, guide my research, 研究, 文献回顾, 系统性回顾, 事实查核 | `_deep-research.md` | 13-agent 团队，8 种模式 |
| write paper, academic paper, paper outline, revise paper, parse reviews, citation check, 写论文, 学术论文, 论文大纲, 修改论文, 审查意见 | `_academic-paper.md` | 12-agent 写作，11 种模式 |
| review paper, peer review, manuscript review, critique paper, simulate review, 审稿, 同行评审 | `_academic-paper-reviewer.md` | 7-agent 审稿，6 种模式 |
| full paper pipeline, end-to-end paper, research-to-publication, 完整论文流程 | `_academic-pipeline.md` | 10-stage 协调器 |

## 多 skill 模糊时的路由规则

当用户请求可能跨多个 skill 时，先澄清意图。例如"我想写一篇关于 AI 的论文"可能触发 deep-research 或 academic-paper。此时优先询问用户是"已有研究数据需要写"还是"需要先做研究"。
