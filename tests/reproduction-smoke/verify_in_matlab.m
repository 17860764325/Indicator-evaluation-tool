% Fusion Lab: direct MATLAB verification, no result cache.
% Uses the exact image and code snapshots of this test.
clear; clc; format long g;
job=jsondecode('{"engine": "D:\\project\\paper\\fusion-eval\\data\\runs\\0470efe007374c6cbc5026a91a9c6f17\\engine", "items": [{"name": "001", "a": "D:\\project\\paper\\fusion-eval\\data\\sources\\f63f46d0936a401781a8dec1927405a3\\a\\6985846668934e958c6263986bd6a251.png", "b": "D:\\project\\paper\\fusion-eval\\data\\sources\\f63f46d0936a401781a8dec1927405a3\\b\\944e713b2ea14a6d82cb9b740c353c7f.png", "f": "D:\\project\\paper\\fusion-eval\\data\\runs\\0470efe007374c6cbc5026a91a9c6f17\\fused\\7d22f9ba98414d4f82eef77414de20b6.png"}, {"name": "002", "a": "D:\\project\\paper\\fusion-eval\\data\\sources\\f63f46d0936a401781a8dec1927405a3\\a\\b7a2e3634b2f40a8b82eb144651ec600.png", "b": "D:\\project\\paper\\fusion-eval\\data\\sources\\f63f46d0936a401781a8dec1927405a3\\b\\cc926ca91ba3427a918c5af34e7d51ca.png", "f": "D:\\project\\paper\\fusion-eval\\data\\runs\\0470efe007374c6cbc5026a91a9c6f17\\fused\\84c5decf439d4c76b85fd10a1a1e28d9.png"}], "metrics": ["Entropy", "SD", "Spatial_frequency"]}');
addpath(job.engine);
clear metricsEntropy metricsSD metricsSpatial_frequency;
records={}; resultsMetrics=nan(numel(job.items),1,numel(job.metrics));
for ii=1:numel(job.items)
 t=job.items(ii); A=imread(t.a); B=imread(t.b); F=imread(t.f);
 for mm=1:numel(job.metrics)
  m=job.metrics{mm}; v=NaN; status='error'; note='';
  try
   v=feval(['metrics' m],A,B,F);
   if ~isnumeric(v)||~isscalar(v)||~isreal(v)||~isfinite(v),error('Invalid scalar result');end
   status='ok';resultsMetrics(ii,1,mm)=double(v);
  catch err,note=getReport(err,'basic','hyperlinks','off');v=NaN;end
  records(end+1,:)={t.name,m,v,status,note};
 end
end
resultsMetricsAverageImg=mean(resultsMetrics,1,'omitnan');
verification=cell2table(records,'VariableNames',{'Group','Metric','Value','Status','Error'});
disp(verification); disp(resultsMetricsAverageImg);
writetable(verification,fullfile(fileparts(mfilename('fullpath')),'matlab_verification.csv'));
