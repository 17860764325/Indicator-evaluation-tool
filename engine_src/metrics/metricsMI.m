% =====================================================================
% metricsFMI_IVIF.m / metricsMI.m —— 互信息 MI
% ---------------------------------------------------------------------
% 定义（经典形式，Piella）：
%   MI = I(A, F) + I(B, F)
% 即融合图与两路源图的互信息之和。数值越大，说明融合图从两路源图
% 中获取的信息越多。
%
% 实现：直接复用 MEFB 库自带的 mutual_info.m（来自
%       https://github.com/zhengliu6699/imageFusionMetrics），
%       该函数返回 MI, H_xy, H_x, H_y，输入需为 0~255 的灰度图。
%
% 参考：G. Qu, D. Zhang, P. Yan, "Information measure for performance
%       of image fusion", Electronics Letters, 2002.
%
% 注意：MI 是"半参考"指标，只需要两路源图 + 融合图，不需要融合真值。
% =====================================================================
function res = metricsMI(img1, img2, fused)

    A = to_gray255(img1);
    B = to_gray255(img2);
    F = to_gray255(fused);

    miA = mutual_info(A, F);      % I(A, F)
    miB = mutual_info(B, F);      % I(B, F)

    res = miA + miB;
end

% 统一转成 0~255 的 uint8 灰度图（mutual_info 要求 0~255 整数）
function g = to_gray255(x)
    x = double(x);
    if ndims(x) > 2 && size(x, 3) > 1
        x = rgb2gray(uint8(min(max(x, 0), 255)));
        g = double(x);
    else
        g = min(max(x, 0), 255);
    end
end
