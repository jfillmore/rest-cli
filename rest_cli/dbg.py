"""
Uses python introspection to provide PHP-like "var_dump" functionality for
debugging objects.
"""

import json
import sys
import time
import traceback
import types
import inspect


dark_colors = {
    'str': '0;37',
    'bool': '1;36',
    'int': '0;32',
    'float': '1;32',
    'NoneType': '0;36',
    'object': '0;36',
    'instance': '0;36',
    'module': '0;36',
    'classobj': '0;36',
    'builtin_function_or_method': '0;36',
    'ArgSpec': '0:36:40',
    'list': ['1;37', '1;33', '0;33', '1;31', '0;31'],
    'tuple': ['1;37', '1;33', '0;33', '1;31', '0;31'],
    'dict': ['1;37', '1;33', '0;33', '1;31', '0;31'],
    'bullet': '1;30',
    'seperator': '1;30'
}

light_colors = {
    'str': '1;30',
    'bool': '0;36',
    'int': '1;31',
    'float': '1;31',
    'NoneType': '0;36',
    'object': '0;30',
    'instance': '0;30',
    'module': '0;30',
    'classobj': '0;30',
    'builtin_function_or_method': '0;30',
    'ArgSpec': '0:30:40',
    'list': ['0;00', '0;34', '0;35', '0;31'],
    'tuple': ['0;00', '0;34', '0;35', '0;31'],
    'dict': ['0;00', '0;34', '0;35', '0;31'],
    'bullet': '1;30',
    'seperator': '1;30'
}


def get_obj_info(obj, include_private=False):
    obj_info = {
        'type': type(obj).__name__,
        'callable': callable(obj),
        'value': str(obj),
        'repr': repr(obj),
        'description': str(getattr(obj, '__doc__', '')).strip()
    }
    # take a look at what it contains and build up description of what we've got
    if obj_info['type'] == 'function':
        obj_info['arg_spec'] = inspect.getargspec(obj)
    elif not obj_info['type'] in ('str', 'int', 'float', 'bool', 'NoneType', 'ArgSpec'):
        for key in dir(obj):
            if key.startswith('__') and not include_private:
                continue
            item = getattr(obj, key)
            if inspect.ismethod(item):
                if not 'methods' in obj_info:
                    obj_info['methods'] = {}
                obj_info['methods'][key] = {
                    'description': str(item.__doc__)[0:64].strip(),
                    'arg_spec': inspect.getargspec(item)
                }
            elif inspect.ismodule(item):
                if not 'modules' in obj_info:
                    obj_info['modules'] = {}
                obj_info['modules'][key] = str(item.__doc__)[0:64].strip()
            elif inspect.isclass(item):
                if not 'classes' in obj_info:
                    obj_info['classes'] = {}
                obj_info['classes'][key] = str(item.__doc__)[0:64].strip()
            else:
                if not 'properties' in obj_info:
                    obj_info['properties'] = {}
                obj_info['properties'][key] = obj2str(item, short_form=True)
    return obj_info


def print_tb(exception=None):
    if exception:
        frames = []
        for i, frame in enumerate(traceback.extract_tb(tb)):
            where = frame.name + ' - ' + frame.filename[len(cwd) + 1:]
            frames.append({
                'line': frame.line,
                'where': f'{where}:{frame.lineno}',
                'depth': i,
            })
    else:
        tb = traceback.extract_stack()
        print('\n'.join([
            "\tTraceback (most recent call on bottom):",
            '\n'.join(['\t\t%s:%i, method "%s"\n\t\t\tLine: %s' % t for t in tb])
        ]))


def log(
        msg, color='1;34', data=None, data_color='1;33', data_inline=False,
        symbol='#'
    ):
    color_parts = color.split(';', 1)
    if len(color_parts) > 1:
        is_light = bool(color_parts[0])
        hue = color_parts[1]
    else:
        is_light = False
        hue = color_parts[0]
    color_alt = str(int(not is_light)) + ';' + hue
    log_str = f'\033[{color_alt}m{symbol}\033[0m ' if symbol else ''
    log_str += f'\033[{color}m{msg}\033[0m' + ('' if data_inline else '\n')
    sys.stderr.write(log_str)
    if data is not None:
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        data_str = data if isinstance(data, str) else json.dumps(data, indent=4) 
        sys.stderr.write(f'\033[{data_color}m%s\033[0m\n' % data_str)


def shell_color(obj, obj_color=None):
    if obj_color:
        return f'\033[{obj_color}m{str(obj)}\033[0;0m'
    return str(obj)


