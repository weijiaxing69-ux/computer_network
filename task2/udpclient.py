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

""" 对应关系如下：
    功能	  TCP 术语	   我的 Type
    连接请求	SYN	        Type=0
    连接确认  SYN+ACK	    Type=1
    数据	    —	        Type=2
    确认	    ACK	        Type=3
    断开请求	FIN	        Type=4
    断开确认  FIN+ACK	    Type=5
"""
FILE_NAME = 'client_run_log.txt'
XOR_KEY = 0x5A3C
WINDOW_SIZE_BYTES = 400    # 发送窗口 400 字节（含13B头部，数据部分上限387B）
TIMEOUT = 0.3          # 超时时间 300ms（可通过命令行覆盖）
DATA_LEN_MIN = 40
DATA_LEN_MAX = 80
TOTAL_PACKETS = 30
STUDENT_ID = 2110
MAX_RETRIES = 15       # 连接/FIN 最大重试次数
HEADER_LEN = 13        # UDP 报文头部长度

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
    """学号加密：取学号后4位 XOR 0x5A3C，返回16位无符号整数"""
    return ((uid % 10000) ^ XOR_KEY) & 0xFFFF


def make_packet(student_id, msg_type, seq, ack, data=b''):
    """构造UDP报文：13字节头部(!HBIIH) + data，返回bytes"""
    #构建首部和数据信息
    header = struct.pack("!HBIIH", student_id, msg_type, seq, ack, len(data))
    return header + data


def parse_packet(packet):
    """解析UDP报文，返回 (sid, msg_type, seq, ack, length, payload)"""
    if len(packet) < HEADER_LEN:
        raise ValueError(f"报文长度不足: {len(packet)} < {HEADER_LEN}")
    sid, msg_type, seq, ack, length = struct.unpack("!HBIIH", packet[:HEADER_LEN])
    if len(packet) < HEADER_LEN + length:
        raise ValueError(f"报文数据段不完整: 头部声明 {length}B, 实际剩余 {len(packet) - HEADER_LEN}B")
    data = packet[HEADER_LEN:HEADER_LEN + length]
    return sid, msg_type, seq, ack, length, data


