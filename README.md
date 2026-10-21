# Fusion Lab · 本地图像融合评估工作台

直接调用现有 MEFB MATLAB 指标的本地扩展工具。原 MEFB 文件不修改。

## 启动

双击 `start.bat`，浏览器访问 http://127.0.0.1:8765 。关闭服务窗口即停止工具。

需要 Python 3.10+、Pillow 和支持 `-batch` 的 MATLAB，以及相应指标使用的 MATLAB 工具箱。本机已发现 Python 3.13、Pillow 12.3、MATLAB R2026a。

命令行启动：

```powershell
cd D:\project\paper\fusion-eval
python -m pip install -r requirements.txt
python app.py
```

默认使用 `D:\project\matlab\测试指标\测试指标\MEFB` 和 `matlab.exe` 的本机路径，可在左下角设置里修改。工具只监听本机 127.0.0.1。

## 操作

1. 创建项目。
2. 在“源图数据集”中导入 A、B 两路图片，支持文件选择、文件夹选择和本地目录路径（大量图片推荐路径）。
3. 新建测试，填写名称、算法/版本和备注，导入融合图片，选择指标。
4. 查看逐组数值、均值、总体标准差和有效数量；点击组编号查看三图预览与错误详情。
5. 在“结果对比”里选择至少两次测试，使用共同指标全部有效的共同图片组进行比较。
6. 导出 Excel、CSV 或 JSON。CSV 可用 Excel 打开；JSON 包含完整结果、输入指纹和指标指纹。

### 图片命名

支持两个文件夹内同名的 `001.png`，或源图 `001_A.png` / `001_B.png`。也支持 MEFB 原有每组子文件夹布局。源图都在同一目录时，A、B 输入填写同一个目录，工具按 `_A` / `_B` 自动分开。

融合图用 `001.png` 或 `001_算法名.png`；填写算法名时优先精确匹配该后缀。新建测试可以选择全部批次或单个批次；要求所选范围所有组都有融合图，未匹配、多余、重名和尺寸不一致均会阻止提交。A/B 文件夹的子目录结构应一致；融合文件夹保留相应子目录。同名图片跨批次合并测试时，融合图需放在“批次名/子目录/图片名”下。

源图支持多次批量追加。在“源图数据集”点击“追加导入”，填写批次名称和 A/B 文件夹路径即可；一次 500 张 A + 500 张 B 将配成 500 组。不同批次允许同名图片；同一批次内容相同会跳过，内容不同会报错，避免覆盖。图片会复制到工具存储目录，后续修改原图片不影响已保存测试。已有测试不自动增加新导入图片；复制重测保留原测试图片范围，使用当前配置的指标代码。

## 与原指标的关系

- 默认沿用 configMetrics.m 当前启用的 19 项；另可选择库中其他指标。
- 保留原指标公式，包括旧 PSNR 的误差实现和 MEF_SSIM 的多尺度调用。
- 不自动转换灰度/彩色、数值范围；不兼容情况记录为失败。
- 原相位一致性代码用 MATLAB 版本号首字符判断 Octave，导致 R2026a 错误调用 `fflush`。工具仅在测试的代码副本中将环境检测改为 `exist('OCTAVE_VERSION','builtin') ~= 0`，不改变指标公式。保存修补前后 SHA256 和修补说明。
- 单次测试独立 MATLAB 进程；多次测试串行排队，逐项写入结果。
- NaN、Inf、非标量、运行异常均保存为失败，不作为 0 参与均值。
- 单项失败后继续剩余指标；服务重启时将未完成记录标记为中断，可复制重测。
- 界面中的指标箭头仅作方向提示，不能独立代表视觉质量。

## 存储与备份

所有数据在 `data/`：SQLite 数据库、复制的源图/融合图、各测试的指标代码快照、MATLAB 日志和原始 JSONL 结果。也可用环境变量 `FUSION_EVAL_DATA` 指定数据目录。

测试结束后备份完整工作空间：

```powershell
python backup.py backup backups\fusion-lab.zip
```

停止服务后，恢复到一个空目录：

```powershell
python backup.py restore backups\fusion-lab.zip D:\FusionLabData
$env:FUSION_EVAL_DATA='D:\FusionLabData'
python app.py
```

迁移电脑后在设置中调整 MATLAB 与 MEFB 路径。备份含全部项目与图片；JSON/CSV/Excel 导出只含实验记录，不含图像。

## 验证

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
```

自动测试验证配对歧义、缺失回滚、图片快照、失败项排除、有效零值、均值与标准差、Excel XML、代码指纹、中断恢复、备份恢复、已有测试后追加500对图片、重复跳过、内容冲突保护、子目录同名图片和批次范围。真实 MATLAB 衔接验证记录保存在“MEFB 实测验证”项目中。
