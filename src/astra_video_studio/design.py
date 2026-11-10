"""Typed editable typography/vector design, immutable tokens and responsive layouts."""
import copy
import hashlib
import json
import math
import shutil
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from astra_video_studio.config import Settings
from astra_video_studio.existing_projects import digest
from astra_video_studio.jobs import write_json
from astra_video_studio.motion_engine.schemas import StrictModel, Target
from astra_video_studio.motion_engine.timeline import frame
from astra_video_studio.project_manager import ProjectManager, valid_id
from astra_video_studio.scene_editing import ID, Name, CompositionTarget, editable, equivalent, find_comp, find_layer

RGB = tuple[float, float, float]
Point = tuple[float, float]


def rgb(value):
    if value is not None and any(not 0 <= c <= 1 for c in value):
        raise ValueError('RGB components must be in [0,1]')


def size_px(value):
    """Explicit stable design precision, avoiding AE's subpixel change threshold."""
    return math.floor(value * 100 + 0.5) / 100


class FontSelection(StrictModel):
    postscript_name: str = Field(min_length=1, max_length=160)
    font_id: int | None = Field(default=None, gt=0)


class FontsQuery(StrictModel):
    query: str = Field(default='', max_length=100)
    limit: int = Field(default=200, ge=1, le=1000)


class CharacterStyle(StrictModel):
    font: FontSelection | None = None
    font_size: float | None = Field(default=None, ge=8, le=500)
    tracking: int | None = Field(default=None, ge=-100, le=500)
    fill: RGB | None = None

    @model_validator(mode='after')
    def color(self):
        rgb(self.fill)
        return self


class StyledRange(CharacterStyle):
    start: int = Field(ge=0, le=499)
    end: int = Field(gt=0, le=500)

    @model_validator(mode='after')
    def interval(self):
        if self.end <= self.start:
            raise ValueError('Character range is empty')
        if not any(getattr(self, k) is not None for k in ('font', 'font_size', 'tracking', 'fill')):
            raise ValueError('Character range has no style changes')
        return self


class TextStyleSet(Target, CharacterStyle):
    leading: float | None = Field(default=None, ge=1, le=1000)
    alignment: Literal['left', 'center', 'right'] | None = None
    box_size: Point | None = None
    ranges: list[StyledRange] = Field(default_factory=list, max_length=30)
    recenter_anchor: bool = True
    overflow_policy: Literal['reject', 'report'] = 'reject'

    @model_validator(mode='after')
    def changes(self):
        if not self.ranges and not any(getattr(self, k) is not None for k in ('font', 'font_size', 'tracking', 'fill', 'leading', 'alignment', 'box_size')):
            raise ValueError('No text style changes')
        if self.box_size and any(not 1 <= v <= 7680 for v in self.box_size):
            raise ValueError('Invalid text box dimensions')
        intervals = sorted((r.start, r.end) for r in self.ranges)
        if any(b > c for (_, b), (c, _) in zip(intervals, intervals[1:])):
            raise ValueError('Overlapping character style ranges')
        return self


class TextAnimatorApply(Target):
    based_on: Literal['characters', 'words'] = 'words'
    position: Point = (0, 35)
    scale: float = Field(default=100, ge=1, le=400)
    opacity: float = Field(default=0, ge=0, le=100)
    start_time: float = Field(default=0, ge=0, le=300)
    duration: float = Field(default=1, gt=0, le=15)

    @model_validator(mode='after')
    def bounds(self):
        if any(abs(v) > 2000 for v in self.position):
            raise ValueError('Text animator position exceeds limits')
        return self


class PathData(StrictModel):
    vertices: list[Point] = Field(min_length=2, max_length=256)
    in_tangents: list[Point] | None = None
    out_tangents: list[Point] | None = None
    closed: bool = False

    @model_validator(mode='after')
    def geometry(self):
        if self.closed and len(self.vertices) < 3:
            raise ValueError('Closed path needs at least three vertices')
        for field in ('in_tangents', 'out_tangents'):
            values = getattr(self, field)
            if values is None:
                setattr(self, field, [(0, 0)] * len(self.vertices))
            elif len(values) != len(self.vertices):
                raise ValueError('Path tangent counts must match vertices')
        if any(abs(v) > 20000 for points in (self.vertices, self.in_tangents, self.out_tangents) for point in points for v in point):
            raise ValueError('Path coordinates exceed bounds')
        return self


