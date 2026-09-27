import re


def byte_range(header, size):
    """Return inclusive bounds, or reject unsupported/unsatisfiable ranges."""
    if size <= 0:
        raise ValueError('Empty file')
    if not header:
        return 0, size - 1
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
    if not match or not any(match.groups()):
        raise ValueError('Invalid range')
    first, last = match.groups()
    if not first:
        if int(last) <= 0:
            raise ValueError('Invalid suffix')
        return max(0, size - int(last)), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError('Unsatisfiable range')
    return start, end
