"""Independent closed-form/arc-length references, not a production interpolator."""
import bisect
from functools import lru_cache
import math

TICKS_PER_SECOND=254016000000
CONTROLS=(((100.,300.),(100.,260.),(220.,240.),(320.,240.)),
          ((320.,240.),(420.,240.),(540.,260.),(540.,300.)))


def cubic(points,u):
    return tuple((1-u)**3*a+3*(1-u)**2*u*b+3*(1-u)*u*u*c+u**3*d for a,b,c,d in zip(*points))


@lru_cache(maxsize=2)
def arc_table(piece):
    # Dense chord integration is deliberately independent of the EC adaptive LUT.
    n=16384;points=[cubic(CONTROLS[piece],i/n) for i in range(n+1)];lengths=[0.]
    for a,b in zip(points,points[1:]):lengths.append(lengths[-1]+math.dist(a,b))
    return points,lengths


def spatial_at(seconds):
    seconds=min(2.,max(0.,seconds));piece=min(1,int(seconds));u=seconds-piece
    points,lengths=arc_table(piece);length=lengths[-1]
    start_speed,end_speed=(0.,180.) if piece==0 else (180.,0.)
    distance=3*(1-u)**2*u*(start_speed/3)+3*(1-u)*u*u*(length-end_speed/3)+u**3*length
    index=min(len(lengths)-1,max(1,bisect.bisect_left(lengths,distance)))
    span=lengths[index]-lengths[index-1];fraction=(distance-lengths[index-1])/span if span else 0.
    return tuple(a+(b-a)*fraction for a,b in zip(points[index-1],points[index]))


def scalar_at(kind,frame):
    u=min(1.,max(0.,frame/60.))
    if kind=='linear':return 100*u
    if kind=='hold':return 0. if frame<60 else 100.
    if kind=='bezier':return 100*(3*u*u-2*u*u*u)
    raise ValueError('Unknown oracle')


def value(raw,kind):
    if not isinstance(raw,dict) or raw.get('t')!=kind or set(raw)!={'t','v'}:raise ValueError('Wrong sample value type')
    result=raw['v'];numbers=result if isinstance(result,list) else [result]
    if any(type(n) not in (float,int) or not math.isfinite(n) for n in numbers):raise ValueError('Non-finite sample')
    return result


def verify_curves(data):
    if [row['frame'] for row in data['samples']]!=list(range(-1,62)):raise ValueError('Incomplete/reordered sample set')
    scalar_error=0.;spatial_error=0.
    for row in data['samples']:
        frame=row['frame']
        for kind in ('linear','hold','bezier'):
            actual=value(row[kind],'Scalar');expected=scalar_at(kind,frame)
            scalar_error=max(scalar_error,abs(actual-expected))
            if not math.isclose(actual,expected,rel_tol=1e-5,abs_tol=1e-5):raise ValueError('Scalar oracle mismatch')
        position=value(row['position'],'Vec3')
        if len(position)!=3:raise ValueError('Spatial dimensions mismatch')
        error=math.dist(position,[*spatial_at(frame/30.),0.]);spatial_error=max(spatial_error,error)
        if error>.1:raise ValueError('Spatial oracle exceeds 0.1px')
    probes=data['join_probes']
    if [p['dt'] for p in probes]!=[-.0001,0.,.0001]:raise ValueError('Join probes missing')
    a,b,c=[value(p['position'],'Vec3') for p in probes]
    velocities=[[(y-x)/.0001 for x,y in zip(a,b)],[(y-x)/.0001 for x,y in zip(b,c)]]
    velocity_error=max(math.dist(v,[180.,0.,0.]) for v in velocities)
    velocity_jump=math.dist(*velocities)
    if velocity_error>.2 or velocity_jump>.2:raise ValueError('Nonzero passage velocity/continuity probe failed')
    for row in data['timing']:
        expected=(row['comp_frame']-10)*TICKS_PER_SECOND//30*100/row['stretch']
        if row['local_ticks']!=expected or row['inverse_comp_ticks']!=row['comp_frame']*TICKS_PER_SECOND//30:raise ValueError('Start/stretch oracle mismatch')
    for row in data['frame_ticks']:
        expected=-(-(row['frame']*TICKS_PER_SECOND*row['den'])//row['num'])
        if row['ticks']!=expected or row['roundtrip_frame']!=row['frame']:raise ValueError('Rational frame/tick mismatch')
    for name in ('linear_keys','hold_keys','bezier_keys','path_keys'):
        for key in data[name]:
            if any(key[flag] for flag in ('auto_bezier','continuous','spatial_auto','spatial_continuous','roving')):raise ValueError('Automatic flag unexpectedly enabled')
    keys=data['path_keys']
    if len(keys)!=3 or [k['time'] for k in keys]!=[0,TICKS_PER_SECOND,2*TICKS_PER_SECOND]:raise ValueError('Spatial key timing changed')
    if keys[1]['in_ease']!=[{'speed':180.,'influence':1/3}] or keys[1]['out_ease']!=keys[1]['in_ease']:raise ValueError('Passage controls changed')
    return {'scalar_max_abs_error':scalar_error,'spatial_max_error_px':spatial_error,
        'join_velocity_error_px_s':velocity_error,'join_velocity_jump_px_s':velocity_jump,
        'sample_count':len(data['samples']),'timing_cases':len(data['timing']),'frame_tick_cases':len(data['frame_ticks'])}


def raster_text_bounds(rgba,width,height,info):
    if len(rgba)!=width*height*4:raise ValueError('Incomplete RGBA frame')
    result={}
    for name,(y0,y1),position in [('point',(15,95),(40,75)),('box',(95,210),(40,100))]:
        pixels=[]
        for y in range(y0,y1):
            for x in range(20,width-20):
                index=(y*width+x)*4
                if any(rgba[index:index+3]):pixels.append((x,y))
        if not pixels:raise ValueError('Text raster absent')
        actual=[min(p[0] for p in pixels),min(p[1] for p in pixels),max(p[0] for p in pixels),max(p[1] for p in pixels)]
        bounds=info[name]['bounds'];px,py=position
        expected=[math.floor(bounds[0]+px),math.floor(bounds[1]+py),math.ceil(bounds[2]+px)-1,math.ceil(bounds[3]+py)-1]
        error=max(abs(a-b) for a,b in zip(actual,expected))
        if error>1:raise ValueError('Text geometry/raster bounds exceeds 1px')
        result[name]={'geometry_pixel_bounds':expected,'raster_pixel_bounds':actual,'max_error_px':error}
    return result
