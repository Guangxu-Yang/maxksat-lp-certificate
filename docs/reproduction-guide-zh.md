> **归档说明**：以下是随新代码包提供的历史复现指南，正文保持原样。其中“本机”、硬件、耗时和 ZIP 哈希属于原指南的验证环境与原始压缩包，并非本次 GitHub 更新的实测记录。当前仓库请优先使用根目录 `INSTALLING` 和 `examples.py` 的命令；完整重放输出必须写在证书包目录之外。

# 0.742694813 跨机器复现验证流程与本机复验

## 1. 本机重新验证的结论

本次不是引用旧报告，而是从收到者会拿到的 ZIP 重新解压并运行包内工具。

- ZIP：`Max-kSAT_strict_certificate_rho_0.742694813_20260910.zip`
- ZIP SHA-256：`8f216328d7ee1f7a267aac0e4b1455b81ba0eeaa1265fea1ea45c473c7a80df3`
- Python：CPython 3.12.14，64 位
- CPU：AMD Ryzen 9 8945HX（16 核 32 线程；验证器实际主要使用一个逻辑核）
- 快速验包：退出码 0，35 个文件、37 项检查全部通过；短路径测试耗时 0.33 秒
- 完整数学重放：退出码 0，总耗时 325.44 秒，其中精确约束计算 325.35 秒
- 得到的精确比值：`742694813/1000000000 = 0.742694813`
- 精确最小余量：`1/1000000000000`
- 14 类约束、全部低阶行、全部高阶行、complete separation、identity 绑定和 numerical payload 绑定全部为 `true`
- 新结果与归档 identity 报告完全相同；精确验证报告除运行时间外逐字段相同

本机结果文件：

`Workspace/runtime/local_reverify_rho_0742694813_20260911/full_exact_replay/FULL_EXACT_REPLAY.json`

这仍是严格开发阶段证书，不是 `0.749` 证书。

## 2. 对方为什么会觉得无法验证

### 2.1 Windows 路径过长

ZIP 内部有几层目录。如果再解压到桌面、OneDrive 或很深的项目目录，完整文件名可能超过 Windows 普通路径接口约 260 个字符的限制。此时文件实际存在，Python 仍可能报 `WinError 3` 或“文件不存在”。

所以 Windows 上必须解压到本地磁盘的短路径，例如：

```text
C:\qc742
```

不要解压到多层工程目录、网盘同步目录或共享盘。

### 2.2 完整重放会静默约数分钟

完整重放是单线程的 Python 精确分数计算。昂贵阶段没有连续输出，本机约 5 分 25 秒才打印最终结果。16 核 32 线程机器只占满一个逻辑核时，任务管理器显示的总 CPU 可能只有约 3%，GPU 为 0；这都是正常现象。

判断是否仍在运行，应看 Python 进程的累计 CPU 秒数是否持续增加，不能只看总 CPU、GPU 或终端有没有新文字。

### 2.3 不能运行错误的入口

只能使用 ZIP 顶层目录下这两个入口：

- `tools/verify_bundle.py`：快速确认收到的所有字节、哈希链和关键结论没有变化。
- `tools/replay_exact_certificate.py`：重新做完整 identity 和 Fraction 精确数学验证。

不要直接运行：

- `run_v016_target_design_fine_unary_full.py`：它用于重新求 LP，不是验证固定证书，而且包内没有带齐重新搜索所需的研究环境。
- `verify_v016_fine_unary_artifact.py --artifact ...`：原始 artifact 为保持 SHA 不变，仍保存生成机器的 `E:\...` 历史路径；换机器直接调用会找错位置。
- `verify_fine_unary_certificate_bruteforce`：它会逐行暴力枚举，规模不可行。

不要修改 JSON 中的历史 `E:\...` 字符串；修改后原始 SHA 会失效。包内 `replay_exact_certificate.py` 已经按 SHA 把原 artifact 与包内 numerical payload 重新绑定，不会访问原机器的 E 盘。

