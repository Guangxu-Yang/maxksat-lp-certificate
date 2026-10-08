# Max-kSAT 严格证书包：rho = 0.742694813

## 先看结论

这份包保存的是当前严格开发基线：`rho = 742694813/1000000000 = 0.742694813`。它是 `v016_j2_group_search` 的 **strict development incumbent（严格开发阶段最优记录）**，不是 `0.749`，也不表示完成了以 `0.749` 为目标的正式实验。

这套结果先用完整 CPU LP 求候选，再通过独立 identity 检查和 `Fraction` 有理数精确重放。全部 14 类约束通过，精确全局最小余量为 `1/1000000000000`。检查覆盖 2,001,000 个低阶标签对、52,899 个高阶 group multiset、21,946,945 次上包络转移。

## 这里的 500 桶是什么意思

设计在正 bias 一侧使用 500 个桶；把每个桶的正、负 signed label 都算进去，就是 1,000 个 signed labels。高阶 H3/H4/H5 统计再把这些标签归入 20 个 signed groups。证书使用 fine-label unary 加 coarse-group-pair 的 surrogate，设计 canonical hash 是 `50840a0d010b4f8ecb7e703bdedf8a058dc0b90d1751b1d13a51af855ebcd5c4`。

## 文件内容

- `original/certificate/`：`target_domain_p500_fine_unary_001` 的完整原始目录，字节不作修改。它包含数值 LP 原始结果、规范化 numerical payload、精确候选、identity 报告、完整 Fraction 验证报告、摘要和内部 SHA-256 清单。
- `original/promotion/`：把本结果登记为严格开发基线的原始晋升记录和 SHA-256 清单。
- `provenance/lineage/`：identity/晋升记录直接引用的 anchor、P500 候选、warm payload 和层级提升摘要。
- `provenance/logs/`：编号 051 的实验记录。
- `provenance/project_state/`：打包时项目的保存索引与稳定版本指针。
- `verifier/source/`：原始验证 CLI、数值 runner，以及重放所需的 v016 源码。
- `validation/`：若最终包已做全量重放，这里保存重放结果。
- `tools/`：最终包加入的快速验包和全量重放工具。

`original/certificate/numerical_payload.json` **单独并不是严格证书**；它是被 SHA-256 绑定的数值输入。严格结论来自 exact candidate、独立 identity 检查和完整 Fraction 重放共同闭环，所以看到 numerical payload 本身仍含浮点数是正常的。

## 快速检查整包

解压后在本目录运行：

```powershell
python .\tools\verify_bundle.py --bundle-root .
```

快速检查逐个核对最终 `BUNDLE_MANIFEST.json`、原始证据哈希和关键结论，但不重新枚举两千多万次精确转移。

## 重新跑完整 Fraction 证书

项目共享 CUDA Python 可这样运行（重放主要是 CPU 的有理数计算，GPU 不是证书来源）：

```powershell
E:\QAlgoCUDA\Scripts\python.exe .\tools\replay_exact_certificate.py --bundle-root . --output-dir ..\manual_full_replay_0742694813
```

也可使用装有相容 Python 依赖的其他解释器。历史完整重放约需数分钟，实际时间随 CPU 而变；以工具退出码和输出 JSON 为准。最终包采用封闭文件清单，手动重放应把结果写到包目录之外；不要把新文件写进已经验收的包内。

## 关于原文件里的 E 盘绝对路径

若干原始 JSON 保存了当时的 `E:\...` 绝对路径。为了保持原证据 SHA-256，这些字符串不能直接改写；它们只是历史来源信息。包内重放工具会在临时副本里把 numerical payload 指向包内文件，不修改 `original/`，因此把 ZIP 移到没有 E 盘的机器仍可校验和重放。

## 历史 policy snapshot 的边界

晋升清单记录了晋升时可变控制文件 `EXPERIMENT_POLICY.json` 的 SHA-256，但那一时点的原始字节没有作为不可变证据单独保留，所以本包不会拿当前版本冒充旧 snapshot。这个 policy 文件只控制“何时开始/停止实验”，不参与 LP 不等式、identity 绑定或 Fraction 数学验证；其历史字节缺失不影响本包的数学证书闭环。当前保存索引和稳定版本指针仅作为项目状态说明。
