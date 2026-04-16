import base64
import struct


def decode_bdata(bdata, dtype):
    binary = base64.b64decode(bdata)

    if dtype == "f8":
        return list(struct.unpack(f"{len(binary)//8}d", binary))
    elif dtype == "f4":
        return list(struct.unpack(f"{len(binary)//4}f", binary))
    elif dtype == "i4":
        return list(struct.unpack(f"{len(binary)//4}i", binary))
    elif dtype == "i2":
        return list(struct.unpack(f"{len(binary)//2}h", binary))
    elif dtype == "i1":
        return list(struct.unpack(f"{len(binary)}b", binary))

    return []


def decode_sql_result(sql_result):
    if not sql_result:
        return sql_result

    if isinstance(sql_result, dict) and "rows" in sql_result:
        return sql_result

    if isinstance(sql_result, dict):
        decoded = {}
        for key, val in sql_result.items():
            if isinstance(val, dict) and "bdata" in val:
                decoded[key] = decode_bdata(val["bdata"], val.get("dtype"))
            else:
                decoded[key] = val
        return decoded

    return sql_result