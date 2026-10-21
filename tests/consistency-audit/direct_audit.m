j=jsondecode(fileread(fullfile(fileparts(mfilename('fullpath')),'job.json')));
addpath(j.source);
fid=fopen(j.output,'w');fclose(fid);
for ii=1:numel(j.items)
 t=j.items(ii); A=imread(t.a); B=imread(t.b); F=imread(t.f);
 if ii<=2, ms=j.all_metrics; else, ms=j.metrics; end
 for mm=1:numel(ms)
  m=ms{mm}; compat=strcmp(m,'Qp');
  if compat, rmpath(j.source);addpath(j.compat);clear metricsQp myphasecong3;end
  x=struct('item_id',t.id,'name',t.name,'metric',m,'value',[],'status','error','error','');
  try
   v=feval(['metrics' m],A,B,F);
   if isnumeric(v)&&isscalar(v)&&isreal(v)&&isfinite(v),x.value=double(v);x.status='ok';else,x.error='nonfinite';end
  catch err,x.error=getReport(err,'basic','hyperlinks','off');end
  if compat,rmpath(j.compat);addpath(j.source);clear metricsQp myphasecong3;end
  fid=fopen(j.output,'a','n','UTF-8');fprintf(fid,'%s\n',jsonencode(x));fclose(fid);
 end
end
