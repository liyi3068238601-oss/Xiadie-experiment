# CYR.2D Planner 多模型质量固定集汇总

- 日期：2026-08-04
- 协议：`cyr2d-planner-quality-v1`
- 合成场景：10 组（不含用户数据）
- 运行环境：真实 DeepSeek API（本机已配置 deepseek provider）；qwen-plus / glm-4-flash 未启用，记为 unavailable

## 结果

| 模型 | 结构合法率 | 结构非法 | 杜撰来源 | 批准当权限 | 锁定被改写 | 资格 |
|---|---:|---:|---:|---:|---:|---|
| deepseek-v4-pro | 0.30 | 7 | 0 | 0 | 0 | 未验证 |
| deepseek-v4-flash | 0.40 | 6 | 0 | 0 | 0 | 未验证 |
| deepseek-chat | 0.90 | 1 | 0 | 0 | 0 | 未验证 |

## 失败模式

- `planner_response_invalid`：模型输出 JSON 无法解析（提示词/输出合同未完全约束到 JSON 单对象）。
- `observer_model_response_empty`：模型返回空内容。
- 未出现杜撰来源、批准被解释为权限、锁定节点被改写（三项零容忍通过）。
- 两次运行结果存在波动（v4-pro 4→7、v4-flash 8→6），反映生成随机性；chat 稳定为 1 个失败。

## 结论

三个 deepseek 模型目前均**未达到零容忍资格**（主要卡在结构合法性），按 spec 如实记为"未验证"；未验证模型不阻塞使用，模型指纹随生成事件记录。后续改进方向：收紧输出合同（强制 JSON 单对象、禁用 markdown 围栏）、对不可解析输出做一次结构化修复重试，或调整场景难度后重测。

## 明细

- `docs/reports/cyr2d-planner-quality-deepseek-deepseek-v4-pro.json`
- `docs/reports/cyr2d-planner-quality-deepseek-deepseek-v4-flash.json`
- `docs/reports/cyr2d-planner-quality-deepseek-deepseek-chat.json`
