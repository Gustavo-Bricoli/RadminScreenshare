import socket
import struct
import time

from UDFBruto.screen_config import (
    AUDIO_PORT,
    VIDEO_CHUNK_HEADER_FORMAT,
    VIDEO_CHUNK_SIZE,
    VIDEO_PORT,
    KEYFRAME_PACKET_DELAY
)


def create_udp_server(port):

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind(("0.0.0.0", port))

    return server


def wait_for_hello(server, expected_message):

    while True:

        data, address = server.recvfrom(1024)

        if data == expected_message:
            return address


def send_video_frame(sock, address, frame_id, frame, is_keyframe):

    chunk_count = (
        len(frame) + VIDEO_CHUNK_SIZE - 1
    ) // VIDEO_CHUNK_SIZE

    for chunk_id in range(chunk_count):

        start = chunk_id * VIDEO_CHUNK_SIZE
        end = start + VIDEO_CHUNK_SIZE

        packet = struct.pack(
            VIDEO_CHUNK_HEADER_FORMAT,
            frame_id,
            chunk_id,
            chunk_count,
            int(is_keyframe)
        ) + frame[start:end]

        sock.sendto(packet, address)

        if is_keyframe:
            time.sleep(KEYFRAME_PACKET_DELAY)

    return chunk_count


def parse_video_packet(packet):

    header_size = struct.calcsize(VIDEO_CHUNK_HEADER_FORMAT)

    if len(packet) <= header_size:
        return None

    frame_id, chunk_id, chunk_count, is_keyframe = struct.unpack(
        VIDEO_CHUNK_HEADER_FORMAT,
        packet[:header_size]
    )

    if chunk_count == 0 or chunk_id >= chunk_count:
        return None

    return (
        frame_id,
        chunk_id,
        chunk_count,
        bool(is_keyframe),
        packet[header_size:]
    )


def encode_audio_packet(sequence, encoded):
    return struct.pack("!I", sequence) + encoded


def parse_audio_packet(packet):

    if len(packet) < 4:
        return None

    return struct.unpack("!I", packet[:4])[0], packet[4:]