def obj2str(
        obj, depth=0, color=True, indent_char=' ', indent_size=4, inline=True,
        short_form=False, invert_color=False
    ):
    """
    Returns a formatted string, optionally with color coding
    """

    palette = light_colors if invert_color else dark_colors

    def rdump(obj, depth=0, indent_size=4, inline=False, short_form=False):
        if short_form:
            return str(obj)[0:80 - (depth * indent_size)]
        obj_info = get_obj_info(obj)
        # indent ourselves
        dump = depth * (indent_size * indent_char)
        # see what we've got and recurse as needed
        if obj_info['type'] == 'list':
            if not len(obj):
                dump += shell_color(' []', palette['object']) + '\n'
            else:
                skip_next_indent = True
                for i in range(0, len(obj)):
                    item = obj[i]
                    item_info = get_obj_info(item)
                    # handy any indentation we may need to do
                    if skip_next_indent:
                        skip_next_indent = False
                    else:
                        dump += depth * (indent_size * indent_char)
                    # add in the key, cycling through the available colors based on depth
                    dump += shell_color(i, palette[obj_info['type']][(depth) % (len(palette[obj_info['type']]))])
                    # format it depending on whether we've nested list with any empty items
                    if item_info['type'] in ('dict', 'tuple', 'list'):
                        if not len(item):
                            dump += rdump(item, 0, indent_size, True)
                        else:
                            dump += '\n' + rdump(item, depth + 1, indent_size, True)
                    else:
                        dump += rdump(item, 1, 1)
        elif obj_info['type'] == 'dict':
            if not len(obj):
                dump += shell_color(' {}', palette['object']) + '\n'
            else:
                skip_next_indent = True
                for key in obj:
                    item = obj[key]
                    item_info = get_obj_info(item)
                    # handy any indentation we may need to do
                    if skip_next_indent:
                        skip_next_indent = False
                    else:
                        dump += depth * (indent_size * indent_char)
                    # add in the key, cycling through the available colors based on depth
                    dump += shell_color(key, palette[obj_info['type']][(depth) % (len(palette[obj_info['type']]))])
                    # add in a bullet
                    dump += shell_color(':', palette['bullet'])
                    # format it depending on whether we've nested list with any empty items
                    if item_info['type'] in ('dict', 'tuple', 'list'):
                        if not len(item):
                            dump += rdump(item, 0, indent_size, True)
                        else:
                            dump += '\n' + rdump(item, depth + 1, indent_size, True)
                            if item_info['type'] == 'tuple':
                                dump += '\n'
                    else:
                        dump += rdump(item, 1, 1)
        elif obj_info['type'] == 'tuple':
            if not len(obj):
                dump += shell_color(' ()', palette['object'])
            else:
                dump += shell_color('(', palette['bullet'])
                dump += ', '.join([str(item)[0:32] for item in obj if item != ()])
                dump += shell_color(')', palette['bullet'])
        elif obj_info['type'] == 'str':
            dump += shell_color(obj, palette[obj_info['type']])
        elif obj_info['type'] == 'bool':
            dump += shell_color(obj, palette[obj_info['type']])
        elif obj_info['type'] == 'NoneType':
            dump += shell_color('(none/null)', palette[obj_info['type']])
        elif obj_info['type'] == 'int':
            dump += shell_color(obj, palette[obj_info['type']])
        elif obj_info['type'] == 'float':
            dump += shell_color(obj, palette[obj_info['type']])
        elif obj_info['type'] == 'object':
            dump += shell_color('(object)', palette[obj_info['type']])
        elif obj_info['type'] == 'instance':
            dump += rdump(obj_info, depth)
        elif obj_info['type'] == 'module':
            dump += rdump(obj_info, depth)
        elif obj_info['type'] == 'function':
            dump += rdump(obj_info, depth)
        elif obj_info['type'] == 'classobj':
            dump += rdump(obj_info, depth)
        elif obj_info['type'] == 'builtin_function_or_method':
            dump += rdump(obj_info, depth)
        elif obj_info['type'] == 'ArgSpec':
            dump += '\n' + rdump({
                'args': obj.args,
                'varargs': obj.varargs,
                'keywords': obj.keywords,
                'defaults': obj.defaults,
            }, depth + 1, inline=True)
        else:
            dump += rdump(obj_info, depth)
        if not inline:
            dump += '\n'
        return dump  # hack hack hack!
    return rdump(obj, depth, indent_size, inline, short_form)


def pretty_print(
        obj, depth=0, color=True, indent_char=' ', indent_size=4,
        stream=sys.stdout, invert_color=False
    ):
    """
    Pretty-prints the contents of the list, tupple, sequence, etc.
    """
    output = obj2str(obj, depth, color, indent_char, indent_size, inline=True, invert_color=invert_color)
    try:
        output = output.encode(sys.stdout.encoding if sys.stdout.encoding else 'utf-8', 'ignore')
    except Exception as e:
        pass
    if not output.endswith("\n"):
        output = output + "\n"
    try:
        stream.write(output)
    except:
        pass

pp = pretty_print
