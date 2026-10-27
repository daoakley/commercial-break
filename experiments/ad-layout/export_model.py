"""Export a reviewed sklearn StandardScaler/SVC pipeline for the TV pilot.
No capture, network, or control operations. The output is a private artifact.
"""
import json
from pathlib import Path
from features import KERNELS

def export_model(pipeline, destination, model_id):
    scaler, svm = pipeline.steps[0][1], pipeline.steps[1][1]
    if scaler.mean_.shape != (141,) or svm.support_vectors_.shape[1] != 141:
        raise ValueError('requires the 141-feature spatial pipeline')
    if list(svm.classes_) != [0,1] or svm.kernel != 'rbf':
        raise ValueError('requires 0=program, 1=ad RBF SVC')
    if not 1 <= len(svm.support_vectors_) <= 128:
        raise ValueError('TV pilot supports at most 128 support vectors')
    obj=dict(version='ad-layout-141-v1',modelId=model_id,threshold=.5,
             mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),
             vectors=svm.support_vectors_.tolist(),dual=svm.dual_coef_[0].tolist(),
             intercept=float(svm.intercept_[0]),gamma=float(svm._gamma),
             kernels=[k.flatten().tolist() for pair in KERNELS for k in pair])
    path=Path(destination)
    path.write_text(json.dumps(obj,separators=(',',':'),allow_nan=False))
    path.chmod(0o600)
