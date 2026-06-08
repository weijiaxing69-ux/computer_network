"""
Task2 UDP GBN 可靠传输 - 客户端
"""
import socket
import struct
import random
import time
import argparse
import os
import pandas as pd

FILE_NAME = 'run_log_udp.txt'
XOR_KEY = 0x5A3C
WINDOW_SIZE_BYTES = 400    # 发送窗口 400 字节
TIMEOUT = 0.3          # 超时时间 300ms
DATA_LEN_MIN = 40
DATA_LEN_MAX = 80
TOTAL_PACKETS = 30
STUDENT_ID = 2110

def get_time():
    """返回毫秒级时间戳字符串 YYYY-MM-DD HH:MM:SS.sss"""
    now = time.time()
    ms = int((now - int(now)) * 1000)
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)) + f'.{ms:03d}'


def write_log(event_type, msg_type, seq, ack, data_len, addr, rtt=None):
    """追加日志：时间戳、事件类型、报文类型、Seq、Ack、RTT(可选)、Length、地址"""
    addr_str = str(addr)
    with open(FILE_NAME, 'a', encoding='ascii') as f:
        line = '[' + get_time() + '] ' + str(event_type) \
               + ' | Type=' + str(msg_type) \
               + ' | Seq=' + str(seq) \
               + ' | Ack=' + str(ack) \
               + ' | Length=' + str(data_len) \
               + ' | Address=' + addr_str
        if rtt is not None:
            line += ' | RTT=' + f"{rtt:.1f} ms"
        line += '\n'
        f.write(line)


def encrypt_id(uid):
    """学号加密：后4位 XOR 0x5A3C，返回16位无符号整数"""
    return (uid ^ XOR_KEY) & 0xFFFF


def make_packet(student_id, msg_type, seq, ack, data=b''):
    """构造UDP报文：13字节头部(!HBIIH) + data，返回bytes"""
    header = struct.pack("!HBIIH", student_id, msg_type, seq, ack, len(data))
    return header + data


def parse_packet(packet):
    """解析UDP报文，返回 (sid, msg_type, seq, ack, length, payload)"""
    sid, msg_type, seq, ack, length = struct.unpack("!HBIIH", packet[:13])
    data = packet[13:13 + length]
    return sid, msg_type, seq, ack, length, data


