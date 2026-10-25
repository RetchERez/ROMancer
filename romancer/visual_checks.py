"""Exact RGB screenshot regions from measured frames, with bounded failure images."""
import base64
import hashlib
import io
import re
from .asset_schema import fields,number

MAX_REGION=256*256*3


def _region(region,width,height):
    fields(region,'x y width height');number(region['x'],0,width-1);number(region['y'],0,height-1)
    number(region['width'],1,256);number(region['height'],1,256)
    if region['x']+region['width']>width or region['y']+region['height']>height:raise ValueError('Screenshot region lies outside the measured frame.')
    return region


def _hash(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value):raise ValueError('Invalid screenshot checksum.')
    return value


def _frame(frame):
    width=number(frame['width'],1,2048);height=number(frame['height'],1,2048);text=frame['rgb24_base64']
    if type(text) is not str or len(text)>((8*1024**2+2)//3)*4:raise ValueError('Measured frame exceeds the pixel budget.')
    raw=base64.b64decode(text,validate=True)
    if len(raw)!=width*height*3 or len(raw)>8*1024**2 or hashlib.sha256(raw).hexdigest()!=_hash(frame['sha256']):raise ValueError('Measured screenshot pixel checksum or dimensions differ.')
    return width,height,raw


def _crop(raw,width,region):
    return b''.join(raw[((region['y']+y)*width+region['x'])*3:((region['y']+y)*width+region['x']+region['width'])*3] for y in range(region['height']))


def make_assertion(frame,region):
    width,height,raw=_frame(frame);_region(region,width,height);pixels=_crop(raw,width,region)
    return {'kind':'frame_region','region':dict(region),'frame_width':width,'frame_height':height,
            'recorded_frame_sha256':frame['sha256'],'expected_rgb24_base64':base64.b64encode(pixels).decode('ascii'),
            'expected_sha256':hashlib.sha256(pixels).hexdigest()}


def validate_assertion(assertion):
    fields(assertion,'kind region frame_width frame_height recorded_frame_sha256 expected_rgb24_base64 expected_sha256')
    if assertion['kind']!='frame_region':raise ValueError('Expected screenshot region assertion.')
    width=number(assertion['frame_width'],1,2048);height=number(assertion['frame_height'],1,2048);region=_region(assertion['region'],width,height)
    _hash(assertion['recorded_frame_sha256']);_hash(assertion['expected_sha256']);text=assertion['expected_rgb24_base64']
    if type(text) is not str or len(text)>((MAX_REGION+2)//3)*4:raise ValueError('Screenshot region exceeds 256 × 256 pixels.')
    raw=base64.b64decode(text,validate=True)
    if len(raw)!=region['width']*region['height']*3 or hashlib.sha256(raw).hexdigest()!=assertion['expected_sha256']:raise ValueError('Expected screenshot region pixels or checksum differ.')
    return raw


def _png(raw,width,height):
    from PIL import Image
    image=Image.frombytes('RGB',(width,height),raw);output=io.BytesIO();image.save(output,format='PNG')
    return base64.b64encode(output.getvalue()).decode('ascii')


def compare_frame(frame,assertion):
    expected=validate_assertion(assertion);width,height,raw=_frame(frame);region=assertion['region']
    result={'kind':'frame_region','region':region,'frame_index':frame['index'],'actual_frame_sha256':frame['sha256'],
            'recorded_frame_sha256':assertion['recorded_frame_sha256'],'expected_sha256':assertion['expected_sha256'],
            'frame_width':width,'frame_height':height,'pass':False,'comparison':'exact_rgb24_no_tolerance'}
    try:_region(region,width,height)
    except ValueError:return {**result,'reason':'Recorded screenshot region is outside the new frame dimensions.','changed_pixels':None}
    actual=_crop(raw,width,region);changed=sum(expected[i:i+3]!=actual[i:i+3] for i in range(0,len(expected),3));same_size=(width,height)==(assertion['frame_width'],assertion['frame_height'])
    result.update(actual_sha256=hashlib.sha256(actual).hexdigest(),changed_pixels=changed,**{'pass':same_size and changed==0})
    if not same_size:result['reason']='Frame dimensions changed from the recorded expectation.'
    if not result['pass']:
        difference=bytes(abs(a-b) for a,b in zip(expected,actual));w,h=region['width'],region['height']
        result['visual']={'expected_png_base64':_png(expected,w,h),'actual_png_base64':_png(actual,w,h),
                          'difference_png_base64':_png(difference,w,h),'width':w,'height':h,'difference_mode':'absolute_channel_difference'}
    return result
