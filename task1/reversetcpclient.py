# -*- coding: utf-8 -*-
"""
TCP 客户端程序 —— 将文件分块发送到服务器进行反转，并重组结果

功能说明：
1. 读取本地文件，按随机大小拆分成多个数据块
2. 通过 TCP 连接将每个数据块发送到服务器
3. 接收服务器反转后的数据块
4. 将所有反转后的数据块按顺序重组，保存为新文件

自定义协议格式（大端字节序）：
- Type 1 (Initialization):   !H=1 + I=数据块总数 N
- Type 2 (Agree):            !H=2（服务器同意连接）
- Type 3 (reverseRequest):   !H=3 + I=数据块长度 + 原始数据
- Type 4 (reverseAnswer):    !H=4 + I=反转后数据长度 + 反转后数据
"""

import socket
import sys
import random
import threading
import time
import struct
import argparse
import os

# 日志文件名（在 main 中解析 --seed 后重新设置）
FILE_NAME = None


def get_time():
    """
    获取带毫秒的当前时间字符串
    返回格式: YYYY-MM-DD HH:MM:SS.mmm
    """
    now = time.time()
    ms = int((now - int(now)) * 1000)
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)) + f'.{ms:03d}'


def write_log(event_type, msg_type, data_len, data, addr):
    """
    将运行日志追加写入文件
    参数：
        event_type: 事件类型描述（如 connection established / send packet）
        msg_type:   协议报文类型描述
        data_len:   数据长度
        data:       数据内容（仅预览前20字符）
        addr:       对端地址 (ip, port) 如果是发出消息 就是发送方自己 接受消息就是对方的地址
    """
    addr_str = str(addr)
    with open(FILE_NAME, 'a', encoding='ascii') as f:
        line = ('[' + get_time() + '] ' + str(event_type) + ' | Type=' + str(msg_type)
                + ' | Length=' + str(data_len) + ' | Preview=' + str(data)[:20]
                + ' | Address=' + addr_str + '\n')
        f.write(line)


def recv_all(sock, n):
    """
    从 TCP socket 中精确接收 n 字节数据
    TCP 是流式协议，一次 recv 不一定能收满 n 字节，
    此函数循环接收直到收满为止。
    参数：
        sock: socket 对象
        n:    期望接收的字节数
    返回：
        完整的 n 字节数据
    异常：
        ConnectionError: 接收失败或连接断开
    """
    data = b''
    while len(data) < n:
        try:
            package = sock.recv(n - len(data))
        except:
            raise ConnectionError('recv error')
        if not package:
            print('all data received')
            raise ConnectionError('connection closed')
        data += package
    return data


def split_file(filepath, lmin, lmax, seed):
    """
    将文件拆分为随机大小的数据块
    参数：
        filepath: 文件路径
        lmin:     数据块最小长度
        lmax:     数据块最大长度
        seed:     随机种子（确保可复现）确保每次取随机的时候都一致
    返回：
        字节串列表，每个元素为一个数据块
    """
    random.seed(seed)
    #以二进制形式打开 读取整个文件中的内容
    with open(filepath, 'rb') as f:
        content = f.read()
    #用来记录分块结果的列表
    chunks = []
    total = len(content)
    pos = 0

    while pos < total:
        remain = total - pos
        # 剩余不足 lmax 时直接取剩余内容
        if remain <= lmax:
            block_len = remain
        else:
            block_len = random.randint(lmin, lmax)
        #将内容分块放入 并且更新位置指针
        chunks.append(content[pos:pos + block_len])
        pos += block_len

    return chunks


