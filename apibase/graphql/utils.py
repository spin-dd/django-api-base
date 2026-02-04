def strip_relay(obj, recursive=False):
    """remove relay nodes"""
    if isinstance(obj, list):
        return [strip_relay(i, recursive=recursive) for i in obj]

    if isinstance(obj, dict):
        if "edges" in obj:
            if not recursive:
                return [i["node"] for i in obj["edges"]]
            return [strip_relay(i["node"], recursive=recursive) for i in obj["edges"]]

        return dict((k, strip_relay(v, recursive=recursive)) for k, v in obj.items())
    return obj
