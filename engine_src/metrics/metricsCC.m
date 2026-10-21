% =====================================================================
% metricsCC.m —— 相关系数 CC (Correlation Coefficient)
% ---------------------------------------------------------------------
% 定义：融合图与两路源图的相关系数的平均
%   CC = ( corr(F, A) + corr(F, B) ) / 2
% 参考：Deshmukh & Bhosale, "Image fusion quality assessment"
%      C. S. Xydeas and V. Petrovic 系列工作，以及
%      https://github.com/zhengliu6699/imageFusionMetrics
%
% 注意：CC 是"半参考"指标，只需要两路源图 + 融合图，不需要融合真值。
% =====================================================================
function res = metricsCC(img1, img2, fused)

    A = to_gray(double(img1));
    B = to_gray(double(img2));
    F = to_gray(double(fused));

    res = (corr2(A, F) + corr2(B, F)) / 2;
end

function g = to_gray(x)
    if ndims(x) > 2 && size(x, 3) > 1
        g = rgb2gray(uint8(min(max(x, 0), 255)));
        g = double(g);
    else
        g = x;
    end
end