def generate_data_blocks(total, min_len, max_len, filepath=None):
    """生成 total 个数据块，每个长度 [min_len, max_len] 间随机

    如果提供 filepath，从文件中读取内容来分包；
    否则生成随机 ASCII 字符串。
    """
    blocks = []
    if filepath:
        with open(filepath, 'rb') as f:
            content = f.read()
        pos = 0
        for _ in range(total):
            remain = len(content) - pos
            if remain <= 0:
                # 文件内容已用完，补空白
                length = random.randint(min_len, max_len)
                block = b' ' * length
            elif remain <= max_len:
                block = content[pos:]
                pos += len(block)
            else:
                length = random.randint(min_len, max_len)
                block = content[pos:pos + length]
                pos += length
            blocks.append(block)
    else:
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        for _ in range(total):
            length = random.randint(min_len, max_len)
            block = ''.join(random.choice(chars) for _ in range(length))
            blocks.append(block.encode('ascii'))
    return blocks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ip', type=str, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--student_id', type=int, default=STUDENT_ID)
    parser.add_argument('--file', type=str, default=None, help='数据文件路径（可选）')
    args = parser.parse_args()

    # 加密学号
    sid = encrypt_id(args.student_id)
    print(f"加密后学号: {sid}")

    # 清空旧日志
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)

    # 创建 UDP socket
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    #用来设置超时的时间
    client.settimeout(TIMEOUT)
    #服务器端的端口和地址
    server_addr = (args.ip, args.port)

    # ========== 1. 连接建立 ==========
    conn_pkt = make_packet(sid, 0, 0, 0)
    client.sendto(conn_pkt, server_addr)
    write_log('send packet', 0, 0, 0, 0, server_addr)
    print(f"发送连接请求至 {args.ip}:{args.port}")

    while True:
        try:
            resp, _ = client.recvfrom(4096)
            #解包
            _, msg_type, _, _, _, _ = parse_packet(resp)
            if msg_type == 1:
                write_log('receive packet', 1, 0, 0, 0, server_addr)
                print("连接建立成功")
                break
        except socket.timeout:
            client.sendto(conn_pkt, server_addr)
            write_log('retransmit', 0, 0, 0, 0, server_addr)
            print("连接请求超时，重发...")

    # ========== 2. 准备数据块 ==========
    random.seed(42)
    blocks = generate_data_blocks(TOTAL_PACKETS, DATA_LEN_MIN, DATA_LEN_MAX, args.file)

    if args.file:
        total_bytes = sum(len(b) for b in blocks)
        print(f"从文件 {args.file} 读取数据，共 {TOTAL_PACKETS} 个数据包，{total_bytes} 字节")
    else:
        print(f"生成随机数据，共 {TOTAL_PACKETS} 个数据包")

    # 计算每个数据包的字节范围（用于输出格式）
    #记录文件总字节偏移量，从 0 开始计数，标记每个数据包在文件中的起始 / 结束位置。
    byte_offset = 0
    #列表，存储每个数据包的字节范围：(起始字节, 结束字节)，用于打印日志、追踪传输进度。 
    packets_info = []
    for block in blocks:
        start_byte = byte_offset #开始位置
        end_byte = byte_offset + len(block) - 1 #结束位置
        packets_info.append((start_byte, end_byte))
        byte_offset += len(block)

    # ========== 3. GBN 滑动窗口传输（按字节计数） ==========
    base = 0           # 窗口基序号（最小未确认序号） 左边界
    next_seq = 0       # 下一个要发送的新包序号
    window = []        # 窗口内包: (seq, pkt(完整数据包), send_time, start_byte, end_byte, block_idx(块编号), data_len)
    rtt_list = []      # RTT 记录列表
    send_total = 0     # 实际发送总包数（含重传） #用来记录丢包率

    def window_bytes_inflight():
        """计算窗口内在飞字节数"""
        return sum(item[6] for item in window) #计算窗口内所有未确认数据包的总字节数 

    while base < TOTAL_PACKETS:
        # 发送窗口内可发的新包（未确认数据总字节 < 400B）
        while next_seq < TOTAL_PACKETS and window_bytes_inflight() < WINDOW_SIZE_BYTES:
            block_idx = next_seq
            pkt = make_packet(sid, 2, next_seq, 0, blocks[block_idx])
            client.sendto(pkt, server_addr)
            send_time = time.time()
            s_byte, e_byte = packets_info[block_idx]
            window.append((next_seq, pkt, send_time, s_byte, e_byte, block_idx, len(blocks[block_idx])))
            send_total += 1
            write_log('send packet', 2, next_seq, 0, len(blocks[block_idx]), server_addr)
            print(f"第 {next_seq} 个（第 {s_byte}~{e_byte} 字节）客户端已经发送")
            next_seq += 1

        # 等待 ACK
        try:
            resp, _ = client.recvfrom(4096)
            _, msg_type, seq, ack, _, _ = parse_packet(resp)
            if msg_type == 3:
                write_log('receive packet', 3, seq, ack, 0, server_addr)

                # 累计确认：所有序号 < ack 的包均已被确认
                while window and window[0][0] < ack:
                    acked_seq, _, send_time, s_byte, e_byte, bidx, dlen = window.pop(0)
                    rtt = (time.time() - send_time) * 1000
                    rtt_list.append(rtt)
                    print(f"第 {acked_seq} 个（第 {s_byte}~{e_byte} 字节）服务端已经收到，RTT是 {rtt:.1f} ms")
                    base = acked_seq + 1

        except socket.timeout:
            # 超时：重传窗口内所有未确认包
            write_log('timeout', '-', base, 0, 0, server_addr)
            print(f"超时，重传窗口内所有包 (base={base})")
            new_window = []
            for seq, pkt, _, s_byte, e_byte, bidx, dlen in window:
                client.sendto(pkt, server_addr)
                send_total += 1
                now = time.time()
                new_window.append((seq, pkt, now, s_byte, e_byte, bidx, dlen))
                write_log('retransmit', 2, seq, 0, len(blocks[bidx]), server_addr)
                print(f"重传第 {seq} 个（第 {s_byte}~{e_byte} 字节）数据包")
            window = new_window

    # ========== 4. 统计输出 ==========
    print("\n======= 传输统计 =======")
    loss_rate = TOTAL_PACKETS / send_total * 100
    print(f"实际发送总包数: {send_total}")
    print(f"丢包率: {loss_rate:.2f}%")

    if rtt_list:
        df = pd.DataFrame(rtt_list, columns=["RTT(ms)"])
        print(f"最大RTT: {df['RTT(ms)'].max():.2f} ms")
        print(f"最小RTT: {df['RTT(ms)'].min():.2f} ms")
        print(f"平均RTT: {df['RTT(ms)'].mean():.2f} ms")
        print(f"RTT标准差: {df['RTT(ms)'].std():.2f} ms")
    else:
        print("无RTT数据")

    client.close()
    write_log('connection closed', '-', 0, 0, 0, server_addr)
    print("连接关闭")


if __name__ == '__main__':
    main()
