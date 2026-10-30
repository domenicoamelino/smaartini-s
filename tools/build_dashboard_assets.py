#!/usr/bin/env python3
"""Build/check the self-contained dashboard assets using vendored local files."""
import argparse,base64,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true');args=parser.parse_args()
    runtime=ROOT if (ROOT/'meeting_worker.py').exists() else ROOT/'ai-platform/transcription/meeting-worker-2.3'
    vendor=(ROOT/'assets/vendor/marked.umd.js').read_text(encoding='utf-8')
    license=(ROOT/'assets/vendor/MARKED-LICENSE.md').read_text(encoding='utf-8').replace('*/','* /')
    app=(ROOT/'assets/dashboard/dashboard-app.js').read_text(encoding='utf-8')
    logo='data:image/png;base64,'+base64.b64encode((ROOT/'assets/brand/smartinis-logo.png').read_bytes()).decode('ascii')
    outputs={'dashboard.js':'/* Bundled marked 17.0.5 — lexer only; HTML rendering is disabled.\n'+license+'\n*/\n'+vendor+'\n// SMARTINI dashboard application\n'+app,
        'dashboard.html':(ROOT/'assets/dashboard/dashboard.template.html').read_text(encoding='utf-8').replace('__SMARTINIS_LOGO_DATA_URI__',logo)}
    for name,text in outputs.items():
        target=runtime/name
        if args.check:
            if target.read_text(encoding='utf-8')!=text:raise SystemExit('Generated dashboard asset is stale: '+name)
        else:
            tmp=target.with_name(target.name+'.build');tmp.write_text(text,encoding='utf-8',newline='\n')
            for attempt in range(4):
                try:os.replace(tmp,target);break
                except PermissionError:
                    if attempt==3:raise
                    time.sleep(.1*(attempt+1))
    print('Dashboard assets '+('match their sources.' if args.check else 'built from local sources.'))

if __name__=='__main__':main()
