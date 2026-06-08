本次实验的实验环境如下：

一、运行环境
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  操作系统  : macOS 15 (Darwin Kernel 24.5.0, ARM64)
  Python    : 3.12.13
  依赖模块  : 除 Python 标准库外，还需安装 pandas
              - socket（UDP 网络通信）
              - struct（二进制数据打包/解包）
              - argparse（命令行参数解析）
              - random / time / os
              - pandas（RTT 统计计算）

  pandas 安装命令:
    pip3 install pandas

二、文件说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  udpserver.py          — UDP GBN 服务器程序
  udpclient.py          — UDP GBN 客户端程序
  test.txt              — 测试用文本文件
  run_log_udp.txt       — 运行日志（程序自动生成）
  readme.txt            — 本说明文档

三、程序概述
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  基于 UDP 实现 GBN（Go-Back-N）可靠传输协议：

  客户端：
    • 将数据拆分为多个数据包（每包 40~80 字节）
    • 采用滑动窗口（窗口大小 400 字节）连续发送
    • 超时（300ms）时重传窗口内所有未确认包
    • 统计 RTT（最大/最小/平均/标准差）和丢包率
    • 连接请求也支持超时重传（循环等待直到收到 Type=1 确认）
    • 使用固定随机种子（seed=42），保证数据块生成可复现

  服务器：
    • 监听 0.0.0.0（所有网络接口），接收 UDP 数据包
    • 接收数据包，模拟随机丢包（默认丢包率 0.3，在回复 ACK 前随机丢弃）
    • 按序到达则累积确认，乱序到达则发送重复 ACK
    • 使用 expect_seq 字典按客户端地址跟踪期望的下一个序号
    • 使用学号异或加密（XOR 0x5A3C）验证客户端身份
    • 使用 Ctrl+C（KeyboardInterrupt）关闭服务器

四、自定义协议格式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  所有多字节字段均采用大端字节序（网络字节序，struct 中前缀 "!"）
  报文结构：[首部 13 字节] + [数据载荷]

  首部格式（!HBIIH）:
    字段       类型      字节  说明
    student_id  H (uint16)  2  学号（后4位 XOR 0x5A3C 加密）
    msg_type    B (uint8)   1  报文类型（0/1/2/3）
    seq         I (uint32)  4  序列号
    ack         I (uint32)  4  确认号
    length      H (uint16)  2  数据载荷长度

  报文类型：
    Type 0  — 连接请求（客户端 → 服务器）
    Type 1  — 连接确认（服务器 → 客户端）
    Type 2  — 数据报文（客户端 → 服务器）
    Type 3  — ACK 确认（服务器 → 客户端，Ack 字段携带累积确认号）

五、服务器命令行参数
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  --port         端口号（必需）              示例: --port 8888
  --loss_rate    模拟丢包率（可选，默认0.3）  示例: --loss_rate 0.2

  启动示例:
    python3 udpserver.py --port 8888 --loss_rate 0.2

六、客户端命令行参数
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  --ip            服务器 IP 地址（必需）          示例: --ip 127.0.0.1
  --port          服务器端口号（必需）            示例: --port 8888
  --student_id    学号（可选，默认 2110）         示例: --student_id 2110
  --file          数据文件路径（可选，默认随机生成）示例: --file test.txt

  启动示例:
    python3 udpclient.py --ip 127.0.0.1 --port 8888 --student_id 2110 --file test.txt

七、GBN 滑动窗口机制说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  客户端常量（在代码中定义）：
    WINDOW_SIZE_BYTES = 400   （发送窗口大小，以字节计）
    TIMEOUT           = 0.3   （超时重传时间，秒）
    TOTAL_PACKETS     = 30    （数据包总数）
    DATA_LEN_MIN      = 40    （每包最小字节数）
    DATA_LEN_MAX      = 80    （每包最大字节数）

  1. 窗口大小：以字节计数，最大 400 字节未确认数据
  2. 发送过程：
     - 窗口未满时连续发送新包
     - 收到 ACK 后滑动窗口（累积确认，所有序号 < ack 的包均视为已确认）
     - 超时（300ms）则重传窗口内所有未确认包
  3. 连接建立：客户端循环发送 Type=0 请求，超时则重发，直到收到 Type=1 确认为止
  4. 共发送 30 个数据包（TOTAL_PACKETS = 30）
  5. 每包数据长度在 40~80 字节间随机

八、运行步骤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. 先在一个终端启动服务器：
     python3 udpserver.py --port 8888 --loss_rate 0.2

  2. 在另一个终端启动客户端：
     python3 udpclient.py --ip 127.0.0.1 --port 8888 --student_id 2110 --file test.txt

  3. 运行结束后，客户端会输出统计信息：
     - 实际发送总包数（含重传）
     - 丢包率
     - 最大/最小/平均 RTT 及 RTT 标准差
     - 同时生成 run_log_udp.txt 通信日志

九、日志格式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [时间] 事件类型 | Type=报文类型 | Seq=序列号 | Ack=确认号 | Length=数据长度 | Address=对端地址 [ | RTT=xx.x ms]

  事件类型说明：
    send packet        — 发送数据包
    receive packet     — 接收数据包
    retransmit         — 超时重传
    timeout            — 发生超时（客户端日志）
    drop               — 模拟丢包（服务器日志，不回复 ACK）
    connection established — 建立连接
    connection closed  — 关闭连接

  示例:
  [2026-06-05 10:30:15.123] send packet | Type=2 | Seq=0 | Ack=0 | Length=55 | Address=('127.0.0.1', 8888)
  [2026-06-05 10:30:15.200] drop | Type=2 | Seq=1 | Ack=0 | Length=60 | Address=('127.0.0.1', 54321)
  [2026-06-05 10:30:15.456] receive packet | Type=3 | Seq=0 | Ack=1 | Length=0 | Address=('127.0.0.1', 8888) | RTT=12.3 ms
  [2026-06-05 10:30:15.789] timeout | Type=- | Seq=0 | Ack=0 | Length=0 | Address=('127.0.0.1', 8888)
  [2026-06-05 10:30:15.790] retransmit | Type=2 | Seq=5 | Ack=0 | Length=60 | Address=('127.0.0.1', 8888)
