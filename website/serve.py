import argparse,csv,errno,io,json,mimetypes,os,sys,threading,time,uuid,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from demo_service import ROOT,DEFAULT,validate_context,validate_run,run_experiment,replay

ENGINE_LOCK=threading.Lock()
JOBS={};JOBS_LOCK=threading.Lock()
DOWNLOADS={
 '/presentation/OS_Research_Presentation.pptx':ROOT/'presentation/OS_Research_Presentation.pptx',
 '/report_ieee/OS_Project_IEEE_Report_Periodic_Recalibration.pdf':ROOT/'report_ieee/OS_Project_IEEE_Report_Periodic_Recalibration.pdf',
 '/files/experiment-plan.md':ROOT/'revisions/2026-10-31/EXPERIMENT_AND_ANALYSIS_PLAN.md',
 '/files/paper-data.csv':ROOT/'results/periodic/runs.csv',
 '/files/paired-results.csv':ROOT/'results/periodic/paired.csv',
}
for name in ('periodic_study.py','run_periodic_study.py','run_calibrated_study.py','calibrated_study.py','analyze_periodic_study.py','study.py'):
    DOWNLOADS['/source/'+name]=ROOT/name

def csv_bytes(rows):
    f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return f.getvalue().encode()

def start_job(value):
    context,seed,repeats=validate_run(value)
    if not ENGINE_LOCK.acquire(blocking=False):raise RuntimeError('A simulation is already running. Wait for it to finish.')
    ident=uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        if len(JOBS)>=12:
            completed=[k for k,v in JOBS.items() if v['status'] in ('complete','error')]
            if completed:del JOBS[completed[0]]
        JOBS[ident]=dict(id=ident,status='running',completed=0,total=repeats,context=context,seed=seed,repeats=repeats)
    def worker():
        try:
            def progress(done,total):
                with JOBS_LOCK:JOBS[ident].update(completed=done,total=total)
            result,rows=run_experiment(dict(context,seed=seed,repeats=repeats),progress)
            result.update(job_id=ident,export_url='/api/jobs/'+ident+'/export.csv')
            with JOBS_LOCK:JOBS[ident].update(status='complete',result=result,rows=rows)
        except Exception as exc:
            with JOBS_LOCK:JOBS[ident].update(status='error',error=str(exc))
        finally:ENGINE_LOCK.release()
    threading.Thread(target=worker,daemon=True).start()
    return ident

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):
        if args and str(args[1] if len(args)>1 else '').startswith(('4','5')):super().log_message(fmt,*args)

    def send(self,status,data,content_type='application/json',filename=None):
        if isinstance(data,(dict,list)):data=json.dumps(data,allow_nan=False).encode()
        elif isinstance(data,str):data=data.encode()
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.end_headers();self.wfile.write(data)

    def local_request(self):
        host=self.headers.get('Host','').split(':')[0]
        if host not in ('127.0.0.1','localhost'):self.send(403,{'error':'This demo accepts local requests only.'});return False
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)):
            self.send(403,{'error':'Open the demo from its local address.'});return False
        return True

    def do_GET(self):
        if not self.local_request():return
        path=urlsplit(self.path).path
        if path=='/api/health':return self.send(200,dict(available=True,engine='periodic_study.py',worker_limit=1,native_testing=False))
        if path.startswith('/api/jobs/'):
            parts=path.split('/');ident=parts[3]
            with JOBS_LOCK:job=JOBS.get(ident)
            if not job:return self.send(404,{'error':'Experiment not found. Run it again in this server session.'})
            if len(parts)>4 and parts[4]=='result':
                if job['status']!='complete':return self.send(409,{'error':'Experiment is not complete.'})
                return self.send(200,job['result'])
            if len(parts)>4 and parts[4]=='export.csv':
                if job['status']!='complete':return self.send(409,{'error':'Experiment is not complete.'})
                return self.send(200,csv_bytes(job['rows']),'text/csv; charset=utf-8',f'experiment-{ident}.csv')
            return self.send(200,{k:v for k,v in job.items() if k not in ('rows','result')})
        if path in DOWNLOADS:
            p=DOWNLOADS[path]
            return self.send(200,p.read_bytes(),mimetypes.guess_type(str(p))[0] or 'application/octet-stream')
        if path in ('/','/index.html'):p=HERE/'index.html'
        elif path in ('/assets/app.css','/assets/app.js','/assets/study-data.js'):p=HERE/path.lstrip('/')
        elif path=='/favicon.ico':return self.send(204,b'','image/x-icon')
        else:return self.send(404,{'error':'Page not found.'})
        if not p.exists():return self.send(503,{'error':'Build the website data first: python3 website/build_site.py'})
        return self.send(200,p.read_bytes(),mimetypes.guess_type(str(p))[0] or 'application/octet-stream')

    def do_POST(self):
        if not self.local_request():return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=16384:raise ValueError('Invalid request size.')
            value=json.loads(self.rfile.read(size))
            if not isinstance(value,dict):raise ValueError('Settings must be an object.')
            path=urlsplit(self.path).path
            if path=='/api/run':return self.send(202,{'id':start_job(value)})
            if path=='/api/replay':
                context,seed,_=validate_run(dict(value,repeats=1))
                if not ENGINE_LOCK.acquire(blocking=False):return self.send(409,{'error':'Finish the current experiment before generating a replay.'})
                try:data=replay(context,seed,value.get('baseline','periodic_20'))
                finally:ENGINE_LOCK.release()
                return self.send(200,data)
            return self.send(404,{'error':'Endpoint not found.'})
        except (ValueError,TypeError,json.JSONDecodeError) as exc:self.send(400,{'error':str(exc)})
        except RuntimeError as exc:self.send(409,{'error':str(exc)})
        except Exception:
            self.send(500,{'error':'The experiment failed. Inspect the local terminal for details.'})
            import traceback;traceback.print_exc()

def main():
    parser=argparse.ArgumentParser(description='Open the professor-facing scheduling simulation website.')
    parser.add_argument('--port',type=int,default=8841);parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    if not (HERE/'assets/study-data.js').exists():
        from build_site import main as build
        build()
    try:os.nice(10)
    except (AttributeError,OSError):pass
    url=f'http://127.0.0.1:{args.port}'
    try:server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError as exc:
        if exc.errno!=errno.EADDRINUSE:raise
        try:
            with urlopen(url+'/api/health',timeout=2) as response:health=json.load(response)
        except Exception:health={}
        if health.get('engine')=='periodic_study.py' and health.get('available'):
            print(f'Project demo is already running: {url}',flush=True)
            if args.open:webbrowser.open(url)
            return
        parser.error(f'Port {args.port} is occupied. Start with --port {args.port+1} instead.')
    print(f'Project demo: {url}\nOne Python simulation worker. No native CPU benchmark or hardware control.\nPress Control-C to stop.',flush=True)
    if args.open:threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
