import numpy as np
import pytest
from cleaner.engine import Settings, clean_percent, clean_u8

def strict(**kw):
    return Settings(**dict(strength=1,compensation=1,neutral_protection=0,smooth_ties=False,tac=400,**kw))

def test_reference_pixel():
    actual,removed=clean_percent(np.array([100,87,27,14]),strict())
    np.testing.assert_allclose(actual,[100,87,0,41]); assert removed==27

def test_compensation_changes_k_only():
    a,_=clean_percent([100,87,27,14],Settings(1,.5,100,0,400,False))
    np.testing.assert_allclose(a,[100,87,0,27.5])

def test_zero_strength_is_identity_even_beyond_limits():
    rng=np.random.default_rng(7); image=rng.integers(0,256,(60,70,4),dtype=np.uint8)
    np.testing.assert_array_equal(clean_u8(image,Settings(strength=0,max_k=20,tac=100)),image)

def test_only_one_cmy_changes_and_other_two_preserved():
    rng=np.random.default_rng(2); src=rng.integers(0,256,(200,200,4),dtype=np.uint8)
    out=clean_u8(src,strict())
    assert np.max((src[...,:3]!=out[...,:3]).sum(axis=-1))<=1
    assert (out[...,:3]<=src[...,:3]).all()
    assert (out[...,3]>=src[...,3]).all()

def test_neutral_protection():
    p=np.array([[40,40,40,20],[20,20,20,0]])
    out,_=clean_percent(p,Settings())
    np.testing.assert_array_equal(out,p)

def test_stable_tie_priority():
    out,_=clean_percent([20,20,80,0],strict())
    np.testing.assert_array_equal(out,[0,20,80,20])

def test_smoothed_crossing_has_no_jump():
    src=np.array([[20,20.001,80,0],[20.001,20,80,0]])
    out,_=clean_percent(src,Settings(1,1,100,0,400,True))
    assert np.max(np.abs(src-out))<.001

def test_k_and_tac_headroom():
    out,_=clean_percent([100,87,27,14],Settings(1,2,30,0,210,False))
    np.testing.assert_allclose(out,[100,87,0,23]); assert out.sum()==210

def test_existing_k_is_never_clipped():
    out,_=clean_percent([10,50,80,95],Settings(1,1,50,0,300,False))
    assert out[3]==95

def test_rounding_and_reproducibility_with_tac():
    src=np.random.default_rng(0).integers(0,140,(128,128,4),dtype=np.uint8)
    s=Settings(1,2,100,0,220,False)
    out=clean_u8(src,s)
    assert (out.astype(float).sum(axis=-1)*100/255<=220).all()
    np.testing.assert_array_equal(out,clean_u8(src,s))

def test_tile_independence():
    src=np.random.default_rng(3).integers(0,256,(130,250,4),dtype=np.uint8)
    entire=clean_u8(src,Settings())
    tiled=np.concatenate([clean_u8(src[:64],Settings()),clean_u8(src[64:],Settings())])
    np.testing.assert_array_equal(entire,tiled)

@pytest.mark.parametrize('kw',[{'strength':2},{'compensation':-1},{'tac':401},{'max_k':101},{'neutral_protection':float('nan')}])
def test_invalid_settings(kw):
    with pytest.raises(ValueError): Settings(**kw)