class GroupTarget(Target):
    group_id: ID


class ShapePathSet(Target):
    path: PathData
    group_id: ID | None = None
    name: Name = 'Path'


class ShapeStyleSet(GroupTarget):
    fill: RGB | None = None
    fill_enabled: bool | None = None
    fill_opacity: float | None = Field(default=None, ge=0, le=100)
    stroke: RGB | None = None
    stroke_enabled: bool | None = None
    stroke_width: float | None = Field(default=None, gt=0, le=200)
    stroke_opacity: float | None = Field(default=None, ge=0, le=100)
    gradient: tuple[RGB, RGB] | None = None

    @model_validator(mode='after')
    def changes(self):
        rgb(self.fill)
        rgb(self.stroke)
        if self.gradient:
            for color in self.gradient: rgb(color)
        if not any(value is not None for key, value in self.model_dump().items() if key not in ('project_id', 'composition_id', 'layer_id', 'group_id')):
            raise ValueError('No shape style changes')
        return self


class ShapeTrimApply(GroupTarget):
    start_time: float = Field(default=0, ge=0, le=300)
    duration: float = Field(default=1, gt=0, le=15)
    start_percent: float = Field(default=0, ge=0, le=100)
    end_percent: float = Field(default=100, ge=0, le=100)
    offset: float = Field(default=0, ge=-360, le=360)


class ShapeMorphApply(GroupTarget):
    end_path: PathData
    start_time: float = Field(default=0, ge=0, le=300)
    duration: float = Field(default=1, gt=0, le=15)


class VectorImport(Target):
    source_path: str = Field(min_length=1, max_length=32767)
    scale: float = Field(default=1, ge=0.01, le=100)


class TypeToken(StrictModel):
    font: FontSelection
    size_ratio: float = Field(default=0.06, ge=0.008, le=0.3)
    tracking: int = Field(default=0, ge=-100, le=500)
    color: str = Field(default='foreground', pattern=r'^[a-z][a-z0-9_]{0,39}$')


class DesignTokens(StrictModel):
    name: Name = 'Brand'
    colors: dict[str, RGB] = Field(default_factory=lambda: {'foreground': (0.95, 0.97, 1), 'accent': (0.3, 0.85, 1)}, min_length=1, max_length=20)
    typography: dict[str, TypeToken] = Field(default_factory=dict, max_length=10)
    spacing_ratio: float = Field(default=0.025, ge=0, le=0.2)
    safe_area: tuple[float, float, float, float] = (0.08, 0.08, 0.08, 0.08)

    @model_validator(mode='after')
    def tokens(self):
        import re
        for key in (*self.colors, *self.typography):
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', key):
                raise ValueError('Invalid token name')
        for color in self.colors.values(): rgb(color)
        if any(not 0 <= v <= 0.4 for v in self.safe_area):
            raise ValueError('Safe area fractions must be in [0,0.4]')
        if any(t.color not in self.colors for t in self.typography.values()):
            raise ValueError('Typography refers to unknown color')
        return self


class TokenRecord(StrictModel):
    token_id: ID
    sha256: str
    path: str
    tokens: DesignTokens


def store_tokens(settings, request):
    directory = settings.contained_path('design-tokens/' + uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / 'tokens.json'
    write_json(path, request.model_dump())
    result = TokenRecord(token_id=directory.name, sha256=digest(path), path=str(path), tokens=request)
    write_json(directory / 'record.json', result.model_dump())
    return result


def load_tokens(settings, identifier):
    directory = settings.contained_path('design-tokens/' + valid_id(identifier))
    record = TokenRecord.model_validate(json.loads((directory / 'record.json').read_text(encoding='utf-8')))
    if digest(directory / 'tokens.json') != record.sha256:
        raise ValueError('Design tokens changed; store a new immutable token set')
    tokens = DesignTokens.model_validate(json.loads((directory / 'tokens.json').read_text(encoding='utf-8')))
    if tokens != record.tokens:
        raise ValueError('Token record mismatch')
    return tokens


class LayoutBinding(StrictModel):
    layer_id: ID
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)
    max_width: float = Field(default=0.8, gt=0, le=1)
    max_height: float = Field(default=0.2, gt=0, le=1)
    role: Literal['content', 'background'] = 'content'
    typography_token: str | None = Field(default=None, max_length=40)


