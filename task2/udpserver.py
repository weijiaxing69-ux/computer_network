"""
Task2 UDP GBN 可靠传输 - 服务端
发送窗口大小为N 接收窗口大小为1
报文的构建
"""
import socket
import struct
import random
import time
import argparse
import os
""" 对应关系如下：
    功能	  TCP 术语	   我的 Type
    连接请求	SYN	        Type=0
    连接确认  SYN+ACK	    Type=1
    数据	    —	        Type=2
    确认	    ACK	        Type=3
    断开请求	FIN	        Type=4
    断开确认  FIN+ACK	    Type=5
"""
FILE_NAME = 'server_run_log.txt'
XOR_KEY = 0x5A3C
IP='0.0.0.0'
HEADER_LEN = 13
def get_time():
    """返回毫秒级时间戳字符串 YYYY-MM-DD HH:MM:SS.sss"""
    now=time.time()
    ms=int((now-int(now))*1000)
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)) + f'.{ms:03d}'
#服务器端的所有RTT都无法计算 因为没有发送数据包 只有ACK 但是ACK不包含数据 所以无法计算RTT 只能在日志里记录ACK的发送时间
def write_log(event_type, msg_type, seq, ack, data_len, addr, rtt=None):
    """追加日志：时间戳、事件类型、报文类型、Seq、Ack、RTT(可选)、Length、地址"""
    addr_str = str(addr)
    with open(FILE_NAME, 'a', encoding='ascii') as f:
        # 基础部分：时间戳、事件类型、报文类型、Seq、Ack、Length、地址 换行在后面加上 \
        line = '[' + get_time() + '] ' + str(event_type) + ' | Type=' + str(msg_type) \
               + ' | Seq=' + str(seq) + ' | Ack=' + str(ack) \
               + ' | Length=' + str(data_len) + ' | Address=' + addr_str
        # 如果提供了 RTT，追加 RTT 字段
        if rtt is not None:
            line += ' | RTT=' + f"{rtt:.1f} ms"
        line += '\n'
        f.write(line)
        
    

def make_packet(student_id, msg_type, seq, ack, data=b''):
    """构造UDP报文：13字节头部(!HBIIH) + data，返回bytes"""
    #也就是首部加上信息
    #开始构建首部
    header=struct.pack("!HBIIH",student_id,msg_type,seq,ack,len(data))
    return header+data#构建完成


def parse_packet(packet):
    """解析UDP报文，返回 (sid, msg_type, seq, ack, length, data)"""
    #收到的是上方的结构 一次性传输的数据不固定 所以不能使用固定格式的解包 只能先解首部 再是数据
    if len(packet) < HEADER_LEN:
        raise ValueError(f"报文长度不足: {len(packet)} < {HEADER_LEN}")
    #这里面数据长度是用来校验的 看看这个包是不是和首部说的信息一致
    sid,msg_type,seq,ack,length=struct.unpack("!HBIIH",packet[:HEADER_LEN])
    if len(packet) < HEADER_LEN + length:
        #在这里面给出错误
        raise ValueError(f"报文数据段不完整: 头部声明 {length}B, 实际剩余 {len(packet) - HEADER_LEN}B")
    data=packet[HEADER_LEN:HEADER_LEN+length]
    return sid,msg_type,seq,ack,length,data
    

