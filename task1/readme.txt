本次实验的实验环境如下：

一、运行环境
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  操作系统  : macOS 15 (Darwin Kernel 24.5.0, ARM64)+Windows 11 Pro（内核版本 NT 10.0，内部版本号 26100）
  Python    : 3.12.13
  依赖模块  : 仅使用 Python 标准库（无需额外安装）
              - socket（TCP 网络通信）
              - threading（多线程并发）
              - struct（二进制数据打包/解包）
              - argparse（命令行参数解析）
              - random / time / os / sys

二、程序概述
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  基于 TCP 实现文本反转传输：

  客户端：
    • 读取文件，按随机大小（lmin~lmax）拆分为多个数据块
    • 通过 TCP 连接依次发送每个数据块到服务器
    • 接收服务器反转后的数据块，按序重组并保存为新文件
    • 使用固定随机种子（seed），保证拆分结果可复现

  服务器：
    • 监听指定端口（0.0.0.0，即所有网络接口），接收 TCP 连接
    • 每个客户端在独立守护线程（daemon thread）中处理
    • 支持多客户端并发连接
    • 将接收到的数据块字节反转后返回
    • 使用 Ctrl+C（KeyboardInterrupt）关闭服务器

三、文件说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  reversetcpserver.py    — TCP 服务器程序
  reversetcpclient.py    — TCP 客户端程序
  test.txt               — 测试用文本文件
  run_log.txt            — 运行日志（程序自动生成）
  readme.txt             — 本说明文档

四、服务器命令行参数
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  --port       端口号（必需）    示例: --port 12345

  启动示例:
    python3 reversetcpserver.py --port 12345

五、客户端命令行参数
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  --server-ip    服务器 IP 地址（必需）        示例: --server-ip 127.0.0.1
  --server-port  服务器端口号（必需）          示例: --server-port 12345
  --lmin         数据块最小长度（必需）        示例: --lmin 5
  --lmax         数据块最大长度（必需）        示例: --lmax 15
  --file         待发送的文件路径（必需）      示例: --file test.txt
  --seed         随机种子（必需，保证可复现）  示例: --seed 42

  启动示例:
    python3 reversetcpclient.py --server-ip 127.0.0.1 --server-port 12345 --lmin 5 --lmax 15 --file test.txt --seed 42

六、运行步骤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. 先在一个终端启动服务器：
     python3 reversetcpserver.py --port 12345

  2. 在另一个终端启动客户端：
     python3 reversetcpclient.py --server-ip 127.0.0.1 --server-port 12345 --lmin 5 --lmax 15 --file test.txt --seed 42

  3. 运行结束后，会在当前目录生成：
     - test_reversed.txt（反转后的文件）
     - run_log.txt（通信过程日志）

七、自定义协议格式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  所有多字节字段均采用大端字节序（网络字节序，struct 中前缀 "!"）

  Type 1 (Initialization)     客户端 → 服务器
     字段: !H(类型=1) + I(数据块总数N)
     总长度: 6 字节

  Type 2 (Agree)              服务器 → 客户端
     字段: !H(类型=2)
     总长度: 2 字节

  Type 3 (reverseRequest)     客户端 → 服务器
     字段: !H(类型=3) + I(数据块长度) + 原始数据

  Type 4 (reverseAnswer)      服务器 → 客户端
     字段: !H(类型=4) + I(反转后数据长度) + 反转后数据

八、日志格式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [时间] 事件类型 | Type=报文类型 | Length=数据长度 | Preview=数据预览(前20字符) | Address=对端地址

  示例:
  [2026-06-05 10:30:15.123] connection established | Type=- | Length=0 | Preview= | Address=('127.0.0.1', 12345)
  [2026-06-05 10:30:15.124] send packet | Type=1 (Initialization) | Length=4 | Preview=N=5 | Address=('127.0.0.1', 54321)
