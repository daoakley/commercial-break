#!/usr/bin/env python3
"""Local zero-shot research benchmark; no TV controls, training, or external inference.

Reads retained images into memory via the existing authenticated lab API. Detailed
results are written only into the lab's retention-managed Docker volume.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request

# Freeze before viewing predictions. No Samsung verdict or native ad flag in input.
PROMPTS = {
    "simple": [
        ("ad", "A screenshot of a television commercial advertisement."),
        ("program", "A screenshot of a television program."),
    ],
    "descriptive": [
        ("ad", "A television commercial advertising a product for sale."),
        ("ad", "A television commercial showing a brand logo and a purchase offer."),
        ("ad", "A television advertisement for a medicine with medical disclaimers."),
        ("ad", "A television commercial advertising insurance, financial services, or a car."),
        ("ad", "A television advertisement asking viewers to call a phone number or visit a website."),
        ("ad", "An advocacy advertisement presenting a persuasive message to television viewers."),
        ("program", "A live sports television broadcast showing a game, players, and a scoreboard."),
        ("program", "A television news broadcast showing a presenter, headlines, and a news ticker."),
        ("program", "A scene from a television movie or drama showing characters in a story."),
        ("program", "A television cooking or food show demonstrating a recipe."),
        ("program", "A television entertainment program or documentary with people talking."),
        ("program", "A television sports broadcast showing commentators and sponsor graphics."),
    ],
}


def main():
    import torch
    import open_clip
    from PIL import Image
    from timm.utils import reparameterize_model
    from teacher_train import usable, positive_rejection, expiration, DEFAULT_SOURCE

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--max-unlabelled", type=int, default=300)
    args = parser.parse_args()
    token = Path(args.token_file).read_text().strip()
    def get(path):
        request = urllib.request.Request("http://127.0.0.1:8795" + path,
                                         headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read()

    now = time.time()
    rows = json.loads(get("/v1/samples?limit=10000"))["samples"]
    clean = sorted([r for r in rows if usable(r, now, DEFAULT_SOURCE) is None],
                   key=lambda r: r["timestamp_unix"])
    positives = [r for r in clean if positive_rejection(r) is None]
    positive_ids = {r["frame_id"] for r in positives}
    others = [r for r in clean if r["frame_id"] not in positive_ids]
    n = min(len(others), args.max_unlabelled)
    selected = [others[round(i * (len(others)-1) / max(1,n-1))] for i in range(n)]
    selected = sorted(positives + selected, key=lambda r: r["timestamp_unix"])
    if not selected:
        raise ValueError("No unexpired clean study samples available")
    print(json.dumps({"selected":len(selected), "teacher_positives":len(positives),
                      "other_clean_frames":n}), flush=True)
    torch.set_num_threads(2)
    model, _, preprocess = open_clip.create_model_and_transforms(
        "MobileCLIP2-S0", pretrained=args.checkpoint,
        image_mean=(0,0,0), image_std=(1,1,1))
    model.eval()
    model = reparameterize_model(model)
    tokenizer = open_clip.get_tokenizer("MobileCLIP2-S0")
    texts = {}
    with torch.inference_mode():
        for name, prompts in PROMPTS.items():
            texts[name] = model.encode_text(tokenizer([p for _,p in prompts]), normalize=True)
        # Warm-up excluded from timings. Text features calculated once.
        model.encode_image(torch.zeros(1,3,256,256), normalize=True)
    timings, results, failures = [], [], Counter()
    for index,row in enumerate(selected):
        if expiration(row) <= time.time():
            failures["expired"] += 1
            continue
        try:
            with Image.open(io.BytesIO(get('/v1/samples/'+row['frame_id']+'/image'))) as im:
                tensor = preprocess(im.convert('RGB')).unsqueeze(0)
        except Exception as error:
            failures[type(error).__name__] += 1
            continue
        with torch.inference_mode():
            start = time.perf_counter()
            feature = model.encode_image(tensor, normalize=True)
            decisions = {}
            for name, prompts in PROMPTS.items():
                scores = (feature @ texts[name].T)[0].tolist()
                # Best matching visual description, same number per class.
                best = {label:max(s for s,(c,_) in zip(scores,prompts) if c==label)
                        for label in ['ad','program']}
                margin = best['ad']-best['program']
                decisions[name] = {'decision':'ad' if margin>0 else 'program',
                                   'ad_minus_program_similarity':margin,
                                   'abstaining_decision':'uncertain' if abs(margin)<.02 else ('ad' if margin>0 else 'program'),
                                   'top_description':prompts[max(range(len(scores)), key=lambda i:scores[i])][1]}
            timings.append((time.perf_counter()-start)*1000)
        results.append({'frame_id':row['frame_id'], 'timestamp_unix':row['timestamp_unix'],
                        'session_id':row['session_id'], 'samsung_positive':row['frame_id'] in positive_ids,
                        'decisions':decisions})
        if (index+1)%50==0:
            print(json.dumps({'processed':index+1,'selected':len(selected)}),flush=True)
    summaries = {}
    for name in PROMPTS:
        p = [r for r in results if r['samsung_positive']]
        u = [r for r in results if not r['samsung_positive']]
        summaries[name] = {'teacher_positives':len(p),
            'teacher_positives_called_ad':sum(r['decisions'][name]['decision']=='ad' for r in p),
            'teacher_positives_called_ad_margin_002':sum(r['decisions'][name]['abstaining_decision']=='ad' for r in p),
            'other_frames':len(u), 'other_frames_called_ad':sum(r['decisions'][name]['decision']=='ad' for r in u),
            'other_frames_called_ad_margin_002':sum(r['decisions'][name]['abstaining_decision']=='ad' for r in u)}
    report = {'model':'MobileCLIP2-S0','revision':args.revision,
              'checkpoint_sha256':hashlib.file_digest(open(args.checkpoint,'rb'),'sha256').hexdigest(),
              'observation_only':True,'trained_on_study':False,
              'expires_unix':min(expiration(r) for r in selected),
              'prompts':PROMPTS,'preprocess':str(preprocess),'device':'cpu','threads':2,
              'versions':{'torch':torch.__version__, 'open_clip':open_clip.__version__},
              'sampling':'all eligible Samsung positives plus uniformly spaced other clean frames',
              'summaries':summaries,'failures':dict(failures),
              'compute_ms':{'median':statistics.median(timings), 'p95':sorted(timings)[min(len(timings)-1,int(len(timings)*.95))]},
              'limitations':['Samsung agreement is not accuracy. Unknown is not programming.',
                'Related frames are correlated, not independent commercials.',
                'Both fixed prompt variants are exploratory; neither is a validated operating policy.',
                'Similarity margins are uncalibrated; .02 is a preregistered exploratory abstention threshold.',
                'CPU timing excludes fetch, image decoding and preprocessing; not TV latency.'],
              'results':results}
    writer = 'import sys,json,pathlib; d=json.load(sys.stdin); p=pathlib.Path("/data/artifacts/mobileclip-zero-shot.json"); p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(d,indent=2))'
    subprocess.run(['docker','exec','-i','commercial-vision-lab-vision-lab-1','python','-c',writer],
                   input=json.dumps(report),text=True,check=True)
    print(json.dumps({k:v for k,v in report.items() if k not in ['results','prompts','preprocess']},indent=2))


if __name__ == '__main__':
    main()