## 3. 两层验证分别证明什么

### 第一层：快速验包

通常不到 1 秒。它检查：

- ZIP 解压后的文件集合恰好是清单中的 35 个文件，没有缺失和额外文件；
- 每个文件的大小和 SHA-256；
- 原始 certificate manifest、promotion、源码和上游输入之间的哈希引用；
- rho、桶数、14 类约束覆盖标志、最小余量、identity 状态等 37 项关键条件。

它证明“收到的文件就是已经完成严格验证的那一份”，但不会重新执行两千多万次精确转移。

### 第二层：完整数学重放

它从包内固定 certificate 重新计算全部约束。成功后才是独立的数学复验。它不重新求 LP，也不依赖 GPU、CUDA、PyTorch、NumPy、SciPy 或 HiGHS；只需要 64 位 CPython 3.10 或更高版本，推荐 3.11/3.12。

## 4. Windows PowerShell 完整复现命令

下面的 `$zip` 要换成对方机器上 ZIP 的真实路径。`$dest` 和 `$out` 必须是短路径；每次重跑要换新的输出目录。

```powershell
$zip = 'D:\Downloads\Max-kSAT_strict_certificate_rho_0.742694813_20260910.zip'
$expected = '8F216328D7EE1F7A267AAC0E4B1455B81BA0EEAA1265FEA1EA45C473C7A80DF3'

$actual = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
if ($actual -ne $expected) {
    throw "ZIP 在传输中发生变化。实际 SHA256: $actual"
}

# 必须使用尚不存在的短目录。
$dest = 'C:\qc742'
if (Test-Path -LiteralPath $dest) {
    throw "$dest 已存在，请换一个新的短目录"
}
Expand-Archive -LiteralPath $zip -DestinationPath $dest
$root = "$dest\Max-kSAT_strict_certificate_rho_0.742694813"

# 必须调用真正安装的 64 位 CPython 3.10+。
# 如果 python 指向 Windows Store 占位程序，请改成 python.exe 的绝对路径。
python --version

# 第一层：快速验包。
python -B "$root\tools\verify_bundle.py" `
    --bundle-root $root `
    --json-output 'C:\qc742_quick_report.json'
if ($LASTEXITCODE -ne 0) {
    throw '快速验包失败，不应继续做完整重放'
}

# 第二层：完整 Fraction/identity 重放。
# 输出目录必须在 bundle 外，且不能已有 FULL_EXACT_REPLAY.json。
$out = 'C:\qc742_replay_01'
python -B "$root\tools\replay_exact_certificate.py" `
    --bundle-root $root `
    --output-dir $out `
    --max-seconds 3600
if ($LASTEXITCODE -ne 0) {
    throw '完整重放未成功结束，请查看输出 JSON'
}

