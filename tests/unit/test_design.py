import json

import pytest
from pydantic import ValidationError

from astra_video_studio.config import Settings
from astra_video_studio.design import (
    DesignTokens, FontSelection, LayoutApply, PathData, ShapeStyleSet, StyledRange,
    TextStyleSet, animation_interval, load_tokens, store_tokens,
)
from astra_video_studio.svg import parse_path, parse_svg

TARGET = {'project_id': '1' * 32, 'composition_id': '2' * 32, 'layer_id': '3' * 32}


@pytest.mark.parametrize('cls,fields', [
    (PathData, {'vertices': [[0, 0]]}),
    (PathData, {'vertices': [[0, 0], [1, 1]], 'closed': True}),
    (PathData, {'vertices': [[0, 0], [1, 1]], 'in_tangents': [[0, 0]]}),
    (PathData, {'vertices': [[0, 0], [float('nan'), 1]]}),
    (PathData, {'vertices': [[0, 0], [30000, 1]]}),
    (StyledRange, {'start': 3, 'end': 2, 'font_size': 20}),
    (StyledRange, {'start': 0, 'end': 2}),
    (TextStyleSet, TARGET),
    (TextStyleSet, TARGET | {'fill': [2, 0, 0]}),
    (TextStyleSet, TARGET | {'ranges': [{'start': 0, 'end': 3, 'font_size': 30}, {'start': 2, 'end': 4, 'tracking': 10}]}),
    (TextStyleSet, TARGET | {'box_size': [0, 100]}),
    (ShapeStyleSet, TARGET | {'group_id': '4' * 32}),
    (DesignTokens, {'colors': {'bad key': [1, 1, 1]}}),
    (DesignTokens, {'safe_area': [0.6, 0, 0, 0]}),
    (DesignTokens, {'typography': {'title': {'font': {'postscript_name': 'ArialMT'}, 'color': 'missing'}}}),
])
def test_invalid_design_inputs(cls, fields):
    with pytest.raises(ValidationError): cls.model_validate(fields)


def test_tokens_immutable_and_integrity(tmp_path):
    settings = Settings(tmp_path)
    request = DesignTokens()
    first, second = store_tokens(settings, request), store_tokens(settings, request)
    assert first.token_id != second.token_id and first.sha256 == second.sha256
    assert load_tokens(settings, first.token_id) == request
    with open(first.path, 'a') as stream: stream.write(' ')
    with pytest.raises(ValueError, match='changed'): load_tokens(settings, first.token_id)


def test_font_design_precision_is_explicit():
    from astra_video_studio.design import size_px
    assert size_px(32.0004) == 32
    assert size_px(32.123456) == 32.12


def test_bezier_relative_and_quadratic_conversion():
    p = parse_path('M 10 20 c 10 0 20 10 30 10 q 15 15 30 0')
    assert p['vertices'] == [[10, 20], [40, 30], [70, 30]]
    assert p['out_tangents'][0] == [10, 0] and p['in_tangents'][1] == [-10, 0]
    assert p['out_tangents'][1] == [10, 10] and p['in_tangents'][2] == [-10, 10]


def test_closed_curve_shared_endpoint():
    p = parse_path('M0 0 L20 0 L20 20 C20 10 10 10 0 0 Z')
    assert p['closed'] and len(p['vertices']) == 3
    assert p['in_tangents'][0] == [10, 10]
    assert PathData.model_validate(p).closed


@pytest.mark.parametrize('path', ['M0 0 A1 1 0 0 0 20 20', 'M0 0 L', 'M0 0 L10 10 M20 20 L30 30', 'M0 0 L1 1 Z L2 2', 'L0 0 L1 1', 'M0 0 S1 1 2 2'])
def test_unsupported_path_commands(path):
    with pytest.raises(ValueError): parse_path(path)


def test_svg_native_geometry_centering_and_style():
    data = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g fill="#3cf"><path d="M0 0 L100 0 L50 100 Z"/></g></svg>'
    groups = parse_svg(data, 2)
    assert groups[0]['path']['vertices'] == [[-100, -100], [100, -100], [0, 100]]
    assert groups[0]['fill']['color'] == [0x33 / 255, 0xCC / 255, 1]
    assert groups[0]['stroke'] is None
    assert len(groups[0]['group_id']) == 32


@pytest.mark.parametrize('body', [
    '<script>alert(1)</script>', '<image href="file:///secret.png"/>',
    '<path transform="scale(2)" d="M0 0L10 10"/>',
    '<path fill="url(#a)" d="M0 0L10 10"/>',
    '<path fill-rule="evenodd" d="M0 0L10 0L0 10Z"/>',
    '<foreignObject/>', '<use href="#x"/>',
])
def test_svg_rejects_unsafe_or_unsupported_features(body):
    with pytest.raises(ValueError): parse_svg(('<svg viewBox="0 0 100 100">' + body + '</svg>').encode())


