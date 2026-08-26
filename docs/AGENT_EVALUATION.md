# Agent 量化评测与展示指标

本项目将 Agent 质量拆成离线确定性门禁和线上运行指标。离线门禁不调用付费模型，可以在 CI 中稳定复现；线上指标用于观察真实请求的延迟、成本、工作流完成情况和过载状态。

## 离线评测

运行：

```powershell
cd backend
.venv\Scripts\python.exe -m scripts.evaluate_agent_quality
```

2026-08-24 基线结果：

| 指标 | 样本数 | 基线 | 门禁 |
| --- | ---: | ---: | ---: |
| 工具选择准确率 | 73 | 100% | ≥98% |
| 工具参数准确率 | 73 | 100% | ≥98% |
| 安全上下文错误写入率 | 73 | 0% | =0% |
| 多工具工作流识别准确率 | 24 | 100% | ≥95% |
| 工作流误触发率 | 24 | 0% | ≤5% |
| 按需上下文选择完全匹配率 | 20 | 100% | ≥95% |

数据集覆盖普通查询、明确写入、否定表达、未来计划、第三方陈述、假设场景、提示词注入、高风险确认、复合查询、复合写入、数据驱动调整，以及运动、饮食、睡眠、形象、体重上下文选择。

这些结果只证明确定性路由和上下文选择在当前测试集上的表现，不等于真实用户语言上的泛化准确率。发布前还应运行带 Qwen Planner 的抽样评测：

```powershell
.venv\Scripts\python.exe -m scripts.evaluate_agent --live --limit 20 --output evals/results/live.json
```

## 线上指标

每次 Agent Run 会保存：

- Planner 调用次数、工具调用次数和总步骤数。
- Agent 规划耗时、回复耗时、模型和 Token 使用量。
- 是否启用多工具工作流、写工具数量和是否发生部分失败。
- 工具参数、Observation、确认状态和最终结果。

内部指标接口还累计：

- `agent:workflow:started`
- `agent:workflow:multi_tool_completed`
- `agent:workflow:partial_failure`
- HTTP P50/P95/P99、状态码和限流拒绝数。
- LLM、Embedding、Face++ 调用、耗时、Token 和容量闸门状态。
- Redis Stream Worker 心跳、积压、延迟、成功和失败数。

## 是否需要多 Agent

当前结论是暂不引入 Subagent。现阶段的主要请求能由“按需上下文 + 最多三工具的受控 Planner–Executor + 风险确认点”完成。多 Agent 会增加调用成本、延迟、状态同步和写入冲突，却还没有独立角色并行带来的确定收益。

只有在以下指标出现后再重新评估：

1. 单 Agent 周计划任务的上下文或工具步骤经常超过上限。
2. 运动、饮食、睡眠和形象方案确实需要并行独立产出。
3. 生成结果的目标一致度或安全检查无法通过单次生成加校验达到要求。
4. 离线或线上评测证明“规划 Agent + 审核 Agent”相对单 Agent 有显著质量收益，且成本和延迟可接受。

因此当前“不使用多 Agent”是基于业务边界和评测门禁的架构选择，而不是功能缺失。