def generate_data_blocks(total, min_len, max_len, filepath=None):
    """生成 total 个数据块，每个长度 [min_len, max_len] 间随机

    如果提供 filepath，从文件中读取内容来分包；
    否则生成随机 ASCII 字符串。
    """
    blocks = []
    #在有文件的情况下
    if filepath:
        with open(filepath, 'rb') as f:
            content = f.read()
        pos = 0
        for _ in range(total):
            remain = len(content) - pos
            if remain <= 0:
                # 文件内容已用完，用空白进行填充
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
    #在没有测试文件的情况下
    else:
        chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        for _ in range(total):
            length = random.randint(min_len, max_len)
            #随机取出lentgh 长度的数据
            block = ''.join(random.choice(chars) for _ in range(length))
            blocks.append(block.encode('ascii'))
    return blocks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server_ip', type=str, required=True)
    parser.add_argument('--server_port', type=int, required=True)
    parser.add_argument('--student_id', type=int, default=STUDENT_ID)
    parser.add_argument('--file', type=str, default=None, help='数据文件路径（可选）')
    parser.add_argument('--timeout', type=float, default=TIMEOUT, help='超时时间（秒，默认0.3）')
    parser.add_argument('--window_size', type=int, default=WINDOW_SIZE_BYTES,
                        help=f'发送窗口大小（字节，含头部，默认{WINDOW_SIZE_BYTES}）')
    parser.add_argument('--data_min', type=int, default=DATA_LEN_MIN,
                        help=f'单包数据最小长度（默认{DATA_LEN_MIN}）')
    parser.add_argument('--data_max', type=int, default=DATA_LEN_MAX,
                        help=f'单包数据最大长度（默认{DATA_LEN_MAX}）')
    parser.add_argument('--total_packets', type=int, default=TOTAL_PACKETS,
                        help=f'总数据包数（默认{TOTAL_PACKETS}）')
    parser.add_argument('--seed', type=int, default=42,
                        help='数据块生成随机种子（默认42，确保复现）')
    args = parser.parse_args()

    # 校验文件是否存在
    if args.file and not os.path.exists(args.file):
        print(f"错误: 文件 '{args.file}' 不存在")
        return

    # 加密学号
    sid = encrypt_id(args.student_id)
    print(f"加密后学号: {sid}")

    # 清空旧日志
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)

    # 创建 UDP socket
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(args.timeout)
    print(f"超时时间设置为 {args.timeout} 秒")
    server_addr = (args.server_ip, args.server_port)

    # ========== 1. 三次握手（连接建立） ==========
    conn_pkt = make_packet(sid, 0, 0, 0)
    retries = 0#重新尝试的次数
    client.sendto(conn_pkt, server_addr)
    write_log('send packet', 0, 0, 0, 0, server_addr)
    print(f"发送连接请求至 {args.server_ip}:{args.server_port}")

    while True:
        try:
            resp, _ = client.recvfrom(4096)
            try:
                _, msg_type, _, _, _, _ = parse_packet(resp)
            except (ValueError, struct.error) as e:
                print(f"解析连接响应异常: {e}")
                continue
            if msg_type == 1: #收到的应该是确认连接的报文
                write_log('receive packet', 1, 0, 0, 0, server_addr)
                # 三次握手第三步：发送 ACK 确认连接建立
                ack_pkt = make_packet(sid, 3, 0, 1)
                client.sendto(ack_pkt, server_addr)
                write_log('send packet', 3, 0, 1, 0, server_addr)
                print("连接建立成功（三次握手完成）")
                break
        except socket.timeout:
            retries += 1
            if retries >= MAX_RETRIES: #大于最大的尝试次数 直接退出
                print(f"连接超时 {MAX_RETRIES} 次，服务器无响应，退出")
                write_log('connection closed', '-', 0, 0, 0, server_addr)
                client.close()
                return
            client.sendto(conn_pkt, server_addr)
            write_log('retransmit', 0, 0, 0, 0, server_addr)
            print(f"连接请求超时（第{retries}次），重发...")
        except (ConnectionResetError, OSError) as e:
            print(f"连接阶段网络异常: {e}，退出")
            client.close()
            return

    # 用命令行参数覆盖常量
    window_size = args.window_size
    data_min = args.data_min
    data_max = args.data_max
    total_packets = args.total_packets

    # 校验窗口大小最小值（至少容纳 1 个最小包：头部13B + 数据最低40B = 53B）
    #窗口必须能装下至少一个包 如果一个包也装不下 那么肯定就是错误的
    if window_size < HEADER_LEN + data_min:
        print(f"错误: 窗口大小({window_size}B) 至少需 {HEADER_LEN + data_min}B (头部{HEADER_LEN}B + 最小数据{data_min}B)")
        client.close()
        return

    # ========== 2. 准备数据块 ==========
    random.seed(args.seed) #给出种子 复现的时候可以好对比
    blocks = generate_data_blocks(total_packets, data_min, data_max, args.file)

    if args.file: #如果文件存在 求出总的字节数
        total_bytes = sum(len(b) for b in blocks)
        print(f"从文件 {args.file} 读取数据，共 {total_packets} 个数据包，{total_bytes} 字节")
    else:
        print(f"生成随机数据，共 {total_packets} 个数据包")

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

    # ========== 3. GBN 滑动窗口传输（快重传机制） ==========
    base = 0            # 窗口基序号（最小未确认序号）
    next_seq = 0        # 下一个要发送的新包序号
    window = []         # 窗口内包: (seq, pkt, send_time, start_byte, end_byte, block_idx, wire_len)
    rtt_list = []       # RTT 记录列表
    send_total = 0      # 实际发送总包数（含重传）
    dup_ack_count = 0   # 重复 ACK 计数（快重传用）
    last_ack = 0        # 上次收到的 ACK 号

    def window_bytes_inflight():
        """计算窗口内在飞字节数（含13B头部）"""
        #当前窗口里所有未确认包的总字节数
        return sum(item[6] for item in window)  # wire_len = 数据长度 + 13B头部

    while base < total_packets:
        # 发送窗口内可发的新包（新包加入后不超过窗口上限）
        #还有没发的新包 并且窗口还能塞下新的包
        while (next_seq < total_packets
               and window_bytes_inflight() + len(blocks[next_seq]) + HEADER_LEN <= window_size):
            #块号是下一个的序列号
            block_idx = next_seq
            #打包
            pkt = make_packet(sid, 2, next_seq, 0, blocks[block_idx])
            #发送包
            client.sendto(pkt, server_addr)
            #发送时间
            send_time = time.time()
            #取出对应的字节范围
            s_byte, e_byte = packets_info[block_idx]
            #              包的序号  UDP报文 发送时间  开始    结束     块号        包的数据+长度 
            window.append((next_seq, pkt, send_time, s_byte, e_byte, block_idx, len(blocks[block_idx]) + HEADER_LEN))
            #成功发送
            send_total += 1
            write_log('send packet', 2, next_seq, 0, len(blocks[block_idx]), server_addr)
            print(f"第 {next_seq} 个（第 {s_byte}~{e_byte} 字节）客户端已经发送")
            next_seq += 1

        # 等待 ACK
        try:
            resp, _ = client.recvfrom(4096)
            try:
                _, msg_type, seq, ack, _, payload = parse_packet(resp)
            except (ValueError, struct.error) as e:
                print(f"解析数据阶段报文异常: {e}")
                continue
            # 校验 ACK 合法性（拒绝过期 ACK 和越界 ACK）
            if ack < base or ack > next_seq:
                print(f"丢弃非法 ACK={ack} (base={base}, next_seq={next_seq})")
                continue
            if msg_type == 3: #确认接收了 这个是从服务器端传来的消息
                write_log('receive packet', 3, seq, ack, 0, server_addr)

                if ack > base:
                    #一个包一个包推进
                    # 累积确认：窗口向前滑动 
                    #                当前包的序号
                    while window and window[0][0] < ack:
                        acked_seq, _, send_time, s_byte, e_byte, bidx, dlen = window.pop(0)
                        #现在的时间减去服务器端发回消息的时间 就是RTT
                        rtt = (time.time() - send_time) * 1000
                        rtt_list.append(rtt)
                        # 输出服务端系统时间（ACK 数据段携带）
                        server_time = payload.decode('ascii') if payload else ''
                        time_info = f"，服务端时间 {server_time}" if server_time else ''
                        print(f"第 {acked_seq} 个（第 {s_byte}~{e_byte} 字节）服务端已经收到，RTT是 {rtt:.1f} ms{time_info}")
                        base = acked_seq + 1
                    # 窗口前进了，重置重复计数
                    dup_ack_count = 0
                    last_ack = ack

                elif ack == last_ack:
                    # 重复 ACK：说明有包丢失，累计计数
                    dup_ack_count += 1
                    print(f"收到重复 ACK={ack}，连续第 {dup_ack_count} 次")
                    if dup_ack_count >= 3:
                        # ================ 快重传触发 ================
                        # GBN 窗口中 window[0] 就是 base 包，无需遍历
                        print(f"===== 快重传！重传 base={base} =====")
                        #生成一个信息 放在窗口第一位
                        seq, pkt, orig_time, s_byte, e_byte, bidx, dlen = window[0]
                        client.sendto(pkt, server_addr)
                        send_total += 1
                        write_log('fast retransmit', 2, seq, 0, len(blocks[bidx]), server_addr)
                        print(f"重传第 {seq} 个（第 {s_byte}~{e_byte} 字节）数据包（快重传）")
                        #改变重复的计数值
                        dup_ack_count = 0
                else:
                    # ACK 变化但未滑动窗口（首次重复/乱序），记录状态
                    last_ack = ack
                    dup_ack_count = 1
        #直接超时重传
        except socket.timeout:
            # 保底超时：作为备份，重传窗口内所有未确认包
            write_log('timeout', '-', base, 0, 0, server_addr)
            print(f"超时，重传窗口内所有包 (base={base})")
            new_window = []#建立新的窗口
            for seq, pkt, orig_time, s_byte, e_byte, bidx, dlen in window:
                client.sendto(pkt, server_addr)#重新发送每一个包
                send_total += 1
                # 重传时更新发送时间，RTT 从最后一次发送算起
                new_window.append((seq, pkt, time.time(), s_byte, e_byte, bidx, dlen))
                write_log('retransmit', 2, seq, 0, len(blocks[bidx]), server_addr)
                print(f"重传第 {seq} 个（第 {s_byte}~{e_byte} 字节）数据包")
            window = new_window
        except (ConnectionResetError, OSError) as e:
            print(f"网络异常: {e}，终止传输")
            break

    # ========== 4. 四次挥手（连接释放） ==========
    # 客户端发送 FIN（带超时重传）
    fin_pkt = make_packet(sid, 4, 0, 0)
    fin_retries = 0
    wave_done = False
    #挥手还没有完成 并且还可以继续进行重传
    while not wave_done and fin_retries < MAX_RETRIES:
        client.sendto(fin_pkt, server_addr)
        write_log('send packet', 4, 0, 0, 0, server_addr)
        print(f"发送断开连接请求 (尝试{fin_retries + 1})")
        try:
            resp, _ = client.recvfrom(4096)
            try:
                _, msg_type, seq, ack, _, _ = parse_packet(resp)
            except (ValueError, struct.error) as e:
                print(f"解析挥手阶段报文异常: {e}")
                fin_retries += 1
                continue
            #收到断开确认了
            if msg_type == 5:
                write_log('receive packet', 5, seq, ack, 0, server_addr)
                print("收到服务端断开确认（挥手完成）")
                # 发送最终 ACK
                last_ack_pkt = make_packet(sid, 3, 0, 1)
                client.sendto(last_ack_pkt, server_addr)
                write_log('send packet', 3, 0, 1, 0, server_addr)
                wave_done = True
            else:
                # 收到非 FIN+ACK 报文，计入重试
                fin_retries += 1
                print(f"收到非预期报文 Type={msg_type}，重试...")
        except socket.timeout:
            fin_retries += 1
            if fin_retries < MAX_RETRIES:
                print(f"挥手超时（第{fin_retries}次），重试...")
            else:
                print("挥手超时已达最大重试次数，直接关闭")

    # ========== 5. 统计输出 ==========
    print("\n======= 传输统计 =======")
    # 丢包率 = 总数据包数 ÷ 实际发送总包数 × 100%
    loss_rate = total_packets / send_total * 100
    print(f"实际发送总包数: {send_total}")
    print(f"丢包率: {loss_rate:.2f}%")

    if rtt_list:
        #创建为DataFrame类型的 方便计算
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
