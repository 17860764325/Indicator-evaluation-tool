job=jsondecode(fileread(fullfile(fileparts(mfilename('fullpath')),'job.json')));
addpath(job.metrics);
A=imread(job.a);B=imread(job.b);
web=metricsEntropy(A,B,imread(job.web));
manual=metricsEntropy(A,B,imread(job.manual));
r=struct('web_direct_matlab',web,'manual_jpg_direct_matlab',manual,'function_file',which('metricsEntropy'));
fid=fopen(job.output,'w','n','UTF-8');fprintf(fid,'%s',jsonencode(r));fclose(fid);
disp(r);
