# CYR.2C 任务工作台 UI 设计

覆盖聊天紧凑计划卡、任务工作台增强（锁定 / 来源引用 / 重新生成计划）与恢复面板。

- [设计规格](2026-08-04-cyr2c-taskworkbench-ui-design.md)：组件、状态、文案与响应式规范。
- [交互原型](prototype/index.html)：基于**当前产品 UI**（`frontend/src`）的可点击原型，演示各状态流转。

设计语言继承当前产品前端 `frontend/src/styles.css` 的设计系统（深紫 `#7c5cff`、幽蓝 `#45c7ff`、银白、玻璃拟态、圆角 16px / 10px、柔光）；组件命名与现有 `TasksPage.tsx`、`ChatView.tsx` 保持一致。原型不修改产品代码。
