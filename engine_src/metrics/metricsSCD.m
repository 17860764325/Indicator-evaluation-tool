% =====================================================================
% metricsSCD.m —— 差异相关性之和 SCD (Sum of Correlation Differences)
% ---------------------------------------------------------------------
% 定义（Piella 提出的经典形式）：
%   先算源图之间的差：  D1 = A - B,  D2 = B - A
%   再算融合图与各自源图的差：
%       D1_F = F - B,   D2_F = F - A
%   然后：
%       SCD = corr(D1, D1_F) + corr(D2, D2_F)
%
% 物理含义：融合图相对 B 的"变化"，应当与 A 相对 B 的变化一致 —— 即
%           融合图既要像 A（保留 A 的信息）又要像 B，两项相加越大说明
%           两路信息都保留得越好。
%
% 注意：本形式是"求和"而非"取平均"，因此取值范围约为 [-2, 2]
%       （若取平均则约为 [-1, 1]）。论文 MSRS 的 SCD = 1.1262 > 1，
%       正好说明论文用的也是"求和"形式。
%
% 参考：V. Petrovic and C. Xydeas, "Objective image fusion performance
%       measure", Electronics Letters, 2000.
%       https://github.com/zhengliu6699/imageFusionMetrics
%
% 注意：SCD 是"半参考"指标，只需要两路源图 + 融合图，不需要融合真值。
% =====================================================================
function res = metricsSCD(img1, img2, fused)

    A = to_gray(double(img1));
    B = to_gray(double(img2));
    F = to_gray(double(fused));

    D1 = A - B;      % 源图之间的差异
    D2 = B - A;

    D1_F = F - B;    % 融合图相对 B 的差异
    D2_F = F - A;    % 融合图相对 A 的差异

    res = corr2(D1, D1_F) + corr2(D2, D2_F);
end

function g = to_gray(x)
    if ndims(x) > 2 && size(x, 3) > 1
        g = rgb2gray(uint8(min(max(x, 0), 255)));
        g = double(g);
    else
        g = x;
    end
end
