# Atlas 体验建议 / Experience Feedback

Atlas 是研究/工程型项目，真实使用中的困惑和摩擦比“功能列表”更有价值。请优先用下面的结构化入口反馈，方便定位和跟进。

## 快速入口

- **体验建议 Issue（推荐，可附截图/环境）**  
  https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/issues/new?template=experience_feedback.yml
- **体验建议收集帖（Ideas）**  
  https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/discussions/26
- **开放讨论（Ideas / Q&A）**  
  https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/discussions
- **可复现 Bug**  
  https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/issues/new?template=bug_report.yml
- **新功能请求**  
  https://github.com/Bruce848647703/Atlas-MultiAsset-Advisor/issues/new?template=feature_request.yml

## 一次好的体验反馈包含什么

1. **场景**：适当性等级 / 本金量级 / 数据源（synthetic / merged / kairos）/ 目标；
2. **卡点**：在哪个页面、哪个标签、哪一步犹豫、重试或失去信任；
3. **期望**：你希望它当时怎么表现（一个默认值、一个提示、一个校验、一个视图）；
4. **影响**：Blocker / High / Medium / Low / Idea；
5. **证据**：脱敏截图、报错文本、commit、浏览器/系统。

不需要写完整报告，一段话 + 截图也可以。

## 我们重点关注

- 首次启动、依赖安装、数据源切换；
- 问卷与适当性、策略过滤、输入校验提示；
- 最终建议/报告是否可解释、是否敢用；
- 中英繁切换、长文本、空数据/网络失败时的降级；
- Kairos 策略实验室、卫星叠加、Factor Forge 的可用性；
- CLI / LLM 工具的错误信息是否可行动。

## 隐私与边界

- **不要**粘贴真实持仓、账号、身份证、API key、券商截图中的个人信息。
- 本金用区间即可（如“约 50 万”），标的可脱敏。
- 本项目输出为研究参考，不构成投资建议；反馈区也不提供个人投资建议。

## 处理方式

- Issue Form 会自动打上 `feedback` + `needs-triage`。
- 维护者会尽量在一周内标记：`bug` / `enhancement` / `ux` / `documentation` / `discussion`，或转成 Discussion。
- 高影响问题会优先进入输入校验、默认值和错误提示的修复，而不是只改文案。
- 讨论区适合“还没想清楚是不是 bug”的体验吐槽；Issue 适合可执行的具体改动。