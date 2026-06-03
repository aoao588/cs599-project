# 分支与发布策略

## 一、分支模型

采用简化的 Git Flow：

| 分支            | 用途                           | 保护规则                   |
| --------------- | ------------------------------ | -------------------------- |
| `main`          | 始终对应已上线的生产版本       | 禁止直推；仅接受合并       |
| `release/x.y.z` | 即将发布的版本，进入冻结期     | 仅 bugfix 可合入           |
| `feature/*`     | 功能开发分支，从 main 切出     | 无保护                     |
| `hotfix/*`      | 线上紧急修复，从 main 切出     | 修复后同时合回 main 与最新 release |

## 二、命名规范

- `feature/<jira-id>-<short-desc>`，例：`feature/PROJ-1234-add-export`
- `hotfix/<jira-id>-<short-desc>`，例：`hotfix/PROJ-5678-fix-login-500`
- `release/<semver>`，例：`release/1.4.0`

## 三、版本号

遵循 SemVer 2.0：`MAJOR.MINOR.PATCH`
- MAJOR：不兼容的 API 变更
- MINOR：向后兼容的功能新增
- PATCH：向后兼容的缺陷修复

预发版本可加 `-rc.N` 后缀，例 `1.4.0-rc.1`。

## 四、发布流程

1. 从 `main` 切出 `release/x.y.z` 分支，进入**冻结期**。
2. 冻结期内只允许 bugfix 合入，新功能一律拒绝。
3. 通过 QA 验收后打 tag `vX.Y.Z` 并部署生产。
4. 发布完成后将 `release/x.y.z` 合回 `main`，删除 release 分支。

## 五、Hotfix 流程

1. 从 `main` 当前 tag 切出 `hotfix/*` 分支。
2. 修复并通过完整 CI。
3. 合入 `main` 后立刻打 patch 版本 tag。
4. 同步 cherry-pick 到正在进行的 `release/*` 分支（如有）。

## 六、回滚策略

线上故障优先 **回滚**，再事后修复：
- 通过 CI/CD 上一版本镜像快速回滚；目标 RTO ≤ 10 分钟。
- 回滚后必须创建 incident 工单，48 小时内提交事后报告。

## 七、解释权
本策略由 DevOps 团队维护，最近一次更新：2025-10-15。