class LayoutApply(CompositionTarget):
    token_id: ID
    profile: Literal['landscape', 'square', 'portrait']
    bindings: list[LayoutBinding] = Field(min_length=1, max_length=20)
    arrangement: Literal['bindings', 'align_left', 'align_center', 'align_right', 'distribute_horizontal', 'distribute_vertical'] = 'bindings'

    @model_validator(mode='after')
    def unique(self):
        if len({b.layer_id for b in self.bindings}) != len(self.bindings):
            raise ValueError('Duplicate layout layer')
        return self


PROFILES = {'landscape': (1920, 1080), 'square': (1080, 1080), 'portrait': (1080, 1920)}
DESIGN_REQUESTS = {'text_style_set': TextStyleSet, 'text_animator_apply': TextAnimatorApply,
                   'shape_path_set': ShapePathSet, 'shape_style_set': ShapeStyleSet,
                   'shape_trim_apply': ShapeTrimApply, 'shape_morph_apply': ShapeMorphApply,
                   'vector_import': VectorImport, 'layout_apply': LayoutApply}


def managed_group(layer, identifier):
    matches = [g for g in layer['shape_groups'] if g['group_id'] == identifier]
    if len(matches) != 1 or len(matches[0]['paths']) != 1:
        raise ValueError('Managed group with exactly one path required')
    return matches[0]


def animation_interval(request, comp, layer):
    a, b = frame(request.start_time, comp['fps']) / comp['fps'], frame(request.start_time + request.duration, comp['fps']) / comp['fps']
    if b <= a or a < layer['in_point'] - 1e-6 or b > min(comp['duration'], layer['out_point']) + 1e-6:
        raise ValueError('Animation outside layer lifetime or collapsed to one frame')
    return [a, b]


def linear_keys(times, values, field='value'):
    return [{'time': time, field: value, 'in_type': 'linear', 'out_type': 'linear'} for time, value in zip(times, values, strict=True)]