$r = Get-Content "$out\FULL_EXACT_REPLAY.json" -Raw | ConvertFrom-Json
$r.status
$r.success
$r.proof_result
$r.archived_report_comparison
```

不要加 `python -O`；用上面的 `-B` 即可。`-B` 只是不写 `.pyc` 缓存，不改变验证条件。

如果系统没有可用的 `python` 命令，把每处 `python` 换成真实解释器，例如：

```powershell
$py = 'C:\Python312\python.exe'
& $py --version
& $py -B "$root\tools\verify_bundle.py" --bundle-root $root
```

## 5. 成功结果必须满足什么

快速验包的终端应出现：

```text
PASS: rho=0.742694813 ... verified.
Files: 35 | Checks: 37
```

快速报告中应有：

- `ok = true`
- `verified_rho = 742694813/1000000000`
- `errors = []`

快速报告中的 `full_fraction_replay_performed = false` 是正常的，因为第一层只检查固定证据链。

完整重放结束后，`FULL_EXACT_REPLAY.json` 必须同时满足：

```text
status = exact_verified
success = true
proof_result.verified_rho = 742694813/1000000000
proof_result.minimum_slack = 1/1000000000000
proof_result.all_14_families_verified = true
proof_result.all_low_order_rows_checked = true
proof_result.all_high_order_rows_checked = true
proof_result.complete_separation = true
proof_result.identity_verified = true
proof_result.numerical_payload_bound = true
archived_report_comparison.identity_report_exact_match = true
archived_report_comparison.verify_report_exact_match_excluding_elapsed_seconds = true
```

## 6. 完整验证为什么能在几分钟内完成

朴素做法要把每个带符号桶的所有三元组、四元组、五元组逐个列出来，最高阶合计约有 `8.6 × 10^15` 个概念行，实际上跑不完。包内验证器做的是严格等价压缩，不是抽样：

1. length 1 和 length 2 直接精确检查；length 2 实际检查 2,001,000 个无序带符号标签对。
2. length 3、4、5 的 pair contribution 只取决于 20 个带符号 group，因此把 1,000 个带符号桶按 group 合并，只需完整遍历 52,899 个无序 group 组合。
3. 对 upper 约束，每个部分选择对应一条精确分数直线；只保留在允许范围内确实可能成为最坏情况的直线。被删掉的直线在任何后续选择下都不可能成为最坏值，所以不会漏约束。实际最多保留 177 个状态，共完成 21,946,945 次转移。
4. 全程使用 Python `Fraction` 精确分数。达到资源或时间上限时只会返回“未完成”，不会把抽样结果冒充通过。

因此，正确入口 `replay_exact_certificate.py` 能在数分钟内完整验证；暴力入口则不可行。

## 7. 如何判断静默期间是否还在计算

在另一个 PowerShell 窗口运行：

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*replay_exact_certificate.py*' } |
    Select-Object ProcessId, CommandLine

Get-Process -Id <上一步看到的PID> |
    Select-Object Id, CPU, @{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB)}}
```

间隔约 30 秒再执行一次。`CPU` 是该进程累计用掉的 CPU 秒数；只要它继续增加，程序就在计算。

输出目录中的 `FULL_EXACT_REPLAY.json` 开始时可能显示：

```text
status = running_exact_fraction_replay
success = false
```

这是运行中的临时状态，不是验证失败。程序结束时才会原子更新成最终结果。

若最终状态为 `incomplete_resource_limit` 或提示 time limit，只说明给定时间内没有算完，不说明证书为假。换一个新的输出目录，把 `--max-seconds` 提高后重跑。若出现哈希不匹配、identity 不匹配或负余量，才是实质失败。

## 8. Linux/macOS 简版命令

```bash
sha256sum Max-kSAT_strict_certificate_rho_0.742694813_20260910.zip
# 必须得到 8f216328d7ee1f7a267aac0e4b1455b81ba0eeaa1265fea1ea45c473c7a80df3

dest=$(mktemp -d /tmp/qc742.XXXXXX)
unzip -q Max-kSAT_strict_certificate_rho_0.742694813_20260910.zip -d "$dest"
root="$dest/Max-kSAT_strict_certificate_rho_0.742694813"

python3 --version
python3 -B "$root/tools/verify_bundle.py" --bundle-root "$root"

out=$(mktemp -d /tmp/qc742-replay.XXXXXX)
python3 -B "$root/tools/replay_exact_certificate.py" \
    --bundle-root "$root" \
    --output-dir "$out" \
    --max-seconds 3600
cat "$out/FULL_EXACT_REPLAY.json"
```

## 9. 仍然失败时应发回什么

请对方不要只发“很慢”的截图，而是发回以下五项：

1. `python --version` 的完整输出；
2. 实际执行的完整命令；
3. 进程退出码；
4. `qc742_quick_report.json`；
5. 完整重放输出目录中的 `FULL_EXACT_REPLAY.json`。

有这五项即可区分：传输损坏、路径过长、Python 不可用、时间不足，还是证书检查本身失败。