def main():
    # ---------- 解析命令行参数 ----------
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-ip', required=True)       # 服务器 IP
    parser.add_argument('--server-port', type=int, required=True)  # 服务器端口
    parser.add_argument('--lmin', type=int, required=True)  # 数据块最小长度
    parser.add_argument('--lmax', type=int, required=True)  # 数据块最大长度
    parser.add_argument('--file', required=True)            # 要发送的文件路径
    parser.add_argument('--seed', type=int, required=True)  # 随机种子
    #解析传入的参数 并且存储到args对象里面
    args = parser.parse_args()

    # 设置日志文件名（使用 seed 区分不同客户端）
    global FILE_NAME
    FILE_NAME = f'run_log_client_seed{args.seed}.txt'
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)

    # ---------- 将文件拆分为数据块 ----------
    #得到数据块
    blocks = split_file(args.file, args.lmin, args.lmax, args.seed)
    N = len(blocks)
    print(f'file split done, total blocks N={N}')

    # ---------- 连接服务器 ----------
    #初始化 TCP 客户端 socket 并连接到服务器
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #连接服务器
    client.connect((args.server_ip, args.server_port))
    #服务器端的地址
    server_addr = (args.server_ip, args.server_port)
    local_addr = client.getsockname() #得到本机的IP地址和端口号
    write_log('connection established', '-', 0, '', server_addr)
    print(f'connected to {args.server_ip}:{args.server_port}')

    # ---------- 发送初始化包 (Type=1) ----------
    # 包格式: !H(类型=1) + I(数据块总数N)
    #这个!代表的是大端传输 网络编程中要注意顺序 并且H代表无符号短整型 2字节 I代表无符号整型 4字节
    init_pkt = struct.pack('!HI', 1, N)
    client.sendall(init_pkt)
    write_log('send packet', '1 (Initialization)', 4, 'N=' + str(N), local_addr)

    # ---------- 接收服务器同意包 (Type=2) ----------
    agree_data = recv_all(client, 2)
    #unpack返回的是元组 这里只有一个元素 所以用[0]取出
    agree_type = struct.unpack('!H', agree_data)[0]
    if agree_type != 2:
        print(f'error: expected Type=2, got Type={agree_type}')
        client.close()
        return
    #没有传输任何数据所以长度为0
    write_log('receive packet', '2 (Agree)', 0, '', server_addr)
    print('received agree')

    # ---------- 逐块发送反转请求，接收反转结果 ----------
    reversed_blocks = []
    #enumeate 函数可以同时获得元素的索引和值 这里从1开始计数
    for i, block in enumerate(blocks, start=1):
        # 构造请求包: !H(类型=3) + I(数据长度) + 原始数据
        req_pkt = struct.pack('!HI', 3, len(block)) + block
        client.sendall(req_pkt)
        write_log('send packet', '3 (reverseRequest)', len(block),
                  block.decode('ascii'), local_addr)
        print(f'send block {i} request')

        # 接收响应头: !H(类型) + I(反转后数据长度) 接收固定的6个字节
        ans_header = recv_all(client, 6)
        #解包的到的是元组 分别取出类型和长度
        ans_type, ans_len = struct.unpack('!HI', ans_header)

        if ans_type != 4:
            print(f'error: expected Type=4, got Type={ans_type}')
            break

        # 接收反转后的数据
        ans_data = recv_all(client, ans_len)
        write_log('receive packet', '4 (reverseAnswer)', ans_len,
                  ans_data.decode('ascii'), server_addr)
        reversed_text = ans_data.decode('ascii')
        print(f'block {i}: {reversed_text}')
        reversed_blocks.append(ans_data)

    # ---------- 关闭连接 ----------
    client.close()
    write_log('connection closed', '-', 0, '', server_addr)
    print('transfer complete, connection closed')

    # ---------- 将反转后的数据块重组，保存为新文件 ----------
    all_reversed = b''.join(reversed_blocks)
    #文件名和后缀名分开
    base, ext = os.path.splitext(args.file)
    output_filename = f'{base}_reversed_seed{args.seed}{ext}'
    with open(output_filename, 'wb') as f:
        f.write(all_reversed)
    print(f'reversed file saved as: {output_filename}')


if __name__ == '__main__':
    main()
