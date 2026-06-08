"""
TCP 服务器程序 —— 接收客户端的数据块并反转后返回

功能说明：
1. 监听指定端口，接收客户端 TCP 连接
2. 为每个客户端创建独立线程处理
3. 接收客户端发送的数据块，将每个数据块内容反转
4. 将反转后的数据块发送回客户端
5. 支持多客户端并发连接

自定义协议格式（大端字节序 用的是 ! 来表示的）：
- Type 1 (Initialization):   客户端 → 服务器，!H=1 + I=N(数据块总数)
- Type 2 (Agree):            服务器 → 客户端，!H=2（确认连接）
- Type 3 (reverseRequest):   客户端 → 服务器，!H=3 + I=长度 + 原始数据
- Type 4 (reverseAnswer):    服务器 → 客户端，!H=4 + I=长度 + 反转后数据
"""

import socket
import threading
import time
import struct
import argparse
import os

# 日志文件常量
FILE_NAME = 'run_log.txt'
# 监听所有网络接口
IP = '0.0.0.0'


def get_time():
    """
    获取带毫秒的当前时间字符串
    返回格式: YYYY-MM-DD HH:MM:SS.mmm
    """
    now = time.time()
    ms = int((now - int(now)) * 1000)
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)) + f'.{ms:03d}'


def write_log(event_type, msg_type, data_len, data, addr):
    #这个addr是一个元组 包含ip地址和端口号
    """
    将运行日志追加写入文件
    参数：
        event_type: 事件类型描述
        msg_type:   协议报文类型描述
        data_len:   数据长度
        data:       数据内容（仅预览前20字符）
        addr:       对端地址 (ip, port)
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
        ConnectionError: 客户端断开连接
    """
    data = b''
    while len(data) < n:
        package = sock.recv(n - len(data))
        if not package:
            raise ConnectionError('client disconnected')
        data += package
    return data


def handle_client(client_socket, addr):
    """
    处理单个客户端的完整请求流程
    每个客户端在独立线程中运行此函数

    流程：
        1. 接收初始化包 (Type=1)，获取数据块总数 N
        2. 回复同意包 (Type=2)
        3. 循环 N 次：
           a. 接收反转请求 (Type=3)，获取数据块
           b. 将数据块内容反转
           c. 回复反转结果 (Type=4)
        4. 关闭连接

    参数：
        client_socket: 客户端的 socket 对象
        addr:          客户端地址 (ip, port)
    """
    try:
        # ---------- 接收初始化包 (Type=1) ----------
        # 包格式: !H(类型) + I(数据块总数N)
        #固定接收初始化的6个字节
        init_header = recv_all(client_socket, 6)
        #type是关键字 用type_来接收类型的值
        type_, N = struct.unpack('!HI', init_header)
        #判断类型是否正确
        if type_ != 1:
            print('error: type should be 1')
            return
        write_log('receive packet', '1 (Initialization)', 4,
                  'N=' + str(N), addr)

        # ---------- 发送同意包 (Type=2) ----------
        client_socket.sendall(struct.pack('!H', 2))
        write_log('send packet', '2 (Agree)', 0, '', addr)
        print(f'send agree to {addr}')

        # ---------- 逐块接收反转请求并处理 ----------
        for i in range(1, N + 1):
            # 接收请求头: !H(类型) + I(数据长度)
            req_header = recv_all(client_socket, 6)
            type_, length = struct.unpack('!HI', req_header)
            
            if type_ != 3:
                print('error: type should be 3')
                return

            # 接收原始数据
            raw_data = recv_all(client_socket, length)
            write_log('receive packet', '3 (reverseRequest)', length,
                      raw_data.decode('ascii'), addr)

            # 反转数据（核心操作：字节串取反）
            reverse_data = raw_data[::-1]

            # 构造并发送响应包: !H(类型=4) + I(反转后数据长度) + 反转后数据
            ans = struct.pack('!HI', 4, len(reverse_data)) + reverse_data
            client_socket.sendall(ans)
            write_log('send packet', '4 (reverseAnswer)', len(reverse_data),
                      reverse_data.decode('ascii'), client_socket.getsockname())
            print(f'block {i} replied')

    except ConnectionError as e:
        print(f'client {addr} disconnected: {e}')
    finally:
        # 确保连接被关闭
        client_socket.close()
        write_log('connection closed', '-', 0, '', addr)
        print(f'client {addr} connection closed')


def main():
    # ---------- 解析命令行参数 ----------
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)  # 监听端口
    args = parser.parse_args()

    # 如果日志文件已存在，先删除
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)

    # ---------- 创建并启动 TCP 服务器 ----------
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR: 允许地址重用，避免 "Address already in use" 错误
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((IP, args.port))
    server.listen(5)  # 最大等待连接数

    try:
        # 持续接受客户端连接
        while True:
            client, addr = server.accept()
            write_log('connection established', '-', 0, '', addr)
            print(f'new connection from {addr}')

            # 为每个客户端创建独立守护线程处理
            t = threading.Thread(
                target=handle_client, #要执行的函数
                args=(client, addr), #给函数传的参数 必须是元组的形式
                daemon=True        # 设置为守护线程，主线程退出时自动结束 所有子线程也会被强制结束
            )
            t.start()
    except:
        print('\nserver closed')
    finally:
        server.close()


if __name__ == '__main__':
    main()
