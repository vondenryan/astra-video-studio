"""Strict local SVG subset → native Bezier paths; no browser/raster fallback."""
import math
import re
from uuid import uuid4
import xml.etree.ElementTree as ET

NUMBER = r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'


def numbers(value):
    if re.sub(NUMBER, '', value).strip(' ,\t\r\n'):
        raise ValueError('Unsupported SVG numeric syntax/units')
    result = [float(x) for x in re.findall(NUMBER, value)]
    if any(not math.isfinite(v) or abs(v) > 1_000_000 for v in result):
        raise ValueError('SVG numeric limit exceeded')
    return result


def color(value):
    value = value.strip().lower()
    if value == 'none': return None
    if value == 'white': return [1, 1, 1]
    if value == 'black': return [0, 0, 0]
    if re.fullmatch(r'#[0-9a-f]{3}', value): value = '#' + ''.join(c * 2 for c in value[1:])
    if not re.fullmatch(r'#[0-9a-f]{6}', value):
        raise ValueError('SVG supports only hex/black/white/none solid colors')
    return [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def parse_path(value):
    tokens = re.findall(r'[a-zA-Z]|' + NUMBER, value)
    if re.sub(r'[a-zA-Z]|' + NUMBER, '', value).strip(' ,\t\r\n'):
        raise ValueError('Invalid SVG path syntax')
    if len(tokens) > 5000: raise ValueError('SVG path token limit exceeded')
    vertices, incoming, outgoing, closed = [], [], [], False
    index, command = 0, None
    current = [0.0, 0.0]
    def add(point, a=(0, 0), b=(0, 0)):
        vertices.append(point); incoming.append(list(a)); outgoing.append(list(b))
        if len(vertices) > 256: raise ValueError('SVG path vertex limit exceeded')
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]; index += 1
        if command is None or command.upper() not in ('M', 'L', 'H', 'V', 'C', 'Q', 'Z'):
            raise ValueError('SVG path supports M/L/H/V/C/Q/Z only; arcs and shorthand curves are not supported')
        upper, relative = command.upper(), command.islower()
        if closed: raise ValueError('Compound SVG subpaths are not supported')
        if upper == 'Z':
            if not vertices: raise ValueError('SVG path closes before move')
            closed = True
            if vertices[-1] == vertices[0] and len(vertices) > 1:
                incoming[0] = incoming[-1]; vertices.pop(); incoming.pop(); outgoing.pop()
            current = vertices[0]
            command = None
            continue
        count = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'Q': 4}[upper]
        if index + count > len(tokens) or any(re.fullmatch(NUMBER, t) is None for t in tokens[index:index + count]):
            raise ValueError('Incomplete SVG path command')
        data = [float(t) for t in tokens[index:index + count]]; index += count
        if any(not math.isfinite(v) or abs(v) > 1_000_000 for v in data): raise ValueError('SVG coordinate limit exceeded')
        def point(x, y): return [x + (current[0] if relative else 0), y + (current[1] if relative else 0)]
        if upper == 'M':
            if vertices: raise ValueError('Compound SVG subpaths are not supported')
            current = point(*data); add(current)
            command = 'l' if relative else 'L'
        elif not vertices:
            raise ValueError('SVG path must start with M')
        elif upper in ('L', 'H', 'V'):
            if upper == 'L': current = point(*data)
            elif upper == 'H': current = [data[0] + (current[0] if relative else 0), current[1]]
            else: current = [current[0], data[0] + (current[1] if relative else 0)]
            add(current)
        else:
            control = point(data[0], data[1])
            if upper == 'C':
                second, end = point(data[2], data[3]), point(data[4], data[5])
            else:
                end = point(data[2], data[3])
                second = [end[i] + (control[i] - end[i]) * 2 / 3 for i in (0, 1)]
                control = [current[i] + (control[i] - current[i]) * 2 / 3 for i in (0, 1)]
            outgoing[-1] = [control[i] - current[i] for i in (0, 1)]
            add(end, [second[i] - end[i] for i in (0, 1)])
            current = end
    if len(vertices) < (3 if closed else 2): raise ValueError('SVG path has too few vertices')
    return {'vertices': vertices, 'in_tangents': incoming, 'out_tangents': outgoing, 'closed': closed}


