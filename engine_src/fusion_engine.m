function fusion_engine(jobPath)
%#function metricsCross_entropy
%#function metricsEntropy
%#function metricsFMI
%#function metricsNMI
%#function metricsPsnr
%#function metricsQncie
%#function metricsTE
%#function metricsAvg_gradient
%#function metricsEdge_intensity
%#function metricsQabf
%#function metricsQp
%#function metricsSD
%#function metricsSpatial_frequency
%#function metricsQc
%#function metricsQw
%#function metricsQy
%#function metricsMEF_SSIM
%#function metricsQcb
%#function metricsQcv
%#function metricsVIF
%#function metricsMI
%#function metricsCC
%#function metricsSCD
%#function metricsNabf

job = jsondecode(fileread(jobPath));
if ~isdeployed, addpath(job.engine); end
v = version;
fid = fopen(job.version_file,'w','n','UTF-8'); fprintf(fid,'%s',v); fclose(fid);
for ii=1:numel(job.items)
    item=job.items(ii);
    for mm=1:numel(job.metrics)
        metric=job.metrics{mm};
        record=struct('item_id',item.id,'metric',metric,'value',[],'status','error','error','','seconds',0);
        started=tic;
        try
            A=imread(item.a); B=imread(item.b); F=imread(item.f);
            value=feval(['metrics' metric],A,B,F);
            if ~isnumeric(value) || ~isscalar(value) || ~isreal(value) || ~isfinite(value)
                error('FusionEval:InvalidResult','指标返回非有限实数标量（NaN / Inf 等）');
            end
            record.value=double(value); record.status='ok';
        catch err
            record.error=getReport(err,'basic','hyperlinks','off');
        end
        record.seconds=toc(started);
        fid=fopen(job.results,'a','n','UTF-8');
        fprintf(fid,'%s\n',jsonencode(record)); fclose(fid);
    end
end

end