def prepare_design(settings, action, request, before):
    comp = find_comp(before, request.composition_id)
    if before['project_dirty'] or any(l['animation_summary']['expressions'] for c in before['compositions'] for l in c['layers']):
        raise ValueError('Preserve unsaved edits; stored expressions are protected')
    context = {}
    if action == 'layout_apply':
        tokens = load_tokens(settings, request.token_id)
        width, height = PROFILES[request.profile]
        if set(b.layer_id for b in request.bindings) != {l['layer_id'].split(':')[-1] for l in comp['layers'] if l['enabled'] and not l['is_null']}:
            raise ValueError('Bind every enabled visual layer, and no disabled/null layer, when resizing layout')
        for binding in request.bindings:
            layer = find_layer(comp, binding.layer_id)
            editable(layer)
            if layer['parent_ae_id'] is not None or not layer['auto_orient_none']:
                raise ValueError('Layout requires unparented layers without auto orientation')
            for name in ('position', 'anchor', 'scale', 'rotation'):
                track = layer['transforms'][name]
                if track['keys'] or track['expression_enabled'] or track['separated']:
                    raise ValueError('Layout cannot replace animated/separated transforms')
            if abs(layer['transforms']['rotation']['value']) > 1e-6:
                raise ValueError('Layout requires zero layer rotation')
            if binding.typography_token and (binding.typography_token not in tokens.typography or layer['text'] is None):
                raise ValueError('Unknown typography token or non-text binding')
        context.update(tokens=tokens.model_dump(mode='json'), width=width, height=height)
        return context
    layer = find_layer(comp, request.layer_id)
    editable(layer)
    if action.startswith('text_'):
        if layer['text'] is None or layer['text_document_animated']:
            raise ValueError('Static text document required')
        if layer['text_style']['styles_truncated']:
            raise ValueError('Text design is limited to 500 Unicode code points')
        if action == 'text_style_set':
            if request.box_size and not layer['text_style']['box_text']:
                raise ValueError('box_size requires an existing box text layer; create it with LayerSpec.text_box')
            if request.recenter_anchor and layer['transforms']['anchor']['keys']:
                raise ValueError('Cannot replace an animated anchor')
            text = layer['text']
            for item in request.ranges:
                if item.end > len(text):
                    raise ValueError('Character style range exceeds text length (Unicode code points)')
            context['native_ranges'] = [item.model_dump() | {'start': len(text[:item.start].encode('utf-16-le')) // 2, 'end': len(text[:item.end].encode('utf-16-le')) // 2} for item in request.ranges]
        else:
            context.update(times=animation_interval(request, comp, layer), animator_id=uuid4().hex)
        return context
    if not layer['is_shape']:
        raise ValueError('Shape layer required')
    if action == 'vector_import':
        from astra_video_studio.svg import parse_svg
        source = settings.read_path(request.source_path, {'.svg'})
        if source.stat().st_size > 2_000_000:
            raise ValueError('SVG exceeds 2 MB')
        with source.open('rb') as stream:
            original_bytes = stream.read(2_000_001)
        if len(original_bytes) > 2_000_000:
            raise ValueError('SVG exceeds 2 MB')
        original_hash = hashlib.sha256(original_bytes).hexdigest()
        groups = parse_svg(original_bytes, request.scale)
        directory = settings.contained_path('assets/' + uuid4().hex)
        directory.mkdir(parents=True, exist_ok=False)
        target = directory / 'source.svg'
        target.write_bytes(original_bytes)
        if digest(source) != original_hash or digest(target) != original_hash:
            raise ValueError('SVG changed during copy')
        context.update(groups=groups, vector_asset={'path': str(target), 'source_path': str(source), 'source_sha256': digest(target), 'editable_native_paths': True, 'format': 'svg_subset'})
    elif action == 'shape_path_set':
        context['group_id'] = request.group_id or uuid4().hex
        if request.group_id and managed_group(layer, request.group_id)['paths'][0]['keys']:
            raise ValueError('Existing path animation is protected')
    else:
        group = managed_group(layer, request.group_id)
        if action == 'shape_style_set':
            if request.gradient is not None:
                raise ValueError('Native gradient color editing is not exposed by this bridge; use solid fills. No raster fallback.')
            if group['style_animated']:
                raise ValueError('Animated shape styles are protected')
        elif action == 'shape_trim_apply':
            if group['trim'] is not None:
                raise ValueError('Existing Trim Paths operator is protected')
            context['times'] = animation_interval(request, comp, layer)
        else:
            original = group['paths'][0]
            if original['keys'] or original['kind'] != 'path':
                raise ValueError('Morph requires a static native Bezier path')
            if len(original['geometry']['vertices']) != len(request.end_path.vertices) or original['geometry']['closed'] != request.end_path.closed:
                raise ValueError('Morph paths must have matching vertex count/order and closure')
            context.update(times=animation_interval(request, comp, layer), start_path=original['geometry'])
    return context


def expanded_styles(text_style, length):
    styles = [None] * length
    for run in text_style['style_runs']:
        for index in range(run['start'], run['end']): styles[index] = copy.deepcopy(run['style'])
    if any(s is None for s in styles):
        raise ValueError('Incomplete character style inspection')
    return styles


def apply_character_style(styles, request, start=0, end=None):
    for style in styles[start:end]:
        for key in ('font_size', 'tracking'):
            value = getattr(request, key)
            if value is not None: style[key] = size_px(value) if key == 'font_size' else value
        if request.font is not None: style['font'] = request.font.postscript_name
        if request.fill is not None: style['fill'] = list(request.fill)


def verify_text_style(old, new, request):
    expected = expanded_styles(old['text_style'], len(old['text']))
    apply_character_style(expected, request)
    for item in request.ranges: apply_character_style(expected, item, item.start, item.end)
    equivalent(expanded_styles(new['text_style'], len(new['text'])), expected, 'character styles')
    for key in ('font', 'font_size', 'tracking', 'fill'):
        equivalent(new['text_style'][key], expected[0][key], 'first character ' + key)
    metadata = {key: copy.deepcopy(old['text_style'][key]) for key in ('leading', 'auto_leading', 'alignment', 'box_size', 'box_text', 'all_caps', 'styles_truncated')}
    if request.leading is not None: metadata.update(leading=request.leading, auto_leading=False)
    if request.alignment is not None: metadata['alignment'] = request.alignment
    if request.box_size is not None: metadata['box_size'] = list(request.box_size)
    for key, value in metadata.items(): equivalent(new['text_style'][key], value, 'text metadata ' + key)
    for field, requested in (('leading', request.leading), ('alignment', request.alignment), ('box_size', list(request.box_size) if request.box_size else None)):
        if requested is not None: equivalent(new['text_style'][field], requested, field)
    if request.leading is not None and new['text_style']['auto_leading']:
        raise ValueError('Explicit leading was not applied')
    if new['text_style']['font_missing']:
        raise ValueError('AE substituted a requested font')
    if new['text_style']['box_overflow'] and request.overflow_policy == 'reject':
        raise ValueError('Text box overflows; enlarge box or reduce typography')


def verify_design(action, request, before, after, ctx):
    normalized = copy.deepcopy(after)
    old_comp = find_comp(before, request.composition_id)
    new_comp = find_comp(normalized, request.composition_id)
    if action == 'layout_apply':
        verify_layout(request, old_comp, new_comp, ctx)
        new_comp['width'], new_comp['height'] = old_comp['width'], old_comp['height']
        for binding in request.bindings:
            old, new = find_layer(old_comp, binding.layer_id), find_layer(new_comp, binding.layer_id)
            for field in ('position', 'anchor', 'transforms', 'bounds', 'visual_bounds', 'layout_bounds', 'text_style'):
                new[field] = copy.deepcopy(old[field])
    else:
        old, new = find_layer(old_comp, request.layer_id), find_layer(new_comp, request.layer_id)
        added_keys = 0
        if action == 'text_style_set':
            verify_text_style(old, new, request)
            new['text_style'] = copy.deepcopy(old['text_style'])
            if request.recenter_anchor:
                rect = new['layout_bounds']
                equivalent(new['anchor'][:2], [rect['left'] + rect['width'] / 2, rect['top'] + rect['height'] / 2], 'text anchor')
                new['anchor'] = copy.deepcopy(old['anchor'])
                new['transforms']['anchor'] = copy.deepcopy(old['transforms']['anchor'])
        elif action == 'text_animator_apply':
            if len(new['text_animators']) != len(old['text_animators']) + 1:
                raise ValueError('Animator was not appended')
            equivalent(new['text_animators'][:-1], old['text_animators'])
            animator = new['text_animators'][-1]
            if animator['animator_id'] != ctx['animator_id']:
                raise ValueError('Animator identity mismatch')
            equivalent(animator['position'], [*request.position, 0])
            equivalent(animator['scale'], [request.scale, request.scale, 100])
            equivalent(animator['opacity'], request.opacity)
            equivalent(animator['based_on'], 3 if request.based_on == 'words' else 1)
            equivalent(animator['start_keys'], linear_keys(ctx['times'], [0, 100]))
            new['text_animators'] = copy.deepcopy(old['text_animators'])
            added_keys = 2
        else:
            expected = copy.deepcopy(old['shape_groups'])
            if action in ('shape_path_set', 'vector_import'):
                additions = ctx['groups'] if action == 'vector_import' else [{'group_id': ctx['group_id'], 'path': request.path.model_dump(mode='json'), 'name': request.name}]
                for addition in additions:
                    actual = managed_group(new, addition['group_id'])
                    equivalent(actual['paths'][0]['geometry'], addition['path'], 'native path')
                    if action == 'shape_path_set' and request.group_id:
                        previous = managed_group({'shape_groups': expected}, request.group_id)
                        previous['paths'][0]['geometry'] = addition['path']
                    else:
                        if actual['paths'][0]['keys'] or actual['trim'] is not None:
                            raise ValueError('New vector is unexpectedly animated')
                        if action == 'vector_import':
                            verify_vector_style(actual, addition)
                        expected.append(copy.deepcopy(actual))
            else:
                group = managed_group({'shape_groups': expected}, request.group_id)
                actual = managed_group(new, request.group_id)
                if action == 'shape_style_set':
                    for field, color, enabled, opacity, width in (
                        ('fill', request.fill, request.fill_enabled, request.fill_opacity, None),
                        ('stroke', request.stroke, request.stroke_enabled, request.stroke_opacity, request.stroke_width),
                    ):
                        if all(v is None for v in (color, enabled, opacity, width)): continue
                        style = group[field] or ({'enabled': True, 'color': [1, 1, 1], 'opacity': 100} | ({'width': 1, 'cap': 1, 'join': 1} if field == 'stroke' else {}))
                        if color is not None: style['color'] = list(color)
                        if enabled is not None: style['enabled'] = enabled
                        if opacity is not None: style['opacity'] = opacity
                        if width is not None: style['width'] = width
                        group[field] = style
                elif action == 'shape_trim_apply':
                    group['trim'] = {'start': request.start_percent, 'end': request.start_percent, 'offset': request.offset,
                                     'end_keys': linear_keys(ctx['times'], [request.start_percent, request.end_percent])}
                    added_keys = 2
                else:
                    group['paths'][0]['keys'] = linear_keys(ctx['times'], [ctx['start_path'], request.end_path.model_dump(mode='json')], 'geometry')
                    added_keys = 2
            equivalent(new['shape_groups'], expected, 'shape groups')
            new['shape_groups'] = copy.deepcopy(old['shape_groups'])
        summary = dict(old['animation_summary'])
        summary['key_count'] += added_keys
        equivalent(new['animation_summary'], summary)
        new['animation_summary'] = copy.deepcopy(old['animation_summary'])
        # Bounds are derived from the edited content; all other retained fields are compared.
        for field in ('bounds', 'visual_bounds', 'layout_bounds'):
            new[field] = copy.deepcopy(old[field])
    equivalent(normalized['compositions'], before['compositions'])
    equivalent(normalized['footage'], before['footage'])


def verify_vector_style(group, addition):
    for kind in ('fill', 'stroke'):
        equivalent(group[kind], addition[kind], 'SVG ' + kind)


def verify_layout(request, old_comp, new_comp, ctx):
    width, height = ctx['width'], ctx['height']
    equivalent([new_comp['width'], new_comp['height']], [width, height])
    left, top, right, bottom = ctx['tokens']['safe_area']
    safe = [left * width, top * height, (1 - right) * width, (1 - bottom) * height]
    rects = []
    for binding in request.bindings:
        old, new = find_layer(old_comp, binding.layer_id), find_layer(new_comp, binding.layer_id)
        for key in ('position', 'anchor', 'scale'):
            if new['transforms'][key]['keys'] or new['transforms'][key]['expression_enabled']:
                raise ValueError('Layout introduced animation')
        bounds = new['layout_bounds']
        anchor, pos, scale = new['anchor'], new['position'], new['transforms']['scale']['value']
        equivalent(scale[0], scale[1], 'uniform layout scale')
        equivalent(anchor[:2], [bounds['left'] + bounds['width'] / 2, bounds['top'] + bounds['height'] / 2])
        if scale[0] <= 0: raise ValueError('Nonpositive layout scale')
        w, h = bounds['width'] * scale[0] / 100, bounds['height'] * scale[1] / 100
        rect = [pos[0] - w / 2, pos[1] - h / 2, pos[0] + w / 2, pos[1] + h / 2]
        if binding.role == 'background':
            if w + 0.1 < width or h + 0.1 < height: raise ValueError('Background does not cover composition')
            equivalent(pos[:2], [width / 2, height / 2])
        else:
            if any(a < b - 0.1 for a, b in zip(rect[:2], safe[:2])) or any(a > b + 0.1 for a, b in zip(rect[2:], safe[2:])):
                raise ValueError('Content outside safe area')
            if w > binding.max_width * width + 0.1 or h > binding.max_height * height + 0.1:
                raise ValueError('Content exceeds binding bounds')
            if request.arrangement == 'bindings':
                equivalent(pos[:2], [binding.x * width, binding.y * height])
            rects.append(rect)
        if new['text'] is not None:
            if new['text_style']['box_overflow'] or new['text_style']['font_missing']:
                raise ValueError('Layout has overflowing text or missing font')
            for key in ('leading', 'auto_leading', 'alignment', 'all_caps', 'box_text', 'styles_truncated'):
                equivalent(new['text_style'][key], old['text_style'][key], 'layout text ' + key)
            if binding.typography_token:
                token = ctx['tokens']['typography'][binding.typography_token]
                change = CharacterStyle(font=FontSelection.model_validate(token['font']), font_size=min(width, height) * token['size_ratio'], tracking=token['tracking'], fill=ctx['tokens']['colors'][token['color']])
                expected = expanded_styles(old['text_style'], len(old['text']))
                apply_character_style(expected, change)
                equivalent(expanded_styles(new['text_style'], len(new['text'])), expected)
            else:
                equivalent(new['text_style']['style_runs'], old['text_style']['style_runs'])
    if request.arrangement.startswith('align_'):
        index = {'align_left': 0, 'align_center': None, 'align_right': 2}[request.arrangement]
        for rect in rects:
            value = (rect[0] + rect[2]) / 2 if index is None else rect[index]
            target = (safe[0] + safe[2]) / 2 if index is None else safe[index]
            equivalent(value, target)
    if request.arrangement.startswith('distribute_') and len(rects) > 1:
        axis = 0 if request.arrangement == 'distribute_horizontal' else 1
        gaps = [b[axis] - a[axis + 2] for a, b in zip(rects, rects[1:])]
        for gap in gaps:
            if gap < ctx['tokens']['spacing_ratio'] * min(width, height) - 0.1: raise ValueError('Insufficient distribution spacing')
            equivalent(gap, gaps[0])


class DesignService:
    def __init__(self, settings):
        self.settings, self.projects = settings, ProjectManager(settings)

    def fonts(self, request):
        return self.projects.runner.run('design_fonts', {'query': request.model_dump()})

    def apply(self, action, request):
        if action not in DESIGN_REQUESTS or not isinstance(request, DESIGN_REQUESTS[action]):
            raise ValueError('Unknown design operation')
        manifest, source = self.projects.load(request.project_id)
        saved = json.loads((source.parent / 'version.json').read_text()) if manifest.get('current_version') else manifest
        source_hash = digest(source)
        if source_hash != saved.get('sha256'): raise ValueError('Source changed outside Astra')
        inspection = self.projects.inspect(request.project_id)
        if inspection.status != 'succeeded': return inspection
        ctx = prepare_design(self.settings, action, request, inspection.data)
        identifier = uuid4().hex
        directory = self.settings.contained_path(f'projects/{request.project_id}/versions/{identifier}')
        directory.mkdir(parents=True, exist_ok=False)
        output, snapshot = directory / 'project.aep', directory / 'source-snapshot.aep'
        shutil.copyfile(source, snapshot)
        if digest(snapshot) != source_hash: raise ValueError('Snapshot mismatch')
        version = {'version_id': identifier, 'status': 'prepared', 'source': str(source), 'snapshot': str(snapshot), 'source_sha256': source_hash, 'action': action, 'request': request.model_dump()}
        write_json(directory / 'version.json', version)
        result = self.projects.runner.run('design_edit', {'project_path': source.as_posix(), 'version_path': output.as_posix(), 'id_map': manifest.get('id_map'), 'design_action': action, 'request': request.model_dump(), 'context': ctx, 'expected_state': inspection.data})
        result.project_id, result.project_path = request.project_id, str(output)
        if result.status == 'succeeded':
            try:
                if digest(source) != source_hash or not output.is_file(): raise ValueError('Source/output mismatch')
                verify_design(action, request, inspection.data, result.data, ctx)
                if 'vector_asset' in ctx:
                    asset = ctx['vector_asset']
                    from pathlib import Path
                    if digest(Path(asset['path'])) != asset['source_sha256'] or digest(Path(asset['source_path'])) != asset['source_sha256']:
                        raise ValueError('SVG source/copy changed after import')
                version['sha256'] = digest(output)
                manifest['current_version'] = identifier
                result.data.update(version_id=identifier, created_group_id=ctx.get('group_id') if action == 'shape_path_set' and request.group_id is None else None)
                if 'vector_asset' in ctx:
                    result.data['vector_asset'] = ctx['vector_asset']
                    result.artifacts.append(ctx['vector_asset']['path'])
                result.artifacts.extend([str(output), str(snapshot)])
            except (OSError, ValueError, KeyError, TypeError) as error:
                result.status, result.error = 'failed', 'Design verification failed: ' + str(error)
        version.update(status=result.status, operation_id=result.operation_id, result=result.model_dump())
        write_json(directory / 'version.json', version)
        if result.status == 'succeeded': write_json(self.settings.contained_path(f'projects/{request.project_id}/project.json'), manifest)
        self.projects._finalize_job(result)
        return result
