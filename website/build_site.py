import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from demo_service import build_payload

def main():
    payload=build_payload()
    target=HERE/'assets/study-data.js'
    target.write_text('window.PROJECT_STUDY = '+json.dumps(payload,separators=(',',':'),allow_nan=False)+';\n')
    print(f'Built {len(payload["cases"])} published conditions, ten actual-source snippets and a validated seed-200 replay.')

if __name__=='__main__':main()