def parse_svg(data: bytes, scale=1):
    try:
        decoded = data.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('SVG must be UTF-8') from error
    if len(data) > 2_000_000 or '\x00' in decoded or re.search(r'<!\s*(DOCTYPE|ENTITY)', decoded, re.I):
        raise ValueError('SVG size/DTD/entity limit exceeded')
    try:
        root = ET.fromstring(decoded)
    except ET.ParseError as error:
        raise ValueError('Malformed SVG XML') from error
    if root.tag.split('}')[-1] != 'svg': raise ValueError('SVG root required')
    view = numbers(root.attrib.get('viewBox', ''))
    if len(view) != 4 or view[2] <= 0 or view[3] <= 0: raise ValueError('Positive SVG viewBox required')
    center = [view[0] + view[2] / 2, view[1] + view[3] / 2]
    groups, elements = [], [0]
    style_keys = {'fill', 'stroke', 'stroke-width', 'fill-opacity', 'stroke-opacity', 'fill-rule', 'stroke-linecap', 'stroke-linejoin'}
    def walk(node, inherited, depth):
        elements[0] += 1
        if elements[0] > 512 or depth > 16: raise ValueError('SVG element/depth limit exceeded')
        if node.tag.startswith('{') and not node.tag.startswith('{http://www.w3.org/2000/svg}'):
            raise ValueError('Unsupported SVG namespace')
        tag = node.tag.split('}')[-1]
        if tag in ('title', 'desc'):
            if list(node) or any(key != 'id' for key in node.attrib):
                raise ValueError('SVG metadata must contain plain text only')
            return
        if tag == 'svg' and depth != 0:
            raise ValueError('Nested SVG viewports are not supported')
        if tag not in ('svg', 'g', 'path', 'polygon', 'polyline', 'rect', 'circle', 'ellipse'):
            raise ValueError('Unsupported SVG element: ' + tag)
        allowed = style_keys | {'id', 'style'} | ({'viewBox', 'width', 'height', 'version'} if tag == 'svg' else set())
        allowed |= {'path': {'d'}, 'polygon': {'points'}, 'polyline': {'points'}, 'rect': {'x', 'y', 'width', 'height'}, 'circle': {'cx', 'cy', 'r'}, 'ellipse': {'cx', 'cy', 'rx', 'ry'}}.get(tag, set())
        if any(key not in allowed for key in node.attrib):
            raise ValueError('Unsupported SVG attribute (including transforms/external references)')
        style = dict(inherited)
        style.update({key: value for key, value in node.attrib.items() if key in style_keys})
        for declaration in node.attrib.get('style', '').split(';'):
            if not declaration.strip(): continue
            pair = declaration.split(':', 1)
            if len(pair) != 2 or pair[0].strip() not in style_keys: raise ValueError('Unsupported SVG CSS style')
            style[pair[0].strip()] = pair[1].strip()
        if style.get('fill-rule', 'nonzero') != 'nonzero' or style.get('stroke-linecap', 'butt') != 'butt' or style.get('stroke-linejoin', 'miter') != 'miter':
            raise ValueError('SVG subset requires nonzero fill, butt caps and miter joins')
        if tag in ('svg', 'g'):
            for child in node: walk(child, style, depth + 1)
            return
        if list(node): raise ValueError('Nested content in SVG geometry is unsupported')
        def scalar(name, default=0):
            vals = numbers(node.attrib.get(name, str(default)))
            if len(vals) != 1: raise ValueError('SVG scalar required')
            return vals[0]
        if tag == 'path':
            path = parse_path(node.attrib.get('d', ''))
        elif tag in ('polygon', 'polyline'):
            coords = numbers(node.attrib.get('points', ''))
            if len(coords) % 2: raise ValueError('SVG point pairs required')
            path = {'vertices': [coords[i:i + 2] for i in range(0, len(coords), 2)], 'closed': tag == 'polygon'}
        elif tag == 'rect':
            x, y, w, h = scalar('x'), scalar('y'), scalar('width'), scalar('height')
            if w <= 0 or h <= 0: raise ValueError('SVG rectangle must have positive dimensions')
            path = {'vertices': [[x, y], [x + w, y], [x + w, y + h], [x, y + h]], 'closed': True}
        else:
            x, y = scalar('cx'), scalar('cy')
            rx, ry = (scalar('r'), scalar('r')) if tag == 'circle' else (scalar('rx'), scalar('ry'))
            if rx <= 0 or ry <= 0: raise ValueError('SVG ellipse must have positive radii')
            k = 0.5522847498307936
            path = {'vertices': [[x, y - ry], [x + rx, y], [x, y + ry], [x - rx, y]], 'closed': True,
                    'in_tangents': [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]],
                    'out_tangents': [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]]}
        from astra_video_studio.design import PathData
        path = PathData.model_validate(path).model_dump(mode='json')
        path['vertices'] = [[(p[i] - center[i]) * scale for i in (0, 1)] for p in path['vertices']]
        for key in ('in_tangents', 'out_tangents'): path[key] = [[v * scale for v in p] for p in path[key]]
        path = PathData.model_validate(path).model_dump(mode='json')
        def paint(kind):
            c = color(style.get(kind, 'black' if kind == 'fill' else 'none'))
            if c is None: return None
            opacity = float(style.get(kind + '-opacity', '1'))
            width = float(style.get('stroke-width', '1')) * scale
            if not math.isfinite(opacity) or not 0 <= opacity <= 1 or not math.isfinite(width) or not 0 < width <= 200:
                raise ValueError('SVG opacity/stroke width exceeds limits')
            result = {'enabled': True, 'color': c, 'opacity': opacity * 100}
            if kind == 'stroke': result.update(width=width, cap=1, join=1)
            return result
        groups.append({'group_id': uuid4().hex, 'name': 'SVG path', 'path': path, 'fill': paint('fill'), 'stroke': paint('stroke')})
        if len(groups) > 32 or sum(len(g['path']['vertices']) for g in groups) > 4096:
            raise ValueError('SVG group/vertex limit exceeded')
    walk(root, {}, 0)
    if not groups: raise ValueError('SVG contains no supported geometry')
    return groups
