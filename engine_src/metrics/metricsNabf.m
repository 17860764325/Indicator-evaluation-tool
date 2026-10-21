% =====================================================================
% metricsNabf.m —— 边缘信息保留度 N_ab/f
% ---------------------------------------------------------------------
% 说明（重要）：
%   N_ab/f 与 Q_AB/F 在本领域资料中指的是**同一个指标** —— Xydeas 与
%   Petrovic 提出的 "Objective image fusion performance measure"
%   （Electronics Letters 2000）。MEFB 库里的 metricsQabf.m 就是它的
%   实现。
%
%   论文 Table 1 把 N_ab/f 标注成 "↓"（越小越好），但按 Xydeas-Petrovic
%   的原始定义它是**越大越好**、取值 [0,1]。这个箭头很可能是排版问题
%   （从 PDF 提取的表头里所有统计量都被挤在了一行）。
%
%   因此本函数直接复用 metricsQabf，作为 N_ab/f 的数值。
%   如果论文确实按"1 - Q_AB/F"使用，可用下面注释里的备用行切换。
%
% 参考：C. S. Xydeas and V. Petrovic, "Objective image fusion performance
%       measure", Electronics Letters, 36(4):308-309, 2000.
%
% 注意：N_ab/f 是"半参考"指标，只需要两路源图 + 融合图，不需要融合真值。
% =====================================================================
function res = metricsNabf(img1, img2, fused)

    res = metricsQabf(img1, img2, fused);

    % 若论文确实把 N_ab/f 定义为 1 - Q_AB/F（越小越好），改用下面这行：
    % res = 1 - metricsQabf(img1, img2, fused);
end
