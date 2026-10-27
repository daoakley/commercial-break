// CPU-only bounded benchmark. No TV APIs, capture, network or playback controls.
#include "net.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <sys/resource.h>
#include <unistd.h>
#include <vector>

static void expired(int) { const char msg[]="benchmark deadline exceeded\n"; write(2,msg,sizeof(msg)-1); _exit(124); }
static double ms(std::chrono::steady_clock::time_point t) {
    return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();
}
extern "C" __attribute__((visibility("default"))) int benchmark_entry(int argc,char**argv) {
    if(argc<5 || argc>7) { fprintf(stderr,"usage: bench model.param model.bin input.f32 reference.f32 [iterations<=10] [threads<=2]\n"); return 2; }
    int iterations=argc>5?atoi(argv[5]):3,threads=argc>6?atoi(argv[6]):1;
    if(iterations<1 || iterations>10 || threads<1 || threads>2) return 2;
    signal(SIGALRM,expired); alarm(25);
    // The managed host reserves address space before loading us. Limit additional
    // virtual space rather than denying its already-mapped runtime.
    unsigned long pages=0;FILE*statm=fopen("/proc/self/statm","r");
    if(!statm || fscanf(statm,"%lu",&pages)!=1)return 3;
    fclose(statm);
    rlim_t cap=(rlim_t)pages*sysconf(_SC_PAGESIZE)+192*1024*1024;
    struct rlimit memory={cap,cap},cpu={20,21};
    if(setrlimit(RLIMIT_AS,&memory)||setrlimit(RLIMIT_CPU,&cpu)) { perror("resource limits");return 3; }
    setpriority(PRIO_PROCESS,0,15);
    ncnn::Net net;
    net.opt.num_threads=threads;
    net.opt.use_vulkan_compute=false;
    net.opt.use_fp16_packed=false;
    net.opt.use_fp16_storage=false;
    net.opt.use_fp16_arithmetic=false;
    net.opt.use_bf16_storage=false;
    auto start=std::chrono::steady_clock::now();
    if(net.load_param(argv[1])||net.load_model(argv[2])) { fprintf(stderr,"model load failed\n"); return 4; }
    double load_ms=ms(start);
    ncnn::Mat input(256,256,3);
    if(input.empty())return 5;
    FILE*f=fopen(argv[3],"rb");if(!f)return 5;
    for(int c=0;c<3;c++)if(fread((float*)input.channel(c),sizeof(float),256*256,f)!=256*256)return 5;
    fclose(f);
    std::vector<float> ref(512);f=fopen(argv[4],"rb");if(!f)return 5;
    if(fread(ref.data(),sizeof(float),512,f)!=512)return 5;fclose(f);
    std::vector<double> times;double warmup=0,cosine=0,maxerr=0;
    for(int i=0;i<=iterations;i++) {
        start=std::chrono::steady_clock::now();
        auto ex=net.create_extractor();ncnn::Mat out;
        if(ex.input("in0",input)||ex.extract("out0",out)||out.total()!=512) { fprintf(stderr,"inference failed\n");return 6; }
        double elapsed=ms(start);if(i==0)warmup=elapsed;else times.push_back(elapsed);
        double dot=0,a=0,b=0;const float*p=out;
        for(int k=0;k<512;k++){if(!std::isfinite(p[k]))return 7;dot+=p[k]*ref[k];a+=p[k]*p[k];b+=ref[k]*ref[k];}
        cosine=dot/std::sqrt(a*b);maxerr=0;
        for(int k=0;k<512;k++)maxerr=std::max(maxerr,std::abs(p[k]/std::sqrt(a)-ref[k]/std::sqrt(b)));
    }
    struct rusage usage;getrusage(RUSAGE_SELF,&usage);
    std::vector<double> sorted=times;std::sort(sorted.begin(),sorted.end());
    printf("{\"threads\":%d,\"iterations\":%d,\"additional_virtual_memory_limit_mib\":192,\"wall_limit_seconds\":25,\"load_ms\":%.3f,\"first_inference_ms\":%.3f,\"median_ms\":%.3f,\"max_ms\":%.3f,\"peak_rss_kib\":%ld,\"reference_cosine\":%.9f,\"normalized_max_error\":%.9f,\"times_ms\":[",threads,iterations,load_ms,warmup,sorted[sorted.size()/2],sorted.back(),usage.ru_maxrss,cosine,maxerr);
    for(size_t i=0;i<times.size();i++)printf("%s%.3f",i?",":"",times[i]);printf("]}\n");
    alarm(0);return cosine>.999?0:8;
}
int main(int argc,char**argv){return benchmark_entry(argc,argv);}