def main():
    """主函数：解析参数、清日志、绑定端口、循环接收处理"""
    #首先开始解析参数
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,required=True) #端口号
    parser.add_argument('--loss_rate',type=float,default=0.3)#丢包率 默认为0.3
    parser.add_argument('--seed',type=int,default=None,help='随机数种子（可选，用于复现丢包场景）')
    args=parser.parse_args()
    #现在开始清空文件
    if os.path.exists(FILE_NAME):
        os.remove(FILE_NAME)
    #初始化套接字 并且使用的是UDP
    serversocket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    #绑定端口
    serversocket.bind((IP,args.port))
    #得到丢失率
    loss_rate=args.loss_rate
    # 校验丢包率范围
    if loss_rate < 0.0 or loss_rate > 1.0:
        print(f"错误: 丢包率 {loss_rate} 超出范围 [0.0, 1.0]")
        return
    # 设置随机种子（用于复现丢包）
    if args.seed is not None:
        random.seed(args.seed)
        print(f"随机种子已设置为 {args.seed}")
    # key=客户端地址addr → 期待的下一个包序号（接收窗口=1） 可以是多个客户端
    expect_seq={}
    # 接收数据缓冲区：addr → bytes，FIN 时保存到文件
    received_data = {}

    # 获取本机实际 IP（用于打印提示）
    try:
        tmp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tmp_sock.connect(('8.8.8.8', 80))
        local_ip = tmp_sock.getsockname()[0]
        tmp_sock.close()
    except Exception:
        local_ip = '0.0.0.0'
    print(f"服务器已启动, 本机IP: {local_ip}, 端口: {args.port}, 丢包率: {loss_rate}")
    print(f"客户端连接请使用: --ip {local_ip} --port {args.port}")

    #现在开始接收数据
    try:
        while True:
            try:
                #接收数据和地址
                data,addr=serversocket.recvfrom(4096)
                #开始解包
                sid, msg_type, seq, ack, length, payload = parse_packet(data)
            except (ValueError, struct.error) as e:
                print(f"解析报文异常: {e} (来源: {addr})")
                write_log("parse error", '-', 0, 0, 0, addr)
                continue
            #现在开始学号验证
            res_id=sid^XOR_KEY
            if res_id > 9999:
                print(f"此学号{res_id}无效")
                #忽略这次传输 因为验证不对
                continue

            # ======= 通用丢包模拟：所有 client→server 报文都参与 =======
            if random.random() < loss_rate:
                write_log("drop", msg_type, seq, 0, length, addr)
                print(f"丢包：Type={msg_type} Seq={seq}")
                continue

            if msg_type == 0:      # 连接请求（SYN）
                expect_seq[addr] = 0
                # 新建接收缓冲区 用来拼接数据
                received_data[addr] = b''
                #组装type=1的报文
                pkt = make_packet(sid, 1, 0, 0)  # Type=1 SYN+ACK
                #发送报文
                serversocket.sendto(pkt, addr)
                write_log("send packet", 1, 0, 0, 0, addr)
                print(f"客户端 {addr} 连接成功")

            elif msg_type == 2:    # 数据报文
                # 按序/乱序判断，发 ACK（附带服务端系统时间）
                """
                    从字典里查出这个客户端当前的期待序号。get(addr, 0) 的意思是：
                    如果这个客户端第一次发数据（字典里还没有），默认从 0 开始等。
                """
                exp = expect_seq.get(addr, 0)
                if seq == exp:
                    #因为是按照包流的顺序来的 所以不用是seq+len(data) 每次发送一个包
                    expect_seq[addr] = exp + 1 #更新期待的seq
                    ack_num = expect_seq[addr] #更新ack
                    # 仅按序到达的包才保存数据（接收窗口=1，乱序丢弃）
                    #拼接送过来的数据
                    if addr in received_data:
                        received_data[addr] += payload
                    print(f"按序到达 seq={seq}，发送 ACK={ack_num}")
                else:
                    ack_num = exp
                    print(f"乱序到达 seq={seq}，发送重复 ACK={ack_num}")
                # 服务端系统时间（格式 hh-mm-ss.sss，与日志时间戳粒度一致）
                now = time.time()
                ms = int((now - int(now)) * 1000)
                server_time_str = time.strftime('%H-%M-%S', time.localtime(now)) + f'.{ms:03d}'
                server_time_data = server_time_str.encode('ascii')
                ack_pkt = make_packet(sid, 3, seq, ack_num, server_time_data)
                serversocket.sendto(ack_pkt, addr)
                write_log("send packet", 3, seq, ack_num, len(server_time_data), addr)

            elif msg_type == 3:    # ACK（握手/挥手阶段的确认）
                write_log("receive packet", 3, seq, ack, length, addr) #确认收到消息

            elif msg_type == 4:    # FIN（客户端断开连接）
                # 保存接收数据到文件
                if addr in received_data:
                    #构建文件名
                    recv_file = f'received_{addr[0]}_{addr[1]}.bin'
                    with open(recv_file, 'wb') as f:
                        #将内容写进去
                        f.write(received_data[addr])
                    print(f"已保存接收数据到 {recv_file} (共 {len(received_data[addr])} 字节)")
                    #写完释放内存
                    del received_data[addr]
                # 发送 FIN+ACK
                fin_ack_pkt = make_packet(sid, 5, 0, 1)
                serversocket.sendto(fin_ack_pkt, addr)
                write_log("send packet", 5, 0, 1, 0, addr)
                print(f"客户端 {addr} 断开连接")
                if addr in expect_seq:
                    del expect_seq[addr]

            else:
                write_log("receive packet", msg_type, seq, ack, length, addr)

    except KeyboardInterrupt:
        print("\n服务器关闭")
    finally:
        serversocket.close()
            

if __name__ == '__main__':
    main()
