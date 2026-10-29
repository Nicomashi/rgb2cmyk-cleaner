"""Experimental mode A. Values in percent; stable C,M,Y tie priority."""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class Settings:
    strength: float = 1
    compensation: float = .82
    max_k: float = 100
    neutral_protection: float = 1
    tac: float = 300
    smooth_ties: bool = True

    def __post_init__(self):
        for key, lo, hi in [('strength',0,1),('compensation',0,2),('max_k',0,100),
                            ('neutral_protection',0,1),('tac',0,400)]:
            v = getattr(self,key)
            if not np.isfinite(v) or not lo <= v <= hi:
                raise ValueError(f'Invalid {key}: {v}')

def smoothstep(x):
    x = np.clip(x,0,1)
    return x*x*(3-2*x)

def clean_percent(source, settings):
    src = np.asarray(source, dtype=np.float32)
    if src.shape[-1] != 4 or not np.isfinite(src).all() or (src<0).any() or (src>100).any():
        raise ValueError('Expected finite CMYK percentages in [0,100]')
    cmy = src[...,:3]
    order = np.sort(cmy, axis=-1)
    minimum = order[...,0]
    gate = 1-settings.neutral_protection*(1-smoothstep((order[...,2]-minimum)/20))
    if settings.smooth_ties:
        # Fade cleaning to zero near channel crossings, without changing two other inks.
        gate *= smoothstep((order[...,1]-minimum)/2)
    removed = minimum*settings.strength*gate
    winner = np.argmin(cmy,axis=-1)
    result = src.copy()
    result[...,:3] -= np.eye(3,dtype=np.float32)[winner]*removed[...,None]
    old_k = src[...,3]
    # Limits restrict ADDED K, never silently recolor already excessive source pixels.
    room_k = np.maximum(0, settings.max_k-old_k)
    room_tac = np.maximum(0, settings.tac-result[...,:3].sum(axis=-1)-old_k)
    added = np.minimum(removed*settings.compensation, np.minimum(room_k,room_tac))
    result[...,3] += added
    return result, removed

def clean_u8(source, settings):
    result, _ = clean_percent(np.asarray(source,dtype=np.float32)*100/255, settings)
    # Round CMY down / K down only if nearest rounding introduces a new TAC violation.
    out = np.rint(result*255/100).clip(0,255).astype(np.uint8)
    limit = int(np.floor(settings.tac*255/100+1e-5))
    total = out.astype(np.int16).sum(axis=-1)
    original_k = np.asarray(source)[...,3].astype(np.int16)
    trim = np.minimum(np.maximum(total-limit,0), np.maximum(out[...,3].astype(np.int16)-original_k,0))
    out[...,3] = out[...,3].astype(np.int16)-trim
    return out

def statistics(before, after, settings):
    b, a = before.astype(np.float32)*100/255, after.astype(np.float32)*100/255
    removed = (b[...,:3]-a[...,:3]).sum(axis=-1)
    tac = a.sum(axis=-1)
    return {'changed_pct':round(float(np.mean(np.any(before!=after,axis=-1))*100),2),
            'removed_mean':round(float(removed.mean()),2),
            'tac_before':round(float(b.sum(axis=-1).max()),1),
            'tac_after':round(float(tac.max()),1),
            'tac_exceeded_pct':round(float(np.mean(tac>settings.tac+.01)*100),2),
            'k_exceeded_pct':round(float(np.mean(a[...,3]>settings.max_k+.01)*100),2)}
