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

FILE_NAME = 'run_log_udp.txt'
XOR_KEY = 0x5A3C
IP='0.0.0.0'
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
    sid,msg_type,seq,ack,length=struct.unpack("!HBIIH",packet[:13])
    data=packet[13:13+length]
    return sid,msg_type,seq,ack,length,data
    

def main():
    """主函数：解析参数、清日志、绑定端口、循环接收处理"""
    #首先开始解析参数
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,required=True) #端口号
    parser.add_argument('--loss_rate',type=float,default=0.3)#丢包率 默认为0.3
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
    #key=客户端地址addr，value=服务器期待该客户端发送的下一个包序号
    expect_seq={}
    print(f"服务器已经启动,端口为{args.port},丢包率为{loss_rate}")

    #现在开始接收数据
    try:
        while True:
            #现在开始解析数据
            data,addr=serversocket.recvfrom(4096)
            sid, msg_type, seq, ack, length, payload = parse_packet(data)
            #现在开始学号验证
            res_id=sid^XOR_KEY
            if res_id<0 or res_id>9999:
                print(f"此学号{res_id}无效")
                #忽略这次传输 因为验证不对
                continue
            if msg_type == 0:      # 连接请求
                expect_seq[addr] = 0
                pkt = make_packet(sid, 1, 0, 0)
                serversocket.sendto(pkt, addr)
                write_log("connection established", 1, 0, 0, 0, addr)
                print(f"客户端 {addr} 连接成功")

            elif msg_type == 2:    # 数据报文
                # ======= 丢包模拟在这儿 =======
                if random.random() < loss_rate:
                    write_log("drop", 2, seq, 0, length, addr)
                    print(f"丢包：序号 {seq}")
                    continue       # 不回复，直接下一轮
                # =============================

                # 正常处理：按序/乱序判断，发 ACK
                exp = expect_seq.get(addr, 0)
                if seq == exp:
                    expect_seq[addr] = exp + 1
                    ack_num = expect_seq[addr]
                    print(f"按序到达 seq={seq}，发送 ACK={ack_num}")
                else:
                    ack_num = exp
                    print(f"乱序到达 seq={seq}，发送重复 ACK={ack_num}")
                ack_pkt = make_packet(sid, 3, seq, ack_num)
                serversocket.sendto(ack_pkt, addr)
                write_log("send packet", 3, seq, ack_num, 0, addr)

    except KeyboardInterrupt:
        print("\n服务器关闭")
    finally:
        serversocket.close()
            

if __name__ == '__main__':
    main()
