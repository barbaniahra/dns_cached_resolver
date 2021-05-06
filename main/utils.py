import struct


def parse_name(data, i):
    result = ''

    while data[i] != 0:
        letters_count = data[i]
        i += 1

        if (letters_count & 0xC0) == 0xC0:
            # first 2 bits are set
            offset = letters_count ^ 0xC0
            offset <<= 8
            offset += data[i]
            i += 1

            result += parse_name(data, offset)[0]
            return result, i
        else:
            for _ in range(letters_count):
                result += chr(data[i])
                i += 1
            result += '.'
    if not result:
        result = '.'
    i += 1

    return result, i


def encode_name(name) -> bytes:
    if name == '.':
        return chr(0).encode()

    result = b''
    for part in name.encode().split(b'.'):
        result += chr(len(part)).encode()
        result += part
    return result


def recv_tcp_message(conn):
    result = b''
    length = conn.recv(2)
    length = struct.unpack('!H', length)[0]
    while len(result) < length:
        data = conn.recv(length - len(result))
        result += data

        if not data:
            break
    return result


def send_tcp_message(conn, data):
    data_length = struct.pack('!H', len(data))
    conn.sendall(data_length + data)
