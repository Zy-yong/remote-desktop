import logging
import json
import traceback

logger = logging.getLogger('service')


class WsDataFormat(object):
    """
    bytes 'operation code + header + data'
    """
    @staticmethod
    def pack(opcode, header=None, data=None):
        pack_data = bytearray()
        pack_data += (opcode).to_bytes(1, byteorder='big')
        if header is not None:
            bin_header = json.dumps(header).encode('utf-8')
            bin_header_len = len(bin_header)
            bin_header_len_data = b''
            try:
                bin_header_len_data = (bin_header_len).to_bytes(2, byteorder='big')
            except Exception as e:
                logger.error(traceback.format_exc())
                print(e)
            pack_data += bin_header_len_data
            pack_data += bin_header
        if data is not None:
            pack_data += data
        return bytes(pack_data)

    @staticmethod
    def unpack(data):
        assert isinstance(data, bytes)

        offset = 0
        if len(data) < offset + 1:
            return 0, {}, None
        opcode = int.from_bytes(data[offset:1], byteorder='big')
        offset += 1

        if len(data) < offset + 2:
            return opcode, {}, None
        bin_header_len = int.from_bytes(data[offset:3], byteorder='big')
        offset += 2

        bin_header = data[offset:offset + bin_header_len]
        offset += bin_header_len

        json_header = bin_header.decode('utf-8')

        return opcode, json.loads(json_header), data[offset: len(data)]


if __name__ == "__main__":
    print(WsDataFormat.unpack(
        WsDataFormat.pack(
            255,
            {
                "filename": "文件名",
                "is_dir": "文件夹"
            }
        ))
    )
