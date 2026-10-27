"""Exploratory cross-program evaluation. No playback actions or persistent model export."""
import argparse,json,time
from pathlib import Path
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

def metrics(y,p):
 tp=int(np.sum((y==1)&p));fp=int(np.sum((y==0)&p));fn=int(np.sum((y==1)&~p));tn=int(np.sum((y==0)&~p))
 return dict(tp=tp,fp=fp,fn=fn,tn=tn,ad_frame_recall=tp/(tp+fn) if tp+fn else None,precision=tp/(tp+fp) if tp+fp else None)
def evaluate(root):
 data=np.load(root/'features-private.npz');rows=json.loads((root/'rows-private.json').read_text());labels=json.loads((root/'labels-private.json').read_text())
 if min(r['expires'] for r in rows)<=time.time():raise ValueError('Retained evidence expired; recollect, do not reuse')
 usable=[r for r in labels if r['label']!='unknown'];ids=np.array([r['row'] for r in usable]);y=np.array([r['label']=='ad' for r in usable],dtype=int);groups=np.array([r['group'] for r in usable]);x=data['x'][ids];flat=data['flat'][ids,None]
 baseline=np.array([rows[i]['samsung']=='ad' and rows[i]['same_session'] is True or rows[i]['pill'] for i in ids])
 results=[];details=[]
 for group in sorted(set(groups)):
  test=groups==group;train=~test
  assert not set(groups[train])&set(groups[test])
  if len(set(y[train]))<2:raise ValueError('Training group lacks both classes')
  fold={'held_out':group,'train_frames':int(train.sum()),'test_frames':int(test.sum()),'train_ads':int(y[train].sum()),'test_ads':int(y[test].sum()),'same_frame_native_baseline':metrics(y[test],baseline[test])}
  for name,values in [('flat_fraction',flat),('spatial_141',x)]:
   model=make_pipeline(StandardScaler(),SVC(C=1,gamma='scale',class_weight='balanced',kernel='rbf'))
   model.fit(values[train],y[train]);start=time.perf_counter();p=model.predict(values[test]).astype(bool);elapsed=(time.perf_counter()-start)*1000
   combined=p|baseline[test]
   fold[name]={'alone':metrics(y[test],p),'combined_same_frame':metrics(y[test],combined),'additional_ad_frames':int(np.sum((y[test]==1)&p&~baseline[test])),'additional_program_false_positives':int(np.sum((y[test]==0)&p&~baseline[test])),'batch_inference_ms_per_frame':elapsed/int(test.sum()),'support_vectors':int(len(model[-1].support_))}
   for j,pred in zip(np.where(test)[0],p):details.append(dict(review_index=usable[j]['review_index'],method=name,held_out=group,truth=usable[j]['label'],prediction='ad' if pred else 'program'))
  results.append(fold)
 report={'status':'exploratory_only_not_for_deployment','reviewed_frames':len(labels),'assistant_labeled_ad':sum(y),'assistant_labeled_program':len(y)-sum(y),'excluded_unknown':len(labels)-len(y),'held_out_program_blocks':results,'feature_median_ms_host':float(np.median(data['timings'])),'feature_p95_ms_host':float(np.quantile(data['timings'],.95)),'limitations':['Labels are assistant visual review, not human ground truth.','Frames selected approximately every20seconds per recorded session; sampling is irregular and neighboring frames may repeat within a test block.','Split by program/time block because recorded sessions overlap; no random adjacent-frame train/test split.','One small training ad break; only two evaluation blocks, neither cartoons.','Baseline is same-frame fresh Samsung verdict or Sponsored hit, not actual blocker effectiveness or its persistent cover state.','No end-to-end onset latency or false blocks per viewing-hour can be inferred from sparse screenshot labels.','Experimental141-feature approximation; no author checkpoint, different image resolution/filter/quantization choices, ad-vs-program training rather than paper FMPI target.','Host timings do not establish TV runtime feasibility.','No control changes and no persistent trained model exported.']}
 def clean(v):
  if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
  if isinstance(v,list):return [clean(x) for x in v]
  if isinstance(v,np.generic):return v.item()
  return v
 (root/'predictions-private.json').write_text(json.dumps(details,indent=2));return clean(report)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('private_dir',type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args();report=evaluate(args.private_dir);args.output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
