from pyquery import PyQuery as pq


def parse_values(items):
    parsed = []
    for item in items:
        if item.tag == 'input':
            parsed.append(item.value)
        else:
            parsed.append(item.text)
    return parsed


def htmlx(data, extract=None, data_map=None, data_store=None):
    try:
        doc = pq(data)
    except:
        doc = pq(data.encode('ascii', 'replace'))
    # return ourself by default
    results = data
    if extract:
        results = []
        for path in extract:
            items = parse_values(doc(path))
            results.append(items)
    if data_map:
        for (key, path) in data_map:
            extracted = parse_values(doc(path))
            data_store[key] = extracted
    return results
