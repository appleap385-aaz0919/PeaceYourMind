"""Probe, decode and sample the actual local MP4; never invokes an uploader."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import math
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
TSHIRT = '--tshirt' in sys.argv
OUT = ROOT / ('work/samples/2026-11-10-tshirt-bag' if TSHIRT else 'work/samples/2026-11-10-remotion')
VIDEO = OUT / ('life-tip-tshirt-bag.mp4' if TSHIRT else 'life-tip-drawer-remotion.mp4')
data = json.loads((OUT/'metadata.json').read_text(encoding='utf-8'))
probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(VIDEO)]))
video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
assert (video['width'],video['height'],video['r_frame_rate']) == (720,1280,'15/1')
assert 65 <= float(probe['format']['duration']) <= 90
assert abs(float(video['duration'])-float(audio['duration'])) < .15
assert ' '.join(c['text'] for c in data['chunks']) == data['spokenScript']
subprocess.run(['ffmpeg','-v','error','-threads','1','-i',str(VIDEO),'-f','null','-'],check=True,capture_output=True)
samples = [(f"{i+1:02d}-{s['kind']}", (s['from']+s['frames']*.55)/15) for i,s in enumerate(data['scenes'])]
for i in (4,7,8,9):
    s=data['scenes'][i]
    samples.extend([(f"{i+1:02d}-{s['kind']}-start",(s['from']+min(10,s['frames']-1))/15),
                    (f"{i+1:02d}-{s['kind']}-end",(s['from']+s['frames']-5)/15)])
samples.append(('last-frame',(data['frames']-1)/15))
frames = OUT/'review-frames'
frames.mkdir(exist_ok=True)
def extract(sample):
    name, t = sample
    target=frames/f'{name}.png'
    subprocess.run(['ffmpeg','-v','error','-threads','1','-ss',f'{t:.4f}','-i',str(VIDEO),'-frames:v','1','-threads','1',str(target),'-y'],check=True,capture_output=True)
    return target
with ThreadPoolExecutor(max_workers=3) as pool:
    paths=list(pool.map(extract,samples))
font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',18)
for batch in range(math.ceil(len(paths)/10)):
    items=paths[batch*10:(batch+1)*10]
    sheet=Image.new('RGB',(360*5,666*2),'#e5e3db')
    draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(items):
        im=Image.open(p).convert('RGB').resize((360,640))
        x,y=(j%5)*360,(j//5)*666
        sheet.paste(im,(x,y))
        draw.text((x+8,y+642),p.stem,font=font,fill='#26322d')
    sheet.save(OUT/f'contact-sheet-{batch+1}.jpg',quality=92)
receipt={'technical_checks':'pass','sampled_frames':len(paths),'durationSeconds':float(probe['format']['duration']),
         'width':720,'height':1280,'fps':15,'audio':audio['codec_name'],'sha256':hashlib.sha256(VIDEO.read_bytes()).hexdigest(),
         'upload_invoked':False,'visual_review':'pending','files':[str(p.relative_to(OUT)) for p in paths]}
(OUT/'review.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='files'},ensure_ascii=False))