def test_svg_dtd_rejected_and_bounded():
    with pytest.raises(ValueError, match='DTD'):
        parse_svg(b'<!DOCTYPE svg [<!ENTITY x "abc">]><svg viewBox="0 0 1 1"/>')
    with pytest.raises(ValueError): parse_svg(b'<svg viewBox="0 0 0 0"/>')


@pytest.mark.parametrize('body', [
    '<svg viewBox="0 0 2 2" width="100"><path d="M0 0L1 1"/></svg>',
    '<title><script>hidden</script></title><path d="M0 0L1 1"/>',
])
def test_svg_rejects_nested_viewports_and_nonplain_metadata(body):
    with pytest.raises(ValueError): parse_svg(('<svg viewBox="0 0 10 10">' + body + '</svg>').encode())


def test_layout_duplicate_bindings_rejected():
    with pytest.raises(ValidationError):
        LayoutApply(project_id='1' * 32, composition_id='2' * 32, token_id='3' * 32, profile='portrait', bindings=[{'layer_id': '4' * 32}, {'layer_id': '4' * 32}])


def test_animation_interval_quantizes_and_guards():
    from astra_video_studio.design import TextAnimatorApply
    r = TextAnimatorApply(**TARGET, start_time=0.26, duration=0.8)
    assert animation_interval(r, {'fps': 24, 'duration': 3}, {'in_point': 0, 'out_point': 3}) == [6 / 24, 25 / 24]
    with pytest.raises(ValueError): animation_interval(r, {'fps': 24, 'duration': 0.5}, {'in_point': 0, 'out_point': 0.5})


@pytest.mark.parametrize('data', [
    '<!DOCTYPE svg [<!ENTITY x "a">]><svg viewBox="0 0 10 10"/>'.encode('utf-16'),
    '<svg viewBox="0 0 10 10"/>'.encode('utf-16-le'),
    b'<svg viewBox="0 0 10 10"><broken>',
    b'<svg viewBox="0 0 10 10"><x:path xmlns:x="http://example.org" d="M0 0L1 1"/></svg>',
])
def test_svg_encoding_xml_and_namespace_boundaries(data):
    with pytest.raises(ValueError): parse_svg(data)


def test_unicode_ranges_compile_to_utf16_without_mutation(tmp_path):
    import copy
    from astra_video_studio.design import prepare_design
    layer = {'layer_id': 'astra:layer:' + TARGET['layer_id'], 'locked': False, 'editable_2d': True,
             'text': 'A😀ção', 'text_document_animated': False, 'text_style': {'box_text': False, 'styles_truncated': False},
             'transforms': {'anchor': {'keys': []}}, 'animation_summary': {'expressions': 0}}
    before = {'project_dirty': False, 'compositions': [{'composition_id': 'astra:composition:' + TARGET['composition_id'], 'layers': [layer]}]}
    original = copy.deepcopy(before)
    request = TextStyleSet(**TARGET, ranges=[{'start': 1, 'end': 2, 'font_size': 40}])
    ctx = prepare_design(Settings(tmp_path), 'text_style_set', request, before)
    assert ctx['native_ranges'][0]['start'] == 1 and ctx['native_ranges'][0]['end'] == 3
    assert before == original
    with pytest.raises(ValueError, match='exceeds'):
        prepare_design(Settings(tmp_path), 'text_style_set', TextStyleSet(**TARGET, ranges=[{'start': 0, 'end': 100, 'tracking': 1}]), before)


@pytest.mark.parametrize('change_source', [False, True])
def test_vector_copy_matches_the_bytes_that_were_parsed(tmp_path, monkeypatch, change_source):
    from astra_video_studio.design import VectorImport, prepare_design
    from astra_video_studio import svg
    source = tmp_path / 'logo.svg'
    original = b'<svg viewBox="0 0 10 10"><path d="M0 0L10 0L5 10Z"/></svg>'
    source.write_bytes(original)
    layer = {'layer_id': 'astra:layer:' + TARGET['layer_id'], 'locked': False, 'editable_2d': True, 'is_shape': True, 'animation_summary': {'expressions': 0}}
    before = {'project_dirty': False, 'compositions': [{'composition_id': 'astra:composition:' + TARGET['composition_id'], 'layers': [layer]}]}
    parser = svg.parse_svg
    def concurrent_change(data, scale):
        parsed = parser(data, scale)
        source.write_bytes(original.replace(b'L5 10', b'L5 5'))
        return parsed
    if change_source:
        monkeypatch.setattr(svg, 'parse_svg', concurrent_change)
        with pytest.raises(ValueError, match='changed during copy'):
            prepare_design(Settings(tmp_path), 'vector_import', VectorImport(**TARGET, source_path=str(source)), before)
    else:
        import hashlib
        context = prepare_design(Settings(tmp_path), 'vector_import', VectorImport(**TARGET, source_path=str(source)), before)
        assert context['vector_asset']['source_sha256'] == hashlib.sha256(original).hexdigest()
        assert context['groups'][0]['path']['vertices'] == [[-5, -5], [5, -5], [0, 5]]
    copied = list((tmp_path / 'assets').glob('*/source.svg'))
    assert len(copied) == 1 and copied[0].read_bytes() == original
